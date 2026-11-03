/**
 * Pump groups in the export (CLAUDE.md D21, slice 4c; proposal pump-groups.md §8 and §16): each
 * group the Pumps together card computed for a case's solve, only as computed and only for a case
 * with values, in five sheets after System curves (Pump groups, Pump group members, Group curves,
 * Group curve members, Group system curves); the groups left out, with why, in About and the
 * dialog; About's group rows and the Methods' group sections only in a file that has them.
 *
 * (a) The shared export fixture's `pump-groups` case (export-input.json: real API responses, two
 * pumps in parallel with an FCV outside the station, and a scenario with PB off), in SI and in
 * display units: every number cell against the API's double through a column-to-field map
 * written here, every word against the card's own helpers.
 * (b) The pump-group fixture's cases (pump-groups-input.json: real API responses): series, a PRV
 * inside, no duty, a controlled member, an off member, a refusal.
 * (c) Synthetic, and labelled so: cloned, relabelled real responses, for the group order and a
 * point without a flow (no real response has one: proposal §14, PG11).
 */
import { describe, expect, it } from 'vitest';
import type {
	Project,
	PumpGroupCurveResponse,
	SolveResponse,
	TopologyIssue,
	UnitPreferences
} from '../../api/types';
import { groupKey, type GroupCurveState } from '../../state/project.svelte';
import groupFixture from '../__fixtures__/pump-groups-input.json';
import { PUMP_CONTROL_STATE_LABELS } from '../labels';
import {
	ARRANGEMENT_WORDS,
	dutyCheckState,
	groupMethodsLines,
	groupSampleRows,
	groupSystemRows,
	MEMBER_STATUS_WORDS,
	stationPortWords,
	systemDutyCheckState
} from '../pump-group-chart';
import { refusalWords, wordsText } from '../pump-groups';
import { flagsForElement, pumpStatusLabel } from '../results';
import { displayUnit, fromSI, type UnitCategory } from '../units';
import { fixtureInput, readSheet, sheetIds, type ReadSheet } from './export-testing.testing';
import { buildExport, type CellValue, type ExportBundle, type ExportInput } from './model';
import { SI_BASE_UNITS } from './units';

const KEY = groupKey(['PA', 'PB']);
const SHEETS = [
	['pump-groups', 'Pump groups'],
	['pump-group-members', 'Pump group members'],
	['group-curves', 'Group curves'],
	['group-curve-members', 'Group curve members'],
	['group-system-curves', 'Group system curves']
] as const;
const IDS = SHEETS.map(([id]) => id);
const NOT_COMPUTED =
	'Not computed: open the Pumps together card on this case, with these pumps ticked';
const NO_DUTY = 'Not defined: the station has no duty in this case';

function ready(state: GroupCurveState | undefined): PumpGroupCurveResponse {
	if (state?.status !== 'ready') throw new Error(`not ready: ${state?.status}`);
	return state.response;
}

/** The file's unit preferences: SI base units in an SI file, else the display units. */
const prefsOf = (input: ExportInput): UnitPreferences =>
	input.options.units === 'si' ? SI_BASE_UNITS : input.prefs;

/** A column: the API value it holds and its unit category (none: a pure number). */
type Field<T> = [
	label: string,
	value: (x: T) => number | null | undefined,
	category?: UnitCategory
];

/** Every number cell of `t` against its field: SI bit for bit, else fromSI(the display unit). */
function checkNumbers<T>(
	input: ExportInput,
	t: ReadSheet,
	find: (row: readonly CellValue[]) => T,
	fields: readonly Field<T>[]
): number {
	const si = input.options.units === 'si';
	let checked = 0;
	for (const row of t.rows) {
		const target = find(row);
		for (const [label, value, category] of fields) {
			const api = value(target);
			const cell = t.get(row, label);
			if (api === null || api === undefined) {
				expect(cell, `${t.sheet.id} ${label}`).toBeNull();
				continue;
			}
			if (si || !category) {
				expect(Object.is(cell, api), `${t.sheet.id} ${label}: ${cell} vs ${api}`).toBe(true);
			} else {
				expect(cell, `${t.sheet.id} ${label}`).toBe(
					fromSI(api, displayUnit(category, input.prefs))
				);
			}
			checked++;
		}
	}
	return checked;
}

/** A row's case, its group's maps and responses, read through its Case id and Group cells. */
function rowGroup(input: ExportInput, t: ReadSheet, row: readonly CellValue[]) {
	const caseId = t.labels.includes('Case id')
		? (t.get(row, 'Case id') as string | null)
		: input.cases[0]!.id;
	const c = input.cases.find((x) => x.id === caseId)!;
	const key = groupKey(String(t.get(row, 'Group')).split('+'));
	const group = c.groupCurves[key];
	const system = c.groupSystemCurves[key];
	return {
		c,
		group: group?.status === 'ready' ? group.response : null,
		system: system?.status === 'ready' ? system.response : null
	};
}

function pointOf(input: ExportInput, t: ReadSheet, row: readonly CellValue[]) {
	const { group } = rowGroup(input, t, row);
	const points = [...group!.points].sort((a, b) => a.head - b.head);
	return { group: group!, point: points[(t.get(row, 'Point #') as number) - 1]! };
}

function systemPointOf(input: ExportInput, t: ReadSheet, row: readonly CellValue[]) {
	const { system } = rowGroup(input, t, row);
	const points = [...system!.systemPoints].sort((a, b) => a.flow - b.flow);
	return { system: system!, point: points[(t.get(row, 'Point #') as number) - 1]! };
}

/** Every number cell of the five sheets against the API (both unit systems). */
function checkAllNumbers(input: ExportInput, bundle: ExportBundle): number {
	const ids = new Set(sheetIds(bundle));
	let checked = 0;
	if (ids.has('pump-groups')) {
		const t = readSheet(bundle, 'pump-groups');
		checked += checkNumbers(
			input,
			t,
			(r) => {
				const { group, system } = rowGroup(input, t, r);
				return (group ?? system)!;
			},
			[
				['Station flow', (s) => s.duty?.flow, 'flow'],
				['Rise', (s) => s.duty?.head, 'head'],
				['Lost in the piping between the pumps', (s) => s.duty?.interstageHeadLoss, 'head']
			]
		);
	}
	if (ids.has('pump-group-members')) {
		const t = readSheet(bundle, 'pump-group-members');
		checked += checkNumbers(
			input,
			t,
			(r) => {
				const { group, system } = rowGroup(input, t, r);
				return (group ?? system)!.duty!.members.find((m) => m.pumpId === t.get(r, 'Pump id'))!;
			},
			[
				['Speed', (m) => (m.status === 'off' ? null : m.speed), 'fraction'],
				['Flow', (m) => m.flow, 'flow'],
				['Head', (m) => m.head, 'head'],
				['Share', (m) => m.share, 'fraction'],
				['Lost on its way', (m) => m.routeHeadLoss, 'head']
			]
		);
	}
	if (ids.has('group-curves')) {
		const t = readSheet(bundle, 'group-curves');
		checked += checkNumbers(input, t, (r) => pointOf(input, t, r), [
			['Rise from', (x) => x.group.headRange?.min, 'head'],
			['Rise to', (x) => x.group.headRange?.max, 'head'],
			['Rise', (x) => x.point.head, 'head'],
			['Station flow', (x) => x.point.flow, 'flow']
		]);
	}
	if (ids.has('group-curve-members')) {
		const t = readSheet(bundle, 'group-curve-members');
		checked += checkNumbers(
			input,
			t,
			(r) => {
				const { point } = pointOf(input, t, r);
				return {
					point,
					member: point.members.find((m) => m.pumpId === t.get(r, 'Pump id'))!
				};
			},
			[
				['Rise', (x) => x.point.head, 'head'],
				['Speed', (x) => (x.member.status === 'off' ? null : x.member.speed), 'fraction'],
				['Flow', (x) => x.member.flow, 'flow'],
				['Head', (x) => x.member.head, 'head']
			]
		);
	}
	if (ids.has('group-system-curves')) {
		const t = readSheet(bundle, 'group-system-curves');
		checked += checkNumbers(input, t, (r) => systemPointOf(input, t, r), [
			['Flow from', (x) => x.system.flowRange?.min, 'flow'],
			['Flow to', (x) => x.system.flowRange?.max, 'flow'],
			['Station flow', (x) => x.point.flow, 'flow'],
			['Rise', (x) => x.point.head, 'head'],
			['Limit flow', (x) => x.point.limitFlow, 'flow'],
			['Passed flow', (x) => x.point.passedFlow, 'flow'],
			['Open-valve rise', (x) => x.point.openHead, 'head']
		]);
	}
	return checked;
}

/** The headers of the five sheets, with the units of `units` (the fixture's display units). */
function expectedHeaders(units: 'si' | 'display'): Record<string, string[]> {
	const q = units === 'si' ? 'm³/s' : 'L/s';
	const h = 'm';
	const fraction = (label: string) => (units === 'si' ? label : `${label} [%]`);
	const cases = ['Case id', 'Case', 'Solved at', 'Results'];
	return {
		'pump-groups': [
			...cases,
			'Group',
			'Pumps',
			'Arrangement',
			'Inlet S',
			'Inlet component id',
			'Inlet port id',
			'Outlet D',
			'Outlet component id',
			'Outlet port id',
			'Interior component ids',
			'Interior connection ids',
			`Station flow [${q}]`,
			`Rise [${h}]`,
			`Lost in the piping between the pumps [${h}]`,
			'Duty check agrees',
			'Duty check',
			'Duty check (as reported, SI)',
			'System duty check agrees',
			'System duty check',
			'System duty check (as reported, SI)',
			'No duty (as reported, SI)',
			'Group curve',
			'Group system curve',
			'Calculation methods version'
		],
		'pump-group-members': [
			...cases,
			'Group',
			'Pump id',
			'Pump',
			'State',
			fraction('Speed'),
			`Flow [${q}]`,
			`Head [${h}]`,
			fraction('Share'),
			`Lost on its way [${h}]`
		],
		'group-curves': [
			...cases,
			'Group',
			`Rise from [${h}]`,
			`Rise to [${h}]`,
			'Point #',
			`Rise [${h}]`,
			`Station flow [${q}]`,
			'Converged',
			'At the duty rise',
			'Reason code',
			'Reason',
			'Message (as reported, SI)',
			'Component ids'
		],
		'group-curve-members': [
			...cases,
			'Group',
			'Point #',
			`Rise [${h}]`,
			'Pump id',
			'Pump',
			'Status',
			'Control state',
			fraction('Speed'),
			`Flow [${q}]`,
			`Head [${h}]`,
			'Beyond data'
		],
		'group-system-curves': [
			...cases,
			'Group',
			`Flow from [${q}]`,
			`Flow to [${q}]`,
			'Point #',
			`Station flow [${q}]`,
			`Rise [${h}]`,
			'Converged',
			'At the duty flow',
			'Reason code',
			'Reason',
			'Message (as reported, SI)',
			`Limit flow [${q}]`,
			`Passed flow [${q}]`,
			`Open-valve rise [${h}]`,
			'Open-valve rise bound',
			'Starts tried',
			'Component ids',
			'Assigned-flow node ids'
		]
	};
}

/** The pump-groups case with every group map emptied: the same file without the groups. */
function withoutGroups(input: ExportInput): ExportInput {
	return {
		...input,
		cases: input.cases.map((c) => ({ ...c, groupCurves: {}, groupSystemCurves: {} }))
	};
}

describe('the pump-groups case (a): five sheets after System curves', () => {
	describe.each(['si', 'display'] as const)('in %s units', (units) => {
		const input = fixtureInput('pump-groups', { units });
		const bundle = buildExport(input);
		const [base, off] = input.cases;
		const group = ready(base!.groupCurves[KEY]);
		const system = ready(base!.groupSystemCurves[KEY]);
		const offGroup = ready(off!.groupCurves[KEY]);
		const prefs = prefsOf(input);

		it('right after System curves, in order, with their files and titles', () => {
			const ids = sheetIds(bundle);
			const at = ids.indexOf('system-curves');
			expect(at).toBeGreaterThan(0);
			expect(ids.slice(at + 1, at + 6)).toEqual(IDS);
			expect(ids[at + 6]).toBe('valves');
			for (const [id, title] of SHEETS) {
				const sheet = bundle.sheets.find((s) => s.id === id)!;
				expect(sheet.file).toBe(`${id}.csv`);
				expect(sheet.title).toBe(title);
				expect(sheet.title.length).toBeLessThanOrEqual(31);
			}
		});

		it('with the headers, their units in the file’s', () => {
			const expected = expectedHeaders(units);
			for (const id of IDS) expect(readSheet(bundle, id).headers, id).toEqual(expected[id]);
		});

		it('with one row per group, member, point and point member of each case', () => {
			const count = (r: PumpGroupCurveResponse) =>
				r.points.reduce((n, p) => n + p.members.length, 0);
			expect(readSheet(bundle, 'pump-groups').rows).toHaveLength(2);
			expect(readSheet(bundle, 'pump-group-members').rows).toHaveLength(4);
			expect(readSheet(bundle, 'group-curves').rows).toHaveLength(
				group.points.length + offGroup.points.length
			);
			expect(readSheet(bundle, 'group-curve-members').rows).toHaveLength(
				count(group) + count(offGroup)
			);
			expect(readSheet(bundle, 'group-system-curves').rows).toHaveLength(
				system.systemPoints.length
			);
			for (const id of IDS) {
				const sheet = bundle.sheets.find((s) => s.id === id)!;
				expect(sheet.rowCount, id).toBe(readSheet(bundle, id).rows.length);
			}
		});

		it('every number cell is the API’s double (SI) or its fromSI (display)', () => {
			expect(checkAllNumbers(input, bundle)).toBeGreaterThan(500);
		});

		it('rows run cases → groups → points → members, Point # from 1 per group per case', () => {
			const t = readSheet(bundle, 'group-curves');
			const expected = [
				...group.points.map((_, i) => [null, 'PA+PB', i + 1]),
				...offGroup.points.map((_, i) => ['S1', 'PA+PB', i + 1])
			];
			expect(
				t.rows.map((r) => [t.get(r, 'Case id'), t.get(r, 'Group'), t.get(r, 'Point #')])
			).toEqual(expected);
			const m = readSheet(bundle, 'group-curve-members');
			const members = [
				...[...group.points]
					.sort((a, b) => a.head - b.head)
					.flatMap((p, i) => p.members.map((x) => [null, i + 1, x.pumpId])),
				...[...offGroup.points]
					.sort((a, b) => a.head - b.head)
					.flatMap((p, i) => p.members.map((x) => ['S1', i + 1, x.pumpId]))
			];
			expect(
				m.rows.map((r) => [m.get(r, 'Case id'), m.get(r, 'Point #'), m.get(r, 'Pump id')])
			).toEqual(members);
			const y = readSheet(bundle, 'group-system-curves');
			expect(y.rows.map((r) => [y.get(r, 'Case id'), y.get(r, 'Point #')])).toEqual(
				system.systemPoints.map((_, i) => [null, i + 1])
			);
			const g = readSheet(bundle, 'pump-group-members');
			expect(g.rows.map((r) => [g.get(r, 'Case id'), g.get(r, 'Pump id')])).toEqual([
				[null, 'PA'],
				[null, 'PB'],
				['S1', 'PA'],
				['S1', 'PB']
			]);
		});

		it('the Pump groups rows: the station, the duty checks and each curve’s state, in the card’s words', () => {
			const t = readSheet(bundle, 'pump-groups');
			const [b, s] = t.rows;
			const station = group.station;
			for (const row of [b!, s!]) {
				expect(t.get(row, 'Group')).toBe('PA+PB');
				expect(t.get(row, 'Pumps')).toBe('Pump PA; Pump PB');
				expect(t.get(row, 'Arrangement')).toBe(ARRANGEMENT_WORDS.parallel);
				expect(t.get(row, 'Inlet S')).toBe(stationPortWords(station.inlet, input.project));
				expect(t.get(row, 'Inlet S')).toBe('Tee T1 (run inlet)');
				expect(t.get(row, 'Inlet component id')).toBe('T1');
				expect(t.get(row, 'Inlet port id')).toBe('run_inlet');
				expect(t.get(row, 'Outlet D')).toBe(stationPortWords(station.outlet, input.project));
				expect(t.get(row, 'Outlet component id')).toBe('T2');
				expect(t.get(row, 'Outlet port id')).toBe('run_outlet');
				expect(t.get(row, 'Interior component ids')).toBe(station.interiorComponentIds.join('; '));
				expect(t.get(row, 'Interior connection ids')).toBe(
					station.interiorConnectionIds.join('; ')
				);
				expect(t.get(row, 'Duty check agrees')).toBe(true);
				expect(t.get(row, 'No duty (as reported, SI)')).toBeNull();
				expect(t.get(row, 'Group curve')).toBe(`Included (${group.points.length} points)`);
				expect(t.get(row, 'Calculation methods version')).toBe(group.methodVersion);
			}
			expect(t.get(b!, 'Duty check')).toBe(dutyCheckState(group));
			expect(t.get(b!, 'Duty check (as reported, SI)')).toBe(group.dutyCheck!.message);
			expect(t.get(b!, 'System duty check agrees')).toBe(true);
			expect(t.get(b!, 'System duty check')).toBe(systemDutyCheckState(system));
			expect(t.get(b!, 'System duty check (as reported, SI)')).toBe(
				system.systemDutyCheck!.message
			);
			expect(t.get(b!, 'Group system curve')).toBe(
				`Included (${system.systemPoints.length} points)`
			);
			expect(t.get(s!, 'Duty check')).toBe(dutyCheckState(offGroup));
			expect(t.get(s!, 'Duty check (as reported, SI)')).toBe(offGroup.dutyCheck!.message);
			expect(t.get(s!, 'System duty check agrees')).toBeNull();
			expect(t.get(s!, 'System duty check')).toBeNull();
			expect(t.get(s!, 'System duty check (as reported, SI)')).toBeNull();
			expect(t.get(s!, 'Group system curve')).toBe(NOT_COMPUTED);
			// In parallel, no interstage loss.
			expect(t.column('Lost in the piping between the pumps')).toEqual([null, null]);
		});

		it('the members’ state is the Pumps sheet’s words; an off member has no speed', () => {
			const t = readSheet(bundle, 'pump-group-members');
			for (const row of t.rows) {
				const c = input.cases.find((x) => x.id === t.get(row, 'Case id'))!;
				const solved = c.response!.solvedState;
				const id = t.get(row, 'Pump id') as string;
				expect(t.get(row, 'Pump')).toBe(input.project.components.find((x) => x.id === id)!.name);
				expect(t.get(row, 'State')).toBe(
					pumpStatusLabel(
						solved.pumpResults[id]!,
						flagsForElement(solved.flags, { kind: 'component', id })
					)
				);
			}
			const offPb = t.rows.find(
				(r) => t.get(r, 'Case id') === 'S1' && t.get(r, 'Pump id') === 'PB'
			)!;
			expect(t.get(offPb, 'State')).toBe('Off');
			expect(t.get(offPb, 'Speed')).toBeNull();
			expect(t.get(offPb, 'Share')).toBe(0);
			expect(t.get(offPb, 'Lost on its way')).toBeNull();
		});

		it('every reason is the card’s data table’s, with the server’s code, message and data', () => {
			const y = readSheet(bundle, 'group-system-curves');
			const notes = groupSystemRows(system, prefs, {
				project: input.project,
				solved: base!.inputs!
			});
			const points = [...system.systemPoints].sort((a, b) => a.flow - b.flow);
			expect(y.column('Reason')).toEqual(notes.map((n) => n.note || null));
			let beyond = 0;
			for (const [i, row] of y.rows.entries()) {
				const p = points[i]!;
				expect(y.get(row, 'Converged')).toBe(p.converged);
				expect(y.get(row, 'At the duty flow')).toBe(p.isDuty);
				expect(y.get(row, 'Reason code')).toBe(p.reason);
				expect(y.get(row, 'Message (as reported, SI)')).toBe(p.message || null);
				expect(y.get(row, 'Open-valve rise bound')).toBe(p.openHeadBound);
				expect(y.get(row, 'Starts tried')).toBe(
					p.startsTried.length ? p.startsTried.join('; ') : null
				);
				expect(y.get(row, 'Component ids')).toBe(
					p.componentIds.length ? p.componentIds.join('; ') : null
				);
				expect(y.get(row, 'Assigned-flow node ids')).toBe(
					p.assignedFlowNodeIds.length ? p.assignedFlowNodeIds.join('; ') : null
				);
				if (p.reason === 'beyond_limit') {
					beyond++;
					expect(y.get(row, 'Reason')).toBeTruthy();
					expect(y.get(row, 'Component ids')).toBe('FC');
				}
			}
			expect(beyond).toBeGreaterThan(0);

			const g = readSheet(bundle, 'group-curves');
			for (const [c, r] of [
				[null, group],
				['S1', offGroup]
			] as const) {
				const rows = g.rows.filter((row) => g.get(row, 'Case id') === c);
				const sample = groupSampleRows(r, r.station.memberIds, prefs, input.project);
				expect(rows.map((row) => g.get(row, 'Reason'))).toEqual(sample.map((n) => n.note || null));
				const sorted = [...r.points].sort((a, b) => a.head - b.head);
				expect(rows.map((row) => g.get(row, 'At the duty rise'))).toEqual(
					sorted.map((p) => p.isDuty)
				);
				expect(rows.map((row) => g.get(row, 'Reason code'))).toEqual(sorted.map((p) => p.reason));
			}
			const m = readSheet(bundle, 'group-curve-members');
			for (const row of m.rows) {
				const { point } = pointOf(input, m, row);
				const member = point.members.find((x) => x.pumpId === m.get(row, 'Pump id'))!;
				expect(m.get(row, 'Status')).toBe(MEMBER_STATUS_WORDS[member.status]);
				expect(m.get(row, 'Control state')).toBeNull();
				expect(m.get(row, 'Beyond data')).toBe(member.beyondData);
			}
		});

		it('the duty check’s values are the rows marked At the duty rise and At the duty flow', () => {
			const value = (v: number, category: UnitCategory) =>
				units === 'si' ? v : fromSI(v, displayUnit(category, input.prefs));
			for (const [c, r] of [
				[null, group],
				['S1', offGroup]
			] as const) {
				const g = readSheet(bundle, 'group-curves');
				const duty = g.rows.filter(
					(row) => g.get(row, 'Case id') === c && g.get(row, 'At the duty rise') === true
				);
				expect(duty).toHaveLength(1);
				expect(g.get(duty[0]!, 'Station flow')).toBe(value(r.dutyCheck!.flow!, 'flow'));
				const m = readSheet(bundle, 'group-curve-members');
				const at = g.get(duty[0]!, 'Point #');
				for (const checked of r.dutyCheck!.members) {
					const row = m.rows.find(
						(x) =>
							m.get(x, 'Case id') === c &&
							m.get(x, 'Point #') === at &&
							m.get(x, 'Pump id') === checked.pumpId
					)!;
					expect(m.get(row, 'Flow')).toBe(value(checked.flow!, 'flow'));
				}
			}
			const y = readSheet(bundle, 'group-system-curves');
			const duty = y.rows.filter((row) => y.get(row, 'At the duty flow') === true);
			expect(duty).toHaveLength(1);
			expect(y.get(duty[0]!, 'Rise')).toBe(value(system.systemDutyCheck!.head!, 'head'));
		});

		it('About differs from the same file without groups only in its group lines', () => {
			const a = readSheet(bundle, 'about').rows;
			const without = buildExport(withoutGroups(input));
			const b = readSheet(without, 'about').rows;
			expect(sheetIds(without).filter((id) => (IDS as readonly string[]).includes(id))).toEqual([]);
			const titles = SHEETS.map(([, title]) => `Sheet: ${title}`);
			const groupRows = ['Pump groups', 'Pump groups: share', 'Pump groups: duty checks'];
			const onlyA = (r: CellValue[]) =>
				r[0] === 'Export' &&
				(titles.includes(String(r[1])) ||
					r[1] === 'Sign: pump group' ||
					groupRows.includes(String(r[1])));
			const onlyB = (r: CellValue[]) =>
				r[0] === 'Not in this file' && String(r[1]).startsWith('Pump groups');
			// A's own rows: the five sheets' counts, the sign and the three group rows, in place.
			expect(a.filter(onlyA).map((r) => r[1])).toEqual([
				...titles,
				'Sign: pump group',
				...groupRows
			]);
			const sign = a.findIndex((r) => r[1] === 'Sign: pump group');
			expect(a[sign - 1]![1]).toBe('Sign: pump flow');
			expect(a[sign]![2]).toBe(
				"Rise = EGL(D) − EGL(S), from the station's inlet S to its outlet D; Station flow is + from S into the station; a pump's flow is suction → discharge."
			);
			const firstGroupRow = a.findIndex((r) => r[1] === 'Pump groups');
			expect(a.slice(firstGroupRow, firstGroupRow + 3).map((r) => r[1])).toEqual(groupRows);
			expect(a[firstGroupRow + 3]![0]).toBe('Not in this file');
			expect(String(a[firstGroupRow]![2])).toContain("pumps' ids joined by +");
			expect(String(a[firstGroupRow + 1]![2]).startsWith('Share:')).toBe(true);
			expect(String(a[firstGroupRow + 2]![2]).startsWith('Duty check:')).toBe(true);
			// B's own rows: no group computed for either case, which About says per case.
			const reason =
				'not computed: the Pumps together card under the pump chart computes them on request';
			expect(b.filter(onlyB)).toEqual([
				['Not in this file', 'Pump groups (Base case)', reason],
				['Not in this file', 'Pump groups (PB off (S1))', reason]
			]);
			// Every other row equal, in order, but the lines that name the groups.
			const restA = a.filter((r) => !onlyA(r));
			const restB = b.filter((r) => !onlyB(r));
			expect(restA).toHaveLength(restB.length);
			const fractions = units === 'si' ? 'none (a pure number)' : '%';
			const changed: [CellValue[], CellValue[]][] = [];
			for (const [i, row] of restA.entries()) {
				if (JSON.stringify(row) !== JSON.stringify(restB[i])) changed.push([row, restB[i]!]);
			}
			const numbers = (r: CellValue[]) => String(r[2]);
			const expected: [CellValue[], CellValue[]][] = [
				[
					[
						'Export',
						"Units: fractions (speed, efficiency, a pump group member's share)",
						fractions
					],
					['Export', 'Units: fractions (speed, efficiency)', fractions]
				],
				...(units === 'si'
					? [
							[
								[
									'Export',
									'Units: fractions',
									"Fractions (speed, efficiency) are 0–1 and carry no unit. A pump group member's share is a ratio with no unit, as the calculation server gives it."
								],
								[
									'Export',
									'Units: fractions',
									'Fractions (speed, efficiency) are 0–1 and carry no unit.'
								]
							] as [CellValue[], CellValue[]]
						]
					: [])
			];
			const numbersRow = changed.find(([x]) => x[1] === 'Numbers')!;
			expect(numbers(numbersRow[0])).toBe(
				numbers(numbersRow[1]) +
					" The Pumps together card shows a station's flow below 1×10⁻⁶ m³/s (its duty check's floor) as 0; the file gives the server's value, which at a station without flow is round-off about zero."
			);
			const methodsRow = changed.find(([x]) => x[1] === 'Sheet: Methods')!;
			const methods = (bundle: ExportBundle) => bundle.sheets.find((s) => s.id === 'methods')!;
			expect(methodsRow).toEqual([
				['Export', 'Sheet: Methods', methods(bundle).rowCount],
				['Export', 'Sheet: Methods', methods(without).rowCount]
			]);
			const included = changed.filter(([x]) => x[1] === 'Pump groups included');
			expect(included).toEqual([
				[
					[
						'Case: Base case',
						'Pump groups included',
						'PA+PB (parallel): group curve, group system curve'
					],
					['Case: Base case', 'Pump groups included', 'None']
				],
				[
					['Case: PB off (S1)', 'Pump groups included', 'PA+PB (parallel): group curve'],
					['Case: PB off (S1)', 'Pump groups included', 'None']
				]
			]);
			expect(
				changed.filter(
					([x]) => !['Numbers', 'Sheet: Methods', 'Pump groups included'].includes(String(x[1]))
				)
			).toEqual(expected);
		});

		it('Methods: each case’s methods, then each group response’s, as the card titles them', () => {
			const t = readSheet(bundle, 'methods');
			const lines = (c: string | null) =>
				t.rows.filter((r) => t.get(r, 'Case id') === c).map((r) => t.get(r, 'Text'));
			const tail = (c: string | null, n: number) => lines(c).slice(-n);
			const baseTail = [
				'',
				'Pumps together: PA+PB, group curve',
				...groupMethodsLines(group),
				'',
				'Pumps together: PA+PB, group system curve',
				...groupMethodsLines(system)
			];
			const offTail = ['', 'Pumps together: PA+PB, group curve', ...groupMethodsLines(offGroup)];
			expect(tail(null, baseTail.length)).toEqual(baseTail);
			expect(tail('S1', offTail.length)).toEqual(offTail);
			expect(groupMethodsLines(group)[0]).toBe('Pump group (calculation methods 1.6.0)');
			expect(groupMethodsLines(group)).toContain('References:');
			// Before them, the case's own methods text, as without groups.
			const plain = readSheet(buildExport(withoutGroups(input)), 'methods');
			const plainLines = (c: string | null) =>
				plain.rows.filter((r) => plain.get(r, 'Case id') === c).map((r) => plain.get(r, 'Text'));
			expect(lines(null)).toEqual([...plainLines(null), ...baseTail]);
			expect(lines('S1')).toEqual([...plainLines('S1'), ...offTail]);
			// methods.txt holds the same lines, cases apart.
			const sheet = bundle.sheets.find((s) => s.id === 'methods')!;
			expect([...sheet.text!()]).toEqual([...lines(null), '', ...lines('S1')]);
		});

		it('the dialog leaves no group out', () => {
			expect(bundle.omitted.filter((o) => o.what.startsWith('Pump group'))).toEqual([]);
			expect(
				readSheet(bundle, 'about').rows.filter(
					(r) => r[0] === 'Not in this file' && String(r[1]).startsWith('Pump group')
				)
			).toEqual([]);
		});
	});
});

// -------------------------------------------------------------------------------------------
// (b) The pump-group fixture's cases
// -------------------------------------------------------------------------------------------

interface GroupFixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: SolveResponse;
	groupCurve: { status: number; body: unknown };
	systemCurve: { status: number; body: unknown } | null;
}
const groupCases = groupFixture.cases as unknown as GroupFixtureCase[];
const named = (name: string) => groupCases.find((c) => c.name === name)!;

/** A fixture answer as the store keeps it: 200 ready, 422 refused with its issues. */
function stateOf(answer: { status: number; body: unknown }): GroupCurveState {
	if (answer.status === 200) {
		return { status: 'ready', response: answer.body as PumpGroupCurveResponse };
	}
	const body = answer.body as { message: string; issues: TopologyIssue[] };
	return { status: 'refused', message: body.message, issues: body.issues };
}

/**
 * The pump-transfer export input with a pump-group fixture case in its place: its project, its
 * solve, and its answers under the group's key (or the states given; null: none).
 */
function inputOf(
	name: string,
	states: { group?: GroupCurveState | null; system?: GroupCurveState | null } = {},
	options: Partial<ExportInput['options']> = { units: 'si' }
): ExportInput {
	const c = named(name);
	const input = fixtureInput('pump-transfer', options);
	const [shown] = input.cases;
	const key = groupKey(c.memberIds);
	const group = states.group !== undefined ? states.group : stateOf(c.groupCurve);
	const system =
		states.system !== undefined ? states.system : c.systemCurve ? stateOf(c.systemCurve) : null;
	return {
		...input,
		project: c.project,
		prefs: c.project.settings.units,
		goalSeek: null,
		cases: [
			{
				...shown!,
				response: c.solve,
				sent: c.project,
				inputs: c.project,
				systemCurves: {},
				groupCurves: group ? { [key]: group } : {},
				groupSystemCurves: system ? { [key]: system } : {}
			}
		]
	};
}

/** The card's words for a refusal's issues, as the export writes them (component order). */
function refusalOf(name: string): string {
	const c = named(name);
	const body = c.groupCurve.body as { issues: TopologyIssue[] };
	const members = c.project.components.filter((x) => c.memberIds.includes(x.id)).map((x) => x.id);
	return body.issues
		.map((issue) =>
			wordsText(
				refusalWords(issue, members, c.project, {
					solved: c.project,
					boxes: Object.keys(c.solve.solvedState.pumpResults)
				})
			)
		)
		.join(' ');
}

const about = (bundle: ExportBundle) => readSheet(bundle, 'about').rows;
const aboutValue = (bundle: ExportBundle, item: string) =>
	about(bundle)
		.filter((r) => r[1] === item)
		.map((r) => r[2]);
const groupSheets = (bundle: ExportBundle) =>
	sheetIds(bundle).filter((id) => (IDS as readonly string[]).includes(id));

describe('the pump-group fixture’s cases (b)', () => {
	it('series: head shares, the interstage loss, no loss on the way', () => {
		const input = inputOf('series');
		const bundle = buildExport(input);
		const response = ready(input.cases[0]!.groupCurves[groupKey(['PA', 'PB'])]);
		const duty = response.duty!;
		const t = readSheet(bundle, 'pump-groups');
		expect(t.rows).toHaveLength(1);
		expect(t.get(t.rows[0]!, 'Arrangement')).toBe(ARRANGEMENT_WORDS.series);
		expect(
			Object.is(t.get(t.rows[0]!, 'Lost in the piping between the pumps'), duty.interstageHeadLoss)
		).toBe(true);
		expect(duty.interstageHeadLoss).not.toBeNull();
		const m = readSheet(bundle, 'pump-group-members');
		expect(m.column('Share')).toEqual(duty.members.map((x) => x.share));
		expect(m.column('Share').every((s) => typeof s === 'number')).toBe(true);
		expect(m.column('Lost on its way')).toEqual([null, null]);
		expect(checkAllNumbers(input, bundle)).toBeGreaterThan(100);
	});

	it('a PRV inside: a row from the group system curve, the group curve not defined', () => {
		const input = inputOf('prv-inside');
		const bundle = buildExport(input);
		const system = ready(input.cases[0]!.groupSystemCurves[groupKey(['PA', 'PB'])]);
		expect(groupSheets(bundle)).toEqual([
			'pump-groups',
			'pump-group-members',
			'group-system-curves'
		]);
		const t = readSheet(bundle, 'pump-groups');
		expect(t.rows).toHaveLength(1);
		const row = t.rows[0]!;
		expect(t.get(row, 'Inlet component id')).toBe(system.station.inlet.componentId);
		expect(t.get(row, 'Outlet component id')).toBe(system.station.outlet.componentId);
		expect(t.get(row, 'Interior component ids')).toBe(
			system.station.interiorComponentIds.join('; ')
		);
		expect(Object.is(t.get(row, 'Station flow'), system.duty!.flow)).toBe(true);
		expect(Object.is(t.get(row, 'Rise'), system.duty!.head)).toBe(true);
		expect(t.get(row, 'Group curve')).toBe(`Not defined: ${refusalOf('prv-inside')}`);
		expect(refusalOf('prv-inside').length).toBeGreaterThan(20);
		for (const label of ['Duty check agrees', 'Duty check', 'Duty check (as reported, SI)'])
			expect(t.get(row, label), label).toBeNull();
		expect(t.get(row, 'System duty check agrees')).toBe(true);
		expect(t.get(row, 'System duty check')).toBe(systemDutyCheckState(system));
		expect(t.get(row, 'System duty check (as reported, SI)')).toBe(system.systemDutyCheck!.message);
		expect(t.get(row, 'Group system curve')).toBe(
			`Included (${system.systemPoints.length} points)`
		);
		expect(readSheet(bundle, 'group-system-curves').rows).toHaveLength(system.systemPoints.length);
		expect(checkAllNumbers(input, bundle)).toBeGreaterThan(100);
		expect(bundle.omitted.filter((o) => o.what.startsWith('Pump group'))).toEqual([]);
	});

	it('a PRV inside, its group system curve failed: no group sheet, the group left out with why', () => {
		const bundle = buildExport(
			inputOf('prv-inside', { system: { status: 'error', message: 'boom' } })
		);
		expect(groupSheets(bundle)).toEqual([]);
		const reason = `group system curve failed: boom; group curve not defined: ${refusalOf('prv-inside')}`;
		expect(bundle.omitted).toContainEqual({ what: 'Pump group PA+PB', reason });
		expect(about(bundle)).toContainEqual(['Not in this file', 'Pump group PA+PB', reason]);
		expect(aboutValue(bundle, 'Pump groups included')).toEqual(['None']);
	});

	it('a PRV inside, its group system curve not asked for: says where to compute it', () => {
		const bundle = buildExport(inputOf('prv-inside', { system: null }));
		expect(bundle.omitted).toContainEqual({
			what: 'Pump group PA+PB',
			reason: `group system curve not computed: open the Pumps together card on this case, with these pumps ticked; group curve not defined: ${refusalOf('prv-inside')}`
		});
	});

	it('no duty: one row with the station and the reason, no member or point rows', () => {
		const input = inputOf('no-duty');
		const bundle = buildExport(input);
		const response = ready(input.cases[0]!.groupCurves[groupKey(['PU1', 'PU2'])]);
		expect(groupSheets(bundle)).toEqual(['pump-groups']);
		const t = readSheet(bundle, 'pump-groups');
		expect(t.rows).toHaveLength(1);
		const row = t.rows[0]!;
		expect(t.get(row, 'Group')).toBe('PU1+PU2');
		expect(t.get(row, 'Arrangement')).toBe(ARRANGEMENT_WORDS.mixed);
		expect(t.get(row, 'Inlet S')).toBe(stationPortWords(response.station.inlet, input.project));
		expect(t.get(row, 'Outlet port id')).toBe(response.station.outlet.portId);
		for (const label of [
			'Station flow',
			'Rise',
			'Lost in the piping between the pumps',
			'Duty check agrees',
			'Duty check',
			'Duty check (as reported, SI)',
			'System duty check agrees',
			'System duty check',
			'System duty check (as reported, SI)'
		])
			expect(t.get(row, label), label).toBeNull();
		expect(t.get(row, 'No duty (as reported, SI)')).toBe(response.message);
		expect(response.message.length).toBeGreaterThan(20);
		expect(t.get(row, 'Group curve')).toBe(NO_DUTY);
		expect(t.get(row, 'Group system curve')).toBe(NO_DUTY);
		expect(aboutValue(bundle, 'Pump groups included')).toEqual(['PU1+PU2 (mixed): no duty']);
		expect(bundle.omitted.filter((o) => o.what.startsWith('Pump group'))).toEqual([]);
	});

	it('a controlled member: its control state in the Pumps sheet’s words', () => {
		const input = inputOf('controlled');
		const bundle = buildExport(input);
		const response = ready(input.cases[0]!.groupCurves[groupKey(['PA', 'PB'])]);
		const m = readSheet(bundle, 'group-curve-members');
		let pb = 0;
		for (const row of m.rows) {
			const { point } = pointOf(input, m, row);
			const member = point.members.find((x) => x.pumpId === m.get(row, 'Pump id'))!;
			if (member.controlState) {
				pb++;
				expect(member.pumpId).toBe('PB');
				expect(m.get(row, 'Control state')).toBe(PUMP_CONTROL_STATE_LABELS[member.controlState]);
			} else {
				expect(member.pumpId).toBe('PA');
				expect(m.get(row, 'Control state')).toBeNull();
			}
		}
		expect(pb).toBe(response.points.filter((p) => p.members.length).length);
		expect(checkAllNumbers(input, bundle)).toBeGreaterThan(100);
	});

	it('an off member: Off, no speed, the share as the API gives it', () => {
		const input = inputOf('off');
		const bundle = buildExport(input);
		const solved = input.cases[0]!.response!.solvedState;
		const response = ready(input.cases[0]!.groupCurves[groupKey(['PA', 'PB'])]);
		const m = readSheet(bundle, 'pump-group-members');
		const pb = m.rows.find((r) => m.get(r, 'Pump id') === 'PB')!;
		expect(m.get(pb, 'State')).toBe(
			pumpStatusLabel(
				solved.pumpResults.PB!,
				flagsForElement(solved.flags, { kind: 'component', id: 'PB' })
			)
		);
		expect(m.get(pb, 'State')).toBe('Off');
		expect(m.get(pb, 'Speed')).toBeNull();
		const share = response.duty!.members.find((x) => x.pumpId === 'PB')!.share;
		expect(share).toBe(0);
		expect(Object.is(m.get(pb, 'Share'), share)).toBe(true);
	});

	it('not a station: no group sheet, the group left out with the card’s words, in About too', () => {
		const bundle = buildExport(inputOf('refused'));
		expect(groupSheets(bundle)).toEqual([]);
		const reason = `not a station: ${refusalOf('refused')}`;
		expect(bundle.omitted).toContainEqual({ what: 'Pump group PA+PB', reason });
		expect(about(bundle)).toContainEqual(['Not in this file', 'Pump group PA+PB', reason]);
		expect(aboutValue(bundle, 'Pump groups included')).toEqual(['None']);
		// The group's own line replaces the one for a case with no group computed.
		expect(bundle.omitted.map((o) => o.what)).not.toContain('Pump groups');
	});

	it('two pumps and no group computed: one line saying where to compute them', () => {
		const bundle = buildExport(inputOf('parallel-ideal', { group: null, system: null }));
		expect(groupSheets(bundle)).toEqual([]);
		const reason =
			'not computed: the Pumps together card under the pump chart computes them on request';
		expect(bundle.omitted).toContainEqual({ what: 'Pump groups', reason });
		expect(about(bundle)).toContainEqual(['Not in this file', 'Pump groups', reason]);
		expect(aboutValue(bundle, 'Pump groups included')).toEqual(['None']);
		// No group lines in About without the sheets.
		expect(about(bundle).filter((r) => r[1] === 'Sign: pump group')).toEqual([]);
	});

	it('one pump: nothing about pump groups', () => {
		const bundle = buildExport(fixtureInput('pump-transfer'));
		expect(groupSheets(bundle)).toEqual([]);
		expect(bundle.omitted.filter((o) => o.what.startsWith('Pump group'))).toEqual([]);
		expect(aboutValue(bundle, 'Pump groups included')).toEqual([]);
		expect(about(bundle).filter((r) => String(r[1]).startsWith('Pump group'))).toEqual([]);
	});
});

// -------------------------------------------------------------------------------------------
// (c) Synthetic: cloned, relabelled real responses
// -------------------------------------------------------------------------------------------

describe('synthetic: cloned, relabelled real responses (c)', () => {
	it('orders the groups of a case by their first member, then by id', () => {
		const ladder = named('ladder');
		const base = ready(stateOf(ladder.groupCurve));
		/** The ladder's response with only `ids` as members (synthetic). */
		const subset = (ids: string[]): GroupCurveState => {
			const r = structuredClone(base);
			r.station.memberIds = r.station.memberIds.filter((id) => ids.includes(id));
			r.duty!.members = r.duty!.members.filter((m) => ids.includes(m.pumpId));
			for (const p of r.points) p.members = p.members.filter((m) => ids.includes(m.pumpId));
			return { status: 'ready', response: r };
		};
		const input = inputOf('ladder', { group: null, system: null });
		const groups = [
			['P2', 'P3'],
			['P1', 'P2', 'P3'],
			['P1', 'P3']
		];
		input.cases = [
			{
				...input.cases[0]!,
				groupCurves: Object.fromEntries(groups.map((ids) => [groupKey(ids), subset(ids)]))
			}
		];
		const bundle = buildExport(input);
		expect(readSheet(bundle, 'pump-groups').column('Group')).toEqual([
			'P1+P2+P3',
			'P1+P3',
			'P2+P3'
		]);
		const m = readSheet(bundle, 'pump-group-members');
		expect(m.rows.map((r) => `${m.get(r, 'Group')}:${m.get(r, 'Pump id')}`)).toEqual([
			'P1+P2+P3:P1',
			'P1+P2+P3:P2',
			'P1+P2+P3:P3',
			'P1+P3:P1',
			'P1+P3:P3',
			'P2+P3:P2',
			'P2+P3:P3'
		]);
		expect(aboutValue(bundle, 'Pump groups included')).toEqual([
			'P1+P2+P3 (parallel): group curve; P1+P3 (parallel): group curve; P2+P3 (parallel): group curve'
		]);
	});

	it('a point without a flow: the card’s reason, the server’s code, message and ids, no members', () => {
		const parallel = named('parallel-ideal');
		const r = structuredClone(ready(stateOf(parallel.groupCurve)));
		const second = [...r.points].sort((a, b) => a.head - b.head)[1]!;
		Object.assign(second, {
			flow: null,
			converged: false,
			reason: 'not_converged',
			message: 'not converged: oscillating',
			members: [],
			componentIds: ['PA']
		});
		const input = inputOf('parallel-ideal', {
			group: { status: 'ready', response: r },
			system: null
		});
		const bundle = buildExport(input);
		const g = readSheet(bundle, 'group-curves');
		const row = g.rows.find((x) => g.get(x, 'Point #') === 2)!;
		const notes = groupSampleRows(r, r.station.memberIds, SI_BASE_UNITS, input.project);
		expect(notes[1]!.note).toBeTruthy();
		expect(g.get(row, 'Reason')).toBe(notes[1]!.note);
		expect(g.get(row, 'Station flow')).toBeNull();
		expect(g.get(row, 'Converged')).toBe(false);
		expect(g.get(row, 'Reason code')).toBe('not_converged');
		expect(g.get(row, 'Message (as reported, SI)')).toBe('not converged: oscillating');
		expect(g.get(row, 'Component ids')).toBe('PA');
		const m = readSheet(bundle, 'group-curve-members');
		expect(m.rows.filter((x) => m.get(x, 'Point #') === 2)).toEqual([]);
		expect(m.rows).toHaveLength(r.points.reduce((n, p) => n + p.members.length, 0));
		expect(readSheet(bundle, 'pump-groups').column('Group system curve')).toEqual([NOT_COMPUTED]);
	});
});
