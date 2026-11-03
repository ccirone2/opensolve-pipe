/**
 * One pump off, drawn together (CLAUDE.md D21 slice 4d): the plan of "Add cases with one pump
 * off" (its gates, words, ids and the scenarios it makes), whether two cases share the rest of the
 * network, the duty claim, the other cases' states, Running combinations and its extremes. The
 * responses are the shared fixture's real API answers (the `one-off` and `one-off-dead-headed`
 * cases and their scenario cases, apps/api/tests/fixtures/pump_groups_input.py); a few edits are
 * synthetic, as named.
 */
import { describe, expect, it } from 'vitest';
import type {
	Flag,
	PipeSpec,
	Project,
	PumpGroupCurveResponse,
	PumpGroupStation,
	PumpResult,
	ResistanceSpec,
	Scenario,
	SolveResponse,
	TopologyIssue
} from '$lib/api/types';
import { hydraulicFingerprint, type GroupCurveState } from '$lib/state/project.svelte';
import fixture from './__fixtures__/pump-groups-input.json';
import { ratedCurveRange } from './pump-chart';
import { groupTable, type GroupMemberInput } from './pump-group-chart';
import { refusalWords, wordsText } from './pump-groups';
import {
	addedNotice,
	chartKeys,
	chartPriority,
	combinationExtremes,
	DUTY_CLAIM_RULE,
	DUTY_CLAIM_WORDS,
	dutyClaim,
	isOnePumpOff,
	MAX_GROUP_CASES,
	offName,
	offOverride,
	onePumpOffPlan,
	otherGroupCases,
	restOf,
	runningCombinations,
	sameStation,
	sharedRest,
	withOnePumpOffCases,
	type CombinationsInput,
	type OtherCasesInput
} from './pump-group-one-off';
import { applyScenario, MAX_SCENARIOS, SCENARIO_NAME_LIMIT, withScenarios } from './scenarios';

interface Answer {
	status: number;
	body: unknown;
}
interface ScenarioCase {
	solve: SolveResponse;
	groupCurve: Answer;
	systemCurve: Answer;
}
interface FixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: SolveResponse;
	groupCurve: Answer;
	systemCurve: Answer | null;
	scenarioCases?: Record<string, ScenarioCase>;
}
const cases = fixture.cases as unknown as FixtureCase[];
const named = (name: string) => cases.find((c) => c.name === name)!;

const oneOff = named('one-off');
const body = (a: Answer) => a.body as PumpGroupCurveResponse;
const station = body(oneOff.groupCurve).station;
const baseSystem = body(oneOff.systemCurve!);
const scenarioCase = (id: string) => oneOff.scenarioCases![id]!;
const withoutScenarios = (p: Project) => withScenarios(structuredClone(p), []);

/** The plan for the `one-off` project's base case (its station, members and base solve). */
function planFor(project: Project, overrides: Partial<Parameters<typeof onePumpOffPlan>[0]> = {}) {
	return onePumpOffPlan({
		project,
		shownCase: null,
		station,
		memberIds: ['PA', 'PB'],
		base: { response: oneOff.solve, stale: false },
		...overrides
	});
}

/** A response with one pump's status changed (synthetic). */
function withStatus(response: SolveResponse, pumpId: string, status: PumpResult['status']) {
	const copy = structuredClone(response);
	copy.solvedState.pumpResults[pumpId]!.status = status;
	return copy;
}

describe('the cases with one pump off', () => {
	it('makes a case per running pump, its only change that pump off, named and numbered', () => {
		const project = withoutScenarios(oneOff.project);
		const plan = planFor(project);
		expect(plan.gate).toBeNull();
		expect(plan.about).toBe(
			'Makes one scenario per pump running in the base case (Pump PA and Pump PB): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.'
		);
		expect(plan.add).toEqual([
			{ pumpId: 'PA', id: 'S1', name: 'Pump PA off' },
			{ pumpId: 'PB', id: 'S2', name: 'Pump PB off' }
		]);
		expect(plan.label).toBe('Add cases with one pump off (2)');
		expect(plan.refusal).toBeNull();
		expect(plan.showSolveAll).toBe(true);
		const made = withOnePumpOffCases(project, plan.add);
		// Exactly the fixture's S1 and S2, the scenarios the API solved.
		expect(made.scenarios).toEqual(oneOff.project.scenarios!.slice(0, 2));
		expect(made.scenarios!.map((s) => s.id)).toEqual(plan.add.map((a) => a.id));
		expect(addedNotice(plan.add.map((a) => a.name))).toBe(
			'Added 2 cases with one pump off: Pump PA off and Pump PB off. Solve all solves every case not yet solved; Undo removes them.'
		);
		expect(addedNotice(['Pump PA off'])).toBe(
			'Added 1 case with one pump off: Pump PA off. Solve all solves every case not yet solved; Undo removes them.'
		);
	});

	it('skips a pump whose case exists, whatever it is named, and refuses when every one exists', () => {
		const plan = planFor(oneOff.project);
		expect(plan.add).toEqual([]);
		expect(plan.existing).toEqual([
			{ pumpId: 'PA', scenarioId: 'S1', scenarioName: 'Pump PA off' },
			{ pumpId: 'PB', scenarioId: 'S2', scenarioName: 'Pump PB off' }
		]);
		expect(plan.notes).toEqual([
			'Pump PA has its case already: Pump PA off.',
			'Pump PB has its case already: Pump PB off.'
		]);
		expect(plan.refusal).toBe(
			'Every case with one pump off already exists: Pump PA off and Pump PB off.'
		);
		expect(plan.label).toBe('Add cases with one pump off');
		// Renamed, it is still PA's case.
		const renamed = structuredClone(oneOff.project);
		renamed.scenarios![0]!.name = 'N-1 (PA)';
		expect(planFor(renamed).existing[0]).toEqual({
			pumpId: 'PA',
			scenarioId: 'S1',
			scenarioName: 'N-1 (PA)'
		});
	});

	it('takes the first free ids on the growing project', () => {
		const project = withScenarios(withoutScenarios(oneOff.project), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		const plan = planFor(project);
		expect(plan.add.map((a) => a.id)).toEqual(['S2', 'S3']);
		const made = withOnePumpOffCases(project, plan.add);
		expect(made.scenarios!.map((s) => [s.id, s.name])).toEqual([
			['S1', 'Winter'],
			['S2', 'Pump PA off'],
			['S3', 'Pump PB off']
		]);
	});

	it('refuses past the scenario limit with the count', () => {
		const nineteen: Scenario[] = Array.from({ length: 19 }, (_, i) => ({
			id: `S${i + 1}`,
			name: `Case ${i + 1}`,
			overrides: []
		}));
		const plan = planFor(withScenarios(withoutScenarios(oneOff.project), nineteen));
		expect(MAX_SCENARIOS).toBe(20);
		expect(plan.refusal).toBe(
			'Adding 2 cases would make 21 scenarios; a project holds at most 20 scenarios.'
		);
		expect(plan.label).toBe('Add cases with one pump off (2)');
	});

	it('cuts a long pump name to the scenario name limit, as copyName cuts', () => {
		const long = 'P'.repeat(98);
		expect(offName(long)).toBe(`${'P'.repeat(96)} off`);
		expect(offName(long)).toHaveLength(SCENARIO_NAME_LIMIT);
		expect(offName('Pump PA')).toBe('Pump PA off');
		// With the id that tells it apart: the name is cut, never the id.
		expect(offName(long, 'PA')).toBe(`${'P'.repeat(91)} (PA) off`);
		expect(offName(long, 'PA')).toHaveLength(SCENARIO_NAME_LIMIT);
	});

	it('tells two pumps of the same name apart by their ids, in the cases it makes and its words', () => {
		// Synthetic: a duty and a standby unit both named "Booster pump" (names need not be unique).
		const project = withoutScenarios(oneOff.project);
		for (const c of project.components) if (c.type === 'pump') c.name = 'Booster pump';
		const plan = planFor(project);
		expect(plan.add).toEqual([
			{ pumpId: 'PA', id: 'S1', name: 'Booster pump (PA) off' },
			{ pumpId: 'PB', id: 'S2', name: 'Booster pump (PB) off' }
		]);
		expect(plan.about).toBe(
			'Makes one scenario per pump running in the base case (Booster pump (PA) and Booster pump (PB)): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.'
		);
		const made = withOnePumpOffCases(project, plan.add);
		const again = planFor(made);
		expect(again.notes).toEqual([
			'Booster pump (PA) has its case already: Booster pump (PA) off.',
			'Booster pump (PB) has its case already: Booster pump (PB) off.'
		]);
		expect(new Set(again.notes).size).toBe(2);
		// A name only one member has keeps its plain words.
		const one = structuredClone(project);
		one.components.find((c) => c.id === 'PB')!.name = 'Pump PB';
		expect(planFor(one).add.map((a) => a.name)).toEqual(['Booster pump off', 'Pump PB off']);
	});

	it('tells a case with one pump off by its one change', () => {
		const [s1, s2, s3, s4] = oneOff.project.scenarios!;
		expect(isOnePumpOff(s1!, 'PA')).toBe(true);
		expect(isOnePumpOff(s2!, 'PB')).toBe(true);
		expect(isOnePumpOff(s1!, 'PB')).toBe(false);
		expect(isOnePumpOff(s3!, 'PA')).toBe(false);
		// Two changes, or a status on.
		expect(isOnePumpOff(s4!, 'PA')).toBe(false);
		const on: Scenario = {
			id: 'S9',
			name: 'On',
			overrides: [{ kind: 'component', componentId: 'PA', field: 'status', value: 'on' }]
		};
		expect(isOnePumpOff(on, 'PA')).toBe(false);
		expect(offOverride('PA')).toEqual({
			kind: 'component',
			componentId: 'PA',
			field: 'status',
			value: 'off'
		});
	});

	it('gives no case to a pump on but held at zero flow, and says why', () => {
		const c = named('one-off-dead-headed');
		const plan = onePumpOffPlan({
			project: withoutScenarios(c.project),
			shownCase: null,
			station: body(c.groupCurve).station,
			memberIds: c.memberIds,
			base: { response: c.solve, stale: false }
		});
		expect(plan.add).toEqual([{ pumpId: 'PA', id: 'S1', name: 'Pump PA off' }]);
		expect(plan.idle).toEqual(['PB']);
		expect(plan.notes).toEqual([
			"Pump PB carries no flow in the base case, so with it off the base case's state is the same: no case is made for it."
		]);
		expect(plan.about).toBe(
			'Makes one scenario per pump running in the base case (Pump PA): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.'
		);
		// The fixture's S1 is what the add makes.
		expect(withOnePumpOffCases(withoutScenarios(c.project), plan.add).scenarios).toEqual(
			c.project.scenarios
		);
	});

	it('is offered for a parallel station from the base case, current, with two pumps on, one running', () => {
		const project = withoutScenarios(oneOff.project);
		const series = body(named('series').groupCurve).station;
		const mixed = { ...station, arrangement: 'mixed' as const };
		const gate = (overrides: Partial<Parameters<typeof onePumpOffPlan>[0]>) =>
			planFor(project, overrides);
		expect(gate({ station: series }).gate).toBe(
			'Cases with one pump off are offered for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.'
		);
		expect(gate({ station: series }).showSolveAll).toBe(false);
		expect(gate({ station: mixed }).gate).toBe(
			'Cases with one pump off are offered for pumps in parallel only; this station is mixed: neither all in parallel nor all in series.'
		);
		const shown = gate({ project: oneOff.project, shownCase: 'S3' });
		expect(shown.gate).toBe(
			'Cases with one pump off are made from the base case: show the base case to add them. To study Delivery tank 5 m higher with a pump off, duplicate it in Scenarios and set that pump off there.'
		);
		expect(shown.showSolveAll).toBe(false);
		// The arrangement first: a series station in a scenario says why in series.
		expect(gate({ station: series, shownCase: 'S3', project: oneOff.project }).gate).toMatch(
			/^Cases with one pump off are offered for pumps in parallel only: in series/
		);
		const stale = gate({ base: { response: oneOff.solve, stale: true } });
		expect(stale.gate).toBe(
			"The base case's results are out of date: solve it again, so the pumps that run are read from the project as it is now."
		);
		expect(stale.showSolveAll).toBe(true);
		const off = gate({ base: { response: withStatus(oneOff.solve, 'PB', 'off'), stale: false } });
		expect(off.gate).toBe(
			'Needs two or more of these pumps switched on in the base case: Pump PB is off.'
		);
		expect(off.showSolveAll).toBe(true);
		const bothOff = gate({
			base: {
				response: withStatus(withStatus(oneOff.solve, 'PB', 'off'), 'PA', 'off'),
				stale: false
			}
		});
		expect(bothOff.gate).toBe(
			'Needs two or more of these pumps switched on in the base case: Pump PA and Pump PB are off.'
		);
		const none = gate({
			base: {
				response: withStatus(withStatus(oneOff.solve, 'PB', 'no_flow'), 'PA', 'no_flow'),
				stale: false
			}
		});
		expect(none.gate).toBe(
			'No pump of the group runs in the base case, so switching one off changes nothing.'
		);
		expect(none.showSolveAll).toBe(true);
		for (const plan of [off, none, stale, shown]) expect(plan.add).toEqual([]);
		// No station: no block.
		expect(gate({ station: null })).toMatchObject({ gate: null, add: [], showSolveAll: false });
	});
});

describe('the rest of the network and the duty claim', () => {
	/** A case as solved: the project as sent with its scenario applied (store.caseInputs). */
	const solvedAs = (project: Project, caseId: string | null) =>
		caseId === null ? project : applyScenario(project, caseId).project;
	const withExtra = (overrides: Scenario['overrides']) =>
		withScenarios(structuredClone(oneOff.project), [
			...oneOff.project.scenarios!,
			{ id: 'S9', name: 'Extra', overrides }
		]);
	const shared = (shown: Project | null, other: Project | null, s: PumpGroupStation = station) =>
		sharedRest(shown, other, s, hydraulicFingerprint);
	const base = oneOff.project;

	it('compares each case as solved without the station inside', () => {
		expect(restOf(base, station).components.map((c) => c.id)).toEqual(['R1', 'R2']);
		expect(restOf(base, station).connections.map((c) => c.id)).toEqual(['L1', 'L2']);
		expect(shared(solvedAs(base, 'S1'), solvedAs(base, null))).toBe(true);
		expect(shared(solvedAs(base, 'S2'), solvedAs(base, 'S1'))).toBe(true);
		expect(shared(solvedAs(base, 'S4'), solvedAs(base, null))).toBe(true);
		expect(shared(solvedAs(base, 'S3'), solvedAs(base, null))).toBe(false);
		expect(shared(null, solvedAs(base, null))).toBe(false);
	});

	it('counts what the solve sees outside the station, never what does not change it', () => {
		const fluid = withExtra([{ kind: 'project', field: 'fluid.temperature', value: 313.15 }]);
		expect(shared(solvedAs(fluid, 'S9'), solvedAs(fluid, null))).toBe(false);
		const sameLevel = withExtra([
			{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 2.0 }
		]);
		expect(shared(solvedAs(sameLevel, 'S9'), solvedAs(sameLevel, null))).toBe(true);
		const speed = withExtra([{ kind: 'component', componentId: 'PB', field: 'speed', value: 0.9 }]);
		expect(shared(solvedAs(speed, 'S9'), solvedAs(speed, null))).toBe(true);
		const spec = withExtra([
			{
				kind: 'pipe',
				connectionId: 'LA1',
				pipeIndex: 0,
				field: 'spec',
				value: { materialId: 'custom', innerDiameter: 0.09, roughness: 4.5e-5 }
			}
		]);
		expect(solvedAs(spec, 'S9').connections.find((c) => c.id === 'LA1')).not.toEqual(
			base.connections.find((c) => c.id === 'LA1')
		);
		expect(shared(solvedAs(spec, 'S9'), solvedAs(spec, null))).toBe(true);
	});

	it('tells a case solved on an earlier base: an outside pipe edited since', () => {
		const edited = structuredClone(base);
		edited.connections.find((c) => c.id === 'L2')!.piping.pipes[0]!.length += 10;
		// The base solved again now; S1 solved on the base before the edit.
		expect(shared(solvedAs(edited, null), solvedAs(base, 'S1'))).toBe(false);
	});

	it('leaves out what changes no value outside: the design checks, library entries only the inside uses', () => {
		// The base edited since S2 was solved (synthetic edits), then solved again.
		const checks = structuredClone(base);
		checks.settings.designChecks!.npshMargin!.minimumMargin = 2.0;
		expect(hydraulicFingerprint(checks)).not.toBe(hydraulicFingerprint(base));
		expect(shared(solvedAs(checks, null), solvedAs(base, 'S2'))).toBe(true);
		// Curve PC-A: only PA and PB, inside the station, use it.
		const curve = structuredClone(base);
		for (const p of curve.pumpLibrary[0]!.points) p.head *= 1.02;
		expect(shared(solvedAs(curve, null), solvedAs(base, 'S2'))).toBe(true);
		expect(restOf(base, station).pumpLibrary).toEqual([]);
		// A pipe spec on an interior pipe only, added since: no library outside either way.
		const spec: PipeSpec = {
			id: 'PS1',
			name: 'Bore of LA1',
			source: 'synthetic',
			materialId: 'custom',
			innerDiameter: base.connections.find((c) => c.id === 'LA1')!.piping.pipes[0]!.innerDiameter!,
			roughness: null
		};
		const inside = structuredClone(base);
		inside.pipeLibrary = [spec];
		inside.connections.find((c) => c.id === 'LA1')!.piping.pipes[0]!.specId = 'PS1';
		expect(shared(solvedAs(inside, null), solvedAs(base, 'S2'))).toBe(true);
		// The same spec on an outside pipe, edited: another rest.
		const outside = structuredClone(inside);
		outside.connections.find((c) => c.id === 'L2')!.piping.pipes[0]!.specId = 'PS1';
		const respec = structuredClone(outside);
		respec.pipeLibrary![0]!.innerDiameter = 0.2;
		expect(restOf(outside, station).pipeLibrary!.map((s) => s.id)).toEqual(['PS1']);
		expect(shared(solvedAs(respec, null), solvedAs(outside, 'S2'))).toBe(false);
		// A resistance entry on an interior fitting, then on an outside one, edited.
		const entry: ResistanceSpec = {
			id: 'RS1',
			name: 'Elbow',
			source: 'synthetic',
			kind: 'Cv',
			value: 400
		};
		const valved = structuredClone(base);
		valved.resistanceLibrary = [entry];
		valved.connections.find((c) => c.id === 'LA1')!.piping.fittings[0]!.resistanceId = 'RS1';
		const revalued = structuredClone(valved);
		revalued.resistanceLibrary![0]!.value = 500;
		expect(shared(solvedAs(revalued, null), solvedAs(valved, 'S2'))).toBe(true);
		const outer = structuredClone(valved);
		outer.connections.find((c) => c.id === 'L2')!.piping.fittings[0]!.resistanceId = 'RS1';
		const outerRevalued = structuredClone(outer);
		outerRevalued.resistanceLibrary![0]!.value = 500;
		expect(shared(solvedAs(outerRevalued, null), solvedAs(outer, 'S2'))).toBe(false);
		// A pump outside the station on the members' curve (synthetic, unconnected): its curve
		// edited changes the rest.
		const pa = base.components.find((c) => c.id === 'PA')!;
		const booster = structuredClone(base);
		booster.components.push({ ...structuredClone(pa), id: 'PX', name: 'Booster PX' });
		const reshaped = structuredClone(booster);
		for (const p of reshaped.pumpLibrary[0]!.points) p.head *= 1.02;
		expect(restOf(booster, station).pumpLibrary.map((c) => c.id)).toEqual(['PC-A']);
		expect(shared(solvedAs(reshaped, null), solvedAs(booster, 'S2'))).toBe(false);
	});

	it('takes a reservoir taken whole as an outside element (not in the interior)', () => {
		const whole: PumpGroupStation = {
			...station,
			inlet: { componentId: 'R1', portId: null }
		};
		expect(whole.interiorComponentIds).not.toContain('R1');
		const level = withExtra([
			{ kind: 'component', componentId: 'R1', field: 'liquidLevel', value: 3.5 }
		]);
		expect(shared(solvedAs(level, 'S9'), solvedAs(level, null), whole)).toBe(false);
	});

	it('tells the same station by its ports, arrangement, members and interior', () => {
		expect(sameStation(body(scenarioCase('S1').groupCurve).station, station)).toBe(true);
		expect(
			sameStation(
				{ ...station, interiorConnectionIds: station.interiorConnectionIds.slice(1) },
				station
			)
		).toBe(false);
		expect(sameStation({ ...station, inlet: station.outlet, outlet: station.inlet }, station)).toBe(
			false
		);
	});

	it('calls a duty a point of the curve shown only on the same rest, above zero flow, between risen points, the shown duty on it', () => {
		const duty = (id: string) => body(scenarioCase(id).groupCurve).duty!;
		expect(dutyClaim({ shared: true, duty: duty('S1'), system: baseSystem })).toBe('on');
		expect(dutyClaim({ shared: true, duty: duty('S2'), system: baseSystem })).toBe('on');
		expect(dutyClaim({ shared: false, duty: duty('S3'), system: baseSystem })).toBe('rest_differs');
		expect(dutyClaim({ shared: true, duty: duty('S4'), system: baseSystem })).toBe('zero_flow');
		// With "Pump PA off" shown, the base's flow lies beyond that case's own curve.
		const s1System = body(scenarioCase('S1').systemCurve);
		const baseDuty = body(oneOff.groupCurve).duty!;
		expect(s1System.flowRange!.max).toBeLessThan(baseDuty.flow);
		expect(dutyClaim({ shared: true, duty: baseDuty, system: s1System })).toBe('beyond_range');
		expect(dutyClaim({ shared: true, duty: duty('S1'), system: null })).toBe('no_curve');
		// Synthetic: a point next to the flow without a rise; the shown duty off its curve.
		const gap = structuredClone(baseSystem);
		const q = duty('S1').flow;
		const next = [...gap.systemPoints].sort((a, b) => a.flow - b.flow).find((p) => p.flow >= q)!;
		next.head = null;
		expect(dutyClaim({ shared: true, duty: duty('S1'), system: gap })).toBe('gap');
		const off = structuredClone(baseSystem);
		off.systemDutyCheck!.agrees = false;
		expect(dutyClaim({ shared: true, duty: duty('S1'), system: off })).toBe('shown_duty');
	});

	it('words a different rest as the two cases’ difference, whichever is shown', () => {
		// "Delivery tank 5 m higher" shown: the base and "Pump PA off" change nothing outside, yet
		// their rests differ from the case shown's, so neither is said to change it.
		const s3 = solvedAs(base, 'S3');
		const s3System = body(scenarioCase('S3').systemCurve);
		const baseDuty = body(oneOff.groupCurve).duty!;
		const claim = dutyClaim({
			shared: shared(s3, solvedAs(base, null)),
			duty: baseDuty,
			system: s3System
		});
		expect(claim).toBe('rest_differs');
		expect(DUTY_CLAIM_WORDS[claim]).toBe(
			"No: the rest of the network differs from this case's; its own group system curve is not drawn"
		);
		expect(DUTY_CLAIM_WORDS[claim]).not.toMatch(/it changes/);
		expect(shared(s3, solvedAs(base, 'S1'))).toBe(false);
	});

	it('words each claim and the rule', () => {
		expect(DUTY_CLAIM_WORDS).toEqual({
			on: 'Yes: the same rest of the network',
			rest_differs:
				"No: the rest of the network differs from this case's; its own group system curve is not drawn",
			no_curve: 'Not said: no group system curve is drawn for this case',
			zero_flow: 'Not said: at zero station flow the rest can hold more than one state (D13)',
			beyond_range: 'Not said: its flow is beyond the flows this curve was computed for',
			gap: 'Not said: the curve has no rise next to its flow',
			shown_duty: "Not said: this case's own duty is not on the curve (D13)"
		});
		expect(DUTY_CLAIM_RULE).toBe(
			"A ring is called a point of the group system curve shown only when its case, as solved, is the same as this one outside the station, its station flow is above zero, the curve has a rise at the computed flows on both sides of it, and this case's own duty is on the curve. Its duty is then a steady state of the same rest of the network, so it lies on the curve wherever the rest has one state at its flow; the curve is drawn through sampled points, each the state the system curve's starts find (D13)."
		);
	});
});

describe('the other cases on the chart', () => {
	const keys = ['S1', 'S2', 'S3', 'S4'].map((id) => ({ key: id, caseId: id }));
	const ready = (a: Answer): GroupCurveState => ({ status: 'ready', response: body(a) });
	/** The four scenario cases of `one-off`, every curve answered, each sharing the rest but S3. */
	function input(values: Partial<OtherCasesInput> = {}): OtherCasesInput {
		return {
			valued: ['S1', 'S2', 'S3', 'S4'].map((id) => ({
				key: id,
				caseId: id,
				name: oneOff.project.scenarios!.find((s) => s.id === id)!.name,
				stale: false,
				group: ready(scenarioCase(id).groupCurve),
				system: undefined,
				shared: id !== 'S3',
				solved: applyScenario(oneOff.project, id).project
			})),
			shownKeys: new Set(['S1', 'S2', 'S3', 'S4']),
			othersOn: true,
			shownSettled: true,
			station,
			systemShown: baseSystem,
			memberIds: ['PA', 'PB'],
			project: oneOff.project,
			boxes: ['PA', 'PB'],
			...values
		};
	}

	it('puts the cases with one pump off first, then case order', () => {
		const project = withScenarios(structuredClone(oneOff.project), [
			{ id: 'S3', name: 'Tank', overrides: [] },
			...oneOff.project.scenarios!.filter((s) => s.id !== 'S3')
		]);
		const order = [{ key: '', caseId: null }, ...keys];
		expect(chartPriority(order, project, ['PA', 'PB'])).toEqual(['S1', 'S2', '', 'S3', 'S4']);
		// A member no longer in the group: its case is an ordinary case.
		expect(chartPriority(order, project, ['PA'])).toEqual(['S1', '', 'S2', 'S3', 'S4']);
	});

	it('takes at most six cases, those with one pump off first; an unticked case lets the next in', () => {
		const scenario = (id: string) => oneOff.project.scenarios!.find((s) => s.id === id)!;
		const level = (id: string, value: number): Scenario => ({
			id,
			name: `Delivery tank at ${value} m`,
			overrides: [{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value }]
		});
		// Seven cases with values in case order, the two with one pump off third and fifth.
		const project = withScenarios(structuredClone(oneOff.project), [
			scenario('S3'),
			scenario('S1'),
			level('S5', 3),
			scenario('S2'),
			scenario('S4'),
			level('S6', 4)
		]);
		const valued = ['', 'S3', 'S1', 'S5', 'S2', 'S4', 'S6'].map((key) => ({
			key,
			caseId: key || null
		}));
		const members = ['PA', 'PB'];
		expect(MAX_GROUP_CASES).toBe(6);
		expect(chartKeys(valued, project, members, [])).toEqual(['S1', 'S2', '', 'S3', 'S5', 'S4']);
		// One unticked: the next case in that order comes in.
		expect(chartKeys(valued, project, members, ['S3'])).toEqual(['S1', 'S2', '', 'S5', 'S4', 'S6']);
		expect(chartKeys(valued, project, members, ['S1'])).toEqual(['S2', '', 'S3', 'S5', 'S4', 'S6']);
		// Six or fewer: every case ticked.
		expect(chartKeys(valued.slice(0, 4), project, members, [''])).toEqual(['S1', 'S3', 'S5']);
	});

	it('numbers the rings in case order, each with its duty and claim', () => {
		const others = otherGroupCases(input());
		expect(others.map((o) => [o.key, o.state, o.number, o.claim])).toEqual([
			['S1', 'ready', 1, 'on'],
			['S2', 'ready', 2, 'on'],
			['S3', 'ready', 3, 'rest_differs'],
			['S4', 'ready', 4, 'zero_flow']
		]);
		expect(others[0]!.duty).toEqual({
			flow: body(scenarioCase('S1').groupCurve).duty!.flow,
			head: body(scenarioCase('S1').groupCurve).duty!.head
		});
		expect(others[0]!.words).toBe('Yes: the same rest of the network');
		// Unticked: no ring, and the next is numbered on.
		const unticked = otherGroupCases(input({ shownKeys: new Set(['S2', 'S3', 'S4']) }));
		expect(unticked.map((o) => [o.state, o.number])).toEqual([
			['unticked', null],
			['ready', 1],
			['ready', 2],
			['ready', 3]
		]);
	});

	it('words every state', () => {
		const one = (
			group: GroupCurveState | undefined,
			values: Partial<OtherCasesInput> = {},
			system?: GroupCurveState
		) => {
			const base = input(values);
			const [first] = base.valued;
			return otherGroupCases({ ...base, valued: [{ ...first!, group, system }] })[0]!;
		};
		const words = (o: ReturnType<typeof one>) => [o.state, o.words, o.retry];
		expect(words(one(undefined, { shownKeys: new Set() }))).toEqual([
			'unticked',
			'not on the chart (unticked under Cases on this chart)',
			false
		]);
		expect(words(one(undefined, { othersOn: false }))).toEqual([
			'off',
			"not computed: tick “Also show the other cases' station duties”",
			false
		]);
		// With the box off, "Cases on this chart" is not shown: an unticked case is off too.
		expect(words(one(undefined, { othersOn: false, shownKeys: new Set() }))).toEqual([
			'off',
			"not computed: tick “Also show the other cases' station duties”",
			false
		]);
		expect(words(one(undefined, { shownSettled: false }))).toEqual([
			'waiting',
			"waits for this case's curves",
			false
		]);
		// Not asked yet while a calculation runs: no other case is asked then, so it waits for it
		// (then for the case shown's curves, while those are still to answer).
		expect(words(one(undefined, { calculating: 'solveAll' }))).toEqual([
			'waiting',
			'waits for Solve all to end',
			false
		]);
		expect(words(one(undefined, { calculating: 'solve', shownSettled: false }))).toEqual([
			'waiting',
			"waits for the solve to end, then for this case's curves",
			false
		]);
		expect(words(one(undefined, { calculating: 'goalSeek' }))).toEqual([
			'waiting',
			'waits for the goal seek to end',
			false
		]);
		// Not asked yet with no calculation and the case shown's curves answered: asked this turn.
		expect(words(one(undefined, { calculating: null }))).toEqual([
			'loading',
			'being computed',
			false
		]);
		expect(words(one({ status: 'loading' }))).toEqual(['loading', 'being computed', false]);
		expect(words(one({ status: 'cancelled', by: 'user' }))).toEqual([
			'cancelled',
			'cancelled: you cancelled it',
			true
		]);
		expect(words(one({ status: 'cancelled', by: 'solve' }))).toEqual([
			'cancelled',
			'cancelled by a solve; asked again when it ends',
			false
		]);
		expect(words(one({ status: 'cancelled', by: 'goalSeek' }))).toEqual([
			'cancelled',
			'cancelled by a goal seek; asked again when it ends',
			false
		]);
		expect(
			words(one({ status: 'error', message: 'Too many requests; try again in a minute.' }))
		).toEqual(['error', 'failed: Too many requests; try again in a minute.', true]);
		const noDuty = structuredClone(body(scenarioCase('S1').groupCurve));
		noDuty.duty = null;
		noDuty.message = "the station's outlet is closed off in this case";
		expect(words(one({ status: 'ready', response: noDuty }))).toEqual([
			'no_duty',
			"no duty: the station's outlet is closed off in this case.",
			false
		]);
		const elsewhere = structuredClone(body(scenarioCase('S1').groupCurve));
		elsewhere.station = { ...elsewhere.station, inlet: { componentId: 'R1', portId: null } };
		expect(words(one({ status: 'ready', response: elsewhere }))).toEqual([
			'other_station',
			'another station in this case: from Reservoir R1 to Tee T2 (run outlet) there',
			false
		]);
	});

	it('words a refusal as the card does, and takes a PRV-refused case’s duty from its system curve', () => {
		const refused = named('refused');
		const issues = (refused.groupCurve.body as { issues: TopologyIssue[] }).issues;
		const base = input();
		const [first] = base.valued;
		const [o] = otherGroupCases({
			...base,
			project: refused.project,
			valued: [
				{
					...first!,
					solved: refused.project,
					group: { status: 'refused', message: 'Not a station.', issues }
				}
			]
		});
		expect(o!.state).toBe('refused');
		// The card's own words for the first issue, with that case's topology.
		const words = wordsText(
			refusalWords(issues[0]!, ['PA', 'PB'], refused.project, {
				solved: refused.project,
				boxes: ['PA', 'PB']
			})
		);
		expect(o!.words).toBe(`not a station in this case: ${words}`);
		expect(words).toMatch(/^The pumps meet the fixed heads of Reservoir R2 and Tank R4,/);
		const prv = named('prv-inside');
		const prvIssues = (prv.groupCurve.body as { issues: TopologyIssue[] }).issues;
		const prvGroup: GroupCurveState = { status: 'refused', message: 'PRV', issues: prvIssues };
		const prvStation = body(prv.systemCurve!).station;
		const answered = otherGroupCases({
			...base,
			station: prvStation,
			valued: [
				{ ...first!, group: prvGroup, system: undefined },
				{ ...first!, key: 'S2', caseId: 'S2', group: prvGroup, system: ready(prv.systemCurve!) }
			]
		});
		expect(answered.map((x) => [x.state, x.number])).toEqual([
			['loading', null],
			['ready', 1]
		]);
		expect(answered[1]!.duty!.flow).toBe(body(prv.systemCurve!).duty!.flow);
	});
});

describe('Running combinations', () => {
	const prefs = oneOff.project.settings.units;
	const members = [
		{ id: 'PA', name: 'Pump PA', slot: 0 },
		{ id: 'PB', name: 'Pump PB', slot: 1 }
	];
	/** Every case of `one-off`, the base shown, each with its fixture solve. */
	function combinationsInput(values: Partial<CombinationsInput> = {}): CombinationsInput {
		return {
			members,
			cases: [null, 'S1', 'S2', 'S3', 'S4'].map((id) => ({
				key: id ?? '',
				name: id ? oneOff.project.scenarios!.find((s) => s.id === id)!.name : 'Base case',
				shown: id === null,
				status: 'solved' as const,
				response: id ? scenarioCase(id).solve : oneOff.solve,
				stale: false,
				station: null
			})),
			prefs,
			project: oneOff.project,
			...values
		};
	}
	const groupMembers = (c: FixtureCase): GroupMemberInput[] =>
		c.memberIds.map((id, slot) => {
			const pump = c.project.components.find((x) => x.id === id)!;
			return {
				id,
				name: pump.name,
				result: c.solve.solvedState.pumpResults[id] as PumpResult,
				ratedRange: ratedCurveRange(c.project, id),
				curveId: pump.type === 'pump' ? pump.curveId : null,
				slot,
				flags: (c.solve.solvedState.flags as Flag[]).filter((f) => f.componentId === id)
			};
		});

	it('lists every case, the shown first, with the group table’s cells for the case shown', () => {
		const table = runningCombinations(combinationsInput());
		expect(table.groups.map((g) => g.heading)).toEqual([
			'Base case (shown)',
			'Pump PA off',
			'Pump PB off',
			'Delivery tank 5 m higher',
			'Both pumps off'
		]);
		// Pump PB runs at 0.85 in the base: the speed column, as the group table has it.
		expect(table.columns.map((c) => c.key)).toEqual([
			'state',
			'speed',
			'flow',
			'head',
			'shaftPower',
			'npshMargin',
			'inCurve',
			'checks'
		]);
		const group = groupTable(
			groupMembers(oneOff),
			oneOff.solve.solvedState.nodeResults,
			null,
			prefs,
			oneOff.project
		);
		const shown = table.groups[0]!;
		for (const [i, row] of shown.rows.entries()) {
			const expected = group.rows[i]!;
			expect(row.id).toBe(expected.id);
			for (const key of ['state', 'speed', 'flow', 'head', 'shaftPower', 'npshMargin', 'inCurve']) {
				expect(row.cells[key], key).toBe(expected.cells[key]);
			}
			expect(row.flags).toEqual(expected.flags);
			expect(row.style).toEqual(expected.style);
		}
		expect(shown.rows[0]!.cells.checks).toBe(
			'Not met: Operating region, Motor power · Met: NPSH margin'
		);
		const pbOff = table.groups[2]!;
		expect(pbOff.rows[0]!.cells.inCurve).toBe('No: beyond its data');
		expect(pbOff.rows[0]!.flags.map((f) => [f.code, f.severity])).toContainEqual([
			'PUMP_OUTSIDE_CURVE',
			'warning'
		]);
		expect(pbOff.rows[1]!.cells.state).toBe('Off');
		expect(table.groups[4]!.rows.map((r) => r.cells.state)).toEqual(['Off', 'Off']);
	});

	it('marks a pump held at zero flow as physically invalid, with its words', () => {
		const c = named('one-off-dead-headed');
		const table = runningCombinations({
			members,
			cases: [
				{
					key: '',
					name: 'Base case',
					shown: true,
					status: 'solved',
					response: c.solve,
					stale: false,
					station: null
				}
			],
			prefs,
			project: c.project
		});
		const pb = table.groups[0]!.rows[1]!;
		expect(pb.cells.state).toBe('No flow (system head above shutoff)');
		expect(pb.invalid).toBe(true);
		expect(pb.flags.map((f) => f.code)).toContain('PUMP_FLOW_REVERSAL');
		expect(table.groups[0]!.rows[0]!.invalid).toBe(false);
		// No design checks in that project: no column.
		expect(table.columns.map((col) => col.key)).not.toContain('checks');
	});

	it('gives a case without values Compare’s words, and no rows', () => {
		const notConverged = structuredClone(scenarioCase('S1').solve);
		notConverged.solvedState.converged = false;
		const base = combinationsInput();
		const table = runningCombinations({
			...base,
			cases: [
				base.cases[0]!,
				{ ...base.cases[1]!, status: 'not_converged', response: notConverged },
				{ ...base.cases[2]!, status: 'failed', response: null },
				{ ...base.cases[3]!, status: 'not_solved', response: null }
			]
		});
		expect(table.groups.slice(1).map((g) => [g.detail, g.values, g.rows.length])).toEqual([
			['Did not converge: no values shown', false, 0],
			['Failed', false, 0],
			['Not solved', false, 0]
		]);
	});

	it('adds the speed column when a pump that is on runs at another speed or under a control', () => {
		const only = (c: FixtureCase) =>
			runningCombinations({
				members,
				cases: [
					{
						key: '',
						name: 'Base case',
						shown: true,
						status: 'solved',
						response: c.solve,
						stale: false,
						station: null
					}
				],
				prefs: c.project.settings.units,
				project: c.project
			});
		expect(only(named('controlled')).columns.map((col) => col.key)).toContain('speed');
		// Pump PB at a fixed 0.85 in every case of `one-off`; off in "Pump PB off".
		const table = runningCombinations(combinationsInput());
		expect(table.columns.map((col) => col.key)).toContain('speed');
		// In % as the group table gives it (its cells for the case shown are compared above).
		expect(table.columns.find((col) => col.key === 'speed')!.unit).toBe('%');
		expect(table.groups[0]!.rows.map((r) => r.cells.speed)).toEqual(['100', '85']);
		expect(table.groups[2]!.rows.map((r) => r.cells.speed)).toEqual(['100', '—']);
		// Both pumps at speed 1 without a control: no column.
		const plain = named('refused-own-loops');
		expect(
			Object.values(plain.solve.solvedState.pumpResults).map((r) => [r.speed, r.control])
		).toEqual([
			[1, null],
			[1, null]
		]);
		expect(only(plain).columns.map((col) => col.key)).not.toContain('speed');
		// Off at another speed: its speed is never shown, so no column for it alone.
		const off = named('off');
		expect(off.solve.solvedState.pumpResults.PB).toMatchObject({ status: 'off', speed: 0.85 });
		expect(only(off).columns.map((col) => col.key)).not.toContain('speed');
	});

	it('heads each group with its state and ring, an out-of-date one tinted', () => {
		const base = combinationsInput();
		const table = runningCombinations({
			...base,
			cases: [
				{ ...base.cases[0]!, station: 'Station 55.15 L/s at a rise of 27.38 m' },
				{ ...base.cases[1]!, stale: true, ring: 1, station: 'line' }
			]
		});
		expect(table.groups[0]!.detail).toBe('Station 55.15 L/s at a rise of 27.38 m');
		expect(table.groups[1]!.heading).toBe('Pump PA off (out of date) · ring 1');
		expect(table.groups[1]!.stale).toBe(true);
	});
});

describe('the extremes over the cases', () => {
	const prefs = oneOff.project.settings.units;
	const members = [
		{ id: 'PA', name: 'Pump PA', slot: 0 },
		{ id: 'PB', name: 'Pump PB', slot: 1 }
	];
	const all = (ids: (string | null)[] = [null, 'S1', 'S2', 'S3', 'S4']): CombinationsInput => ({
		members,
		cases: ids.map((id) => ({
			key: id ?? '',
			name: id ? oneOff.project.scenarios!.find((s) => s.id === id)!.name : 'Base case',
			shown: id === null,
			status: 'solved' as const,
			response: id ? scenarioCase(id).solve : oneOff.solve,
			stale: false,
			station: null
		})),
		prefs,
		project: oneOff.project
	});

	it('gives each pump’s largest flow and shaft power and smallest NPSH margin, with its case', () => {
		const { lines, notCounted } = combinationExtremes(all());
		expect(notCounted).toEqual([]);
		const line = (term: string) => lines.find((l) => l.term === term)!.value;
		expect(line('Pump PA, largest flow')).toBe(
			'40.75 L/s in Pump PB off; beyond its curve data (over 5 of 5 cases)'
		);
		expect(line('Pump PA, largest shaft power')).toMatch(
			/^15\.02 kW in Base case \(over 3 of 5 cases; no value in 2\)$/
		);
		expect(line('Pump PA, smallest NPSH margin')).toBe(
			'6.806 m in Pump PB off; beyond its curve data (over 3 of 5 cases; no value in 2)'
		);
		expect(lines.map((l) => l.term)).toEqual([
			'Pump PA, largest flow',
			'Pump PA, largest shaft power',
			'Pump PA, smallest NPSH margin',
			'Pump PB, largest flow',
			'Pump PB, largest shaft power',
			'Pump PB, smallest NPSH margin'
		]);
	});

	it('keys each line by the pump and the measure, and tells two pumps of the same name apart', () => {
		// Synthetic: both members named "Booster pump" (names need not be unique).
		const twins = { ...all(), members: members.map((m) => ({ ...m, name: 'Booster pump' })) };
		// Running combinations' row headers too (the slot's symbol is hidden from screen readers).
		const rows = runningCombinations(twins).groups.map((g) => g.rows.map((r) => [r.id, r.name]));
		expect(rows).toHaveLength(5);
		for (const group of rows) {
			expect(group).toEqual([
				['PA', 'Booster pump (PA)'],
				['PB', 'Booster pump (PB)']
			]);
		}
		expect(runningCombinations(all()).groups[0]!.rows.map((r) => r.name)).toEqual([
			'Pump PA',
			'Pump PB'
		]);
		const { lines } = combinationExtremes(twins);
		expect(lines.map((l) => l.key)).toEqual([
			'PA:operatingFlow',
			'PA:shaftPower',
			'PA:npshMargin',
			'PB:operatingFlow',
			'PB:shaftPower',
			'PB:npshMargin'
		]);
		expect(lines.map((l) => l.term)).toEqual([
			'Booster pump (PA), largest flow',
			'Booster pump (PA), largest shaft power',
			'Booster pump (PA), smallest NPSH margin',
			'Booster pump (PB), largest flow',
			'Booster pump (PB), largest shaft power',
			'Booster pump (PB), smallest NPSH margin'
		]);
		// Names of their own: the plain words.
		expect(combinationExtremes(all()).lines[0]!.term).toBe('Pump PA, largest flow');
	});

	it('names the other cases on equal doubles', () => {
		const input = all();
		const copy = { ...input.cases[2]!, key: 'S5', name: 'Copy of Pump PB off', shown: false };
		const { lines } = combinationExtremes({ ...input, cases: [...input.cases, copy] });
		expect(lines.find((l) => l.term === 'Pump PA, largest flow')!.value).toBe(
			'40.75 L/s in Pump PB off and 1 other case; beyond its curve data (over 6 of 6 cases)'
		);
	});

	it('counts current cases only, names those out of date, and needs two', () => {
		const input = all();
		const stale = { ...input.cases[2]!, stale: true };
		const { lines, notCounted } = combinationExtremes({
			...input,
			cases: [input.cases[0]!, input.cases[1]!, stale, input.cases[3]!]
		});
		expect(notCounted).toEqual(['Pump PB off']);
		expect(lines.find((l) => l.term === 'Pump PA, largest flow')!.value).toBe(
			'37.37 L/s in Base case (over 3 of 3 cases)'
		);
		expect(combinationExtremes(all([null])).lines).toEqual([]);
		const none = combinationExtremes(all([null, 'S4']));
		expect(none.lines.find((l) => l.term === 'Pump PA, largest shaft power')!.value).toBe(
			'15.02 kW in Base case (over 1 of 2 cases; no value in 1)'
		);
		const dead = named('one-off-dead-headed');
		const invalid = combinationExtremes({
			members,
			cases: [
				{
					key: '',
					name: 'Base case',
					shown: true,
					status: 'solved',
					response: dead.solve,
					stale: false,
					station: null
				},
				{
					key: 'S1',
					name: 'Pump PA off',
					shown: false,
					status: 'solved',
					response: dead.scenarioCases!.S1!.solve,
					stale: false,
					station: null
				}
			],
			prefs,
			project: dead.project
		});
		const pbHead = invalid.lines.find((l) => l.term === 'Pump PB, smallest NPSH margin')!;
		expect(pbHead.value).toBe('no case gives one');
		const pbFlow = invalid.lines.find((l) => l.term === 'Pump PB, largest flow')!;
		expect(pbFlow.value).toMatch(/ in Pump PA off \(over 2 of 2 cases\)$/);
		expect(pbFlow.invalid).toBe(false);
		// Held at zero flow in both (synthetic: the base twice): physically invalid where it is.
		const held = combinationExtremes({
			members,
			cases: ['Base case', 'Copy'].map((name, i) => ({
				key: String(i),
				name,
				shown: i === 0,
				status: 'solved' as const,
				response: dead.solve,
				stale: false,
				station: null
			})),
			prefs,
			project: dead.project
		});
		const pbHeld = held.lines.find((l) => l.term === 'Pump PB, largest flow')!;
		expect(pbHeld.value).toBe(
			'0 L/s in Base case and 1 other case; physically invalid (over 2 of 2 cases)'
		);
		expect(pbHeld.invalid).toBe(true);
	});
});
