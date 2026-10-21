"""Generate ``src/opensolve_pipe/data/pipe_materials.json`` from the fluids library.

Every number in the output comes from a fluids 1.3.1 function call: pipe dimensions from
``fluids.piping.nearest_pipe`` (tabulated standards, cited below) and absolute roughness from
``fluids.friction.roughness_Farshad`` (Farshad & Rieke 2006, diameter dependent). Nominal sizes
are NPS (inches) times ``scipy.constants.inch``. Nothing is typed in by hand.

Run from ``apps/api``::

    uv run python scripts/generate_pipe_data.py          # write the JSON
    uv run python scripts/generate_pipe_data.py --check  # exit 1 if the JSON is stale

``tests/unit/test_pipe_library.py`` regenerates the data in memory and asserts the committed
file matches, so the JSON can never drift from its sources.
"""

import json
import sys
from pathlib import Path
from typing import Any

import fluids
from fluids.friction import roughness_Farshad
from fluids.piping import nearest_pipe, schedule_lookup
from scipy.constants import inch

OUTPUT = (
    Path(__file__).resolve().parents[1] / "src" / "opensolve_pipe" / "data" / "pipe_materials.json"
)

_FLUIDS = f"fluids {fluids.__version__}"

# Reference strings copied from the fluids.piping.nearest_pipe and
# fluids.friction.roughness_Farshad docstrings.
_B36_10M = (
    "ANSI/ASME B36.10M-2004: Welded and Seamless Wrought Steel Pipe. New York: American "
    "Society of Mechanical Engineers, 2004"
)
_B36_19M = (
    "ANSI/ASME B36.19M-2004: Stainless Steel Pipe. New York: American Society of Mechanical "
    "Engineers, 2004"
)
_D1785 = (
    "ASTM D1785-15E01: Specification for Poly(Vinyl Chloride) (PVC) Plastic Pipe, Schedules "
    "40, 80, and 120. ASTM International. doi:10.1520/D1785-15E01"
)
_FARSHAD = (
    "Farshad, F. F., and H. H. Rieke. 'Surface Roughness Design Values for Modern Pipes.' SPE "
    "Drilling & Completion 21, no. 3 (2006): 212-215. doi:10.2118/89040-PA"
)

# (id, name, notes, schedules, dimensions citation, Farshad surface ID)
_MATERIALS: list[tuple[str, str, str, list[str], str, str]] = [
    (
        "carbon_steel",
        "Carbon steel",
        "Roughness: Farshad & Rieke 'Carbon steel, bare', diameter dependent.",
        ["10", "20", "30", "40", "STD", "60", "80", "XS", "100", "120", "140", "160", "XXS"],
        _B36_10M,
        "Carbon steel, bare",
    ),
    (
        "stainless_steel",
        "Stainless steel (13Cr roughness)",
        "Roughness: Farshad & Rieke 'Cr13, bare' (13% chromium steel), the cited stainless "
        "surface available in fluids; diameter dependent.",
        ["5S", "10S", "40S", "80S"],
        _B36_19M,
        "Cr13, bare",
    ),
    (
        "pvc",
        "PVC",
        "Roughness: fluids has no PVC entry; Farshad & Rieke 'Plastic coated' is used as the "
        "closest cited plastic surface; diameter dependent.",
        ["40D1785", "80D1785", "120D1785"],
        _D1785,
        "Plastic coated",
    ),
]


def _nps_label(nps: float) -> str:
    """NPS as fluids tabulates it (a float in inches), printed without trailing zeros."""
    return f"{nps:g}"


def build_pipe_materials() -> dict[str, Any]:
    """Build the pipe materials library from fluids. Deterministic: same fluids, same output."""
    materials: list[dict[str, Any]] = []
    for mat_id, name, notes, schedules, dims_source, surface in _MATERIALS:
        schedule_entries: list[dict[str, Any]] = []
        for schedule in schedules:
            sizes: list[dict[str, Any]] = []
            for nps in schedule_lookup[schedule][0]:
                nps_out, di, do, t = nearest_pipe(NPS=nps, schedule=schedule)
                sizes.append(
                    {
                        "nps": _nps_label(nps_out),
                        "nominalSize": nps_out * inch,
                        "outerDiameter": do,
                        "wallThickness": t,
                        "innerDiameter": di,
                        "roughness": roughness_Farshad(ID=surface, D=di),
                    }
                )
            schedule_entries.append({"id": schedule, "sizes": sizes})
        materials.append(
            {
                "id": mat_id,
                "name": name,
                "notes": notes,
                "roughness": roughness_Farshad(ID=surface),
                "roughnessModel": {"function": "fluids.friction.roughness_Farshad", "ID": surface},
                "roughnessSource": (
                    f"{_FARSHAD}; '{surface}', via {_FLUIDS} fluids.friction.roughness_Farshad "
                    "(per size: evaluated at the inner diameter; material value: the average)"
                ),
                "dimensionsSource": f"{dims_source}; via {_FLUIDS} fluids.piping.nearest_pipe",
                "schedules": schedule_entries,
            }
        )
    return {
        "generatedBy": "apps/api/scripts/generate_pipe_data.py",
        "fluidsVersion": fluids.__version__,
        "units": "m",
        "materials": materials,
    }


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = render(build_pipe_materials())
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT} is stale; run scripts/generate_pipe_data.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
