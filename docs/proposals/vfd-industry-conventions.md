**Status: research notes for `vfd-pump-modes.md`** (public documentation only; every claim cites its URL, and unverified excerpts are labelled).

# Speed-controlled pumps in steady state: how AFT Fathom, Bentley WaterGEMS/WaterCAD, EPANET and PIPE-FLO define them

Sources are public vendor documentation, the EPANET 2.2 manual and source code, two Bentley patents and four papers or guides. Where I could not find something I say so. PIPE-FLO is the thinnest; parts of it were readable only through search-engine excerpts, which I label "unverified".

## 1. AFT Fathom (Datacor)

**What is controlled**
- The pump's Variable Speed tab offers either "Fixed Speed (%)" or "Controlled Pump (Variable Speed)". It is for centrifugal pumps only, and the entered curve "is always assumed to be the 100% speed curve" (https://docs.aft.com/fathom13/PumpPropertiesWindow.html, https://docs.aft.com/fathom/PumpPropertiesWindow.html).
- The setpoint can be volumetric flow, mass flow, discharge head, discharge pressure, suction head or suction pressure (AFT tip "To Affinity and Beyond", https://www.datacor.com/resources/to-affinity-and-beyond).
- The listed setpoints are all measured at the pump itself. Pump head rise is not listed as a setpoint.
- A setpoint at a remote location needs the separate Goal Seek & Control (GSC) module. GSC is an optimizer that "call[s] the Hydraulic Solver repeatedly", adjusting variables such as pump speed until goals are met (https://docs.aft.com/fathom13/IntroductiontotheGSCModule.html).
- For a suction or discharge pressure, "control can optionally be enforced only if the value is above/below the setpoint" (pump page above).

**Speed limits**
- A minimum speed is optional: "A minimum speed can be entered to limit how much the speed is varied." No default is given and none is cited.
- I found no maximum-speed field.
- NPSHr scales with speed squared by default; the exponent can be edited (https://docs.aft.com/fathom/PumpConfiguration.html, https://docs.aft.com/fathom/AffinityLaws.html).

**When the setpoint cannot be met — NOT FOUND**
- I found no public documentation for a controlled pump at maximum speed, at minimum speed, or in reverse flow. The Warnings, Critical Warnings and Cautions lists have no speed-limit or pump-control message (https://docs.aft.com/fathom/Warnings.html, https://docs.aft.com/fathom/CriticalWarnings.html, https://docs.aft.com/fathom/Cautions.html).
- Reverse flow through any pump raises "Junction X had reverse flow - Pump head could not be predicted".
- The documented failure behaviour is for control valves only, and it is a useful contrast. The default is "Always Control (Never Fail)": the valve adds pressure like a pump and the output warns. Otherwise an FCV opens fully; a PRV opens on low upstream pressure and closes on high downstream pressure; a PSV does the opposite (https://docs.aft.com/fathom/ControlValveSetpointNotAchievable.html).
- AFT's convergence advice says "VFD pumps will operate at the fixed speed necessary to achieve their set criteria" and tells users to check for unrealistic setpoints (https://www.datacor.com/resources/getting-that-stubborn-aft-fathom-model-to-converge).
- In pump sizing, pressure-type controlled pumps are "always" modelled at a fixed 100% speed (https://docs.aft.com/fathom13/SpecialConcernsForSizingPumps.html).

**Ill-posed layouts**
- A flow-controlled VFD pump counts as a "flow-defined" junction.
- In series with an FCV, "there is no solution to the problem".
- With FCVs in parallel, the section between them has no pressure reference and Fathom reports "Reference Pressure Needed" (https://www.datacor.com/resources/reference-pressure).

**Parallel controlled pumps:** not found.

**Reporting:** the worked example reports "88.77 percent speed" for a 5,000 gal/min setpoint. Head rise, NPSHr, efficiency and power are reported at that speed using the affinity laws (to-affinity page).

## 2. Bentley WaterGEMS / WaterCAD (and HAMMER help)

**Definition:** relative speed is "the ratio of the pump's actual speed to some reference speed", generally full motor speed, applied through the affinity laws (https://docs.bentley.com/LiveContent/web/Bentley%20WaterGEMS%20SS6-v1/en/GUID-6A75A17C38FE4345BE63613582C22758.html).

**Pump types:** Pattern Based, Fixed Head and Fixed Flow (Pump Attributes, https://docs.bentley.com/LiveContent/web/Bentley%20HAMMER%20SS6-v1/en/GUID-24422862721E431585934602A51A1E3D.html).

**What is controlled**
- The quantity is "Hydraulic Grade (Target)", a static head (HGL), at a "Control Node". That node can be any junction or tank.
- The node can be on the discharge side or, with "Control Node on Suction Side?", on the suction side. Suction-side control acts in reverse: the pump speeds up when the wet-well level is above target (https://docs.bentley.com/LiveContent/web/Bentley%20WaterCAD%20CONNECT%20Edition%20Help-v1/en/GUID-A8CBBCFECB6542FCA45E3DA40BE2BF87.html).
- The node should be in the pump's pressure zone with no tank between it and the pump. The target must be feasible. If the suction head exceeds the target, pump head is reported as zero and "the speed value will not be meaningful" (https://docs.bentley.com/LiveContent/web/Bentley%20HAMMER%20SS6-v1/en/GUID-DA491001-73BE-4B16-9729-A3F9D8626DA2.html).
- Only one VSP may serve a pressure zone. Two VSPs on the same control node is an error (https://docs.bentley.com/LiveContent/web/Bentley%20WaterCAD%20CONNECT%20Edition%20Help-v1/en/GUID-CD4637E3-BF11-4C6D-8FF9-4D4A3918F229.html).
- A differential pressure setpoint is not offered.

**Speed limits**
- "Relative Speed Factor (Maximum)" defaults to 1.0, described as typically the motor's rated speed. Entering a large value effectively removes the limit (Fixed Head page). No standard is cited.
- I found no minimum-speed attribute. The 2008 patent (below) mentions "minimum and maximum limits".

**When the setpoint cannot be met** (https://docs.bentley.com/LiveContent/web/Bentley%20WaterGEMS%20SS6-v1/en/GUID-31A4A446A15F448E8C7BD7C3B8D1249E.html)
- *Fixed Speed Override:* "the pump will operate at the maximum speed setting and the target head will no longer be maintained."
- *Temporarily Closed:* the pump's built-in check valve has closed and "the target head cannot be maintained."
- *Off:* with a junction control node, "If the head at the control node is above the target head, the pump state will automatically switch to Off."
- The pump switches in and out of these states automatically.
- The computed statuses are On, Off, Pump Cannot Deliver Head (Closed) and Cannot Deliver Flow (Open).
- **Fixed Flow:** speed is computed "up to the maximum relative speed factor" (https://docs.bentley.com/LiveContent/web/Bentley%20WaterCAD%20CONNECT%20Edition%20Help-v1/en/GUID-C7B51BFA-2FA0-4A1E-A53F-F61A93A61B27.html). I did not find what happens when the target flow is unreachable at maximum speed.

**Parallel pumps** (https://docs.bentley.com/LiveContent/web/Bentley%20WaterCAD%20CONNECT%20Edition%20Help-v1/en/GUID-44B157D2-F6BB-4F37-A782-A82E3BF0284D.html)
- One lead pump runs first. A lag pump starts when the lead pump at maximum speed cannot meet the target, and "All VSPs that are turned on are operated at the same speed."
- Parallel VSPs must share the control node and target, have the same maximum speed factor and identical curves, and share junctions within 3 nodes. Otherwise the run stops with an error.
- If all pumps are at maximum and the target is still not met, they become fixed-speed pumps.
- A Variable Speed Pump Battery groups identical parallel pumps with a lag-pump count; lag pumps run at the lead's speed (https://docs.bentley.com/LiveContent/web/Bentley%20HAMMER%20SS6-v1/en/GUID-F9668FAA145945B88F740FED7F29C636.html).
- A Fixed Flow battery "evenly divide[s]" its target flow among its pumps. Separate parallel fixed-flow VSPs may have different targets (Fixed Flow page).

**Reporting:** "Relative Speed Factor (Calculated)" plus the computed status.

**Algorithm behind it: two patents**
- US 7,013,248 (Todini, Tryby, Cook, Walski, Mankowski; Haestad Methods, filed 2002; Google Patents lists it expired 2024-07-11).
  - The control node's head is fixed inside the global gradient method and solved through a non-symmetric partition of the matrix.
  - Speed is then found as the root of the pump equation h = −ω²(h₀ − r(Q/ω)ⁿ).
  - Fixed flow is enforced by holding the pump flow at its target.
  - The worked example sets a maximum relative speed factor of 2.00.
  - https://patents.google.com/patent/US7013248
- US 8,265,911 (Wu, Tryby, Todini, Walski, Hartell, Culin; Bentley, filed 2008; Google lists it **active, expires 2030-11-27**).
  - Claim 1 recites a tank as the control node, an extended-period run over several time steps, and the computed speed included in the results.
  - Dependent claims cover the fixed-flow update q^{k+1}=q^k=q_target and a pump battery treated as one equivalent pump.
  - It describes lead/lag pumps at a common speed, run at maximum if the target is still not achieved.
  - https://patents.google.com/patent/US8265911
  - I am not giving a legal reading. Someone should review its claims before parallel pumps are built.
- Related papers:
  - Wu & Todini (2007), "Extended approach for modelling fixed-flow variable speed pumps" (https://cris.unibo.it/handle/11585/47883).
  - "Modeling variable-speed pump operations for target hydraulic characteristics" (https://www.researchgate.net/publication/289907789). Blocked (403); I did not read it.

## 3. EPANET 2.2 (and 2.3)

**Speed is an input, never solved for**
- "By definition, the original pump curve supplied to the program has a relative speed setting of 1." Speed can be changed only by time patterns or controls, for example "LINK 12 1.5 AT TIME 16" (https://usepa.github.io/EPANET2.2/3_network_model.html).
- Pump head: h = −ω²(h₀ − r(q/ω)ⁿ) (https://usepa.github.io/EPANET2.2/12_analysis_algorithms.html). A custom curve is read at q/ω, and a speed of 0 closes the pump (https://github.com/OpenWaterAnalytics/EPANET/blob/master/src/hydcoeffs.c).

**Limits:** I found no minimum or maximum speed parameter in the manual or the source. The manual itself uses a speed of 1.5.

**What one steady solve can and cannot do**
- Simple controls on junction pressure are re-checked after each converged solution in a single run (`pswitch`, https://github.com/OpenWaterAnalytics/EPANET/blob/master/src/hydsolver.c). They can only switch to preset values: a discrete step, not a continuous speed.
- EPANET has no control over a pump group. The usual workaround runs pumps at maximum with PRVs or FCVs, which "fail[s] to model the real operation of the pump group" (Elhay et al. 2025, below).
- EPANET 2.3's release notes add no speed control (https://github.com/OpenWaterAnalytics/EPANET/blob/master/ReleaseNotes2_3.md).

**Status rules**
- A pump closes if its head gain exceeds ω²h₀ + Htol (12_analysis_algorithms).
- The status texts are "closed because cannot deliver head" and "open but exceeds maximum flow" (flow above ω·Qmax), with the warning "Pumps cannot deliver enough flow or head." (https://github.com/OpenWaterAnalytics/EPANET/blob/master/src/text.h, report.c).

**Usable as references**
- The EPANET FAQ gives substitutes for the two operating points (https://usepa.github.io/EPANET2.2/13_questions.html):
  - **Specific flow:** close the pump and put demands of +Q and −Q at its two ends.
  - **Specific head:** replace the pump with a reversed pressure breaker valve.
- Efficiency is read at q/ω with the Sárbu–Borza correction e' = 100 − (100−e)(1/ω)^0.1. This is already in v2.2 (https://github.com/OpenWaterAnalytics/EPANET/blob/v2.2/src/hydraul.c).
- Our installed WNTR 1.5.0 writes `SPEED` into the EPANET input file when `base_speed != 1` (local file `apps/api/.venv/lib/python3.12/site-packages/wntr/epanet/io.py`, around lines 812–814).

## 4. PIPE-FLO (Engineered Software / Revalize) — partial

- The knowledge-base articles now redirect to https://support.revalizesoftware.com/, and the web archive is blocked by this session's network policy. Everything below is **unverified**, taken from search excerpts of:
  - http://kb.eng-software.com/eskb/pipe-flo/messages-and-warnings/over-controlled-improvements-in-pipe-flo-professional-v15
  - http://kb.eng-software.com/eskb/ask-an-engineer/piping-system-and-device-questions/dp-control-with-variable-speed-pumps
- PIPE-FLO 15 added discharge-pressure "Variable Speed modes" to the centrifugal pump. PIPE-FLO "will also calculate the speed" for the solved flow and head.
- Sizing pumps have no curve, so they report no speed.
- A VFD pump with a flow setting can cause an "Over Controlled" condition. Changing it to a fixed-speed pump removes that condition.
- A remote differential pressure is modelled with a "Fixed dP Device" at the transmitter location. The example reports the speed in rpm (1616 rpm).
- A third-party copy of the PIPE-FLO 15 tutorial (https://pdfcoffee.com/pipe-flo-professional-15-tutorials-pdf-free.html, blocked) reportedly says the user enters a flow and the speed is computed. A flow outside the curve's operating limits gives an error in the Messages window.
- **Not found:** speed limits, parallel controlled pumps.

## 5. Other tools found

- **Autodesk InfoWorks WS Pro** (https://help.autodesk.com/cloudhelp/2027/ENU/WSPro-Help/files/GUID-EF90E86C-328E-4BB3-82B4-0D5BBA636862.htm)
  - Modes: PROFILE (target pressure or level at a control node) and TARGET FLOW (flow in a control pipe).
  - Minimum and maximum speeds are required on the Pump Data page, and the initial speed is clamped to them.
  - With "Multiple VSP Regulation", identical VSPs change speed together. If the pumps are not identical, only the first VSP and its identical twins regulate and the rest run at full speed.
  - Standby pumps switch on and off at "% Speed On/Off" thresholds of the reference pump's maximum speed.
  - **Not found:** behaviour when the target cannot be met.
- **Pipe Flow Expert** offers ideal "fixed flow rate" and "fixed head increase" pumps. These compute the required head or the resulting flow, but no speed and no power (https://www.pipeflow.com/software-technical-support/pipe-flow-expert-pumps).
- **Fluidit (district heating):** "Most VSP strategies … use differential pressure control" at one or more reference points (https://fluidit.com/how-to-model-variable-speed-pump-control-in-a-district-heating-network/).

## 6. Literature

- **Elhay, Fischer, Piller, Deuerlein & Simpson (2025)**, Cambridge Prisms: Water 3 e11, open access (https://doi.org/10.1017/wat.2025.10005)
  - Control targets for pump groups: "set downstream head, set suction head, set pressure at a critical node and total pump flow".
  - Solving for speed is an inverse problem "for which there may be no unique solution". Two VSPs with one target flow is not unique, and identical pumps can share the duty in any ratio. They add minimum electrical power as the deciding criterion.
  - A flow-controlled station is a lower flow bound whose Lagrange multiplier is the pumping head.
  - A pressure-controlled station is treated like a PRV whose "loss" is non-positive, i.e. a head gain.
- **Guo et al. (ORNL)**, "Variable speed pump efficiency calculation…" (https://www.osti.gov/servlets/purl/1649114)
  - With no static head: S = Q'/Q.
  - With a quadratic curve H = a + bQ + cQ², the closed form is S = [−bQ' + √((bQ')² − 4a(cQ'² − H'))]/(2a).
  - Efficiency is taken as unchanged above 66.7% speed. Below that, η' = 1 − (1−η)(1/S)^0.1 (Sárbu & Borza 1998).
  - Minimum continuous stable flow (MCSF) and NPSH available must be checked.
- **DOE/Hydraulic Institute/Europump**, VSP guide executive summary (https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/variable_speed_pumping.pdf)
  - With static head, the system curve cuts across the constant-efficiency curves.
  - Using the affinity laws alone there is "a common mistake … can lead to major errors".
  - Higher speed worsens suction performance.

## 7. Conventions common to most tools

1. **Speed definition:** a relative factor s = n/n_ref, where the entered curve is s = 1 (100%). Affinity laws apply: Q ∝ s, H ∝ s², and NPSHr ∝ s² by default (AFT, Bentley, EPANET, WS Pro).
2. **Method:** the controlled quantity is imposed as a constraint in the network solve, and speed is recovered afterwards from the solved operating point by root-finding on the pump curve. Speed is then reported as a result (AFT %, Bentley calculated factor, PIPE-FLO rpm).
3. **Pressure targets are static values at a node** (pressure, head or HGL), never an energy grade. Supported locations are the pump suction or discharge, or a remote node. Flow targets are the pump's own flow or the flow in a named pipe.
4. **Maximum speed:** above the cap the pump becomes a fixed-speed pump at maximum, the target is dropped, and an explicit status says so (Bentley Fixed Speed Override; parallel pumps converted to fixed speed; the 2008 patent).
5. **Integral check valve:** no reverse flow. When the target is met without pumping, the pump goes Off or Temporarily Closed (Bentley) or closes (EPANET).
6. **A flow or pressure controller needs a free pressure reference and cannot share a degree of freedom with another controller:** one VSP per zone and per control node (Bentley), "Reference Pressure Needed" (AFT), "Over Controlled" (PIPE-FLO).
7. **Parallel pumps:** identical pumps share one target and run at equal speed. Lag pumps start when the lead pump at maximum cannot meet the target (Bentley, WS Pro, 2008 patent).

## 8. Where tools disagree

1. **Controlled quantity**
   - Bentley: HGL at any node, including suction side and remote nodes.
   - AFT: flow or suction/discharge pressure or head at the pump; remote only via the GSC optimizer.
   - PIPE-FLO: discharge pressure or flow; remote differential pressure via a fixed-dP device.
   - WS Pro: control node or control pipe.
   - Differential head across the pump: no tool offers it as a mode. EPANET reaches it only through the reversed-PBV substitute.
2. **Maximum speed**
   - Bentley: default 1.0, settable above 1 (2.0 in the patent example; "large value" removes it).
   - EPANET: none (1.5 used in the manual).
   - AFT: none documented.
   - WS Pro: required.
   - Our `Pump.speed` currently has `le=1.0` (`apps/api/src/opensolve_pipe/models/components.py:187`).
3. **Minimum speed and where its value comes from:** AFT optional, WS Pro required, Bentley has none (pump goes Off), EPANET has none. No tool cites a default value; the literature ties the low end to MCSF and efficiency loss, not to a fixed number.
4. **Below-target behaviour:** Bentley switches Off. AFT offers an "enforce only above/below" option for pressure. WS Pro uses % Speed Off thresholds.
5. **Unreachable target**
   - Bentley: physical fallback (run at maximum) plus a status.
   - AFT: undocumented for pumps; its valves default to a non-physical "never fail" mode.
   - PIPE-FLO: an error, per unverified excerpts.
6. **Parallel speed sharing**
   - Bentley: equal speed with lead/lag staging; a fixed-flow battery splits the target flow equally.
   - WS Pro: non-identical pumps leave one regulating and the others at full speed.
   - Elhay et al.: choose the minimum-power combination.
7. **Efficiency at reduced speed**
   - EPANET: Sárbu–Borza correction at every speed.
   - ORNL: only below 66.7%.
   - AFT and our `pumps.py`: plain affinity law, η = η₀(Q/s). EPANET power comparisons at s ≠ 1 will therefore differ from ours.

## 9. Notes for our design (my inferences, not tool claims)

- **Unique speed:** for H₀ > 0 and H₀' ≤ 0, d/ds[s²H₀(Q/s)] = 2sH₀ − QH₀' > 0 (my derivation). So for a given flow and head rise the speed is unique on our monotone PCHIP curves, and finding it is a bracketed one-dimensional root. This fails on a rising-curve section.
- **Fit with the current solver:** following the patent and Elhay's framing, a pressure-controlled pump looks like the existing PRV/PSV held-node mechanism with head gain bounded by the curve at s_min and s_max. A flow-controlled pump looks like the existing fixed-flow link used for the FCV. The setpoint as a static pressure at the pump's port is consistent with D9 and with every tool above.
- **Reference cases with sources:**
  - Closed form: ORNL eq. (10).
  - EPANET via WNTR at the reported speed: confirm the setpoint holds within the D6 tolerance.
  - The EPANET FAQ substitutes: a demand pair for fixed flow, a reversed PBV for fixed head rise.

(The researcher kept text extracts of these sources in a scratch directory; they are not part of the repository.)

No repository file was edited.