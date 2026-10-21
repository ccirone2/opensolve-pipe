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

Expected values: the EPANET flow of every connection and, for every reservoir and tee port, the
EPANET head of its node (EPANET neglects velocity head, so its head is our EGL, design §1.1).
"""

import ctypes
import tempfile
import warnings
from pathlib import Path

import wntr
from scipy.constants import gallon
from wntr.epanet.toolkit import ENepanet

from opensolve_pipe.models.components import Component, Reservoir, TeeBranch
from opensolve_pipe.models.piping import CUSTOM_MATERIAL_ID
from opensolve_pipe.models.project import Project
from tests.reference.case_format import (
    Expected,
    ReferenceCase,
    connect,
    custom_fluid,
    custom_pipe,
    fitting,
    ideal_tee,
    make_project,
    reservoir,
    write_case,
)
from tests.reference.derivations import G

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


def source_text() -> str:
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
        "and its results are float32 (about 1e-7 relative)."
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
}


# --- Conversion and run ------------------------------------------------------------------------


def _node_names(project: Project) -> dict[str, str]:
    """EPANET node for every "componentId:portId"."""
    names: dict[str, str] = {}
    for component in project.components:
        if isinstance(component, Reservoir) or (
            isinstance(component, TeeBranch) and component.loss_model == "ideal"
        ):
            for port in component.ports:
                names[f"{component.id}:{port.id}"] = component.id
        else:
            raise ValueError(f"no EPANET equivalent for component {component.id}")
    return names


def project_to_wntr(project: Project) -> wntr.network.WaterNetworkModel:
    """Build the WNTR model of a project as design §11 prescribes (see the module docstring)."""
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
    nodes = _node_names(project)

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


def run_epanet(project: Project) -> tuple[dict[str, float], dict[str, float]]:
    """Solve with EPANET; return (flow per connection, EPANET head per port key)."""
    wn = project_to_wntr(project)
    with tempfile.TemporaryDirectory() as tmp:
        simulator = wntr.sim.EpanetSimulator(wn)
        results = simulator.run_sim(file_prefix=str(Path(tmp) / "case"), convergence_error=True)
    flow_table = results.link["flowrate"]
    head_table = results.node["head"]
    # float() of a float32 is exact, so the JSON holds EPANET's values unchanged.
    flows = {c.id: float(flow_table.loc[0, c.id]) for c in project.connections}
    heads = {key: float(head_table.loc[0, node]) for key, node in _node_names(project).items()}
    return flows, heads


def build_case(name: str) -> ReferenceCase:
    make, description = EPANET_NETWORKS[name]
    project = make()
    flows, heads = run_epanet(project)
    fluid = project.fluid
    assert fluid.kind == "custom"
    return ReferenceCase(
        name=name,
        description=description,
        source=source_text(),
        project=project,
        expected=Expected(
            density=fluid.density,
            dynamic_viscosity=fluid.dynamic_viscosity,
            flows=flows,
            egl=heads,
        ),
    )


def main() -> None:
    for name in EPANET_NETWORKS:
        path = write_case(build_case(name))
        print(f"wrote {path.name}")


if __name__ == "__main__":
    main()
