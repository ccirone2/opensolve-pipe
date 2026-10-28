"""The web's copy of decision 17 (c)'s bound r_max (proposal orifice-plate.md §1.2 and §12) is the
API's: goal seek's default boxes (apps/web/src/lib/utils/orifice-bound.ts) transcribe
``orifice.ratio_range`` and are pinned in the web to the values in
``apps/web/src/lib/testing/orifice-r-max.ts``, which this test reads and checks against the API
now, so a change to the API's bound fails here while the web's copy is stale (D10's pattern for
what the web repeats). The tolerance, 10⁻¹² relative, is the web test's: fixed, far above the
round-off of a closed form and far below the 1 % margin the default boxes keep."""

import math
import re
from pathlib import Path

import pytest
from fluids.constants import g

from opensolve_pipe.services.solver.orifice import ratio_range, re_lo, refusal

WEB_LIB = Path(__file__).parents[3] / "web" / "src" / "lib"
ROWS = WEB_LIB / "testing" / "orifice-r-max.ts"
BOUND = WEB_LIB / "utils" / "orifice-bound.ts"

NUMBER = r"(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)"
ROW = re.compile(rf"\['(corner|flange)', {NUMBER}, {NUMBER}, {NUMBER}\]")


def _rows() -> list[tuple[str, float, float, float]]:
    text = ROWS.read_text(encoding="utf-8")
    rows = [(t, float(d), float(b), float(r)) for t, d, b, r in ROW.findall(text)]
    assert len(rows) == text.count("['corner',") + text.count("['flange',")
    return rows


def test_the_webs_r_max_rows_are_the_apis_ratio_range() -> None:
    rows = _rows()
    assert len(rows) >= 40
    assert {taps for taps, *_ in rows} == {"corner", "flange"}
    for taps, d_pipe, beta, web in rows:
        bore = beta * d_pipe
        # Every plate listed is one the API builds on ISO 5167-2's C, as the web module says.
        assert refusal(d_pipe, bore, None, taps, g) is None, (taps, d_pipe, beta)  # type: ignore[arg-type]
        api = ratio_range(d_pipe, bore, taps, re_lo(beta, d_pipe, "d_and_d_2"))[1]
        assert api == pytest.approx(web, rel=1e-12), (taps, d_pipe, beta)


def test_ratio_bound_any_is_above_every_r_max_the_api_builds_on_isos_c() -> None:
    """RATIO_BOUND_ANY, the web's bound for a plate whose D it does not know, exceeds r_max on
    every plate the API builds on ISO's C at corner or flange taps, D from 0.1 mm to 10 m: β
    bisected to the refusal (decision 17 (b)) with the API's own ``refusal``, and r_max at that β
    and on a grid of β below it."""
    found = re.search(r"export const RATIO_BOUND_ANY = ([0-9.]+);", BOUND.read_text("utf-8"))
    assert found is not None
    bound = float(found.group(1))
    largest = 0.0
    built = 0
    for taps in ("corner", "flange"):
        for k in range(31):
            d_pipe = 1.0e-4 * 10.0 ** (5.0 * k / 30)
            good, bad = 0.02, 1.0
            if refusal(d_pipe, good * d_pipe, None, taps, g) is not None:  # type: ignore[arg-type]
                continue  # no plate on ISO's C at these taps (flange taps on the smallest pipes)
            for _ in range(48):
                mid = 0.5 * (good + bad)
                if refusal(d_pipe, mid * d_pipe, None, taps, g) is None:  # type: ignore[arg-type]
                    good = mid
                else:
                    bad = mid
            for j in range(21):
                beta = 0.02 + (good - 0.02) * j / 20
                assert refusal(d_pipe, beta * d_pipe, None, taps, g) is None  # type: ignore[arg-type]
                low = re_lo(beta, d_pipe, "d_and_d_2")
                r_max = ratio_range(d_pipe, beta * d_pipe, taps, low)[1]
                assert math.isfinite(r_max)
                largest = max(largest, r_max)
            built += 1
    assert built >= 50
    assert 2.0 < largest < bound, (largest, bound)
