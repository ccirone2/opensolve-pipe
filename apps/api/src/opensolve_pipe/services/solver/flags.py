"""Physics flags (GOALS §4.6): on by default, attached to the element they concern.

Every flag code has one severity (``FLAG_SEVERITY``), so a condition reads the same wherever it
is raised:

- ``invalid``: the result is physically invalid (cavitation, flow reversal through a pump,
  flashing, a reservoir port drawing air, no cited correlation for the solved pattern,
  non-convergence).
- ``warning``: the result is unreliable or incomplete: a correlation used outside its validated
  range, an extrapolated pump curve, transitional flow, a fallback correlation, a section whose
  pressure level nothing fixes (its pressures and NPSH are not computed), a running pump with
  an NPSHr curve whose NPSH available cannot be computed (no vapor pressure), so the cavitation
  check is lost.
- ``info``: a state worth knowing (a closed check valve, a control valve off its setpoint, a
  closed-off section, a fluid without a vapor pressure: a property of the fluid, which only
  matters where a pump's cavitation check needs it, NPSH_NOT_CHECKED).
"""

from ...models.results import Flag, FlagCode, FlagSeverity

FLAG_SEVERITY: dict[FlagCode, FlagSeverity] = {
    "NOT_CONVERGED": "invalid",
    "CAVITATION": "invalid",
    "BELOW_VAPOR_PRESSURE": "invalid",
    "PUMP_FLOW_REVERSAL": "invalid",
    "UNSUPPORTED_FLOW_PATTERN": "invalid",
    "PORT_ABOVE_LIQUID_LEVEL": "invalid",
    "PUMP_OUTSIDE_CURVE": "warning",
    "TRANSITIONAL_FLOW": "warning",
    "CORRELATION_OUT_OF_RANGE": "warning",
    "TEE_PATTERN_FALLBACK": "warning",
    "UNDETERMINED_PRESSURE": "warning",
    "NPSH_NOT_CHECKED": "warning",
    "NO_VAPOR_PRESSURE": "info",
    "CHECK_VALVE_CLOSED": "info",
    "CONTROL_VALVE_SETPOINT_NOT_MET": "info",
    "PUMP_SETPOINT_NOT_MET": "info",
    "ISOLATED_SECTION": "info",
}
"""The severity of every flag code (module docstring)."""


def make_flag(
    code: FlagCode,
    severity: FlagSeverity,
    message: str,
    *,
    component_id: str | None = None,
    connection_id: str | None = None,
    port_id: str | None = None,
    details: dict[str, float | str] | None = None,
) -> Flag:
    """A flag; ``severity`` must be the code's severity in ``FLAG_SEVERITY`` (written out at
    every call site so the severity is visible where the flag is raised)."""
    if FLAG_SEVERITY[code] != severity:
        raise ValueError(f"flag {code} has severity {FLAG_SEVERITY[code]!r}, not {severity!r}")
    return Flag(
        code=code,
        severity=severity,
        message=message,
        component_id=component_id,
        connection_id=connection_id,
        port_id=port_id,
        details=details or {},
    )
