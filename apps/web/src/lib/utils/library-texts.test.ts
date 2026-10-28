/**
 * Flags and topology issues about the project library (CLAUDE.md D21): the advice a Crane
 * default's range flag gains (proposal project-library.md §4.3), and the issues the solver raises
 * for references and entries (UNKNOWN_PIPE_SPEC, UNKNOWN_RESISTANCE, VALVE_RESISTANCE_OUT_OF_RANGE,
 * FITTING_RESISTANCE_OUT_OF_RANGE, an unknown material of a spec), told with names from the
 * project. Flags and issues are made-up test inputs shaped like the API's (codes, details and
 * message wording of apps/api solver/builder.py and results.py).
 */
import { describe, expect, it } from 'vitest';
import type { TopologyIssue } from '../api/types';
import { libraryProject } from '../testing/helpers';
import { flag } from '../testing/results';
import { pumpTransferExample } from './examples';
import { FITTING_LIBRARY_ADVICE, flagText, VALVE_LIBRARY_ADVICE } from './flag-text';
import { topologyIssueViews } from './issue-text';
import { SI_UNITS } from './units';

describe("a Crane default's range flag", () => {
	const project = pumpTransferExample();
	const context = { project, prefs: SI_UNITS };

	it("on a valve's default K advises the manufacturer's coefficient, on the valve or in the library", () => {
		const text = flagText(
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message:
					"valve 'V1': its default Crane K at the inlet pipe's 0.762 m: diameter 0.762 m is outside the sizes the Crane table covers (0.0508 to 0.6096 m; NPS 2 to 24); K evaluated with the nearest size class",
				componentId: 'V1',
				details: { referenceDiameter: 0.762 }
			}),
			context
		);
		expect(text.endsWith(`K evaluated with the nearest size class. ${VALVE_LIBRARY_ADVICE}`)).toBe(
			true
		);
		expect(VALVE_LIBRARY_ADVICE).toBe(
			"Enter the manufacturer's coefficient as a resistance, or in the project library."
		);
	});

	it("on a fitting's Crane table advises it too, but not on a laminar-flow flag", () => {
		const range = flagText(
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message:
					"connection 'L1' fitting 1 (butterfly_valve): diameter 0.762 m is outside the sizes the Crane table covers (0.0508 to 0.6096 m; NPS 2 to 24); K evaluated with the nearest size class",
				connectionId: 'L1',
				details: { fittingIndex: 0 }
			}),
			context
		);
		expect(range.endsWith(` ${FITTING_LIBRARY_ADVICE}`)).toBe(true);
		const laminar = flagText(
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message:
					"connection 'L1' fitting 1 (elbow_90_lr): its K correlation is for turbulent flow but the flow is laminar (Re = 900); the loss is likely underestimated",
				connectionId: 'L1',
				details: { fittingIndex: 0, reynoldsNumber: 900 }
			}),
			context
		);
		expect(laminar).not.toContain('project library');
	});

	it("is unchanged on a valve's laminar-flow flag and on a pipe", () => {
		const laminar = flagText(
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message:
					"valve 'V1': its Crane K is for turbulent flow but the flow is laminar (Re = 900); the loss is likely underestimated",
				componentId: 'V1',
				details: { reynoldsNumber: 900 }
			}),
			context
		);
		expect(laminar).not.toContain('project library');
		const pipe = flagText(
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message: "connection 'L1' pipe 1: made-up reason",
				connectionId: 'L1',
				details: { segmentIndex: 0, reynoldsNumber: 1e9, relativeRoughness: 0.1 }
			}),
			context
		);
		expect(pipe).not.toContain('project library');
	});
});

function issue(code: string, message: string, componentIds: string[], connectionIds: string[]) {
	return { code, message, componentIds, connectionIds } as TopologyIssue;
}

describe('topology issues about the project library', () => {
	const project = libraryProject();
	const views = (i: TopologyIssue) => topologyIssueViews([i], project, true, SI_UNITS);

	it('name a reference the library does not have, with the element', () => {
		const [valve] = views(
			issue(
				'UNKNOWN_RESISTANCE',
				"valve 'V1' refers to resistance entry 'RS9', which is not in the project library",
				['V1'],
				[]
			)
		);
		expect(valve!.text).toBe(
			'Gate valve V1 refers to a resistance entry the project library does not have (“RS9”): choose an entry from the library, enter its resistance, or leave it on its default.'
		);
		expect(valve!.links).toEqual([{ componentId: 'V1' }]);
		const [pipe] = views(
			issue(
				'UNKNOWN_PIPE_SPEC',
				"connection 'L1' pipe 1 refers to pipe spec 'PS9', which is not in the project library",
				[],
				['L1']
			)
		);
		expect(pipe!.text).toBe(
			'Piping Upper tank → Gate valve V1, pipe 1 refers to a pipe spec the project library does not have (“PS9”): choose a spec from the library, or give the pipe its own size.'
		);
		expect(pipe!.links[0]).toMatchObject({ componentId: 'R1', portId: 'port_1' });
		const [fitting] = views(
			issue(
				'UNKNOWN_RESISTANCE',
				"connection 'L1' fitting 2 (custom) refers to resistance entry 'RS9', which is not in the project library",
				[],
				['L1']
			)
		);
		expect(fitting!.text).toBe(
			'Piping Upper tank → Gate valve V1, fitting 2 (custom fitting (enter k)) refers to a resistance entry the project library does not have (“RS9”): choose an entry from the library, or enter its K.'
		);
		expect(fitting!.detail).toBe(
			"connection 'L1' fitting 2 (custom) refers to resistance entry 'RS9', which is not in the project library"
		);
	});

	it('name an entry the solver cannot represent on an element, in display units', () => {
		const [valve] = views(
			issue(
				'VALVE_RESISTANCE_OUT_OF_RANGE',
				"valve 'V1': its project library resistance entry 'RS2', K 0.3 at 1e-80 m, on the inlet pipe's inner diameter of 0.1 m gives a loss coefficient that is not a finite positive floating-point number; the solver cannot represent this valve",
				['V1'],
				[]
			)
		);
		expect(valve!.text).toBe(
			"Gate valve V1: its project library entry “Elbow (K)” (K 0.3 at 1e-77 mm) on its inlet pipe's inner diameter (100 mm) gives a loss coefficient that is not a finite positive floating-point number, so the solver cannot represent this valve. Check the entry."
		);
		const [fitting] = views(
			issue(
				'FITTING_RESISTANCE_OUT_OF_RANGE',
				"connection 'L1' fitting 2 (custom): its project library resistance entry 'RS1', Cv 1e-170, on the inner diameter of pipe 2, 0.10226 m, gives a loss coefficient that is not a finite floating-point number; the solver cannot represent this fitting",
				[],
				['L1']
			)
		);
		expect(fitting!.text).toBe(
			'Piping Upper tank → Gate valve V1, fitting 2 (custom fitting (enter k)): its project library entry “Gate, open” (Cv 1e-170) on the inner diameter of pipe 2 (102.3 mm) gives a loss coefficient that is not a finite floating-point number, so the solver cannot represent this fitting. Check the entry.'
		);
	});

	it('name a spec whose material the pipe library does not have', () => {
		const [view] = views(
			issue(
				'UNKNOWN_PIPE_MATERIAL',
				"connection 'L1' pipe 1: pipe spec 'PS1': unknown pipe material 'carbon_steel'; available: pvc",
				[],
				['L1']
			)
		);
		expect(view!.text).toBe(
			'Piping Upper tank → Gate valve V1, pipe 1: its pipe spec “NPS 4 measured” names a material the pipe library does not have, “carbon_steel”: choose a material from the library for the spec, or make it a custom spec.'
		);
	});

	it("keep the server's message when it is not in the form expected", () => {
		const message = "valve 'V1' refers to something else";
		const [view] = views(issue('UNKNOWN_RESISTANCE', message, ['V1'], []));
		expect(view!.text).toBe(message);
	});
});
