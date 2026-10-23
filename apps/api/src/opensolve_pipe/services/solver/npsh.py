"""Atmospheric pressure and net positive suction head available (design §8, D4).

p_atm is the project's override if set, else the US Standard Atmosphere 1976 at the site
elevation (``fluids.atmosphere.ATMOSPHERE_1976(Z).P``, Z the geometric elevation above sea
level; NOAA/NASA/USAF 1976).

NPSH available at a pump's suction port (elevation z_s, EGL H_s) is the absolute total head
above the vapor pressure head:

    NPSHa = p_abs/(ρg) + v_s²/(2g) − p_vap/(ρg) = (H_s − z_s) + (p_atm − p_vap)/(ρg)

since H_s − z_s = p/(ρg) + v_s²/(2g) with p the gauge static pressure and p_abs = p + p_atm.
NPSH margin = NPSHa − NPSHr(Q); a negative margin is flagged CAVITATION.
"""

from fluids.atmosphere import ATMOSPHERE_1976

from ...models.project import Project


def atmospheric_pressure(project: Project) -> tuple[float, str]:
    """Absolute atmospheric pressure [Pa] and where it came from (D4)."""
    settings = project.settings
    if settings.atmospheric_pressure is not None:
        return settings.atmospheric_pressure, "user override"
    z = settings.site_elevation
    p = float(ATMOSPHERE_1976(z).P)
    return p, (
        f"US Standard Atmosphere 1976 at the site elevation {z:g} m "
        "(fluids.atmosphere.ATMOSPHERE_1976)"
    )


def npsh_available(
    egl: float,
    elevation: float,
    p_atm: float,
    vapor_pressure: float,
    density: float,
    g: float,
) -> float:
    """NPSHa [m] at a port: (H − z) + (p_atm − p_vap)/(ρg) (module docstring)."""
    return (egl - elevation) + (p_atm - vapor_pressure) / (density * g)
