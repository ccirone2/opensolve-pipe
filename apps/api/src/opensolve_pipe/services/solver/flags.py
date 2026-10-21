"""Physics flags (GOALS §4.6): on by default, attached to the element they concern."""

from ...models.results import Flag, FlagCode, FlagSeverity


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
    return Flag(
        code=code,
        severity=severity,
        message=message,
        component_id=component_id,
        connection_id=connection_id,
        port_id=port_id,
        details=details or {},
    )
