"""Check the orifice plate against the isolation valves it can stand in for, over the corpus
(proposal orifice-plate.md §7.4, decision 24), in two modes with an exact expected answer each.

    uv run python -m tests.differential.orifice_check [--mode entered|iso] [--workers N]
                                                       [--only PREFIX] [--out FILE]

An active isolation valve's law is K_open·v|v|/(2g), v = Q/A on its reference bore: the inner
diameter of its inlet pipe's end segment at its inlet port (D9), the bore D an orifice plate's
law is taken on too (decision 3). Its control is fixed open, which the status rules never change,
and an orifice plate has no status and no control (decision 1). So for every corpus project
(``corpus.items()``) with an active isolation valve (gate, ball, butterfly or globe), the project
is solved (A), then, in each mode, solved again (B) with every active isolation valve that has a
result in A replaced by an orifice plate with the same id, name, elevation and ports (so the same
connections, port elevations and D, the valve's ``referenceDiameter``):

- mode ``entered`` (decision 13: an entered C without taps is the C that sets the loss, C_L, and
  K is constant): C drawn per replaced valve, in component order, uniform in 0.6-0.65 with
  ``random.Random(f"orifice:{name}")`` (a test input), no taps, and the bore from the exact
  inverse of ISO 5167-2's pressure-loss relation K = (S/(Cβ²) − 1)², S = √(1 − β⁴(1 − C²))
  (decision 4): β⁴ = 1/(1 + C²(K + 2√K)) with K = K_open. The plate's law is then the valve's,
  and B must equal A to round-off, as ``equipment_check``'s elements do;
- mode ``iso`` (ISO 5167-2's C, decisions 5-7): the bore by brentq so that K(C_L) = K_open at A's
  flow through the valve, C_L ISO 5167-2's Reader-Harris/Gallagher C at D and D/2 tappings
  (fluids ``C_Reader_Harris_Gallagher``) at Re_eff = max(Re_D, Re_lo(β)), Re_D = 4ρ|Q_A|/(πDμ),
  Re_lo = max(5000, 16000β²) (decision 7), K fluids' ``discharge_coefficient_to_K``; taps drawn
  per replaced valve uniformly among none, corner, flange and D and D/2 with
  ``random.Random(f"orifice:iso:{name}")``: with ISO's C they set only the reading (decision 5).
  A's state then satisfies B's equations, so B must reproduce it through the Reynolds-dependent
  law and its slope. Valves at zero flow are included, with C held at Re_lo. A plate whose drawn
  taps decision 17 would refuse (eq. (4) above 1 at the flange taps of a small pipe at a high β;
  the solver's own ``orifice.refusal`` decides, a guard on the selection only) gets no taps, and
  is counted ('untapped').

In either mode a valve whose K_open the plate cannot reach for β in [BETA_MIN, BETA_MAX] (0.02 to
0.95; at β 0.95 K is 0.058-0.077 with an entered C of 0.6-0.65 and 0.031-0.042 on ISO 5167-2's C,
and a fully open ball valve's can be less) stays a valve and is counted ('kept'), and so does one
without a result in A ('no_result').

Checks (a difference names its letter):

- (a) the same convergence: both solves converged, or neither (then nothing else is compared);
- (b) every connection's flow, and every port's EGL and static pressure, within D6 of A's
  (``equipment_check.network_problems``: a value different only at zero flow is listed, not a
  difference, CLAUDE.md D13);
- (c) each plate's flow and head loss within D6 of its valve's (a valve with no plate result
  likewise only at zero flow);
- (d) in each plate's own result, pressureLoss = ρg × headLoss, and pressureDrop equal to the
  static-drop identity ρg·headLoss + ρg(z_out − z_in) + ρ(v_out² − v_in²)/2 (§3.7, D7), both to
  round-off as ``equipment_check``'s (d) (ρ the dump's fluid density, g = 9.80665 m/s², the
  project's port elevations and the connected pipes' end-segment velocities from B);
- (e) the plate's own coefficients at its reported flow Q, from fluids and the formulas of §1.1
  restated here, each to round-off (``ROUND_OFF`` relative): pipeDiameter the valve's
  referenceDiameter, boreDiameter the plate's, beta = d/D, reynoldsNumber = 4ρ|Q|/(πDμ), taps as
  the plate's; mode ``entered``: coefficientSource 'entered', dischargeCoefficient the entered C,
  and no coefficientReynoldsNumber, tapCoefficientRatio, meterDischargeCoefficient or
  differentialPressure; mode ``iso``: coefficientSource 'iso_5167_2', coefficientReynoldsNumber =
  Re_eff, dischargeCoefficient eq. (4) at D and D/2 tappings there, no tapCoefficientRatio, and
  with taps meterDischargeCoefficient eq. (4) at the taps at max(Re_D, Re_lo(taps)) (C_L at D
  and D/2 taps) and differentialPressure ISO 5167-2 eq. (1)'s (1 − β⁴)/(C_M²β⁴)·ρv|v|/2 (none
  without taps); in both, lossCoefficient = K(C_L), headLoss = K·v|v|/(2g) within
  ``LAW_TOLERANCE`` (ten times the solver's energy stop test, gga.ENERGY_TOL, plus round-off of
  the heads), and venaContractaPressure = p_up + ρg(z_up − z_down) − (1 − β⁴)/(C_L²β⁴)·ρv²/2,
  p_up the static pressure of the port the flow enters, z_down the elevation of the port it
  leaves by (decision 15), to round-off; none at zero flow or in a floating section.

Solves run without system curves. The report counts, per mode and profile (the name's prefix:
ref, unit, ladder, wye, fuzz, fuzzfc, fuzzaf), the projects checked, the valves replaced, the
plates that carry flow ('flowing'), those whose valve's head loss is above D6's 0.01 m floor
('lossy': where D6 can see a change of the law), those whose C is held below Re_lo ('held'),
the lossy ones on ISO's C at their own Reynolds number ('varying': where D6 can see the law's
Reynolds dependence) and those with taps ('tapped'), the valves kept and without a result, the
projects where neither solve converged, the plates in reverse flow, the values different only
at zero flow, and the projects with differences, each listed. It also records, with no
threshold, the largest differences of (b) and (c) over the projects (``largest_differences``):
D6 is the criterion (CLAUDE.md D13), but where a valve carries no flow or a small loss a law
wrong by a few percent stays within D6, so the largest differences show how closely the plate
reproduces the valve.
Exit status 1 on any difference; ``--out`` writes every project's record as JSON.
``test_orifice_check_smoke.py`` runs the reference cases, the unit-test data networks and a few
seeds of each fuzz profile.
"""

import argparse
import copy
import json
import math
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from multiprocessing import Pool
from typing import Any

from fluids.flow_meter import C_Reader_Harris_Gallagher, discharge_coefficient_to_K
from scipy.optimize import brentq

from opensolve_pipe.models.components import OrificeTaps
from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import TopologyError, solve_project
from opensolve_pipe.services.solver.orifice import refusal
from tests.differential.corpus import Item, items, load
from tests.differential.equipment_check import (
    HEAD_FLOOR,
    NO_CURVES,
    PROFILES,
    ROUND_OFF,
    G,
    _dump,
    active_isolation_valves,
    d6,
    head_bound,
    network_problems,
    port_connections,
    port_elevation,
    profile,
)

MODES = ("entered", "iso")
"""Mode 1, an entered C without taps; mode 2, ISO 5167-2's C (module docstring)."""
ENTERED_C = (0.6, 0.65)
"""The range an entered C is drawn from (a test input, proposal §7.4)."""
TAPS: tuple[OrificeTaps | None, ...] = (None, "corner", "flange", "d_and_d_2")
"""The taps a plate on ISO 5167-2's C is drawn with (none: a restriction orifice)."""
BETA_MIN, BETA_MAX = 0.02, 0.95
"""The diameter ratios a plate is given: K strictly decreases in β between them for every tap set
(proposal §7.7 R4), and decision 17 refuses none on ISO's C (from 0.97) or an entered one."""
LOSS_TAPS = "d_and_d_2"
"""The tap set whose C sets every plate's loss (decision 5)."""
FLUIDS_TAPS = {"corner": "corner", "flange": "flange", "d_and_d_2": "D and D/2"}
"""fluids' names of the tap sets (``fluids.flow_meter.ORIFICE_*_TAPS``)."""
RE_LO_MIN = 5000.0
"""ISO 5167-2's lowest Reynolds number for every tap set (decision 7, fluids' docstring)."""
RE_LO_BETA = 16000.0
"""Corner and D and D/2 tappings: Re_D ≥ 16000 β² (decision 7, fluids' docstring)."""
RE_LO_FLANGE = 170000.0
"""Flange tappings: Re_D ≥ 170000 β² D, D in m (decision 7, fluids' docstring)."""
ENERGY_TOL = 1.0e-7
"""m: the solver's energy stop test, |h(Q) − (H_start − H_end)| ≤ 10⁻⁷ m + round-off (CLAUDE.md
D7, gga.ENERGY_TOL), restated."""
LAW_TOLERANCE = 10.0 * ENERGY_TOL
"""m: (e)'s allowance between a plate's head loss as solved and its law at the reported flow,
plus ``ROUND_OFF`` × the heads it is the difference of."""


def re_lo(beta: float, d_pipe: float, taps: str) -> float:
    """ISO 5167-2's lowest Reynolds number of a tap set, made continuous at β 0.56 (decision 7)."""
    if taps == "flange":
        return max(RE_LO_MIN, RE_LO_FLANGE * beta * beta * d_pipe)
    return max(RE_LO_MIN, RE_LO_BETA * beta * beta)


def iso_c(d_pipe: float, d_bore: float, rho: float, mu: float, re: float, taps: str) -> float:
    """ISO 5167-2's C at Re_D = re ≥ 5000 (eq. (4), fluids), at the mass flow whose Re_D is re."""
    m = math.pi * d_pipe * mu * re / 4.0
    return float(C_Reader_Harris_Gallagher(d_pipe, d_bore, rho, mu, m, FLUIDS_TAPS[taps]))


def iso_loss_c(d_pipe: float, beta: float, rho: float, mu: float, re_d: float) -> float:
    """C_L on ISO 5167-2's C: at D and D/2 tappings, held at Re_lo below it (decisions 5, 7)."""
    re = max(re_d, re_lo(beta, d_pipe, LOSS_TAPS))
    return iso_c(d_pipe, beta * d_pipe, rho, mu, re, LOSS_TAPS)


def loss_k(d_pipe: float, d_bore: float, c: float) -> float:
    """ISO 5167-2's pressure-loss relation over ρv²/2 on the pipe's velocity (fluids)."""
    return float(discharge_coefficient_to_K(d_pipe, d_bore, c))


def entered_beta(k: float, c: float) -> float:
    """β with K(C, β) = k: β⁴ = 1/(1 + C²(K + 2√K)) (module docstring)."""
    return float((1.0 / (1.0 + c * c * (k + 2.0 * math.sqrt(k)))) ** 0.25)


def iso_beta(k: float, d_pipe: float, rho: float, mu: float, re_d: float) -> float | None:
    """β in [BETA_MIN, BETA_MAX] with K(C_L(β, Re_eff)) = k at Re_D = re_d, or None."""

    def residual(beta: float) -> float:
        return loss_k(d_pipe, beta * d_pipe, iso_loss_c(d_pipe, beta, rho, mu, re_d)) - k

    low, high = residual(BETA_MIN), residual(BETA_MAX)
    if not (low > 0.0 > high):
        return None
    return float(brentq(residual, BETA_MIN, BETA_MAX, xtol=1.0e-15, rtol=1.0e-15, maxiter=200))


# --------------------------------------------------------------------------- the replacement


@dataclass(frozen=True)
class Plate:
    """An orifice plate that stands in for a valve: its pipe and bore diameters, m, its entered
    C (None: ISO 5167-2's) and taps."""

    d_pipe: float
    d_bore: float
    entered: float | None
    taps: OrificeTaps | None


def plate_for(
    mode: str,
    result: dict[str, Any],
    fluid: dict[str, Any],
    rng: random.Random,
    scale: float = 1.0,
) -> tuple[Plate | None, str]:
    """The plate that stands in for a valve whose A result is ``result`` (module docstring), or
    None ('kept'); the second item counts a plate whose drawn taps were dropped ('untapped').
    ``scale`` multiplies K (1: the valve's own law; a test of the check uses another)."""
    d_pipe = float(result["referenceDiameter"])
    k = float(result["kOpen"]) * scale
    if mode == "entered":
        c = rng.uniform(*ENTERED_C)
        beta = entered_beta(k, c) if k > 0.0 else 1.0
        if not BETA_MIN <= beta <= BETA_MAX:
            return None, ""
        plate = Plate(d_pipe, beta * d_pipe, c, None)
        return (plate, "") if refusal(d_pipe, plate.d_bore, c, None, G) is None else (None, "")
    taps = rng.choice(TAPS)
    rho, mu = float(fluid["density"]), float(fluid["dynamicViscosity"])
    re_d = 4.0 * rho * abs(float(result["flow"])) / (math.pi * d_pipe * mu)
    found = iso_beta(k, d_pipe, rho, mu, re_d) if k > 0.0 else None
    if found is None:
        return None, ""
    d_bore = found * d_pipe
    if taps is not None and refusal(d_pipe, d_bore, None, taps, G) is not None:
        return Plate(d_pipe, d_bore, None, None), "untapped"
    if refusal(d_pipe, d_bore, None, None, G) is not None:
        return None, ""
    return Plate(d_pipe, d_bore, None, taps), ""


def replaced(
    name: str, project: dict[str, Any], state: dict[str, Any], mode: str, scale: float = 1.0
) -> tuple[dict[str, Any], dict[str, Plate], Counter[str]]:
    """(B's project, each replaced valve's id -> its plate, the counts: 'replaced', 'tapped'
    (and 'taps_<taps>' by tap set), 'untapped', 'kept', 'no_result'). The project is API JSON
    without scenarios; ``state`` A's solved state (API JSON)."""
    rng = random.Random(f"orifice:{name}" if mode == "entered" else f"orifice:iso:{name}")
    data = copy.deepcopy(project)
    data.pop("scenarios", None)
    plates: dict[str, Plate] = {}
    counts: Counter[str] = Counter()
    for valve in active_isolation_valves(data):
        result = state["valveResults"].get(valve["id"])
        if result is None:
            counts["no_result"] += 1
            continue
        plate, note = plate_for(mode, result, state["fluid"], rng, scale)
        if plate is None:
            counts["kept"] += 1
            continue
        if note:
            counts[note] += 1
        component: dict[str, Any] = {
            "type": "orifice",
            "id": valve["id"],
            "name": valve["name"],
            "elevation": valve["elevation"],
            "ports": valve["ports"],
            "boreDiameter": plate.d_bore,
        }
        if plate.entered is not None:
            component["dischargeCoefficient"] = plate.entered
        if plate.taps is not None:
            component["taps"] = plate.taps
            counts["tapped"] += 1
            counts[f"taps_{plate.taps}"] += 1
        data["components"][data["components"].index(valve)] = component
        plates[valve["id"]] = plate
        counts["replaced"] += 1
    return data, plates, counts


# --------------------------------------------------------------------------- the checks


def _ports(project: dict[str, Any], pid: str) -> dict[str, tuple[str, str]]:
    ends = port_connections(project)
    return {port: ends[f"{pid}:{port}"] for port in ("inlet", "outlet")}


def _velocity(state: dict[str, Any], conn: str, end: str) -> float:
    segments = state["linkResults"][conn]["segments"]
    return float(segments[0 if end == "from" else -1]["velocity"])


def element_problems(
    project: dict[str, Any], a: dict[str, Any], b: dict[str, Any], pid: str
) -> tuple[list[str], list[str]]:
    """(c) and (d) for the plate ``pid`` (B) that stands in for the valve ``pid`` (A):
    (differences, values different only at zero flow)."""
    rho = float(a["fluid"]["density"])
    valve, item = a["valveResults"][pid], b["orificeResults"].get(pid)
    if item is None:
        text = f"(c) {pid}: no orifice result, its valve carried {valve['flow']!r}"
        return ([], [text]) if valve["flow"] == 0.0 else ([text], [])
    differences: list[str] = []
    at_zero: list[str] = []
    for field, quantity in (("flow", "flow"), ("headLoss", "head")):
        va, vb = valve[field], item[field]
        if abs(vb - va) > d6(quantity, va, rho):
            text = f"(c) {field} of {pid}: valve {va!r}, orifice {vb!r}"
            (at_zero if 0.0 in (valve["flow"], item["flow"]) else differences).append(text)
    rho_b = float(b["fluid"]["density"])
    loss = rho_b * G * item["headLoss"]
    if abs(item["pressureLoss"] - loss) > ROUND_OFF * abs(loss):
        differences.append(
            f"(d) {pid}: pressureLoss {item['pressureLoss']!r} != ρg·headLoss {loss!r}"
        )
    terms: dict[str, tuple[float, float, float]] = {}  # port -> (|EGL|, z, v)
    for port, (conn, end) in _ports(project, pid).items():
        node = b["nodeResults"].get(f"{pid}:{port}")
        egl = abs(node["egl"]) if node is not None else head_bound(b)  # a floating section
        terms[port] = (egl, port_elevation(project, f"{pid}:{port}"), _velocity(b, conn, end))
    (h_in, z_in, v_in), (h_out, z_out, v_out) = terms["inlet"], terms["outlet"]
    identity = loss + rho_b * G * (z_out - z_in) + rho_b * (v_out * v_out - v_in * v_in) / 2.0
    size = rho_b * G * (h_in + h_out + abs(z_in) + abs(z_out))
    size += rho_b * (v_in * v_in + v_out * v_out) / 2.0
    if not abs(item["pressureDrop"] - identity) <= ROUND_OFF * size:
        differences.append(
            f"(d) {pid}: pressureDrop {item['pressureDrop']!r} != the identity {identity!r}"
            f" (ρg·headLoss + ρgΔz + ρΔ(v²)/2)"
        )
    return differences, at_zero


def coefficient_problems(
    project: dict[str, Any], b: dict[str, Any], pid: str, plate: Plate
) -> list[str]:
    """(e) for the plate ``pid`` in B (module docstring): the differences found."""
    item = b["orificeResults"].get(pid)
    if item is None:
        return []  # (c) reports it
    out: list[str] = []

    def same(what: str, got: Any, expected: Any, size: float | None = None) -> None:
        if got is None or expected is None or isinstance(expected, str):
            if got != expected:
                out.append(f"(e) {pid}: {what} {got!r}, expected {expected!r}")
            return
        scale = abs(expected) if size is None else size
        if not abs(got - expected) <= ROUND_OFF * scale:
            out.append(f"(e) {pid}: {what} {got!r} != {expected!r}")

    rho, mu = float(b["fluid"]["density"]), float(b["fluid"]["dynamicViscosity"])
    d_pipe, d_bore = plate.d_pipe, plate.d_bore
    same("pipeDiameter", item["pipeDiameter"], d_pipe)
    same("boreDiameter", item["boreDiameter"], d_bore)
    same("taps", item["taps"], plate.taps)
    beta = d_bore / d_pipe
    same("beta", item["beta"], beta)
    q = float(item["flow"])
    area = math.pi * d_pipe * d_pipe / 4.0
    v = q / area
    re = 4.0 * rho * abs(q) / (math.pi * d_pipe * mu)
    same("reynoldsNumber", item["reynoldsNumber"], re)
    beta4 = beta**4
    if plate.entered is not None:
        c_loss = plate.entered
        same("coefficientSource", item["coefficientSource"], "entered")
        same("coefficientReynoldsNumber", item["coefficientReynoldsNumber"], None)
        same("meterDischargeCoefficient", item["meterDischargeCoefficient"], None)
        same("differentialPressure", item["differentialPressure"], None)
    else:
        re_eff = max(re, re_lo(beta, d_pipe, LOSS_TAPS))
        c_loss = iso_c(d_pipe, d_bore, rho, mu, re_eff, LOSS_TAPS)
        same("coefficientSource", item["coefficientSource"], "iso_5167_2")
        same("coefficientReynoldsNumber", item["coefficientReynoldsNumber"], re_eff)
        c_meter: float | None = None
        reading: float | None = None
        if plate.taps is not None:
            c_meter = (
                c_loss
                if plate.taps == LOSS_TAPS
                else iso_c(
                    d_pipe, d_bore, rho, mu, max(re, re_lo(beta, d_pipe, plate.taps)), plate.taps
                )
            )
            reading = (1.0 - beta4) / (c_meter * c_meter * beta4) * rho * v * abs(v) / 2.0
        same("meterDischargeCoefficient", item["meterDischargeCoefficient"], c_meter)
        same("differentialPressure", item["differentialPressure"], reading)
    same("tapCoefficientRatio", item["tapCoefficientRatio"], None)
    same("dischargeCoefficient", item["dischargeCoefficient"], c_loss)
    k = loss_k(d_pipe, d_bore, c_loss)
    same("lossCoefficient", item["lossCoefficient"], k)
    ports = _ports(project, pid)
    heads = {}
    for port in ports:
        node = b["nodeResults"].get(f"{pid}:{port}")
        heads[port] = abs(node["egl"]) if node is not None else head_bound(b)
    law = k * v * abs(v) / (2.0 * G)
    if not abs(item["headLoss"] - law) <= LAW_TOLERANCE + ROUND_OFF * sum(heads.values()):
        out.append(f"(e) {pid}: headLoss {item['headLoss']!r} != K·v|v|/(2g) {law!r}")
    up, down = ("inlet", "outlet") if q >= 0.0 else ("outlet", "inlet")
    upstream = b["nodeResults"].get(f"{pid}:{up}")
    vena: float | None = None
    size = 0.0
    if q != 0.0 and upstream is not None:
        z_up = port_elevation(project, f"{pid}:{up}")
        z_down = port_elevation(project, f"{pid}:{down}")
        drop = (1.0 - beta4) / (c_loss * c_loss * beta4) * rho * v * v / 2.0
        vena = upstream["pressure"] + rho * G * (z_up - z_down) - drop
        size = abs(upstream["pressure"]) + rho * G * (abs(z_up) + abs(z_down)) + drop
    same("venaContractaPressure", item["venaContractaPressure"], vena, size)
    return out


def largest_differences(
    a: dict[str, Any], b: dict[str, Any], plates: list[str]
) -> dict[str, float]:
    """The largest differences between A's and B's values that both have, recorded with no
    threshold: 'flow', of the connections and the plates against their valves, relative to the
    largest flow of A; 'head', m, of the port EGLs, the static pressures as heads (÷ ρg) and the
    plates' head losses against their valves'."""
    rho_g = float(a["fluid"]["density"]) * G
    q_max = max((abs(link["flow"]) for link in a["linkResults"].values()), default=0.0)
    flows = [
        abs(b["linkResults"][k]["flow"] - link["flow"])
        for k, link in a["linkResults"].items()
        if k in b["linkResults"]
    ]
    heads = []
    for key, node in a["nodeResults"].items():
        other = b["nodeResults"].get(key)
        if other is not None:
            heads += [abs(other["egl"] - node["egl"]), abs(other["pressure"] - node["pressure"])]
            heads[-1] /= rho_g
    for pid in plates:
        valve, item = a["valveResults"][pid], b["orificeResults"].get(pid)
        if item is not None:
            flows.append(abs(item["flow"] - valve["flow"]))
            heads.append(abs(item["headLoss"] - valve["headLoss"]))
    return {
        "flow": max(flows, default=0.0) / q_max if q_max > 0.0 else max(flows, default=0.0),
        "head": max(heads, default=0.0),
    }


def check_mode(
    name: str, base: dict[str, Any], a: dict[str, Any], mode: str, scale: float = 1.0
) -> dict[str, Any]:
    """One mode's record for a project with an active isolation valve, solved in A."""
    data, plates, counts = replaced(name, base, a, mode, scale)
    record: dict[str, Any] = {"counts": dict(counts), "differences": [], "atZeroFlow": []}
    if not plates:
        record["outcome"] = "none_replaced"
        return record
    differences: list[str] = record["differences"]
    try:
        b = _dump(solve_project(Project.model_validate(data), NO_CURVES))
    except TopologyError as exc:
        record["outcome"] = "different"
        differences.append(f"(a) B is a topology error: {[i.code for i in exc.issues]}")
        return record
    record["outcome"] = "checked"
    record["converged"] = bool(a["converged"])
    if a["converged"] != b["converged"]:
        differences.append(f"(a) converged {a['converged']} in A, {b['converged']} in B")
    elif a["converged"]:
        found, at_zero = network_problems(data, a, b)
        differences += found
        record["atZeroFlow"] += at_zero
        for pid, plate in plates.items():
            found, at_zero = element_problems(data, a, b, pid)
            differences += found
            record["atZeroFlow"] += at_zero
            differences += coefficient_problems(data, b, pid, plate)
        results = [b["orificeResults"].get(p) for p in plates]
        record["reverse"] = sum(r is not None and r["flow"] < 0 for r in results)
        record["flowing"] = sum(r is not None and r["flow"] != 0 for r in results)
        record["held"] = sum(
            r is not None
            and r["coefficientReynoldsNumber"] is not None
            and r["reynoldsNumber"] < r["coefficientReynoldsNumber"]
            for r in results
        )
        lossy = [abs(a["valveResults"][p]["headLoss"]) > HEAD_FLOOR for p in plates]
        record["lossy"] = sum(lossy)
        record["varying"] = sum(
            big
            and r is not None
            and r["coefficientSource"] == "iso_5167_2"
            and r["reynoldsNumber"] >= r["coefficientReynoldsNumber"]
            for r, big in zip(results, lossy, strict=True)
        )
        record["largest"] = largest_differences(a, b, list(plates))
    if differences:
        record["outcome"] = "different"
    return record


def check(
    name: str, project: Project, modes: tuple[str, ...] = MODES, scale: float = 1.0
) -> dict[str, Any]:
    """The record of one project: its outcome, each mode's record, and every difference found,
    named by its mode (none: passed). ``scale`` multiplies each plate's K (1: the valves' own
    law)."""
    record: dict[str, Any] = {
        "name": name,
        "profile": profile(name),
        "differences": [],
        "atZeroFlow": [],
        "modes": {},
    }
    base = project.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if not active_isolation_valves(base):
        record["outcome"] = "no_valve"
        return record
    try:
        a = _dump(solve_project(project, NO_CURVES))
    except TopologyError:
        record["outcome"] = "topology_error"
        return record
    record["outcome"] = "checked"
    for mode in modes:
        sub = check_mode(name, base, a, mode, scale)
        record["modes"][mode] = sub
        record["differences"] += [f"[{mode}] {d}" for d in sub["differences"]]
        record["atZeroFlow"] += [f"[{mode}] {t}" for t in sub["atZeroFlow"]]
    if record["differences"]:
        record["outcome"] = "different"
    return record


# --------------------------------------------------------------------------- the corpus


def run(work: tuple[tuple[str, ...], Item]) -> dict[str, Any]:
    modes, (name, spec) = work
    try:
        project = load(spec)
    except Exception as ex:  # a corpus file that does not load is not an orifice finding
        return {
            "name": name,
            "profile": profile(name),
            "outcome": "load_error",
            "error": repr(ex),
            "differences": [],
            "atZeroFlow": [],
            "modes": {},
        }
    try:
        return check(name, project, modes)
    except Exception as ex:
        return {
            "name": name,
            "profile": profile(name),
            "outcome": "crash",
            "differences": [f"crash: {ex!r}"],
            "atZeroFlow": [],
            "modes": {},
        }


def check_all(
    selection: list[Item], workers: int = 1, modes: tuple[str, ...] = MODES
) -> list[dict[str, Any]]:
    """The records of ``selection`` (corpus items), in order."""
    work = [(modes, item) for item in selection]
    if workers <= 1:
        return [run(w) for w in work]
    with Pool(workers) as pool:
        return pool.map(run, work, chunksize=4)


COLUMNS = (
    "projects",
    "checked",
    "different",
    "replaced",
    "flowing",
    "lossy",
    "held",
    "varying",
    "tapped",
    "untapped",
    "kept",
    "no_result",
    "not_converged",
    "at_zero_flow",
    "reverse",
    "no_valve",
    "none_replaced",
    "topology_error",
    "load_error",
    "crash",
)
"""The report's columns, per mode and profile (module docstring)."""


def summarize(records: list[dict[str, Any]], modes: tuple[str, ...] = MODES) -> list[str]:
    """The report's lines (module docstring)."""
    lines: list[str] = []
    for mode in modes:
        by_profile: dict[str, Counter[str]] = defaultdict(Counter)
        for r in records:
            tally = by_profile[r["profile"]]
            tally["projects"] += 1
            sub = r["modes"].get(mode)
            if sub is None:
                tally[r["outcome"]] += 1
                continue
            tally[sub["outcome"]] += 1
            for kind, n in sub["counts"].items():
                tally[kind] += n
            if sub["outcome"] in ("checked", "different") and sub.get("converged") is False:
                tally["not_converged"] += 1
            tally["at_zero_flow"] += len(sub["atZeroFlow"])
            for key in ("reverse", "flowing", "held", "lossy", "varying"):
                tally[key] += sub.get(key, 0)
        lines.append(f"mode {mode}")
        lines.append("profile " + " ".join(COLUMNS))
        total: Counter[str] = Counter()
        for name in sorted(by_profile, key=lambda p: (*PROFILES, p).index(p)):
            tally = by_profile[name]
            total += tally
            lines.append(f"{name} " + " ".join(str(tally[c]) for c in COLUMNS))
        lines.append("all " + " ".join(str(total[c]) for c in COLUMNS))
        compared = [(r["name"], r["modes"][mode]) for r in records if mode in r["modes"]]
        compared = [(n, sub) for n, sub in compared if "largest" in sub]
        for quantity, unit in (("flow", "× the largest flow"), ("head", "m (pressures as heads)")):
            worst = max(compared, key=lambda t: t[1]["largest"][quantity], default=None)
            if worst is not None:
                lines.append(
                    f"largest {quantity} difference ({mode}):"
                    f" {worst[1]['largest'][quantity]:.3g} {unit} ({worst[0]})"
                )
    for r in records:
        for text in r["atZeroFlow"]:
            lines.append(f"at zero flow: {r['name']} {text}")
    different = [r for r in records if r["differences"]]
    for r in different:
        lines.append(f"{r['name']}: " + "; ".join(r["differences"][:10]))
    lines.append(f"different: {len(different)}")
    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tests.differential.orifice_check",
        description="Check orifice plates against isolation valves over the corpus (proposal"
        " orifice-plate.md §7.4).",
    )
    parser.add_argument(
        "--mode", choices=MODES, action="append", help="a mode to run (default: both)"
    )
    parser.add_argument("--workers", type=int, default=3, help="worker processes (default 3)")
    parser.add_argument("--only", default="", help="only projects whose name starts with this")
    parser.add_argument("--out", default="", help="write every project's record to this file")
    args = parser.parse_args(argv)
    modes = tuple(args.mode) if args.mode else MODES
    selection = [t for t in items() if t[0].startswith(args.only)]
    print(f"projects: {len(selection)}", flush=True)
    records = check_all(selection, args.workers, modes)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(records, f, indent=1, sort_keys=True)
    print("\n".join(summarize(records, modes)))
    sys.exit(1 if any(r["differences"] for r in records) else 0)


if __name__ == "__main__":
    main()
