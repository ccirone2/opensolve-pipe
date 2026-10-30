"""Generate ``src/opensolve_pipe/data/api526_orifices.json``: the relief valve's cited data
(proposal pressure-relief-valve.md decision 27, CLAUDE.md D8's pattern).

- API 526's orifice letters and their effective areas, from fluids 1.3.1
  (``fluids.safety_valve.API526_letters``, ``API526_A_sq_inch`` and ``API526_A``, the areas in m²
  as fluids computes them, so a capacity is the area ``API520_round_size`` returns);
- API 520's effective coefficient of discharge for preliminary sizing, 0.65: the default ``Kd``
  of ``fluids.safety_valve.API520_A_l`` ("0.65 normally");
- ASME VIII's liquid certification overpressure, 10 % of the set pressure or 3 psi, whichever is
  greater, and its scope, set pressures of 15 psi and above, as Pentair's handbook quotes ASME
  (the psi from ``fluids.constants.psi``).

Each entry carries its citation. The model reads this file (``models/components.py``) and
publishes it as ``x-relief-data``, so the web reads the letters and bounds instead of copying them
(D10), and a library change shows up as a diff here.

Run from ``apps/api``::

    uv run python scripts/generate_relief_data.py          # write the JSON
    uv run python scripts/generate_relief_data.py --check  # exit 1 if the JSON is stale

``tests/unit/test_relief_model.py`` regenerates the data in memory and asserts the committed
file matches, so the JSON can never drift from its sources.
"""

import inspect
import json
import sys
from pathlib import Path
from typing import Any

import fluids
from fluids.constants import psi
from fluids.safety_valve import API526_A, API520_A_l, API526_A_sq_inch, API526_letters

OUTPUT = (
    Path(__file__).resolve().parents[1] / "src" / "opensolve_pipe" / "data" / "api526_orifices.json"
)

_FLUIDS = f"fluids {fluids.__version__}"

# Reference strings: API 526 as the fluids.safety_valve docstrings cite it; the Pentair handbook
# as downloaded and read by the design (proposal pressure-relief-valve.md §3.10).
_API526 = "API Standard 526, Flanged Steel Pressure-Relief Valves (effective orifice areas)"
_API520 = "API Standard 520, Part I, Sizing and Selection, 10th edition"
_PENTAIR = (
    "Pentair, Pressure Relief Valve Engineering Handbook, Technical Publication No. TP-V300, "
    "rev. 12-2012"
)
_TABLE_7_6 = (
    f"{_PENTAIR}, Table 7-6 (API effective orifice area and coefficient of discharge, liquid "
    "K = 0.650), gives the same areas"
)

ASME_OVERPRESSURE_FRACTION = 0.10
"""ASME VIII's liquid certification overpressure, as a fraction of the set pressure: "The steam,
gas, or liquid capacity tests are performed with 10% or 3 psi [0.207 bar] overpressure"
(Pentair TP-V300 ch. 3, p. 3.15)."""
ASME_OVERPRESSURE_FLOOR_PSI = 3.0
"""psi: the floor of that overpressure (the same sentence)."""
ASME_MINIMUM_SET_PSI = 15.0
"""psi: ASME VIII's scope for a pressure relief valve's set pressure, "outside of the scope of
ASME (below 15 psig)" (Pentair TP-V300 ch. 5, p. 5.3)."""


def _effective_kd() -> float:
    """API520_A_l's default Kd, read from its signature (not typed in here)."""
    default = inspect.signature(API520_A_l).parameters["Kd"].default
    assert isinstance(default, float)
    return default


def build_relief_data() -> dict[str, Any]:
    """Build the relief valve data from fluids and the cited constants. Deterministic: same
    fluids, same output."""
    orifices = [
        {
            "letter": letter,
            "area": area,
            "areaSquareInches": square_inches,
            "source": (
                f"{_API526}; letter {letter}, {square_inches:g} in², via {_FLUIDS} "
                "fluids.safety_valve.API526_A (API526_A_sq_inch × inch²); "
                f"{_TABLE_7_6}"
            ),
        }
        for letter, square_inches, area in zip(
            API526_letters, API526_A_sq_inch, API526_A, strict=True
        )
    ]
    return {
        "description": (
            "The pressure relief valve's cited data (proposal pressure-relief-valve.md decision "
            "27). orifices: API 526's letters with their effective areas, m², for preliminary "
            "sizing with API 520's effective coefficient of discharge (never with a valve's rated "
            "coefficient or actual area). effectiveDischargeCoefficient: that coefficient. "
            "asmeOverpressureFraction and asmeOverpressureFloor (Pa, a difference): ASME VIII's "
            "liquid certification overpressure, the fraction of the set pressure or the floor, "
            "whichever is greater, the default overpressure at full lift. "
            "asmeMinimumSetPressure (Pa, a difference): ASME VIII's scope, below which that "
            "default is not cited."
        ),
        "generatedBy": "apps/api/scripts/generate_relief_data.py",
        "fluidsVersion": fluids.__version__,
        "units": "m² (areas), Pa (pressures), fractions (no unit)",
        "orifices": orifices,
        "effectiveDischargeCoefficient": {
            "value": _effective_kd(),
            "source": (
                f"{_API520}: the effective coefficient of discharge for preliminary sizing of a "
                f"liquid relief valve ('0.65 normally'), via {_FLUIDS} "
                "fluids.safety_valve.API520_A_l's default Kd; "
                f"{_PENTAIR}, Table 7-6 (liquid K = 0.650)"
            ),
        },
        "asmeOverpressureFraction": {
            "value": ASME_OVERPRESSURE_FRACTION,
            "source": (
                f"{_PENTAIR}, ch. 3, p. 3.15, on ASME Section VIII: 'The steam, gas, or liquid "
                "capacity tests are performed with 10% or 3 psi [0.207 bar] overpressure'"
            ),
        },
        "asmeOverpressureFloor": {
            "value": ASME_OVERPRESSURE_FLOOR_PSI * psi,
            "psi": ASME_OVERPRESSURE_FLOOR_PSI,
            "source": (
                f"{_PENTAIR}, ch. 3, p. 3.15, the same sentence ('10% or 3 psi'); "
                f"3 psi × {_FLUIDS} fluids.constants.psi ({psi!r} Pa)"
            ),
        },
        "asmeMinimumSetPressure": {
            "value": ASME_MINIMUM_SET_PSI * psi,
            "psi": ASME_MINIMUM_SET_PSI,
            "source": (
                f"{_PENTAIR}, ch. 5, p. 5.3: 'outside of the scope of ASME (below 15 psig)'; "
                f"15 psi × {_FLUIDS} fluids.constants.psi ({psi!r} Pa)"
            ),
        },
    }


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = render(build_relief_data())
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT} is stale; run scripts/generate_relief_data.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
