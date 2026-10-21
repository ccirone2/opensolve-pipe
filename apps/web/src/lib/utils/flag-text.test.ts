/**
 * Flag text in the project's names and display units. Flags are made-up test inputs shaped like
 * the API's (codes, details keys and message wording of apps/api solver/results.py); expected
 * conversions are computed here from the unit definitions.
 */
import { describe, expect, it } from 'vitest';
import type { Project } from '../api/types';
import { flag } from '../testing/results';
import { gravityBranchExample, pumpTransferExample } from './examples';
import { flagText, messageText } from './flag-text';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

const IN = 0.0254;
const FT = 0.3048;
const PSI = (0.45359237 * 9.80665) / (IN * IN);
const GPM = (231 * IN ** 3) / 60;
const sig4 = (v: number) => String(Number(v.toPrecision(4)));
const ft2 = (m: number) => String(Number((m / FT).toFixed(2)));

const pumpProject = pumpTransferExample();
const us = (project: Project = pumpProject) => ({ project, prefs: IMPERIAL_UNITS });

describe('flag text from code and details', () => {
	it('pump outside its curve: the flow in display units, no ids', () => {
		const text = flagText(
			flag({
				code: 'PUMP_OUTSIDE_CURVE',
				severity: 'warning',
				message:
					"pump 'P1' operates at 0.0475089 m³/s, outside its curve's flow range at speed 1 (0 to 0.04 m³/s)",
				componentId: 'P1',
				details: { flow: 0.0475089, speed: 1, curve: 'head' }
			}),
			us()
		);
		expect(text).toBe(
			`It operates at ${sig4(0.0475089 / GPM)} gpm, outside the flow range of its curve at 100 % speed: the head is extrapolated along the curve's end slope (dashed on the pump chart).`
		);
		expect(text).not.toMatch(/m³\/s|'P1'/);
	});

	it('a pressure below the vapor pressure: absolute, in psia, at the named port', () => {
		const text = flagText(
			flag({
				code: 'BELOW_VAPOR_PRESSURE',
				severity: 'invalid',
				message: "absolute pressure at 'P1:suction' (-52340.5 Pa) is below the vapor pressure",
				componentId: 'P1',
				portId: 'suction',
				details: { absolutePressure: -52340.5, vaporPressure: 2339 }
			}),
			us()
		);
		expect(text).toBe(
			`The absolute pressure at Suction is ${sig4(-52340.5 / PSI)} psia, below the vapor pressure (${sig4(2339 / PSI)} psia): the liquid would flash.`
		);
	});

	it('pipes are numbered from 1, as in the tables', () => {
		const text = flagText(
			flag({
				code: 'TRANSITIONAL_FLOW',
				severity: 'warning',
				message: "connection 'L1' pipe 2: Re = 2909 is in the transition range",
				connectionId: 'L1',
				details: { segmentIndex: 1, reynoldsNumber: 2908.8 }
			}),
			{ project: pumpProject, prefs: SI_UNITS }
		);
		expect(text).toMatch(/^Pipe 2: Re = 2909 is in the laminar–turbulent transition range/);
	});

	it('a pipe outside a correlation range keeps the number the API gives it (from 1)', () => {
		const text = flagText(
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message: "connection 'L1' pipe 2: made-up reason for the test",
				connectionId: 'L1',
				details: { segmentIndex: 1, reynoldsNumber: 2.5e8 }
			}),
			{ project: pumpProject, prefs: SI_UNITS }
		);
		expect(text).toBe('Pipe 2: Made-up reason for the test');
	});

	it('a fitting is named, numbered from 1, with the reason the API gives', () => {
		const text = flagText(
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message:
					"connection 'L1' fitting 1 (elbow_90_lr): its K correlation is for turbulent flow (Re = 900)",
				connectionId: 'L1',
				details: { fittingIndex: 0, reynoldsNumber: 900 }
			}),
			{ project: pumpProject, prefs: SI_UNITS, fittingName: () => 'Library elbow name' }
		);
		expect(text).toBe(
			'Library elbow name (fitting 1): Its K correlation is for turbulent flow (Re = 900)'
		);
	});

	it('pump flow reversal: dead-headed or stopped by the system head', () => {
		const reversal = (headRise: number) =>
			flag({
				code: 'PUMP_FLOW_REVERSAL',
				severity: 'invalid',
				message: 'made-up',
				componentId: 'P1',
				details: { headRise, shutoffHead: 30 }
			});
		expect(flagText(reversal(30), us())).toBe(
			`Its discharge is closed off, so it runs dead-headed at its shutoff head (${ft2(30)} ft), held at zero flow by its check.`
		);
		expect(flagText(reversal(35), us())).toMatch(
			new RegExp(`^The system head across it \\(${ft2(35)} ft\\) exceeds its shutoff head`)
		);
	});

	it('a control valve setpoint in its own unit, gauge for pressure', () => {
		const project = pumpTransferExample();
		const text = flagText(
			flag({
				code: 'CONTROL_VALVE_SETPOINT_NOT_MET',
				severity: 'info',
				message: "PRV 'V1' is open: it cannot hold its outlet pressure setpoint 150000",
				componentId: 'V1',
				details: { state: 'open', setpoint: 150000 }
			}),
			{ ...us(project), valveTypes: { V1: 'prv' } }
		);
		expect(text).toBe(
			`It is open: it cannot hold its outlet pressure setpoint (${sig4(150000 / PSI)} psig).`
		);
	});

	it('cavitation, check valve, reservoir port and isolated section', () => {
		expect(
			flagText(
				flag({
					code: 'CAVITATION',
					severity: 'invalid',
					message: 'made-up',
					componentId: 'P1',
					details: { npshAvailable: 2, npshRequired: 3, npshMargin: -1 }
				}),
				{ project: pumpProject, prefs: SI_UNITS }
			)
		).toBe('NPSH available 2 m is below NPSH required 3 m (margin -1 m): the pump would cavitate.');
		expect(
			flagText(
				flag({
					code: 'CHECK_VALVE_CLOSED',
					severity: 'info',
					message: 'made-up',
					componentId: 'V1',
					details: { headDifference: -2.5, crackingHead: 0.1 }
				}),
				{ project: pumpProject, prefs: SI_UNITS }
			)
		).toBe(
			'Closed: the head across it (-2.5 m) does not exceed its cracking head (0.1 m) in the forward direction.'
		);
		expect(
			flagText(
				flag({
					code: 'PORT_ABOVE_LIQUID_LEVEL',
					severity: 'invalid',
					message: 'made-up',
					componentId: 'R1',
					portId: 'port_1',
					details: { portElevation: 5, liquidSurfaceElevation: 4 }
				}),
				{ project: pumpProject, prefs: SI_UNITS }
			)
		).toBe('Port 1 is above the liquid surface (5 m > 4 m): it would draw air.');
		expect(
			flagText(
				flag({
					code: 'ISOLATED_SECTION',
					severity: 'info',
					message: 'made-up',
					componentId: 'P1',
					details: { componentIds: 'P1, V1' }
				}),
				{ project: pumpProject, prefs: SI_UNITS }
			)
		).toMatch(/closed off\): Transfer pump, Discharge isolation valve\./);
	});
});

describe('flag text from the message', () => {
	it('replaces ids with names and converts SI quantities by their unit', () => {
		const gravity = gravityBranchExample();
		const text = messageText(
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message:
					"branch 'T1': the run pipes differ in inner diameter (0.10226 m and 0.07792 m); see 'L1'",
				componentId: 'T1'
			}),
			{ project: gravity, prefs: IMPERIAL_UNITS }
		);
		expect(text).toBe(
			`The run pipes differ in inner diameter (${sig4(0.10226 / IN)} in and ${sig4(0.07792 / IN)} in); see “Elevated tank → Distribution tee”`
		);
	});

	it('keeps what it does not know, and capitalizes', () => {
		expect(
			messageText(
				flag({
					code: 'NOT_CONVERGED',
					severity: 'invalid',
					message: "the solve did not converge: unsupported pattern at 'X9'"
				}),
				{ project: pumpProject, prefs: SI_UNITS }
			)
		).toBe("The solve did not converge: unsupported pattern at 'X9'");
	});

	it('names a port of a component and converts a pressure without adding a marker', () => {
		expect(
			messageText(
				flag({
					code: 'BELOW_VAPOR_PRESSURE',
					severity: 'invalid',
					message: "absolute pressure at 'P1:suction' (-52340.5 Pa) is below 0 Pa"
				}),
				{ project: pumpProject, prefs: SI_UNITS }
			)
		).toBe('Absolute pressure at “Suction of Transfer pump” (-52.34 kPa) is below 0 kPa');
	});
});
