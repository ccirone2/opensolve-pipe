# D12. Assigned-flow node

Decision D12 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D12`.

---

Added to v1 by the owner (PR #229; D5). Specs: SDD §4.11, TSD §4.8.

### Model

`AssignedFlow`, type `assigned_flow`, one port `port_1`, a required `flow` in m³/s within ±100 (D11's flow bound): positive is a demand leaving the network, negative a supply entering it. It has no default flow, and `flow = 0` behaves exactly as a plug. `schemaVersion` stays 1 (an additive type, nothing deployed). *(GOALS §4.1: no source cites a default flow.)*

### Solve

The port is a free node whose demand is the flow, entering the GGA's continuity rows as a `FIXED_FLOW` link's demand and supply do. It is never a fixed head, so D1's boundary rule holds, and `NO_FIXED_HEAD` says why. A dead-end branch to a nonzero flow carries it.

### No steady state

A part that no fixed head reaches can hold assigned flows only if they sum to zero (to the continuity tolerance); it then floats (flows solved, `UNDETERMINED_PRESSURE`). Otherwise it is disconnected (EPANET's "system disconnected"): it is left out of the inner solve, and the closed elements around it whose rules open as its level runs away (down with a net demand, up with a net supply) are re-opened. With none to open, the solve is not converged, naming the nodes with their flows and each element closed around them with the reason: the user's status, a side with no fixed head, or its rule.

### Flow controls feeding assigned flows

The status rules decide, as D11 does for two flow controls in series. This corrects the first text of TSD §4.8 (PR #229), which said that any different setpoint has no solution: the independent reference cases derive a valid steady state for an FCV set above the demand and for a flow-controlled pump fed another flow. An FCV fed less than its setpoint ends fully open (`CONTROL_VALVE_SETPOINT_NOT_MET`), and a speed-controlled pump fed another flow runs at its maximum or minimum speed (`PUMP_SETPOINT_NOT_MET`). More than an FCV's setpoint, or reverse flow through an FCV or pump, has no steady state; an equal setpoint is over-controlled. Both end not converged, naming the control and the nodes, whichever path the solve takes. *(GOALS §3: correctness over convergence.)*

### System curves

`flow_limit` counts assigned flows as fixed supplies and demands (Gale 1957: a flow exists only if no node set holds more net supply than its cut passes), which bounds the forced flow from above and, where only the pump can feed a demand or drain a supply, from below: points outside the bounds have no steady state and are not solved again. A pump side that reaches only assigned-flow nodes has no point with a head: the one flow they fix leaves its head undetermined.

### Traceability

The port has a node result like any port (EGL, HGL, static and absolute pressure, `BELOW_VAPOR_PRESSURE`), and the boundary result's outflow is −flow. The trace gives the flow with its sign convention and the continuity at the port. The methods summary mentions assigned flows only when a project has one (EPANET, Gale). *(GOALS §4.2.)*

### Versions and proof

Added in `METHOD_VERSION` 1.1.0 (unreleased), with a changelog line: projects without assigned-flow nodes are unchanged in every solved value, trace, message and system-curve point (corpus comparison against `c03217c`: 4,120 projects identical, 0 different, no ignores; TSD §10.4). Reference: 12 closed-form cases, 2 EPANET cases and 18 scenario tests; fuzz profile `assigned_flow` (TSD §10.4). *(GOALS §4.3.)*
