"""EPANET differential fuzz driver (TSD §10.4).

    uv run python -m tests.differential.fuzz START STOP [--workers N] [--out DIR] [--strict]
                                                        [--profile P]

Each seed in [START, STOP) is generated (``generator``, in profile P, default 'default'), solved
by our solver and by EPANET 2.2 (``epanet_model``), compared with the D6 criteria and checked
independently (``checks``), and classified. Writes DIR/results/<seed>.json (one record per
network) and DIR/findings/<class>/<seed>.json (a reproducer: project API JSON, EPANET's and our
numbers and the diagnosis inputs). DIR defaults to a new temporary directory, printed first and
last; ``tests.differential.stats DIR`` summarizes a run. The exit status is 1 when a seed is
critical.

Flow-controlled pumps (profile 'flow_control', proposal vfd-pump-modes.md §7.4): every EPANET
run stands for the state our solver reports for each (``epanet_model.control_pins``); our
result's control fields are part of the self-check (``checks.control_problems``); the speed is
compared (``checks.speed_comparison``); and a converged network is searched over its
controlled pumps' states (``state_search.control_search``): its record's ``control_search``
holds the valid states found; distinct valid solutions that differ in flowing state
(``state_search.multiple``) are written to findings/control_multiple_states, alternatives that
only put more of the network at rest to findings/control_rest_alternatives (the class is not
changed). A record of a non-default profile names it (``profile``).

The classes and which of them are critical are listed in ``classes.py``.
"""

import argparse
import functools
import json
import os
import sys
import tempfile
import time
import traceback
from multiprocessing import Pool
from typing import Any

from opensolve_pipe.models.components import CheckValve, ControlValve, Pump
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.results import SolvedState
from opensolve_pipe.services.solver import solve_project
from tests.differential import checks as ck
from tests.differential import epanet_model as em
from tests.differential.classes import is_critical
from tests.differential.generator import DEFAULT, PROFILES, generate
from tests.differential.state_search import (
    LIMIT,
    control_search,
    distinct,
    fully_determined,
    multiple,
    search,
)
from tests.reference import element_laws as el

EP_HTOL = 0.0005 * 0.3048  # EPANET Htol (types.h HTOL 0.0005 ft)
EP_QTOL = 1e-4 * 0.3048**3  # EPANET Qtol (0.0001 cfs)

Record = dict[str, Any]


def mapped(states: ck.States) -> dict[str, str]:
    return {k: {"xfcv": "open", "xpressure": "open"}.get(v, v) for k, v in states.items()}


def state_diffs(states_o: ck.States, states_e: ck.States) -> list[tuple[str, str, str | None]]:
    out = []
    for k, so in states_o.items():
        se = mapped(states_e).get(k)
        if so == "isolated":
            continue
        if so != se:
            out.append((k, so, states_e.get(k)))
    return out


def documented_pins(
    project: Project, ep: em.EpanetResult, lay: em.Layout, egl_e: ck.Heads
) -> tuple[dict[str, str], dict[str, str]]:
    """Pins that make EPANET follow our documented departures (TSD §5.4, D9)."""
    pins, why = {}, {}
    st = em.element_state(project, lay, ep)
    for c in project.components:
        if not isinstance(c, ControlValve) or c.status != "active":
            continue
        a, b = f"{c.id}:inlet", f"{c.id}:outlet"
        q = ep.element_flows[c.id]
        dh = egl_e[a] - egl_e[b]
        if c.valve_type == "fcv":
            if st[c.id] == "xfcv" and (q < -ck.QTOL or dh < -EP_HTOL):
                pins[c.id] = "closed"
                why[c.id] = "FCV closes on reverse flow (EPANET XFCV passes it)"
            elif st[c.id] == "active":
                d_in = lay.d_in[c.id]
                k = lay.k_open[c.id]
                hml = el.valve_loss(k, c.setpoint, d_in, ck.EP_MODEL.g) * ck.EP_MODEL.k_scale
                if k > 0 and dh < hml - ck.HTOL:
                    pins[c.id], why[c.id] = "open", "FCV opens below its fully open loss"
        elif st[c.id] == "xpressure":
            pins[c.id] = "closed"
            why[c.id] = "PRV/PSV with no fixed head on one side (EPANET XPRESSURE)"
    return pins, why


def pins_for(states_o: ck.States) -> dict[str, str]:
    return {k: v for k, v in states_o.items() if v in ("open", "closed", "no_flow")}


def fcv_doc_pins(
    project: Project, states_o: ck.States, states_e: ck.States, detected: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """EPANET with our documented semantics: every active FCV whose EPANET state differs from
    ours (or shows a detected departure) pinned to our final state; a PRV/PSV EPANET reports
    XPRESSURE pinned to ours (closed when starved/isolated)."""
    pins, why = {}, {}
    for c in project.components:
        if not isinstance(c, ControlValve) or c.status != "active":
            continue
        so, se = states_o.get(c.id), states_e.get(c.id)
        pin = {"isolated": "closed"}.get(so, so)
        # only where EPANET shows the departure itself (XFCV, or active below its open loss)
        if (
            c.valve_type == "fcv"
            and (c.id in detected or (se == "xfcv" and so != "isolated"))
            and pin in ("open", "closed")
        ):
            pins[c.id] = pin
            why[c.id] = (detected.get(c.id) or "FCV state differs") + f" [ours {so}, EPANET {se}]"
        elif se == "xpressure" and pin in ("open", "closed"):
            pins[c.id] = pin
            why[c.id] = f"PRV/PSV XPRESSURE in EPANET [ours {so}]"
    return pins, why


def ep_valid(
    project: Project, ep: em.EpanetResult, egl: ck.Heads, states: ck.States
) -> tuple[list[str], list[str]]:
    """(law problems, status-rule problems) of EPANET's solution, within EPANET's tolerances."""
    leak = ck.epanet_leak(ep)
    abs_q = 1e-6 * max([abs(q) for q in ep.flows.values()] + [0]) + 1e-7 + 2 * leak
    laws = ck.law_problems(
        project, ep.flows, egl, mapped(states), ck.EP_MODEL, rel=1e-4, abs_h=1e-4, abs_q=abs_q
    )
    rules = ck.status_problems(
        project,
        ep.flows,
        egl,
        mapped(states),
        ck.EP_MODEL,
        tol_h=0.01,
        qtol=max(EP_QTOL, 2 * ck.epanet_leak(ep)),
    )
    return laws, rules


def run_seed(
    seed: int,
    findings_dir: str | None = None,
    *,
    strict: bool = False,
    workdir: str | None = None,
    profile: str = DEFAULT,
) -> Record:
    """Classify one seed of a generator profile. Findings (reproducers) go to ``findings_dir``
    when given; ``workdir`` holds EPANET's files, its own scratch files included (the system
    temporary directory by default). When anything raises, the record keeps what was computed
    before (``self_check`` included, so ``is_critical`` still sees a failed self-check) with
    status 'harness_error'."""
    out: Record = {"seed": seed}
    if profile != DEFAULT:  # default records stay as they were
        out["profile"] = profile
    try:
        _run_seed(out, findings_dir, strict, workdir, profile)
    except Exception as ex:
        out["status"] = "harness_error"
        out["error"] = "".join(traceback.format_exception(ex))[-1500:]
    return out


def _run_seed(
    out: Record, findings_dir: str | None, strict: bool, workdir: str | None, profile: str
) -> None:
    """Fill ``out`` (the record) as the seed's classification proceeds."""
    t0 = time.time()
    seed = out["seed"]

    def save(ep: em.EpanetResult | None, result: SolvedState | None, cls: str) -> None:
        if findings_dir is not None:
            _save(findings_dir, project, out, ep, result, cls)

    try:
        project = generate(seed, profile)
    except Exception as ex:  # generator limits
        out["status"] = "gen_error"
        out["error"] = repr(ex)
        return
    out["n_components"] = len(project.components)
    out["n_connections"] = len(project.connections)
    out["kinds"] = sorted({ck.element_kind(c) for c in project.components})
    try:
        result = solve_project(project)
    except Exception as ex:
        out["status"] = "ours_exception"
        out["error"] = "".join(traceback.format_exception(ex))[-2000:]
        save(None, None, "ours_exception")
        return
    out["ours_converged"] = result.converged
    out["ours_message"] = result.convergence.message
    flows_o, egl_o, states_o = ck.ours_solution(project, result)
    speeds_o = ck.our_speeds(project, result)  # {} without flow-controlled pumps
    # EPANET stands for our controlled pumps' states (no result, held at no flow: no_flow)
    held = dict.fromkeys(ck.closed_without_result(project, result), "no_flow")
    ctl = em.control_pins(project, {**states_o, **held})

    def run_ep(pins: dict[str, str] | None = None) -> tuple[em.EpanetResult, em.Layout]:
        return em.run_epanet(project, pins={**ctl, **(pins or {})}, workdir=workdir)

    out["states_o"] = states_o
    controlled = [c.id for c in project.components if isinstance(c, Pump) and c.control is not None]
    if controlled:  # default records stay as they were
        out["controlled"] = controlled
        out["speeds_o"] = speeds_o
    if result.converged:
        out["self_check"] = (
            ck.law_problems(project, flows_o, egl_o, states_o)
            + ["status " + s for s in ck.status_problems(project, flows_o, egl_o, states_o)]
            + ck.zero_flow_and_floating(project, flows_o, egl_o, states_o, result)
            + ck.control_problems(project, result, flows_o, egl_o, states_o)
        )
        if out["self_check"]:
            save(None, result, "self_check_failed")
        if ctl:  # more than one valid state over the controlled pumps' states?
            elems, valid = control_search(project)
            groups = distinct(project, valid)
            out["control_search"] = {
                "elements": elems,
                "valid": [w for w, _, _ in valid],
                "distinct": [w for w, _, _ in groups],
                "multiple": multiple(groups),
            }
            if out["control_search"]["multiple"]:
                save(None, result, "control_multiple_states")
            elif len(groups) > 1:
                save(None, result, "control_rest_alternatives")
    try:
        ep, lay = run_ep()
    except em.UnsupportedError as ex:
        out["status"] = "unsupported"
        out["error"] = str(ex)
        return
    except em.EpanetError as ex:  # an EPANET toolkit error; anything else is harness_error
        out["status"] = "epanet_failed"
        out["error"] = repr(ex)
        save(None, result, "epanet_failed")
        return
    egl_e = ck.epanet_egl(project, ep, lay)
    states_e = em.element_state(project, lay, ep)
    out.update(
        states_e=states_e,
        ep_iterations=ep.iterations,
        ep_criteria=ep.criteria,
        ep_warnings=ep.warnings,
    )
    if not result.converged:
        laws, rules = ep_valid(project, ep, egl_e, states_e)
        out["ep_laws"], out["ep_rules"] = laws, rules
        out["status"] = "both_unconverged" if ep.iterations > em.TRIALS else "ours_not_converged"
        # does a valid, fully determined steady state exist? (brute force over pinned states)
        _, valid = search(project, limit=LIMIT)
        full = [w for w, _, _ in fully_determined(project, valid)]
        out["valid_full_states"] = full[:5]
        out["n_valid_full_states"] = len(full)
        if full:
            out["status"] += "_valid_state_exists"
        save(ep, result, out["status"])
        return
    if ep.iterations > em.TRIALS:
        # EPANET's relative-error test cannot pass when every flow is a closed-link leak or
        # when CV/XFCV statuses cycle; compare its last iterate, then try our documented FCV
        # semantics, then EPANET pinned to all our states (a check of our element laws).
        mism_u, rec_u = ck.compare(
            project, flows_o, egl_o, states_o, ep, lay, strict=strict, speeds_o=speeds_o
        )
        if not mism_u and not state_diffs(states_o, states_e):
            out["records"] = list(rec_u)
            out["status"] = "pass_ep_unbalanced"
            return
        detected, _ = documented_pins(project, ep, lay, egl_e)
        pins, why = fcv_doc_pins(project, states_o, states_e, detected)
        ep_u = None
        if pins:
            ep_u, lay_u = run_ep(pins)
            if ep_u.iterations <= em.TRIALS:
                out["documented_unbalanced"] = why
                ep, lay = ep_u, lay_u
                egl_e = ck.epanet_egl(project, ep, lay)
                states_e = em.element_state(project, lay, ep)
            else:
                ep_u = None
        if ep_u is None:
            epp, layp = run_ep(pins_for(states_o))
            misp, recp = ck.compare(
                project, flows_o, egl_o, states_o, epp, layp, strict=strict, speeds_o=speeds_o
            )
            out["pinned_iterations"] = epp.iterations
            out["pinned_mismatch"] = [list(m) for m in misp][:20]
            if not misp and epp.iterations <= em.TRIALS:
                out["records"] = list(recp)
                out["status"] = "ours_verified_by_pinned_epanet"
            else:
                out["status"] = "epanet_unbalanced"
                save(ep, result, "epanet_unbalanced")
            return
    mism, rec = ck.compare(
        project, flows_o, egl_o, states_o, ep, lay, strict=strict, speeds_o=speeds_o
    )
    out["records"] = list(rec)
    sdiff = state_diffs(states_o, states_e)
    out["mismatch"] = [list(m) for m in mism]
    out["state_diff"] = [list(s) for s in sdiff]
    if not mism and not sdiff:
        out["status"] = "documented" if out.get("documented_unbalanced") else "pass"
        out["time"] = time.time() - t0
        return

    # ---- documented departures (FCV semantics, XPRESSURE): EPANET pinned to ours there
    detected, _ = documented_pins(project, ep, lay, egl_e)
    pins_doc, why = fcv_doc_pins(project, states_o, states_e, detected)
    if pins_doc:
        ep2, lay2 = run_ep(pins_doc)
        egl2 = ck.epanet_egl(project, ep2, lay2)
        for _ in range(4):  # departures that appear only once others are pinned
            det2, _ = documented_pins(project, ep2, lay2, egl2)
            states_2 = em.element_state(project, lay2, ep2)
            more, why2 = fcv_doc_pins(project, states_o, states_2, det2)
            more = {k: v for k, v in more.items() if k not in pins_doc}
            if not more:
                break
            pins_doc.update(more)
            why.update(why2)
            ep2, lay2 = run_ep(pins_doc)
            egl2 = ck.epanet_egl(project, ep2, lay2)
        mism2, rec2 = ck.compare(
            project, flows_o, egl_o, states_o, ep2, lay2, strict=strict, speeds_o=speeds_o
        )
        out["records_final"] = list(rec2)
        sdiff2 = state_diffs(states_o, em.element_state(project, lay2, ep2))
        out["documented"] = why
        out["documented_run_iterations"] = ep2.iterations
        out["mismatch_after_documented"] = [list(m) for m in mism2]
        out["state_diff_after_documented"] = [list(s) for s in sdiff2]
        if not mism2 and not sdiff2:
            out["status"] = "documented"
            out["time"] = time.time() - t0
            return
        # classify against EPANET with our FCV semantics (its last iterate when unbalanced)
        ep, lay, egl_e, mism, sdiff = ep2, lay2, egl2, mism2, sdiff2
        states_e = em.element_state(project, lay, ep)

    # ---- classification
    ours_rules = ck.status_problems(project, flows_o, egl_o, states_o)
    ours_laws = ck.law_problems(project, flows_o, egl_o, states_o)
    ours_laws = ours_laws + ck.zero_flow_and_floating(project, flows_o, egl_o, states_o, result)
    ours_laws = ours_laws + ck.control_problems(project, result, flows_o, egl_o, states_o)
    ep_laws_f, ep_rules_f = ep_valid(project, ep, egl_e, states_e)
    out.update(
        ours_rules=ours_rules,
        ours_laws=ours_laws,
        ep_final_laws=ep_laws_f,
        ep_final_rules=ep_rules_f,
        ep_final_states=states_e,
    )
    # our solver pinned to EPANET's final states: does it reproduce EPANET's solution?
    # (a diagnosis stored in the record; it does not change the class)
    try:
        pp = pin_project(project, mapped(states_e))
        rp = solve_project(pp)
        fp, hp, sp = ck.ours_solution(pp, rp)
        misq, _ = ck.compare(pp, fp, hp, sp, ep, lay, strict=strict)
        if all(m[0] == "egl" for m in mism):
            misq = [m for m in misq if m[0] != "egl"]
        out["ours_pinned_to_ep_converged"] = rp.converged
        out["ours_pinned_to_ep_mismatch"] = [list(m) for m in misq][:20]
    except Exception as ex:
        out["ours_pinned_to_ep_error"] = repr(ex)
    only_heads = all(m[0] == "egl" for m in mism)
    if not mism:
        cls = "state_only"
        diffs = [d[0] for d in sdiff]
        flows_at = [abs(ep.element_flows.get(k, 0.0)) for k in diffs]
        if all(q <= max(EP_QTOL, 2 * ck.epanet_leak(ep)) for q in flows_at):
            cls = "state_only_zero_flow"
    elif ours_rules or ours_laws:
        cls = "a_ours_invalid"
    elif ep.iterations > em.TRIALS:
        cls = "d_no_converged_reference"  # EPANET (with our FCV semantics) unbalanced
    elif only_heads and not ep_rules_f and not ep_laws_f:
        cls = "b_stagnant_heads"
    elif not ep_rules_f and not ep_laws_f:
        cls = "b_multiple_steady_states"
    elif ep_laws_f:
        cls = "e_epanet_invalid"
    else:
        cls = "review"
    out["status"] = cls
    save(ep, result, cls)
    out["time"] = time.time() - t0


def pin_project(project: Project, states: ck.States) -> Project:
    """A copy of the project with every pump and valve fixed in the given state (a
    flow-controlled pump at a speed limit as the fixed-speed pump at that speed; active left
    controlled)."""
    comps = []
    for c in project.components:
        st = states.get(c.id)
        if isinstance(c, Pump) and st == "no_flow":
            c = c.model_copy(update={"status": "off"})
        elif isinstance(c, Pump) and c.control is not None and st in ("max_speed", "min_speed"):
            speed = c.control.min_speed if st == "min_speed" else c.speed
            c = c.model_copy(update={"speed": speed, "control": None})
        elif isinstance(c, CheckValve) and c.status == "active" and st in ("open", "closed"):
            update = {"status": "locked_open" if st == "open" else "locked_closed"}
            c = c.model_copy(update=update)
        elif isinstance(c, ControlValve) and c.status == "active" and st in ("open", "closed"):
            update = {"status": "failed_open" if st == "open" else "failed_closed"}
            c = c.model_copy(update=update)
        comps.append(c)
    return project.model_copy(update={"components": comps})


def _save(
    findings_dir: str,
    project: Project,
    out: Record,
    ep: em.EpanetResult | None,
    result: SolvedState | None,
    cls: str,
) -> None:
    d = os.path.join(findings_dir, cls)
    os.makedirs(d, exist_ok=True)
    rec: Record = {
        "seed": out["seed"],
        "class": cls,
        "summary": {k: v for k, v in out.items() if k != "records"},
        "project": project.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    if ep is not None:
        rec["epanet"] = {
            "flows": ep.flows,
            "heads": ep.heads,
            "raw_status": ep.raw_status,
            "iterations": ep.iterations,
            "settings_m": ep.settings,
            "criteria_level": ep.criteria,
            "warnings": ep.warnings,
        }
    if result is not None:
        ctl_results = {k: v for k, v in result.pump_results.items() if v.control is not None}
        rec["ours"] = {
            "converged": result.converged,
            "message": result.convergence.message,
            "flows": {k: v.flow for k, v in result.link_results.items()},
            "egl": {k: v.egl for k, v in result.node_results.items()},
            "pumps": {k: v.status for k, v in result.pump_results.items()},
            **(
                {"controls": {k: (v.control.state, v.speed) for k, v in ctl_results.items()}}
                if ctl_results
                else {}
            ),
            "valves": {k: v.state for k, v in result.valve_results.items()},
            "flags": [(f.code, f.severity, f.component_id, f.connection_id) for f in result.flags],
        }
    with open(os.path.join(d, f"{out['seed']}.json"), "w") as f:
        json.dump(rec, f, indent=1, default=str)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.fuzz",
        description="EPANET differential fuzz: classify random networks (TSD §10.4).",
    )
    parser.add_argument("start", type=int, help="first seed")
    parser.add_argument("stop", type=int, help="seed after the last one")
    parser.add_argument("--workers", type=int, default=4, help="worker processes (default 4)")
    parser.add_argument("--out", help="output directory (default: a new temporary directory)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="compare flows to 0.5%% or 1e-7 m³/s, without the D6 head-equivalent floor",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default=DEFAULT,
        help="generator profile (default: default; flow_control's seeds are 10000-12999)",
    )
    args = parser.parse_args(argv)
    out_dir = args.out or tempfile.mkdtemp(prefix="opensolve-fuzz-")
    results_dir = os.path.join(out_dir, "results")
    os.makedirs(results_dir, exist_ok=True)
    print("output:", out_dir, flush=True)
    work = functools.partial(
        run_seed,
        findings_dir=os.path.join(out_dir, "findings"),
        strict=args.strict,
        profile=args.profile,
    )
    critical = []
    with Pool(args.workers) as pool:
        for out in pool.imap_unordered(work, range(args.start, args.stop)):
            with open(os.path.join(results_dir, f"{out['seed']}.json"), "w") as f:
                json.dump(out, f, default=str)
            print(out["seed"], out["status"], out.get("documented", ""), flush=True)
            if is_critical(out):
                critical.append(out["seed"])
    print("output:", out_dir)
    print("critical (converged, fails the independent checks):", sorted(critical))
    sys.exit(1 if critical else 0)


if __name__ == "__main__":
    main()
