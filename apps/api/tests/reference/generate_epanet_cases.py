"""EPANET reference cases: looped water networks solved by WNTR's EpanetSimulator (design §11).

Each network is written once, as an OpenSolve Pipe ``Project``; ``project_to_wntr`` converts that
same project into a WNTR ``WaterNetworkModel``, EPANET 2.2 solves it, and the EPANET flows and heads
become the expected values. Run from ``apps/api``::

    uv run python -m tests.reference.generate_epanet_cases

Conversion rules (design §11; facts from research notes coolprop_wntr_epanet.md §B, §C):

- Reservoir → EPANET reservoir with head z + level + p_surface/(ρg) (all its ports share it).
- Ideal tee (lossModel 'ideal') → EPANET junction, zero demand: like EPANET, an ideal tee has
  one head at all three ports.
- Connection → EPANET pipe from the 'from' component's node to the 'to' component's node:
  one custom-material segment (length, inner diameter, roughness — D-W roughness is passed to
  WNTR in metres), and the sum of its 'custom' fittings' K · quantity as the pipe's minor-loss
  coefficient (EPANET's minor loss is K on the same pipe's v²/2g, as ours is).
- Fluid: a custom fluid with EPANET's default viscosity VISCOS = 1.1e-5 ft²/s (types.h:53),
  i.e. 1.1e-5 · 0.3048² m²/s, with the EPANET viscosity option as a multiplier of 1.0. Density is
  1000 kg/m³ and does not affect the comparison: friction depends only on ν = μ/ρ (Re, f), and ρ
  enters a head only through a reservoir's surface pressure p/(ρg), which the conversion computes
  with the same ρ and g as the solver.
- Options: headloss 'D-W'; INP flow units GPM, whose EPANET constant GPMperCFS = 448.831
  (types.h:68) is 3.8e-7 below the exact value (CFS has no constant bias, but WNTR writes curve
  points with six decimals, which costs more in CFS once pump curves appear; research notes
  §B.3.3); accuracy 1e-5 (the INP minimum); headerror 1e-9 and flowchange 1e-12 (EPANET 2.2
  convergence extras). WNTR writes both numbers unconverted and EPANET reads them in the INP's
  units (input1.c:595-596), so they are 1e-9 ft and 1e-12 gpm.
- The project solves in 'swamee_jain' mode, EPANET's friction formula (with its laminar 64/Re
  below Re 2000 and Dunlop's cubic between 2000 and 4000).

- Pump → EPANET pump between two junctions (its suction and discharge ports, at the pump's
  elevation) with a HEAD curve of the same points and the same relative speed. Pump cases use
  collinear curve points, so EPANET's piecewise-linear curve and our PCHIP coincide (design §11).
- PRV / PSV / FCV → EPANET valve of the same type between two junctions (its inlet and outlet
  ports), diameter of the inlet pipe, no minor loss (our control valves default to ideal).
  FCV setting = our flow setpoint. EPANET's PRV/PSV setting is a pressure head without velocity
  head (hset = El + setting, hydstatus.c:74, 79), ours is a static pressure at the port, i.e.
  EGL = z + p_set/(ρg) + v²/(2g) with v in the pipe on that port (design §5.3). The generator
  therefore iterates setting = p_set/(ρg) + v²/(2g), v from the previous EPANET run's flow in that
  pipe (v = 0 to start), until the setting changes by less than 1e-12 m, then keeps that run.

Expected values: the EPANET flow of every connection and, for every port, the EPANET head of its
node (EPANET neglects velocity head, so its head is our EGL, design §1.1); the EPANET status of
every pump ('running') and valve ('active', 'open' or 'closed'); and the warning flags the
pipes' friction regimes call for at the EPANET flows (TRANSITIONAL_FLOW, ``regime_flags``).

Flow-controlled pumps (CLAUDE.md D11; proposal docs/proposals/vfd-pump-modes.md §7.2). EPANET
2.2 has no flow-controlled pump, so each case states the EPANET run that stands for the state
the proposal's rules select, and checks that this state holds (``PUMP_CONTROL_RUNS``):

- active: the EPANET 2.2 FAQ substitute, "How do I size a pump to meet a specific flow? Set the
  status of the pump to CLOSED. At the suction (inlet) node of the pump add a demand equal to
  the required pump flow and place a negative demand of the same magnitude at the discharge
  node. After analyzing the network, the difference in heads between the two nodes is what the
  pump needs to deliver." (https://usepa.github.io/EPANET2.2/13_questions.html). The speed is
  then the closed-form root of s² H₀(Q_set/s) = H for the straight curve H₀ = a − b x, s* =
  [b Q + √(b² Q² + 4 a H)]/(2a) (``derivations_pump_control.speed_linear``); the generator
  asserts that EPANET run at SPEED = s* passes Q_set within D6. A second case finds the speed
  from EPANET alone: brentq over the relative speed ω ∈ [s_min, s_max] of EPANET runs until the
  pump passes Q_set (EPANET evaluates h = ω² H₀(q/ω), WNTR writes ω as the pump's SPEED).
- max_speed / min_speed: EPANET with the pump OPEN at SPEED = s_max / s_min; the generator
  asserts with the FAQ run at Q_set that the setpoint needs more than F(s_max, Q_set) / less
  than F(s_min, Q_set), and that the flow at the limit is clearly below / above Q_set.
"""

import ctypes
import tempfile
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import wntr
from fluids.friction import fmethods
from scipy.constants import gallon
from scipy.optimize import brentq
from wntr.epanet.toolkit import ENepanet

from opensolve_pipe.models.components import Component, ControlValve, Pump, Reservoir, TeeBranch
from opensolve_pipe.models.fluids import CustomFluid
from opensolve_pipe.models.piping import CUSTOM_MATERIAL_ID, PipeConnection
from opensolve_pipe.models.project import Project
from opensolve_pipe.models.pumps import PumpCurve
from tests.reference import element_laws as el
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    connect,
    control_valve,
    custom_fluid,
    custom_pipe,
    fitting,
    flow_control,
    ideal_tee,
    make_project,
    pump,
    pump_curve,
    reservoir,
    write_case,
)
from tests.reference.derivations import RE_LAMINAR, RE_TURBULENT, G, area, regime, reynolds
from tests.reference.derivations_pump_control import collinear_coefficients, speed_linear
from tests.reference.network_check import EPANET_FCV_LEAK

FOOT = 0.3048
"""m per international foot (exact; EPANET's MperFT, types.h:79)."""
EPANET_VISCOS_FT2_S = 1.1e-5
"""EPANET's default kinematic viscosity of water, ft²/s (VISCOS, types.h:53)."""
NU_EPANET = EPANET_VISCOS_FT2_S * FOOT**2
"""The same viscosity in m²/s (1.02193344e-6)."""
EPANET_FLUID_DENSITY = 1000.0
"""kg/m³; the comparison does not depend on it (see the module docstring)."""
EPANET_GPM_PER_CFS = 448.831
"""EPANET's flow-unit constant GPMperCFS (types.h:68); the exact value is ft³/(gallon/60)."""
GPM_PER_CFS_BIAS = EPANET_GPM_PER_CFS / (FOOT**3 / (gallon / 60.0)) - 1.0
"""Relative flow bias of EPANET's GPM constant (about −3.8e-7); gallon = US gallon, exact."""


def _epanet_version() -> str:
    """EPANET toolkit version of the library WNTR loads, from EN_getversion (e.g. 20200)."""
    version = ctypes.c_int()
    ENepanet(version=2.2).ENlib.EN_getversion(ctypes.byref(version))
    v = version.value
    return f"{v // 10000}.{(v // 100) % 100}.{v % 100}"


SETTING_TOLERANCE = 1.0e-12
"""m; the PRV/PSV setting iteration stops when the setting changes by less than this."""
MAX_SETTING_ITERATIONS = 50


def source_text(project: Project | None = None) -> str:
    extra = ""
    if project is not None:
        types = {c.type for c in project.components}
        controlled = any(isinstance(c, Pump) and c.control is not None for c in project.components)
        if "pump" in types and not controlled:
            extra += (
                " Pumps: EPANET HEAD curve through the same collinear points (EPANET's "
                "piecewise-linear curve then equals our PCHIP) at the same relative speed."
            )
        elif controlled:
            extra += (
                " Pumps: EPANET HEAD curve through the same collinear points (EPANET's "
                "piecewise-linear curve then equals our PCHIP), run as stated below."
            )
        if any(isinstance(c, ControlValve) and c.valve_type != "fcv" for c in project.components):
            extra += (
                " PRV/PSV: EPANET's setting is a head above the node elevation without velocity "
                "head, ours a static pressure at the valve port, so the generator iterates "
                "setting = p_set/(rho g) + v^2/(2g) with v from the previous EPANET run in the "
                "pipe on that port until the setting changes by < 1e-12 m."
            )
        if any(isinstance(c, ControlValve) and c.valve_type == "fcv" for c in project.components):
            extra += (
                " FCV: EPANET flow setting = our flow setpoint; an active EPANET FCV keeps a "
                "1/CBIG conductance (CBIG = 1e8, hydcoeffs.c:35, fcvcoeff) and settles at "
                "q_set + dh/CBIG in ft and cfs (newflows, hydsolver.c:431), about 1e-6 "
                "relative here."
            )
    return (
        f"WNTR {wntr.__version__} EpanetSimulator (EPANET {_epanet_version()}); see "
        "tests/reference/generate_epanet_cases.py. D-W headloss, GPM INP units, accuracy 1e-5, "
        "headerror 1e-9 ft and flowchange 1e-12 gpm (EPANET reads both in the INP units, "
        "input1.c:595-596; WNTR writes them unconverted); viscosity VISCOS = 1.1e-5 ft2/s = "
        "1.02193344e-6 m2/s (the project's custom fluid has the same nu; its density, 1000 "
        "kg/m3, does not affect the comparison because friction depends only on nu and a "
        "surface-pressure head p/(rho g) is converted with the same rho and g on both sides); "
        "solver run in 'swamee_jain' mode. Known EPANET biases, all far inside the 0.5% "
        "criterion: EPANET's "
        "head-loss coefficients use g = 32.2 ft/s2 = 9.81456 m/s2 against our 9.80665 (0.08% "
        "in head loss), its minor-loss constant is 0.02517 against the exact 1/(2g(pi/4)^2) = "
        "0.0251730 in US units (0.012%), its GPM flow-unit constant GPMperCFS = 448.831 "
        f"differs from the exact ft3/(gal/60) by {GPM_PER_CFS_BIAS:.2g} (relative, in flow), "
        "and its results are float32 (about 1e-7 relative)." + extra
    )


# --- Networks ----------------------------------------------------------------------------------


def looped_network_a() -> Project:
    """Two loops, three reservoirs (heads 14, 9 and 0.5 m), five ideal tees, nine pipes.

    Loops: TA-TB-TC (P2, P4, P3) and TB-TD-TE-TC (P5, P7, P6, P4). P4 and P8 are drawn against
    the flow, so their expected flows are negative. P3 carries custom minor losses
    (K 4.0 + 2 × 0.9 = 5.8). All pipe data are test inputs.
    """
    fluid = custom_fluid(
        "Water at EPANET's default viscosity",
        EPANET_FLUID_DENSITY,
        NU_EPANET * EPANET_FLUID_DENSITY,
    )
    components: list[Component] = [
        reservoir("RA", 10.0, 4.0),
        reservoir("RB", 6.0, 3.0),
        reservoir("RC", -1.5, 2.0),
        ideal_tee("TA", 4.0),
        ideal_tee("TB", 3.0),
        ideal_tee("TC", 2.5),
        ideal_tee("TD", 1.0),
        ideal_tee("TE", 0.0),
    ]
    connections = [
        connect("P1", "RA:port_1", "TA:run_inlet", [custom_pipe(0.2027, 400.0, 4.5e-5)]),
        connect("P2", "TA:run_outlet", "TB:run_inlet", [custom_pipe(0.1541, 350.0, 1.5e-4)]),
        connect(
            "P3",
            "TA:branch",
            "TC:run_inlet",
            [custom_pipe(0.1023, 500.0, 4.5e-5)],
            [fitting("custom", k_override=4.0), fitting("custom", quantity=2, k_override=0.9)],
        ),
        connect("P4", "TC:branch", "TB:branch", [custom_pipe(0.0779, 300.0, 1.0e-5)]),
        connect("P5", "TB:run_outlet", "TD:run_inlet", [custom_pipe(0.1023, 450.0, 2.6e-4)]),
        connect("P6", "TC:run_outlet", "TE:branch", [custom_pipe(0.1023, 380.0, 4.5e-5)]),
        connect("P7", "TD:run_outlet", "TE:run_inlet", [custom_pipe(0.1541, 200.0, 4.5e-5)]),
        connect("P8", "TD:branch", "RB:port_1", [custom_pipe(0.0779, 250.0, 4.5e-5)]),
        connect("P9", "TE:run_outlet", "RC:port_1", [custom_pipe(0.1541, 150.0, 4.5e-5)]),
    ]
    return make_project(
        "ref-epanet-looped-a",
        "Looped network A (EPANET reference)",
        fluid,
        components,
        connections,
        friction_method="swamee_jain",
    )


def looped_network_b() -> Project:
    """Three loops, four reservoirs (S1 with two ports), seven ideal tees, thirteen pipes.

    Loops: S1-J1-J2-S1 (through S1's two ports), J1-J2-J4-J3 and J3-J4-J6-J5. The small pipes
    Q3 and Q9 run in the transition zone (Re about 2900) and in laminar flow (Re about 1050), so
    all three friction regimes appear. Q6 is drawn against the flow. S4 has a surface pressure.
    Minor losses on Q1 and Q12. All pipe data are test inputs.
    """
    fluid = custom_fluid(
        "Water at EPANET's default viscosity",
        EPANET_FLUID_DENSITY,
        NU_EPANET * EPANET_FLUID_DENSITY,
    )
    components: list[Component] = [
        reservoir("S1", 8.0, 4.0, ports=("port_1", "port_2")),
        reservoir("S2", 2.0, 3.0),
        reservoir("S3", -2.0, 2.0),
        reservoir("S4", 0.0, 1.0, surface_pressure=2.0e4),
        ideal_tee("J1", 3.0),
        ideal_tee("J2", 3.0),
        ideal_tee("J3", 2.0),
        ideal_tee("J4", 2.0),
        ideal_tee("J5", 1.0),
        ideal_tee("J6", 1.0),
        ideal_tee("J7", 0.0),
    ]
    connections = [
        connect(
            "Q1",
            "S1:port_1",
            "J1:run_inlet",
            [custom_pipe(0.1541, 120.0, 4.5e-5)],
            [fitting("custom", k_override=1.5)],
        ),
        connect("Q2", "S1:port_2", "J2:run_inlet", [custom_pipe(0.1023, 150.0, 4.5e-5)]),
        connect("Q3", "J1:branch", "J2:branch", [custom_pipe(0.0158, 200.0, 4.5e-5)]),
        connect("Q4", "J1:run_outlet", "J3:run_inlet", [custom_pipe(0.1023, 300.0, 1.5e-4)]),
        connect("Q5", "J2:run_outlet", "J4:run_inlet", [custom_pipe(0.1023, 250.0, 4.5e-5)]),
        connect("Q6", "J4:branch", "J3:branch", [custom_pipe(0.0779, 200.0, 4.5e-5)]),
        connect("Q7", "J3:run_outlet", "J5:run_inlet", [custom_pipe(0.0779, 350.0, 4.5e-5)]),
        connect("Q8", "J4:run_outlet", "J6:run_inlet", [custom_pipe(0.1023, 300.0, 2.6e-4)]),
        connect("Q9", "J5:branch", "J6:branch", [custom_pipe(0.0092, 500.0, 1.5e-6)]),
        connect("Q10", "J5:run_outlet", "S2:port_1", [custom_pipe(0.0627, 180.0, 4.5e-5)]),
        connect("Q11", "J6:run_outlet", "J7:run_inlet", [custom_pipe(0.1023, 200.0, 4.5e-5)]),
        connect(
            "Q12",
            "J7:run_outlet",
            "S3:port_1",
            [custom_pipe(0.0779, 160.0, 4.5e-5)],
            [fitting("custom", k_override=3.0), fitting("custom", quantity=2, k_override=0.5)],
        ),
        connect("Q13", "J7:branch", "S4:port_1", [custom_pipe(0.0627, 140.0, 1.0e-5)]),
    ]
    return make_project(
        "ref-epanet-looped-b",
        "Looped network B (EPANET reference)",
        fluid,
        components,
        connections,
        friction_method="swamee_jain",
    )


def _water() -> CustomFluid:
    """Water at EPANET's viscosity (see the module docstring)."""
    return custom_fluid(
        "Water at EPANET's default viscosity",
        EPANET_FLUID_DENSITY,
        NU_EPANET * EPANET_FLUID_DENSITY,
    )


def _pipe(cid: str, a: str, b: str, d: float, length: float, eps: float = 4.5e-5) -> PipeConnection:
    return connect(cid, a, b, [custom_pipe(d, length, eps)])


def pump_network(
    speed: float = 0.9,
    control: tuple[float, float] | None = None,
    pid: str = "ref-epanet-pump-network",
    name: str = "Pump into a looped network (EPANET reference)",
) -> Project:
    """A pump at speed ratio 0.9 lifting from S1 (head 5 m) into a loop TA-TB-TC that feeds two
    reservoirs at heads 30 and 25 m. Curve (test input): four collinear points H = 50 − 300 Q,
    so EPANET's piecewise-linear curve and our PCHIP are the same line (design §11).
    ``control``: (Q_set, s_min) of a flow control, with ``speed`` its maximum speed."""
    curve = pump_curve("PC-LIN", [(0.0, 50.0), (0.02, 44.0), (0.04, 38.0), (0.06, 32.0)])
    components: list[Component] = [
        reservoir("S1", 2.0, 3.0),
        pump(
            "PU",
            1.0,
            curve.id,
            speed=speed,
            control=None if control is None else flow_control(*control),
        ),
        ideal_tee("TA", 3.0),
        ideal_tee("TB", 6.0),
        ideal_tee("TC", 4.0),
        reservoir("S2", 26.0, 4.0),
        reservoir("S3", 22.0, 3.0),
    ]
    connections = [
        _pipe("P1", "S1:port_1", "PU:suction", 0.2027, 20.0),
        _pipe("P2", "PU:discharge", "TA:run_inlet", 0.1541, 300.0),
        _pipe("P3", "TA:run_outlet", "TB:run_inlet", 0.1023, 400.0),
        _pipe("P4", "TA:branch", "TC:run_inlet", 0.1023, 350.0, 1.5e-4),
        _pipe("P5", "TB:branch", "TC:branch", 0.0779, 300.0),
        _pipe("P6", "TB:run_outlet", "S2:port_1", 0.1023, 250.0),
        _pipe("P7", "TC:run_outlet", "S3:port_1", 0.1023, 200.0),
    ]
    return make_project(
        pid,
        name,
        _water(),
        components,
        connections,
        friction_method="swamee_jain",
        pump_library=[curve],
    )


# The flow-controlled variants of pump_network (test inputs: Q_set m³/s, s_min, s_max).
E1_CONTROL = (0.018, 0.6, 0.9)
"""E1/E1b: Q_set between the flows at s_min and s_max, so the pump regulates."""
E2_CONTROL = (0.025, 0.6, 0.9)
"""E2: Q_set above the flow at s_max (about 0.021 m³/s), so the pump runs at s_max."""
E3_CONTROL = (0.014, 0.85, 0.95)
"""E3: Q_set below the flow at s_min (about 0.0176 m³/s), so the pump runs at s_min."""


def _controlled_pump_network(control: tuple[float, float, float], pid: str, name: str) -> Project:
    q_set, s_min, s_max = control
    return pump_network(s_max, (q_set, s_min), pid, name)


def pump_flow_control_network() -> Project:
    """E1: pump_network with the pump flow-controlled, Q_set = 0.018 m³/s, s ∈ [0.6, 0.9]."""
    return _controlled_pump_network(
        E1_CONTROL,
        "ref-epanet-pump-flow-control",
        "Flow-controlled pump into a looped network (EPANET reference)",
    )


def pump_flow_control_speed_network() -> Project:
    """E1b: the E1 network, its speed found from EPANET runs alone."""
    return _controlled_pump_network(
        E1_CONTROL,
        "ref-epanet-pump-flow-control-speed",
        "Flow-controlled pump, speed by EPANET runs (EPANET reference)",
    )


def pump_flow_control_max_network() -> Project:
    """E2: Q_set = 0.025 m³/s, s ∈ [0.6, 0.9]: unreachable at s_max."""
    return _controlled_pump_network(
        E2_CONTROL,
        "ref-epanet-pump-flow-control-max",
        "Flow-controlled pump at maximum speed (EPANET reference)",
    )


def pump_flow_control_min_network() -> Project:
    """E3: Q_set = 0.014 m³/s, s ∈ [0.85, 0.95]: exceeded at s_min."""
    return _controlled_pump_network(
        E3_CONTROL,
        "ref-epanet-pump-flow-control-min",
        "Flow-controlled pump at minimum speed (EPANET reference)",
    )


def prv_network() -> Project:
    """S1 (head 70 m) feeds a high zone (S2, head 50 m) and, through a PRV at 15 m holding
    200 kPa static at its outlet, a looped low zone (TB-TC) draining to S3 (head 10 m)."""
    components: list[Component] = [
        reservoir("S1", 60.0, 10.0),
        ideal_tee("TA", 30.0),
        reservoir("S2", 45.0, 5.0),
        control_valve("PRV1", 15.0, "prv", 200000.0),
        ideal_tee("TB", 12.0),
        ideal_tee("TC", 8.0),
        reservoir("S3", 5.0, 5.0),
    ]
    connections = [
        _pipe("P1", "S1:port_1", "TA:run_inlet", 0.2027, 500.0),
        _pipe("P2", "TA:run_outlet", "S2:port_1", 0.1541, 400.0),
        _pipe("P3", "TA:branch", "PRV1:inlet", 0.1023, 200.0),
        _pipe("P4", "PRV1:outlet", "TB:run_inlet", 0.1023, 150.0),
        _pipe("P5", "TB:run_outlet", "TC:run_inlet", 0.1023, 300.0),
        _pipe("P6", "TB:branch", "TC:branch", 0.0779, 250.0),
        _pipe("P7", "TC:run_outlet", "S3:port_1", 0.1023, 200.0),
    ]
    return make_project(
        "ref-epanet-prv-network",
        "PRV feeding a looped zone (EPANET reference)",
        _water(),
        components,
        connections,
        friction_method="swamee_jain",
    )


def psv_network() -> Project:
    """S1 (head 60 m) supplies a looped main TA-TB to a zone tank S2 (head 35 m); a PSV at
    10 m, set to 250 kPa static at its inlet, releases the surplus to S3 (head 2 m) while
    sustaining the main's pressure."""
    components: list[Component] = [
        reservoir("S1", 50.0, 10.0),
        ideal_tee("TA", 20.0),
        ideal_tee("TB", 18.0),
        ideal_tee("TC", 12.0),
        reservoir("S2", 30.0, 5.0),
        control_valve("PSV1", 10.0, "psv", 250000.0),
        reservoir("S3", 0.0, 2.0),
    ]
    connections = [
        _pipe("P1", "S1:port_1", "TA:run_inlet", 0.1541, 600.0),
        _pipe("P2", "TA:run_outlet", "TB:run_inlet", 0.1023, 300.0),
        _pipe("P3", "TA:branch", "TB:branch", 0.0779, 300.0),
        _pipe("P4", "TB:run_outlet", "TC:run_inlet", 0.1541, 200.0),
        _pipe("P5", "TC:run_outlet", "S2:port_1", 0.1023, 200.0),
        _pipe("P6", "TC:branch", "PSV1:inlet", 0.1023, 100.0),
        _pipe("P7", "PSV1:outlet", "S3:port_1", 0.1023, 150.0),
    ]
    return make_project(
        "ref-epanet-psv-network",
        "PSV sustaining a main's pressure (EPANET reference)",
        _water(),
        components,
        connections,
        friction_method="swamee_jain",
    )


def fcv_network() -> Project:
    """S1 (head 50 m) → TA; an FCV path (TA → FCV1 at 5 m, 15 L/s → TB) beside a bypass pipe
    (TA:branch → TB:branch) forms a loop; TB → TC feeds S2 (head 10 m) and S3 (head 15 m)."""
    components: list[Component] = [
        reservoir("S1", 40.0, 10.0),
        ideal_tee("TA", 8.0),
        control_valve("FCV1", 5.0, "fcv", 0.015),
        ideal_tee("TB", 4.0),
        ideal_tee("TC", 2.0),
        reservoir("S2", 6.0, 4.0),
        reservoir("S3", 12.0, 3.0),
    ]
    connections = [
        _pipe("P1", "S1:port_1", "TA:run_inlet", 0.1541, 300.0),
        _pipe("P2", "TA:run_outlet", "FCV1:inlet", 0.1023, 100.0),
        _pipe("P3", "FCV1:outlet", "TB:run_inlet", 0.1023, 100.0),
        _pipe("P4", "TA:branch", "TB:branch", 0.0779, 400.0),
        _pipe("P5", "TB:run_outlet", "TC:run_inlet", 0.1541, 300.0),
        _pipe("P6", "TC:run_outlet", "S2:port_1", 0.1023, 200.0),
        _pipe("P7", "TC:branch", "S3:port_1", 0.0779, 250.0),
    ]
    return make_project(
        "ref-epanet-fcv-network",
        "FCV beside a bypass (EPANET reference)",
        _water(),
        components,
        connections,
        friction_method="swamee_jain",
    )


EPANET_NETWORKS = {
    "epanet_looped_network_a": (
        looped_network_a,
        "Looped water network with two loops and three reservoirs at different heads, five ideal "
        "tees and nine pipes of mixed diameter, length and roughness, one with minor losses: "
        "verifies the network solution (flow split, EGL at every tee) against EPANET 2.2.",
    ),
    "epanet_looped_network_b": (
        looped_network_b,
        "Looped water network with three loops (one through a two-port reservoir), four "
        "reservoirs (one pressurized), seven ideal tees and thirteen pipes spanning laminar, "
        "transitional and turbulent flow, with minor losses: verifies the network solution and "
        "the laminar/Dunlop/Swamee-Jain friction regimes against EPANET 2.2.",
    ),
    "epanet_pump_network": (
        pump_network,
        "A pump at 90% speed (collinear four-point curve) lifting into a looped network that "
        "feeds two reservoirs: verifies the pump operating point, the affinity-law speed "
        "scaling and the network solution against EPANET 2.2.",
    ),
    "epanet_prv_network": (
        prv_network,
        "A PRV holding 200 kPa static pressure at its outlet feeds a looped low-pressure zone "
        "beside a high zone: verifies the active PRV (static-pressure setpoint converted to "
        "EPANET's head setting) within a network against EPANET 2.2.",
    ),
    "epanet_psv_network": (
        psv_network,
        "A PSV sustaining 250 kPa static pressure at its inlet on a looped main that also feeds "
        "a zone tank: verifies the active PSV within a network against EPANET 2.2.",
    ),
    "epanet_fcv_network": (
        fcv_network,
        "An FCV limiting one path of a loop to 15 L/s while a bypass carries the rest: "
        "verifies the active FCV within a network against EPANET 2.2.",
    ),
    "epanet_pump_flow_control": (
        pump_flow_control_network,
        "The pump network with its pump flow-controlled at 18 L/s within speeds 0.6 to 0.9: "
        "verifies the setpoint imposed as the pump's flow (EPANET 2.2's FAQ substitute: pump "
        "closed, a demand pair at its ports) and the speed recovered from the head across it.",
    ),
    "epanet_pump_flow_control_speed": (
        pump_flow_control_speed_network,
        "The same flow-controlled pump network, its reference speed found from EPANET alone "
        "(the relative speed at which EPANET's pump passes 18 L/s, by brentq): an independent "
        "reference for the solved speed.",
    ),
    "epanet_pump_flow_control_max": (
        pump_flow_control_max_network,
        "The pump network with a flow setpoint of 25 L/s the pump cannot reach at its maximum "
        "speed 0.9: verifies that it runs as EPANET's pump at that speed, below its setpoint.",
    ),
    "epanet_pump_flow_control_min": (
        pump_flow_control_min_network,
        "The pump network with a flow setpoint of 14 L/s that the pump exceeds even at its "
        "minimum speed 0.85: verifies that it runs as EPANET's pump at that speed, above its "
        "setpoint.",
    ),
}


# --- Conversion and run ------------------------------------------------------------------------


def _node_names(project: Project) -> dict[str, str]:
    """EPANET node for every "componentId:portId": one per reservoir and ideal tee (all its
    ports share it), one junction per port of a pump or control valve."""
    names: dict[str, str] = {}
    for component in project.components:
        if isinstance(component, Reservoir) or (
            isinstance(component, TeeBranch) and component.loss_model == "ideal"
        ):
            for port in component.ports:
                names[f"{component.id}:{port.id}"] = component.id
        elif isinstance(component, Pump | ControlValve):
            for port in component.ports:
                names[f"{component.id}:{port.id}"] = f"{component.id}_{port.id}"
        else:
            raise ValueError(f"no EPANET equivalent for component {component.id}")
    return names


def _port_pipe(project: Project, key: str) -> tuple[PipeConnection, float]:
    """The connection on a port and the inner diameter of its end segment at that port."""
    for c in project.connections:
        if f"{c.from_component_id}:{c.from_port_id}" == key:
            d = c.piping.pipes[0].inner_diameter
        elif f"{c.to_component_id}:{c.to_port_id}" == key:
            d = c.piping.pipes[-1].inner_diameter
        else:
            continue
        assert d is not None
        return c, d
    raise KeyError(key)


@dataclass(frozen=True)
class PumpRun:
    """How EPANET runs one pump: OPEN at relative speed ``speed`` (SPEED), or, with
    ``fixed_flow``, the EPANET 2.2 FAQ substitute for a pump delivering that flow: the pump
    CLOSED, a demand of the flow at its suction node and its negative at its discharge node."""

    speed: float | None = None
    fixed_flow: float | None = None


def project_to_wntr(
    project: Project,
    settings: Mapping[str, float] | None = None,
    pump_runs: Mapping[str, PumpRun] | None = None,
) -> wntr.network.WaterNetworkModel:
    """Build the WNTR model of a project as design §11 prescribes (see the module docstring).
    ``settings``: EPANET head setting (m) per PRV/PSV id, from the setting iteration.
    ``pump_runs``: how EPANET runs each flow-controlled pump (required for those)."""
    pump_runs = pump_runs or {}
    demands: dict[str, float] = {}
    for component in project.components:
        if isinstance(component, Pump) and component.control is not None:
            if component.id not in pump_runs:
                raise ValueError(f"{component.id}: a flow-controlled pump needs an EPANET run")
            q = pump_runs[component.id].fixed_flow
            if q is not None:
                demands[f"{component.id}_suction"] = q
                demands[f"{component.id}_discharge"] = -q
    fluid = project.fluid
    if fluid.kind != "custom":
        raise ValueError("EPANET cases use a custom fluid with EPANET's viscosity")
    rho = fluid.density
    if abs(fluid.dynamic_viscosity / rho / NU_EPANET - 1.0) > 1.0e-12:
        raise ValueError("the fluid's kinematic viscosity must equal EPANET's VISCOS")
    if project.settings.solver_options.friction_method != "swamee_jain":
        raise ValueError("EPANET cases run the solver in 'swamee_jain' mode")

    wn = wntr.network.WaterNetworkModel()
    options = wn.options.hydraulic
    with warnings.catch_warnings():
        # WNTR warns that changing H-W to D-W does not convert roughness; ours is in metres.
        warnings.simplefilter("ignore", UserWarning)
        options.headloss = "D-W"
    options.inpfile_units = "GPM"
    options.accuracy = 1.0e-5
    options.headerror = 1.0e-9
    options.flowchange = 1.0e-12
    options.viscosity = 1.0
    options.specific_gravity = 1.0
    wn.options.time.duration = 0

    for component in project.components:
        if isinstance(component, Reservoir):
            head = (
                component.elevation
                + component.liquid_level
                + component.surface_pressure / (rho * G)
            )
            wn.add_reservoir(component.id, base_head=head)
        elif isinstance(component, TeeBranch):
            wn.add_junction(component.id, base_demand=0.0, elevation=component.elevation)
        elif isinstance(component, Pump | ControlValve):
            for port in component.ports:
                z = component.elevation if port.elevation is None else port.elevation
                junction = f"{component.id}_{port.id}"
                wn.add_junction(junction, base_demand=demands.get(junction, 0.0), elevation=z)
    nodes = _node_names(project)

    curves = {curve.id: curve for curve in project.pump_library}
    for component in project.components:
        if isinstance(component, Pump):
            curve = curves[component.curve_id]
            run = pump_runs.get(component.id, PumpRun())
            closed = component.status != "on" or run.fixed_flow is not None
            if curve.id not in wn.curve_name_list:
                wn.add_curve(curve.id, "HEAD", [(p.flow, p.head) for p in curve.points])
            wn.add_pump(
                component.id,
                nodes[f"{component.id}:suction"],
                nodes[f"{component.id}:discharge"],
                pump_type="HEAD",
                pump_parameter=curve.id,
                speed=component.speed if run.speed is None else run.speed,
                initial_status="CLOSED" if closed else "OPEN",
            )
        elif isinstance(component, ControlValve):
            if component.resistance is not None or component.status != "active":
                raise ValueError(f"{component.id}: EPANET cases use ideal, active valves")
            _, d_in = _port_pipe(project, f"{component.id}:inlet")
            if component.valve_type == "fcv":
                setting = component.setpoint
            else:
                setting = (settings or {}).get(component.id, component.setpoint / (rho * G))
            wn.add_valve(
                component.id,
                nodes[f"{component.id}:inlet"],
                nodes[f"{component.id}:outlet"],
                diameter=d_in,
                valve_type=component.valve_type.upper(),
                minor_loss=0.0,
                initial_setting=setting,
            )

    for connection in project.connections:
        pipes = connection.piping.pipes
        if len(pipes) != 1 or pipes[0].material_id != CUSTOM_MATERIAL_ID:
            raise ValueError(f"{connection.id}: EPANET cases use one custom pipe segment")
        pipe = pipes[0]
        if pipe.inner_diameter is None or pipe.roughness is None:
            raise ValueError(f"{connection.id}: a custom pipe needs innerDiameter and roughness")
        minor_loss = 0.0
        for item in connection.piping.fittings:
            if item.type != "custom" or item.k_override is None:
                raise ValueError(f"{connection.id}: only 'custom' fittings map to EPANET")
            minor_loss += item.k_override * item.quantity
        wn.add_pipe(
            connection.id,
            nodes[f"{connection.from_component_id}:{connection.from_port_id}"],
            nodes[f"{connection.to_component_id}:{connection.to_port_id}"],
            length=pipe.length,
            diameter=pipe.inner_diameter,
            roughness=pipe.roughness,
            minor_loss=minor_loss,
        )
    return wn


EpanetRun = tuple[dict[str, float], dict[str, float], dict[str, int]]
"""(flow per connection, EPANET head per port key, EPANET status per pump and valve)."""


def run_epanet(
    project: Project,
    settings: Mapping[str, float] | None = None,
    pump_runs: Mapping[str, PumpRun] | None = None,
) -> EpanetRun:
    """Solve with EPANET; return flows, heads and pump/valve statuses (0 closed, 1 open,
    2 active, as WNTR reports them)."""
    wn = project_to_wntr(project, settings, pump_runs)
    with tempfile.TemporaryDirectory() as tmp:
        simulator = wntr.sim.EpanetSimulator(wn)
        results = simulator.run_sim(file_prefix=str(Path(tmp) / "case"), convergence_error=True)
    flow_table = results.link["flowrate"]
    head_table = results.node["head"]
    status_table = results.link["status"]
    # float() of a float32 is exact, so the JSON holds EPANET's values unchanged.
    flows = {c.id: float(flow_table.loc[0, c.id]) for c in project.connections}
    heads = {key: float(head_table.loc[0, node]) for key, node in _node_names(project).items()}
    statuses = {
        c.id: int(status_table.loc[0, c.id])
        for c in project.components
        if isinstance(c, Pump | ControlValve)
    }
    return flows, heads, statuses


def _setting_heads(project: Project, flows: Mapping[str, float]) -> dict[str, float]:
    """EPANET head setting of every PRV/PSV for the given flows: p_set/(ρg) + v²/(2g), v in the
    pipe on the outlet (PRV) or inlet (PSV) port (design §5.3, §12)."""
    fluid = project.fluid
    assert fluid.kind == "custom"
    out = {}
    for c in project.components:
        if isinstance(c, ControlValve) and c.valve_type in ("prv", "psv"):
            port = "outlet" if c.valve_type == "prv" else "inlet"
            connection, d = _port_pipe(project, f"{c.id}:{port}")
            v = flows[connection.id] / area(d)
            out[c.id] = c.setpoint / (fluid.density * G) + v * v / (2.0 * G)
    return out


def run_with_settings(project: Project) -> EpanetRun:
    """Run EPANET, iterating the PRV/PSV head settings to our static-pressure setpoints."""
    settings = _setting_heads(project, {c.id: 0.0 for c in project.connections})
    run = run_epanet(project, settings)
    for _ in range(MAX_SETTING_ITERATIONS):
        new = _setting_heads(project, run[0])
        if all(abs(new[k] - settings[k]) < SETTING_TOLERANCE for k in settings):
            return run
        settings = new
        run = run_epanet(project, settings)
    raise RuntimeError("the PRV/PSV setting iteration did not converge")


PUMP_STATUS = {1: "running"}
VALVE_STATE = {0: "closed", 1: "open", 2: "active"}
REGIME_MARGIN = 0.01
"""Every pipe's Reynolds number must clear the regime bounds (2000, 4000, and Swamee–Jain's
5000) by this fraction, so that EPANET's flows and ours put each pipe in the same regime."""


def regime_flags(project: Project, flows: Mapping[str, float]) -> list[dict[str, str]]:
    """The warning flags the friction regimes call for (design §2.1), from each pipe's
    Reynolds number at the EPANET flow: TRANSITIONAL_FLOW for 2000 <= Re < 4000. A turbulent
    pipe outside Swamee & Jain's documented range (fluids.friction.fmethods
    'Swamee_Jain_1976': 5e3 <= Re <= 1e8, 1e-6 <= ε/D <= 5e-2), or a Reynolds number near a
    bound, is not allowed in an EPANET case (ValueError)."""
    bounds = fmethods["Swamee_Jain_1976"]
    if any(b is None for b in bounds):
        raise ValueError("fluids documents no complete Swamee-Jain range")
    re_lo, re_hi, ed_lo, ed_hi = (float(b) for b in bounds if b is not None)
    nu = NU_EPANET
    out = []
    for c in project.connections:
        pipe = c.piping.pipes[0]
        assert pipe.inner_diameter is not None
        assert pipe.roughness is not None
        re = reynolds(flows[c.id], pipe.inner_diameter, nu)
        for bound in (RE_LAMINAR, RE_TURBULENT, re_lo):
            if abs(re - bound) <= REGIME_MARGIN * bound:
                raise ValueError(f"{c.id}: Re = {re:.1f} is too close to {bound:g}")
        kind = regime(re)
        if kind == "transitional":
            out.append({"code": "TRANSITIONAL_FLOW", "connectionId": c.id})
        if kind != "laminar" and not ed_lo <= pipe.roughness / pipe.inner_diameter <= ed_hi:
            raise ValueError(f"{c.id}: ε/D outside the Swamee-Jain range")
        if kind == "turbulent" and not re_lo <= re <= re_hi:
            raise ValueError(f"{c.id}: Re = {re:.1f} outside the Swamee-Jain range")
    return out


# --- Flow-controlled pumps (module docstring) ----------------------------------------------------

D6_RELATIVE = 0.005
"""The D6 flow criterion (CLAUDE.md D6) the EPANET run at the solved speed must meet."""
SPEED_XTOL = 1.0e-9
"""Absolute tolerance of the brentq over EPANET's relative speed (E1b); EPANET's float32 flows
resolve the speed to about 1e-8."""
WNTR_SPEED_DIGITS = 11
"""WNTR writes a pump's SPEED with 11 significant digits ('{speed:15.11g}', wntr/epanet/io.py
_write_pumps); the reference speed is rounded the same way, so it is the speed EPANET ran."""


@dataclass(frozen=True)
class ControlRun:
    """The EPANET run standing for a flow-controlled pump's state, and that state's speed."""

    run: EpanetRun
    state: el.ControlState
    speed: float
    method: str


def _only_controlled_pump(project: Project) -> Pump:
    [pu] = [c for c in project.components if isinstance(c, Pump) and c.control is not None]
    return pu


def _pump_flow(project: Project, run: EpanetRun, pid: str) -> float:
    """The pump's flow: the EPANET flow in the pipe on its suction port."""
    connection, _ = _port_pipe(project, f"{pid}:suction")
    sign = 1.0 if connection.to_component_id == pid else -1.0
    return sign * run[0][connection.id]


def _pump_lift(run: EpanetRun, pid: str) -> float:
    return run[1][f"{pid}:discharge"] - run[1][f"{pid}:suction"]


def _faq_run(project: Project, pid: str, q: float) -> EpanetRun:
    """The EPANET 2.2 FAQ substitute: the pump closed, demand +q at suction, −q at discharge."""
    return run_epanet(project, pump_runs={pid: PumpRun(fixed_flow=q)})


def _speed_run(project: Project, pid: str, speed: float) -> EpanetRun:
    return run_epanet(project, pump_runs={pid: PumpRun(speed=speed)})


def _curve(project: Project, pu: Pump) -> PumpCurve:
    return next(c for c in project.pump_library if c.id == pu.curve_id)


def control_active_faq(project: Project) -> ControlRun:
    """E1: the FAQ run at Q_set; s* in closed form from EPANET's head difference; asserts the
    active state is clear by STATE_MARGIN and that EPANET at SPEED = s* passes Q_set (D6)."""
    pu = _only_controlled_pump(project)
    assert pu.control is not None
    q_set = pu.control.setpoint
    curve = _curve(project, pu)
    run = _faq_run(project, pu.id, q_set)
    lift = _pump_lift(run, pu.id)
    if not (
        el.pump_head(curve, pu.control.min_speed, q_set) + el.STATE_MARGIN
        <= lift
        <= el.pump_head(curve, pu.speed, q_set) - el.STATE_MARGIN
    ):
        raise ValueError("the FAQ head must lie clearly inside the speed range's heads")
    # EPANET gives a closed link the conductance 1/CBIG, so the closed pump passes
    # (H_s − H_d)/CBIG in ft and cfs: the suction pipe carries Q_set less that leak.
    leak = EPANET_FCV_LEAK * lift
    q_pipe = _pump_flow(project, run, pu.id)
    if abs(q_set - q_pipe - leak) > 8 * 2.0**-23 * q_set:
        raise RuntimeError(f"suction flow {q_pipe}: not Q_set less the closed-link leak {leak}")
    a, b = collinear_coefficients(curve)
    s_star = speed_linear(a, b, q_set, lift)
    check = _pump_flow(project, _speed_run(project, pu.id, s_star), pu.id)
    if abs(check - q_set) > D6_RELATIVE * q_set:
        raise RuntimeError(f"EPANET at SPEED = s* passes {check}, not {q_set}")
    return ControlRun(
        run,
        "active",
        s_star,
        " Flow-controlled pump (active): EPANET 2.2 FAQ substitute 'How do I size a pump to "
        "meet a specific flow? Set the status of the pump to CLOSED. At the suction (inlet) "
        "node of the pump add a demand equal to the required pump flow and place a negative "
        "demand of the same magnitude at the discharge node.' "
        "(https://usepa.github.io/EPANET2.2/13_questions.html); expected speed s* = "
        "[bQ + sqrt(b^2 Q^2 + 4aH)]/(2a) for the straight curve H0 = a - b x at EPANET's head "
        f"difference H; EPANET at SPEED = s* passes {check!r} m3/s (Q_set {q_set!r}). EPANET "
        "gives the closed pump a 1/CBIG conductance (CBIG = 1e8 in ft and cfs), so the pipes "
        f"at its ports carry Q_set less (H_d - H_s) 0.3048^2/CBIG = {leak!r} m3/s (checked).",
    )


def control_active_speed_search(project: Project) -> ControlRun:
    """E1b: brentq over EPANET's relative speed ω ∈ [s_min, s_max] for the pump flow Q_set;
    the reference is the EPANET run at that speed (rounded as WNTR writes it)."""
    pu = _only_controlled_pump(project)
    assert pu.control is not None
    q_set = pu.control.setpoint

    def excess(omega: float) -> float:
        return _pump_flow(project, _speed_run(project, pu.id, omega), pu.id) - q_set

    omega = float(brentq(excess, pu.control.min_speed, pu.speed, xtol=SPEED_XTOL, rtol=1.0e-12))
    omega = float(f"{omega:.{WNTR_SPEED_DIGITS}g}")
    run = _speed_run(project, pu.id, omega)
    q = _pump_flow(project, run, pu.id)
    if abs(q - q_set) > 8 * 2.0**-23 * q_set:
        raise RuntimeError(f"EPANET at the found speed passes {q}, not {q_set}")
    return ControlRun(
        run,
        "active",
        omega,
        " Flow-controlled pump (active): reference speed by scipy.optimize.brentq over the "
        "pump's relative speed (EPANET SPEED, h = w^2 H0(q/w)) between its minimum and maximum "
        f"speeds, xtol {SPEED_XTOL:g}, for the EPANET pump flow to equal Q_set; expected "
        f"values from the EPANET run at that speed, rounded to {WNTR_SPEED_DIGITS} digits as "
        "WNTR writes it.",
    )


def _control_limit(project: Project, state: el.ControlState) -> ControlRun:
    """E2 / E3: EPANET at SPEED = s_max (max_speed) or s_min (min_speed). Asserts with the FAQ
    run at Q_set that the setpoint's head lies clearly outside the speed range on that side,
    and that the flow at the limit is clearly below / above Q_set (along the curve, by
    STATE_MARGIN), inside the curve points."""
    pu = _only_controlled_pump(project)
    assert pu.control is not None
    q_set = pu.control.setpoint
    curve = _curve(project, pu)
    speed = pu.speed if state == "max_speed" else pu.control.min_speed
    needed = _pump_lift(_faq_run(project, pu.id, q_set), pu.id)
    at_limit = el.pump_head(curve, speed, q_set)
    side = needed - at_limit if state == "max_speed" else at_limit - needed
    if not side >= el.STATE_MARGIN:
        raise ValueError(f"the setpoint's head must lie clearly beyond the {state} limit")
    run = _speed_run(project, pu.id, speed)
    q = _pump_flow(project, run, pu.id)
    along = el.pump_head(curve, speed, q) - at_limit
    if not (run[2][pu.id] == 1 and (along if state == "max_speed" else -along) >= el.STATE_MARGIN):
        raise ValueError(f"EPANET's flow at the {state} limit is not clearly past Q_set")
    if not el.pump_in_curve_range(curve, speed, q):
        raise ValueError("the limit's operating point stays inside the curve points")
    limit = "maximum" if state == "max_speed" else "minimum"
    return ControlRun(
        run,
        state,
        speed,
        f" Flow-controlled pump at its {limit} speed: EPANET with the pump OPEN at SPEED = "
        f"{speed:g}; the FAQ substitute at Q_set needs {needed!r} m, beyond F({speed:g}, Q_set) "
        f"= {at_limit!r} m.",
    )


PUMP_CONTROL_RUNS: dict[str, Callable[[Project], ControlRun]] = {
    "epanet_pump_flow_control": control_active_faq,
    "epanet_pump_flow_control_speed": control_active_speed_search,
    "epanet_pump_flow_control_max": lambda p: _control_limit(p, "max_speed"),
    "epanet_pump_flow_control_min": lambda p: _control_limit(p, "min_speed"),
}


def build_case(name: str) -> ReferenceCase:
    make, description = EPANET_NETWORKS[name]
    project = make()
    control = PUMP_CONTROL_RUNS[name](project) if name in PUMP_CONTROL_RUNS else None
    flows, heads, statuses = run_with_settings(project) if control is None else control.run
    fluid = project.fluid
    assert fluid.kind == "custom"
    pumps: dict[str, dict[str, float | str]] = {}
    valves: dict[str, dict[str, str]] = {}
    flags: list[dict[str, str]] = []
    for c in project.components:
        if isinstance(c, Pump) and c.control is not None:
            assert control is not None
            q = _pump_flow(project, control.run, c.id)
            pumps[c.id] = {
                "status": el.CONTROL_STATUS[control.state],
                "operatingFlow": q,
                "operatingHead": _pump_lift(control.run, c.id),
                "speed": control.speed,
                "controlState": control.state,
            }
            if control.state != "active":
                flags.append({"code": "PUMP_SETPOINT_NOT_MET", "componentId": c.id})
        elif isinstance(c, Pump):
            pumps[c.id] = {"status": PUMP_STATUS[statuses[c.id]]}
        elif isinstance(c, ControlValve):
            valves[c.id] = {"state": VALVE_STATE[statuses[c.id]]}
            if valves[c.id]["state"] != "active":
                raise ValueError(f"{name}: {c.id} is {valves[c.id]['state']} in EPANET")
    source = source_text(project)
    if control is not None:
        source += control.method
    return ReferenceCase(
        name=name,
        description=description,
        source=source,
        project=project,
        expected=Expected(
            density=fluid.density,
            dynamic_viscosity=fluid.dynamic_viscosity,
            flows=flows,
            egl=heads,
            pumps=pumps,
            valves=valves,
            flags=flags + regime_flags(project, flows),
        ),
    )


def main() -> None:
    for name in EPANET_NETWORKS:
        path = write_case(build_case(name))
        print(f"wrote {path.name}")


if __name__ == "__main__":
    main()
