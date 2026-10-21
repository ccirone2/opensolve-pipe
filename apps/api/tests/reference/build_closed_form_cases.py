"""Write ``cases/<name>.json`` for every closed-form derivation in ``derivations.py``.

Run from ``apps/api``::

    uv run python -m tests.reference.build_closed_form_cases

``test_derivations_current.py`` fails when a case file no longer matches its derivation.
"""

from tests.reference.case_format import write_case
from tests.reference.derivations import CLOSED_FORM_CASES


def main() -> None:
    for derive in CLOSED_FORM_CASES:
        path = write_case(derive())
        print(f"wrote {path.name}")


if __name__ == "__main__":
    main()
