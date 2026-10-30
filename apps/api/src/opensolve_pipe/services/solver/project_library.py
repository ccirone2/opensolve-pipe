"""The project library (CLAUDE.md D22, docs/proposals/project-library.md): pipe specs and
resistance entries the user defines once, each with its source, resolved where the solver
resolves library data today, to exactly the values a user could have typed on each element.

- A pipe of a spec (``specId``) is resolved as the pipe {materialId, innerDiameter, roughness,
  length} it stands for (``spec_pipe``), by ``library.resolve_pipe``: a custom spec gives its
  inner diameter and roughness; a library material without a roughness takes that material's
  Farshad roughness at the spec's inner diameter, as a library pipe with an inner-diameter
  override does (proposal §1.2, P2).
- A resistance entry on an element of reference bore D (a valve's inlet pipe, a fitting's pipe
  ``pipeIndex``): a Cv or Kv converted as one entered on that element
  (``coefficients.k_from_coefficient``, the same fluids call on the same bore); a K stated at d₀
  moved to D, K = K₀ (D/d₀)⁴ (``coefficients.k_at_bore``), exactly K₀ when D = d₀.

The numbers are therefore the hand-typed project's, bit for bit, and nothing in the network
solve changes; the entries add only text: the trace's inputs keep the source "user" and their
notes and data sources name the entry and its source (proposal §4.1), and the methods summary
gains a "Project library" section (§4.2). A reference to an entry the project does not have is
a topology issue (``builder.validate_topology``).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from ...models.components import FlowCoefficient
from ...models.piping import PipeDefinition
from ...models.project import Project
from ...models.project_library import PipeSpec, ResistanceSpec
from .coefficients import k_at_bore, k_from_coefficient

PipeSpecs = Mapping[str, PipeSpec]
"""A project's pipe specs by id."""
ResistanceEntries = Mapping[str, ResistanceSpec]
"""A project's resistance entries by id."""

ENTERED_UNITS = {"K": "", "Cv": "US gpm/psi^0.5", "Kv": "m³/h/bar^0.5"}
"""A coefficient's unit as entered, as a valve's trace writes it ('' for K)."""

LIBRARY_DECISION = (
    "OpenSolve Pipe design decision D22 (CLAUDE.md), from docs/proposals/project-library.md."
)

K_AT_BORE = (
    "K = K₀ (D/d₀)⁴: a K₀ stated at bore d₀ moved to the bore D it is used on, the same head loss "
    "K₀ (Q/A₀)²/(2g) at a given flow (A₀ = π d₀²/4)"
)
"""The conversion of a K entry, as equations and the methods summary state it."""


def pipe_specs(project: Project | None) -> PipeSpecs:
    """The project's pipe specs by id ({} without a project)."""
    return {} if project is None else {s.id: s for s in project.pipe_library}


def resistance_entries(project: Project | None) -> ResistanceEntries:
    """The project's resistance entries by id ({} without a project)."""
    return {} if project is None else {e.id: e for e in project.resistance_library}


def spec_label(spec: PipeSpec) -> str:
    """'project library pipe spec "NPS 60 STD" (PS1)': how texts name a spec."""
    return f'project library pipe spec "{spec.name}" ({spec.id})'


def resistance_label(entry: ResistanceSpec) -> str:
    """'project library resistance "30 in butterfly valve" (RS1)': how texts name an entry."""
    return f'project library resistance "{entry.name}" ({entry.id})'


def provenance(entry: PipeSpec | ResistanceSpec) -> str:
    """The entry and its source, as a trace's note and data source state it (proposal §4.1)."""
    label = spec_label(entry) if isinstance(entry, PipeSpec) else resistance_label(entry)
    return f"{label}: {entry.source}"


def spec_pipe(pipe: PipeDefinition, spec: PipeSpec) -> PipeDefinition:
    """The pipe a spec stands for: its material, inner diameter and roughness (when given), with
    the segment's own length (proposal §3.1). A library material without a roughness takes its
    Farshad roughness at that inner diameter in ``resolve_pipe``."""
    return PipeDefinition(
        material_id=spec.material_id,
        inner_diameter=spec.inner_diameter,
        roughness=spec.roughness,
        length=pipe.length,
    )


def entered_text(entry: ResistanceSpec) -> str:
    """The entry's coefficient as entered: 'Cv 60000', 'K 0.3 at 0.7366 m'."""
    text = f"{entry.kind} {entry.value:.6g}"
    if entry.reference_diameter is not None:
        text += f" at {entry.reference_diameter:.6g} m"
    return text


@dataclass(frozen=True)
class EntryK:
    """A resistance entry on one element: its K on the element's reference bore."""

    entry: ResistanceSpec
    bore: float
    """D, m: the element's reference bore (a valve's inlet pipe, a fitting's pipe pipeIndex)."""
    k: float
    """K on D: K₀ (D/d₀)⁴ for a K, the ISA-75.01.01 conversion for a Cv or Kv (inf where it
    divides by zero or overflows: a topology issue, ``builder``)."""
    how: str
    """How K was obtained, with its numbers."""


def entry_k(entry: ResistanceSpec, d: float) -> EntryK:
    """K of ``entry`` on an element of reference bore ``d`` (module docstring)."""
    if entry.kind == "K":
        assert entry.reference_diameter is not None  # the model requires it for K
        d0 = entry.reference_diameter
        try:
            k = k_at_bore(entry.value, d0, d)
        except OverflowError:
            k = float("inf")
        if d == d0:
            how = f"K = K₀ = {entry.value:.6g}, stated at this bore (D = d₀ = {d:.6g} m)"
        else:
            how = (
                f"K = K₀ (D/d₀)⁴ = {entry.value:.6g} × ({d:.6g} m / {d0:.6g} m)⁴ = {k:.6g}, "
                "the same head loss at a given flow"
            )
        return EntryK(entry, d, k, how)
    try:
        k, how = k_from_coefficient(FlowCoefficient(kind=entry.kind, value=entry.value), d)
    except (ZeroDivisionError, OverflowError):
        k = float("inf")
        how = f"{entry.kind} = {entry.value:g} converted with fluids.fittings.{entry.kind}_to_K"
    return EntryK(entry, d, k, how)
