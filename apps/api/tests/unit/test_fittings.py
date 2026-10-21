"""Inline fitting K factors (design §3) checked against the fluids 1.3.1 documentation.

Expected values are the fluids docstring examples or formulas quoted in
research/fluids_reference.md (§1.3-1.6), or a direct call of the cited fluids function.
"""

import json
import math
from pathlib import Path
from typing import Any, get_args

import fluids.fittings as ff
import pytest
from fluids.friction import ft_Crane

from opensolve_pipe.models.piping import Fitting, FittingType
from opensolve_pipe.services.solver.fittings import load_fittings, resolve_fitting

DATA = Path(__file__).parents[2] / "src" / "opensolve_pipe" / "data" / "fittings.json"


def k_of(fitting: dict[str, Any], diameters: list[float], flow: float = 1.0) -> float:
    return resolve_fitting(0, Fitting.model_validate(fitting), diameters).k(flow)


def test_every_fitting_type_has_exactly_one_entry() -> None:
    entries = [e["type"] for e in json.loads(DATA.read_text())["fittings"]]
    assert sorted(entries) == sorted(get_args(FittingType))
    assert len(entries) == len(set(entries))


def test_every_entry_is_cited_and_callable() -> None:
    for spec in load_fittings().values():
        assert spec.source
        assert spec.reference_diameter in ("pipe", "smaller pipe")
        for call in spec.calls.values():
            assert callable(getattr(ff, call.function))
        if spec.type != "custom":
            assert "fluids" in spec.source
            assert not spec.valid_in_laminar_flow


# --- fluids docstring examples (research/fluids_reference.md) -----------------------------


def test_bend_doc_example() -> None:
    # bend_rounded_Crane(Di=.4020, rc=.4*5, angle=30) -> 0.09321910015613409
    k = k_of({"type": "bend", "angle": 30, "radiusRatio": 0.4 * 5 / 0.4020}, [0.4020])
    assert k == pytest.approx(0.09321910015613409, rel=1e-12)


def test_sudden_contraction_doc_example() -> None:
    # contraction_sharp(method='Crane') is contraction_conical_Crane(l=0):
    # contraction_conical_Crane(Di1=0.0779, Di2=0.0525, l=0) -> 0.2729017979998056
    fit = resolve_fitting(0, Fitting(type="reducer_sudden"), [0.0779, 0.0525])
    assert fit.k(1.0) == pytest.approx(0.2729017979998056, rel=1e-12)
    assert fit.segment(1.0) == 1  # K on the smaller, downstream pipe


def test_sudden_expansion_doc_example() -> None:
    # diffuser_sharp(Di1=.5, Di2=1) -> 0.5625, on the smaller (upstream) pipe
    fit = resolve_fitting(0, Fitting(type="reducer_sudden"), [0.5, 1.0])
    assert fit.k(1.0) == 0.5625
    assert fit.segment(1.0) == 0


def test_reducer_picks_contraction_or_expansion_from_flow_direction() -> None:
    fit = resolve_fitting(0, Fitting(type="reducer_sudden"), [0.5, 1.0])
    # Reverse flow runs from the 1.0 m pipe into the 0.5 m pipe: a contraction.
    assert fit.k(-1.0) == ff.contraction_sharp(1.0, 0.5, method="Crane")
    assert fit.segment(-1.0) == 0  # still the smaller pipe
    assert "contraction_sharp" in fit.correlation(-1.0)
    assert "diffuser_sharp" in fit.correlation(1.0)


def test_equal_diameter_reducer_has_no_loss() -> None:
    fit = resolve_fitting(0, Fitting(type="reducer_conical", angle=30), [0.1, 0.1])
    assert fit.k(1.0) == fit.k(-1.0) == 0.0


def test_conical_reducer_follows_the_crane_formulas() -> None:
    d_small, d_large, theta = 0.05, 0.1, 30.0
    beta = d_small / d_large
    fit = resolve_fitting(0, Fitting(type="reducer_conical", angle=theta), [d_small, d_large])
    # Expansion (fluids diffuser_conical_Crane code, θ < 45°, on the upstream pipe):
    # K1 = 2.6 sin(θ/2) (1 − β²)²; probe value 0.3785228534624366.
    expansion = 2.6 * math.sin(math.radians(theta / 2)) * (1 - beta**2) ** 2
    assert fit.k(1.0) == pytest.approx(expansion, rel=1e-12)
    assert fit.k(1.0) == pytest.approx(0.3785228534624366, rel=1e-12)
    # Contraction (contraction_conical_Crane docstring, θ < 45°): K2 = 0.8 sin(θ/2)(1 − β²).
    contraction = 0.8 * math.sin(math.radians(theta / 2)) * (1 - beta**2)
    assert fit.k(-1.0) == pytest.approx(contraction, rel=1e-12)
    assert fit.segment(1.0) == fit.segment(-1.0) == 0


def test_swing_check_doc_example() -> None:
    # K_swing_check_valve_Crane(D=.02) -> 2.3974274785373257
    assert k_of({"type": "swing_check_valve"}, [0.02]) == pytest.approx(
        2.3974274785373257, rel=1e-12
    )


def test_entrances_and_exit() -> None:
    # "0.5 is the result for ... 'Crane'"; "The 'Crane' method returns 0.78 for all cases";
    # exit_normal() -> 1.0
    assert k_of({"type": "entrance_sharp"}, [0.1]) == 0.5
    assert k_of({"type": "entrance_projecting"}, [0.1]) == 0.78
    assert k_of({"type": "exit"}, [0.1]) == 1.0
    # Rounded entrance at a Crane table point (fluids entrance_rounded_*_Crane tables).
    ratios, ks = ff.entrance_rounded_ratios_Crane, ff.entrance_rounded_Ks_Crane
    i = len(ratios) - 2
    assert k_of({"type": "entrance_rounded", "radiusRatio": ratios[i]}, [0.1]) == pytest.approx(
        ks[i], rel=1e-12
    )


@pytest.mark.parametrize("d", [0.02664, 0.10226, 0.30318])
def test_crane_valves_and_elbows_use_full_bore_crane_multipliers(d: float) -> None:
    """Multipliers of ft_Crane(D) from the fluids docstring formulas (research notes
    §1.3, §1.4.1): gate 8, ball 3, globe 340, plug (straight-through) 18, swing check
    (angled pattern) 100, lift check (angled pattern) 55, threaded elbow 30 (90°) / 16 (45°)."""
    ft = ft_Crane(d)
    expected = {
        "gate_valve": 8,
        "ball_valve": 3,
        "globe_valve": 340,
        "plug_valve": 18,
        "swing_check_valve": 100,
        "lift_check_valve": 55,
        "elbow_90_threaded": 30,
        "elbow_45_threaded": 16,
    }
    for fitting_type, multiplier in expected.items():
        assert k_of({"type": fitting_type}, [d]) == pytest.approx(multiplier * ft, rel=1e-12)


def test_butterfly_is_the_centric_style() -> None:
    # Centric (style 0) multipliers by size: 45 for D <= 0.2286 m (docstring table §1.4.1).
    assert k_of({"type": "butterfly_valve"}, [0.1]) == pytest.approx(45 * ft_Crane(0.1), rel=1e-12)


@pytest.mark.parametrize(
    ("fitting_type", "angle", "r_d"),
    [
        ("elbow_90_lr", 90, 1.5),
        ("elbow_90_sr", 90, 1.0),
        ("elbow_45_lr", 45, 1.5),
        ("elbow_45_sr", 45, 1.0),
    ],
)
def test_welded_elbows_call_bend_rounded_crane(fitting_type: str, angle: float, r_d: float) -> None:
    d = 0.10226
    expected = ff.bend_rounded_Crane(Di=d, angle=angle, bend_diameters=r_d)
    assert k_of({"type": fitting_type}, [d]) == expected


def test_k_override_wins_and_is_on_pipe_index() -> None:
    fit = resolve_fitting(
        3, Fitting(type="elbow_90_lr", k_override=0.7, quantity=2, pipe_index=1), [0.1, 0.2]
    )
    assert (fit.k(1.0), fit.k(-1.0), fit.segment(1.0), fit.segment(-1.0)) == (0.7, 0.7, 1, 1)
    assert fit.user_k
    assert fit.source == "user"
    assert fit.valid_in_laminar_flow
    assert (fit.index, fit.quantity) == (3, 2)
    reducer = resolve_fitting(0, Fitting(type="reducer_sudden", k_override=0.3), [0.1, 0.2])
    assert (reducer.k(1.0), reducer.k(-1.0), reducer.segment(-1.0)) == (0.3, 0.3, 0)
    custom = resolve_fitting(0, Fitting(type="custom", k_override=2.5), [0.1])
    assert custom.k(1.0) == 2.5


def test_range_warnings_for_clamped_tables() -> None:
    def warning(fitting: dict[str, Any]) -> str | None:
        return resolve_fitting(0, Fitting.model_validate(fitting), [0.1]).range_warning

    assert warning({"type": "bend", "angle": 90, "radiusRatio": 3}) is None
    assert warning({"type": "bend", "angle": 90, "radiusRatio": 0.5}) is not None
    assert warning({"type": "bend", "angle": 90, "radiusRatio": 25}) is not None
    assert warning({"type": "entrance_rounded", "radiusRatio": 0.1}) is None
    assert warning({"type": "entrance_rounded", "radiusRatio": 0.5}) is not None
    assert warning({"type": "bend", "angle": 90, "radiusRatio": 25, "kOverride": 0.2}) is None


def test_correlation_text_names_the_fluids_call() -> None:
    spec = load_fittings()["elbow_90_lr"]
    assert spec.correlation == (
        "k: fluids.fittings.bend_rounded_Crane(Di=D, angle=90.0, bend_diameters=1.5)"
    )
    assert load_fittings()["custom"].correlation == "user K (kOverride)"


@pytest.mark.parametrize(
    ("fitting_type", "function", "args"),
    [
        ("swing_check_valve", "K_swing_check_valve_Crane", {"D": 0.10226}),
        ("lift_check_valve", "K_lift_check_valve_Crane", {"D1": 0.10226, "D2": 0.10226}),
    ],
)
def test_check_valve_fittings_state_their_pattern(
    fitting_type: str, function: str, args: dict[str, float]
) -> None:
    """fluids defaults to angled=True, and the straight pattern differs (docstrings: "For angled
    swing check valves N = 100; for straight valves, N = 50", "For angled lift check valves
    N = 55; for straight valves, N = 600"). The library passes the pattern explicitly and names
    it, so the angled K is never applied to a straight valve unawares."""
    spec = load_fittings()[fitting_type]
    call = spec.calls["k"]
    assert call.function == function
    assert call.arguments["angled"] is True
    assert "angled pattern" in spec.name
    assert "angled=True" in spec.correlation
    angled = getattr(ff, function)(**args, angled=True)
    straight = getattr(ff, function)(**args, angled=False)
    assert k_of({"type": fitting_type}, [0.10226]) == angled
    assert angled != pytest.approx(straight, rel=0.1)
