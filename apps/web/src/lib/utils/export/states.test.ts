/**
 * What a file holds for each state of a case (proposal export.md §2.4, §7.1 items 4–9, 11 and 14),
 * with the real ProjectStore and Workspace (testing/workspace.ts) and a fake solver that answers
 * with the made-up states of testing/results.ts: the snapshot (exportInput) then the model
 * (buildExport). Values follow Compare's rule and `hasValues` and `stale`, never the status alone.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { TopologyError, NetworkError } from '../../api/client';
import type { Project, SolvedState, SolveResponse } from '../../api/types';
import { sourceLinks } from '../../components/links';
import {
	flag,
	link,
	pumpResult,
	pumpTransferSolved,
	response,
	systemCurveResponse
} from '../../testing/results';
import { testWorkspace } from '../../testing/workspace';
import type { Workspace } from '../../state/workspace.svelte';
import { compareCells, QUANTITIES, type CompareColumn } from '../compare';
import { decodeProject, fragmentOf, projectUrl } from '../encoding';
import { reversePiping } from '../edit';
import { pumpTransferExample } from '../examples';
import { addPipe } from '../piping';
import { pumpChartData } from '../pump-chart';
import { Formatter } from '../results';
import { withScenarios } from '../scenarios';
import { displayUnit, fromSI } from '../units';
import { writeCsvZip } from './csv';
import { fixtureInput, readSheet, sheetIds } from './export-testing.testing';
import { exportInput, type PageFacts } from './input';
import { buildExport, type ExportBundle, type ExportOptions } from './model';
import { writeXlsx } from './xlsx';
import { blobBytes, entryText, readZip } from './zip-reader.testing';

const NOW = new Date('2026-10-25T12:32:05Z');
const PAGE: PageFacts = {
	appVersion: 'feedfacefeedfacefeedfacefeedfacefeedface',
	serverSource: 'https://api.example.test/source',
	origin: 'https://opensolve-pipe.app'
};
const SHOWN: ExportOptions = { cases: 'shown', format: 'xlsx', units: 'display', link: true };
const ALL: ExportOptions = { ...SHOWN, cases: 'all' };

type Answer = (scenarioId: string | null, project: Project) => SolveResponse | Error;

/** A workspace whose solver answers with `answer` (a response, or an error to throw). */
function workspace(project: Project, answer: Answer): Workspace {
	return testWorkspace(project, {
		solver: {
			solve: async (p, _o, request) => {
				const a = answer(request?.scenarioId ?? null, p);
				if (a instanceof Error) throw a;
				return a;
			}
		}
	});
}

const converged = (values: Partial<SolvedState> = {}) => response(pumpTransferSolved(values));
const notConverged = () =>
	response(
		pumpTransferSolved({
			converged: false,
			flags: [flag({ code: 'NOT_CONVERGED', severity: 'invalid', message: 'did not converge' })]
		})
	);

const twoScenarios = () =>
	withScenarios(pumpTransferExample(), [
		{
			id: 'S1',
			name: 'Winter',
			overrides: [{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 4 }]
		},
		{
			id: 'S2',
			name: 'Peak',
			overrides: [{ kind: 'component', componentId: 'P1', field: 'speed', value: 0.9 }]
		}
	]);

const bundleOf = (ws: Workspace, options: ExportOptions = SHOWN): ExportBundle =>
	buildExport(exportInput(ws, options, NOW, PAGE));

/** A hydraulic edit: the length of L3's pipe (results go out of date). */
function lengthen(ws: Workspace): void {
	const result = ws.store.update((d) => {
		d.connections.find((c) => c.id === 'L3')!.piping.pipes[0]!.length += 1;
	}, 'lengthen');
	expect(result.ok).toBe(true);
}

const ELEMENT_SHEETS = [
	'nodes',
	'links',
	'pipes',
	'fittings',
	'pumps',
	'pump-curves',
	'valves',
	'boundaries'
];

describe('a solve that did not converge (item 4)', () => {
	it('gives About, Flags and Methods only, saying so, and "(not converged)"', async () => {
		const ws = workspace(pumpTransferExample(), () => notConverged());
		await ws.store.solve();
		expect(ws.store.caseStatus(null)).toBe('not_converged');
		const bundle = bundleOf(ws);
		expect(sheetIds(bundle)).toEqual(['about', 'flags', 'methods']);
		for (const id of ['flags', 'methods']) {
			expect(bundle.sheets.find((s) => s.id === id)!.caption).toContain(
				' — DID NOT CONVERGE: not a solution'
			);
		}
		expect(readSheet(bundle, 'flags').column('Results')).toEqual(['Did not converge']);
		expect(bundle.fileName).toMatch(/ \(not converged\)\.xlsx$/);
		expect(bundle.warnings.map((w) => w.kind)).toEqual(['not_converged']);
		const about = readSheet(bundle, 'about');
		expect(about.rows.find((r) => r[1] === 'Values in this file')?.[2]).toMatch(
			/^No: the solve did not converge/
		);
	});

	it('the same when it is out of date too (caseStatus says "stale")', async () => {
		const ws = workspace(twoScenarios(), (id) => (id === null ? notConverged() : converged()));
		await ws.store.solveAll();
		lengthen(ws);
		expect(ws.store.caseStatus(null)).toBe('stale');
		const shown = bundleOf(ws);
		expect(sheetIds(shown)).toEqual(['about', 'flags', 'methods']);
		expect(shown.warnings[0]).toEqual({
			kind: 'not_converged',
			text: expect.stringContaining('This out-of-date solve did not converge')
		});
		expect(shown.fileName).toMatch(
			/^Pump transfer between two tanks - Base case - results .* \(not converged\)\.xlsx$/
		);
		expect(readSheet(shown, 'flags').column('Results')).toEqual(['Did not converge, out of date']);
		const all = bundleOf(ws, ALL);
		const compare = readSheet(all, 'compare-cases');
		expect(compare.get(compare.rows[0]!, 'Base case')).toBe('Out of date; Did not converge');
		expect(readSheet(all, 'nodes').column('Case id').includes(null)).toBe(false);
	});
});

describe('out-of-date results (item 5)', () => {
	it('are labelled in About, every caption, every row and Compare, and link the project as solved', async () => {
		const ws = workspace(twoScenarios(), () => converged());
		await ws.store.solveAll();
		const sent = ws.store.sentProjectFor(null)!;
		lengthen(ws);
		const bundle = bundleOf(ws);
		for (const sheet of bundle.sheets) {
			expect(sheet.caption).toContain(' — OUT OF DATE: the project changed after this solve');
		}
		for (const id of ELEMENT_SHEETS) {
			expect(new Set(readSheet(bundle, id).column('Results'))).toEqual(new Set(['Out of date']));
		}
		const about = readSheet(bundle, 'about');
		const row = (item: string) => about.rows.find((r) => r[1] === item)?.[2];
		expect(row('Out of date')).toContain(
			'Results out of date: the project changed after this solve.'
		);
		const asSolved = projectUrl({ ...sent, methodVersion: '1.0.0' }, PAGE.origin);
		expect(row('Link 1')).toBe(asSolved);
		expect(row('Link 1 is')).toBe('the project as solved, before the later changes');
		expect(bundle.warnings.map((w) => w.kind)).toEqual(['stale']);
		const compare = readSheet(bundleOf(ws, ALL), 'compare-cases');
		expect(compare.rows[0]!.slice(5).filter((c) => c !== null)).toEqual([
			'Out of date; Converged, 0 physically invalid',
			'Out of date; Converged, 0 physically invalid',
			'Out of date; Converged, 0 physically invalid'
		]);
	});
});

describe('names and structure (item 6)', () => {
	it('a current case takes the current names', async () => {
		const ws = workspace(pumpTransferExample(), () => converged());
		await ws.store.solve();
		ws.store.update((d) => {
			d.components.find((c) => c.id === 'V1')!.name = 'Renamed valve';
		}, 'rename');
		expect(ws.store.results.stale).toBe(false);
		const bundle = bundleOf(ws);
		expect(readSheet(bundle, 'valves').column('Valve')).toEqual(['Renamed valve']);
		expect(readSheet(bundle, 'links').column('Connection')).toContain(
			'Transfer pump → Renamed valve'
		);
	});

	it('an out-of-date case keeps its connection ends, flow sign and names as solved', async () => {
		const ws = workspace(pumpTransferExample(), () => converged());
		await ws.store.solve();
		const reversed = ws.store.update((d) => {
			const c = d.connections.find((x) => x.id === 'L3')!;
			[c.fromComponentId, c.toComponentId] = [c.toComponentId, c.fromComponentId];
			[c.fromPortId, c.toPortId] = [c.toPortId, c.fromPortId];
		}, 'reverse');
		expect(reversed.ok).toBe(true);
		expect(ws.store.results.stale).toBe(true);
		const t = readSheet(bundleOf(ws), 'links');
		const l3 = t.rows.find((r) => t.get(r, 'Connection id') === 'L3')!;
		expect(t.get(l3, 'Connection')).toBe('Discharge isolation valve → Discharge tank');
		expect(t.get(l3, 'From id')).toBe('V1');
		expect(t.get(l3, 'Flow (+ from → to)')).toBe(fromSI(0.02, 'L/s'));
	});

	it('an out-of-date row keeps the solved element’s name and type when its id is re-used', async () => {
		const ws = workspace(pumpTransferExample(), () => converged());
		await ws.store.solve();
		expect(ws.remove('V1', true)).toBe(true);
		const joined = ws.project.connections.find((c) => c.fromComponentId === 'P1')!;
		expect(ws.insert(joined.id, 'prv')).toBe('V1');
		expect(ws.project.components.find((c) => c.id === 'V1')).toMatchObject({ valveType: 'prv' });
		const t = readSheet(bundleOf(ws), 'valves');
		expect(t.column('Valve')).toEqual(['Discharge isolation valve']);
		expect(t.column('Type')).toEqual(['Gate']);
	});
});

describe('cases (item 7)', () => {
	it('Case id and Case columns appear exactly with scenarios; Solved at and Results always', async () => {
		const plain = workspace(pumpTransferExample(), () => converged());
		await plain.store.solve();
		const scenarios = workspace(twoScenarios(), () => converged());
		await scenarios.store.solve();
		for (const sheet of bundleOf(plain).sheets.filter((s) => s.kind === 'table')) {
			const labels = sheet.columns.map((c) => c.label);
			expect(labels.slice(0, 2)).toEqual(['Solved at', 'Results']);
			expect(labels).not.toContain('Case id');
		}
		for (const sheet of bundleOf(scenarios).sheets.filter((s) => s.kind === 'table')) {
			expect(sheet.columns.slice(0, 4).map((c) => c.label)).toEqual([
				'Case id',
				'Case',
				'Solved at',
				'Results'
			]);
		}
	});

	it('All cases stacks the rows in case order, with Compare cases and no Trace', async () => {
		const ws = workspace(twoScenarios(), () => converged());
		await ws.store.solveAll();
		const bundle = bundleOf(ws, ALL);
		const ids = sheetIds(bundle);
		expect(ids).toContain('compare-cases');
		expect(ids).not.toContain('trace');
		const nodes = readSheet(bundle, 'nodes');
		const cases = nodes.column('Case id');
		expect(cases).toEqual([...Array(6).fill(null), ...Array(6).fill('S1'), ...Array(6).fill('S2')]);
		expect(nodes.column('Case').slice(6, 7)).toEqual(['Winter']);
		expect(bundle.fileName).toMatch(/^Pump transfer between two tanks - All cases - results /);
		expect(bundle.omitted.map((o) => o.what)).toContain('Trace');
	});

	it('marks exactly the out-of-date case and the one that did not converge', async () => {
		const ws = workspace(twoScenarios(), (id) => (id === 'S1' ? notConverged() : converged()));
		await ws.store.solveAll();
		// A change to S2's own value: only S2 goes out of date.
		ws.store.update((d) => {
			d.scenarios!.find((s) => s.id === 'S2')!.overrides![0]!.value = 0.8;
		}, 'speed');
		expect(ws.store.caseIds.map((c) => ws.store.caseStatus(c))).toEqual([
			'solved',
			'not_converged',
			'stale'
		]);
		const bundle = bundleOf(ws, ALL);
		const flags = readSheet(bundle, 'flags');
		expect(flags.rows.map((r) => [flags.get(r, 'Case id'), flags.get(r, 'Results')])).toEqual([
			['S1', 'Did not converge']
		]);
		const nodes = readSheet(bundle, 'nodes');
		const marks = new Map(
			nodes.rows.map((r) => [nodes.get(r, 'Case id'), nodes.get(r, 'Results')])
		);
		expect([...marks]).toEqual([
			[null, 'Current'],
			['S2', 'Out of date']
		]);
		expect(bundle.sheets.find((s) => s.id === 'flags')!.caption).toContain(
			' — includes a solve that did not converge'
		);
		expect(bundle.sheets.find((s) => s.id === 'nodes')!.caption).toContain(
			' — includes out-of-date results'
		);
		expect(bundle.sheets.find((s) => s.id === 'nodes')!.caption).not.toContain('did not converge');
		expect(bundle.warnings.map((w) => w.kind)).toEqual(['not_converged', 'stale']);
	});

	it('lists failed, not reached and not solved cases in About only', async () => {
		const ws = workspace(twoScenarios(), (id) =>
			id === 'S1' ? new TopologyError('No fixed head', []) : converged()
		);
		await ws.store.solve(undefined, null);
		await ws.store.solve(undefined, 'S1');
		expect(ws.store.caseIds.map((c) => ws.store.caseStatus(c))).toEqual([
			'solved',
			'failed',
			'not_solved'
		]);
		const bundle = bundleOf(ws, ALL);
		expect(new Set(readSheet(bundle, 'nodes').column('Case id'))).toEqual(new Set([null]));
		const about = readSheet(bundle, 'about');
		const value = (section: string, item: string) =>
			about.rows.find((r) => r[0] === section && r[1] === item)?.[2];
		expect(value('Case: Winter (S1)', 'Status')).toBe('Failed');
		expect(value('Case: Winter (S1)', 'Values in this file')).toBe(
			'No: the latest solve failed (No fixed head); results kept from an earlier version of the project are not used.'
		);
		expect(value('Case: Winter (S1)', 'Error')).toBe('No fixed head');
		expect(value('Case: Peak (S2)', 'Values in this file')).toBe('No: not solved.');

		const stopped = workspace(twoScenarios(), (id) =>
			id === 'S1' ? new NetworkError('The server is busy', 503) : converged()
		);
		await stopped.store.solveAll();
		expect(stopped.store.caseStatus('S2')).toBe('not_reached');
		const about2 = readSheet(bundleOf(stopped, ALL), 'about');
		expect(
			about2.rows.find((r) => r[0] === 'Case: Peak (S2)' && r[1] === 'Values in this file')?.[2]
		).toBe('No: not solved: the Solve all run stopped after a network error.');
	});

	it('never uses a failed case’s earlier response, even when revealed, and warns', async () => {
		let fail = false;
		const ws = workspace(pumpTransferExample(), () =>
			fail ? new TopologyError('Broken', []) : converged()
		);
		await ws.store.solve();
		lengthen(ws);
		fail = true;
		await ws.store.solve();
		expect(ws.store.caseStatus(null)).toBe('failed');
		expect(ws.store.results.response).not.toBeNull();
		const bundle = bundleOf(ws);
		expect(sheetIds(bundle)).toEqual(['about', 'flags']);
		expect(readSheet(bundle, 'flags').rows).toEqual([]);
		expect(bundle.warnings.map((w) => w.kind)).toEqual(['failed_shown']);
		expect(bundle.sheets[0]!.caption).toBe(
			'About — Pump transfer between two tanks — no results in this file: Failed'
		);
	});
});

describe('project links (item 8)', () => {
	it('a current case links the current project; one link for every case it reproduces', async () => {
		const ws = workspace(twoScenarios(), () => converged());
		await ws.store.solveAll();
		const about = readSheet(bundleOf(ws, ALL), 'about');
		const links = about.rows.filter(
			(r) => r[0] === 'Project links' && /^Link \d+$/.test(r[1] as string)
		);
		expect(links.map((r) => r[2])).toEqual([projectUrl(ws.store.project, PAGE.origin)]);
		expect(about.rows.find((r) => r[1] === 'Link 1 reproduces')?.[2]).toBe(
			'Base case; Winter (S1); Peak (S2)'
		);
	});

	it('an out-of-date case of a 1.1.0 link solved under 1.2.0 records 1.2.0 in its link', async () => {
		const project = { ...pumpTransferExample(), methodVersion: '1.1.0' };
		const ws = workspace(project, () => converged({ methodVersion: '1.2.0' }));
		await ws.store.solve();
		expect(ws.store.sentProjectFor(null)!.methodVersion).toBe('1.1.0');
		lengthen(ws);
		const about = readSheet(bundleOf(ws), 'about');
		const value = (item: string) => about.rows.find((r) => r[1] === item)?.[2];
		expect(value('Calculation methods version')).toBe('1.2.0');
		expect(value('Calculation methods changed')).toContain(
			'last solved with calculation methods version 1.1.0'
		);
		const linked = decodeProject(fragmentOf(value('Link 1') as string));
		expect(linked.methodVersion).toBe('1.2.0');
		expect(linked.connections.find((c) => c.id === 'L3')!.piping.pipes[0]!.length).toBe(60);
	});

	it('with the checkbox off: no link, and the file says it was left out', async () => {
		const ws = workspace(pumpTransferExample(), () => converged());
		await ws.store.solve();
		const bundle = bundleOf(ws, { ...SHOWN, link: false });
		const about = readSheet(bundle, 'about');
		expect(about.rows.some((r) => r[0] === 'Project links')).toBe(false);
		expect(about.rows.some((r) => typeof r[2] === 'string' && r[2].includes('/p#'))).toBe(false);
		expect(about.rows).toContainEqual([
			'Not in this file',
			'Project link',
			'left out when exported'
		]);
		expect(about.rows).toContainEqual(['Results', 'Project link', 'Left out when exported']);
		expect(bundle.omitted).toContainEqual({
			what: 'Project link',
			reason: 'left out when exported'
		});
	});

	it('a link longer than a cell gives a note in the workbook and the full link in about.csv', async () => {
		// Random text, so the link cannot compress below a cell's 32,767 characters.
		let x = 7;
		const noise = Array.from({ length: 60_000 }, () => {
			x ^= x << 13;
			x ^= x >>> 17;
			x ^= x << 5;
			return String.fromCharCode(33 + ((x >>> 0) % 90));
		}).join('');
		const input = fixtureInput('pump-transfer');
		input.project = {
			...input.project,
			metadata: { ...input.project.metadata, description: noise }
		};
		const url = projectUrl(input.project, input.origin);
		expect(url.length).toBeGreaterThan(32_767);
		const xlsx = readSheet(buildExport(input), 'about');
		expect(xlsx.rows.find((r) => r[1] === 'Link 1')?.[2]).toBe(
			`Not included: ${url.length} characters, more than a spreadsheet cell holds; copy it from Share in the app`
		);
		const csvInput = { ...input, options: { ...input.options, format: 'csv' as const } };
		const zip = readZip(await blobBytes(await writeCsvZip(buildExport(csvInput))));
		const about = entryText(zip, 'results 2026-10-25 1432/about.csv');
		expect(about).toContain(`Project links,Link 1,${url}\r\n`);
	});
});

describe('Compare cases (item 9)', () => {
	it('values and exact differences equal compareCells’, with no "Same"', async () => {
		const ws = workspace(twoScenarios(), (id) =>
			id === 'S1'
				? converged({
						pumpResults: { P1: pumpResult({ operatingFlow: 0.018, operatingHead: 23.5 }) },
						linkResults: {
							...pumpTransferSolved().linkResults,
							L2: link({ flow: 0.018, velocity: 3.6 })
						}
					})
				: converged()
		);
		await ws.store.solveAll();
		ws.compareRows = [
			{ quantity: 'status' },
			{ quantity: 'pumpFlow', elementId: 'P1' },
			{ quantity: 'pumpHead', elementId: 'P1' },
			{ quantity: 'linkVelocity', elementId: 'L2' },
			{ quantity: 'portPressure', elementId: 'P1', portId: 'discharge' },
			{ quantity: 'valveState', elementId: 'V1' },
			{ quantity: 'lowestPressure' }
		];
		const bundle = bundleOf(ws, ALL);
		const t = readSheet(bundle, 'compare-cases');
		expect(t.column('Row').slice(0, 2)).toEqual(['Status', 'Solved at']);
		const prefs = ws.displayUnits;
		const f = new Formatter(prefs);
		const solved = ws.store.caseIds.map((c) => ws.store.resultsFor(c).response!.solvedState);
		const columns: CompareColumn[] = solved.map((s) => ({ solved: s, converged: true }));
		for (const row of ws.compareRows.slice(1)) {
			const spec = QUANTITIES[row.quantity];
			const exported = t.rows.find(
				(r) =>
					t.get(r, 'Quantity') === spec.label && t.get(r, 'Element id') === (row.elementId ?? null)
			)!;
			const cells = compareCells(row, columns, ws.labelsProject, prefs);
			const base = spec.value(solved[0]!, row) as number | string;
			const scenario = spec.value(solved[1]!, row) as number | string;
			if (typeof base === 'string') {
				expect(t.get(exported, 'Base case')).toBe(base);
				expect(t.get(exported, 'Winter (S1): difference from base')).toBeNull();
				continue;
			}
			const unit = displayUnit(spec.category!, prefs);
			expect(t.get(exported, 'Base case')).toBe(fromSI(base, unit));
			expect(t.get(exported, 'Winter (S1)')).toBe(fromSI(scenario as number, unit));
			const exact = (scenario as number) - base;
			expect(t.get(exported, 'Winter (S1): difference from base')).toBe(fromSI(exact, unit));
			expect(cells[1]!.diff!.title).toBe(`Difference: ${f.value(exact, spec.category!)}`);
			const pct = t.labels.indexOf('Winter (S1): difference from base') + 1;
			expect(exported[pct]).toBe(
				spec.relative && base !== 0 ? (exact / Math.abs(base)) * 100 : null
			);
		}
		expect(t.rows.flat()).not.toContain('Same');
		expect(t.column('Row')).toContain('Network · Lowest pressure (where)');
	});
});

describe('Compare cases reads a connection on it as it is now (rows name its ends now)', () => {
	/** Reverse L3 (ends swapped, pipes in the other order), as Build's turning of a connection does. */
	function reverseL3(ws: Workspace): void {
		const result = ws.store.update((d) => {
			const c = d.connections.find((x) => x.id === 'L3')!;
			[c.fromComponentId, c.toComponentId] = [c.toComponentId, c.fromComponentId];
			[c.fromPortId, c.toPortId] = [c.toPortId, c.fromPortId];
			c.piping = reversePiping(c.piping);
		}, 'reverse');
		expect(result.ok).toBe(true);
	}
	/** The solver's L3: from the discharge tank once reversed, so its flow and head loss are negative. */
	const answer: Answer = (_id, p) => {
		const back = p.connections.find((c) => c.id === 'L3')?.fromComponentId === 'R2';
		return back
			? converged({
					linkResults: {
						...pumpTransferSolved().linkResults,
						L3: link({ flow: -0.02, velocity: -4, headLoss: -8 })
					}
				})
			: converged();
	};
	const l3Rows = [
		{ quantity: 'linkFlow', elementId: 'L3' },
		{ quantity: 'linkHeadLoss', elementId: 'L3' }
	] as const;

	it('gives a case solved before a reversal with the other sign, and About says which', async () => {
		const ws = workspace(twoScenarios(), answer);
		await ws.store.solveAll();
		reverseL3(ws);
		await ws.store.solve(); // the base again; Winter and Peak stay out of date
		ws.compareRows = [...l3Rows];
		const bundle = bundleOf(ws, ALL);
		const t = readSheet(bundle, 'compare-cases');
		const row = (quantity: string) =>
			t.rows.find((r) => t.get(r, 'Element id') === 'L3' && t.get(r, 'Quantity') === quantity)!;
		for (const [quantity, si, unit] of [
			['Flow', -0.02, 'L/s'],
			['Head loss', -8, 'm']
		] as const) {
			expect(t.get(row(quantity), 'Base case')).toBe(fromSI(si, unit));
			expect(t.get(row(quantity), 'Winter (S1)')).toBe(fromSI(si, unit));
			expect(t.get(row(quantity), 'Winter (S1): difference from base')).toBe(0);
		}
		const sign = readSheet(bundle, 'about').rows.find((r) => r[1] === 'Sign: Compare cases');
		expect(sign?.[2]).toContain('Discharge tank → Discharge isolation valve · Flow (Winter (S1))');
	});

	it('leaves out what a case solved before an end moved cannot place, and says so', async () => {
		const ws = workspace(twoScenarios(), () => converged());
		await ws.store.solveAll();
		expect(ws.insert('L3', 'gate')).toBe('V2');
		await ws.store.solve();
		ws.compareRows = [...l3Rows];
		const bundle = bundleOf(ws, ALL);
		const t = readSheet(bundle, 'compare-cases');
		const loss = t.rows.find(
			(r) => t.get(r, 'Element id') === 'L3' && t.get(r, 'Quantity') === 'Head loss'
		)!;
		// L3 now ends at the new valve: its head loss as solved was to the tank.
		expect(t.get(loss, 'Winter (S1)')).toBeNull();
		const what =
			'Compare cases: Discharge isolation valve → Gate valve V2 · Head loss (Winter (S1))';
		expect(readSheet(bundle, 'about').rows).toContainEqual([
			'Not in this file',
			what,
			"its connection's ends changed since that case was solved"
		]);
		expect(bundle.omitted).toContainEqual({
			what,
			reason: "its connection's ends changed since that case was solved"
		});
	});

	it('leaves out the largest velocity of a case solved before a pipe was added, and says so', async () => {
		const ws = workspace(twoScenarios(), () => converged());
		await ws.store.solveAll();
		ws.editConnection('L3', 'add pipe segment', (c) => ({ ...c, piping: addPipe(c.piping) }));
		await ws.store.solve();
		ws.compareRows = [
			{ quantity: 'linkFlow', elementId: 'L3' },
			{ quantity: 'linkVelocity', elementId: 'L3' }
		];
		const bundle = bundleOf(ws, ALL);
		const t = readSheet(bundle, 'compare-cases');
		const row = (quantity: string) =>
			t.rows.find((r) => t.get(r, 'Element id') === 'L3' && t.get(r, 'Quantity') === quantity)!;
		// Winter's solve has no velocity of the pipe added: no largest velocity refers to L3 now.
		expect(t.get(row('Largest velocity'), 'Winter (S1)')).toBeNull();
		// Its flow is still the flow between the ports it was solved between (out of date).
		expect(t.get(row('Flow'), 'Winter (S1)')).toBe(fromSI(0.02, 'L/s'));
		const what =
			'Compare cases: Discharge isolation valve → Discharge tank · Largest velocity (Winter (S1))';
		const reason = "its connection's pipes changed since that case was solved";
		expect(readSheet(bundle, 'about').rows).toContainEqual(['Not in this file', what, reason]);
		expect(bundle.omitted).toContainEqual({ what, reason });
	});
});

describe('system curves (item 12)', () => {
	it("give the chart table's reason for a point without a head; About lists those not computed", async () => {
		const curve = systemCurveResponse('P1', [1, 3]);
		const ws = testWorkspace(pumpTransferExample(), {
			solver: { solve: async () => converged(), systemCurve: async () => curve }
		});
		await ws.store.solve();
		const before = bundleOf(ws);
		expect(sheetIds(before)).not.toContain('system-curves');
		const reason = 'not computed: open the pump’s chart to compute it';
		expect(readSheet(before, 'about').rows).toContainEqual([
			'Results',
			'System curve of Transfer pump',
			`Not included: ${reason}`
		]);
		expect(before.omitted).toContainEqual({ what: 'System curve of Transfer pump', reason });
		ws.store.loadSystemCurve('P1');
		await new Promise((resolve) => setTimeout(resolve, 0));
		const t = readSheet(bundleOf(ws), 'system-curves');
		const solved = ws.store.results.response!.solvedState;
		const rows = pumpChartData(solved.pumpResults.P1!, ws.displayUnits, null, curve, {
			project: ws.labelsProject,
			solved: ws.store.solvedProject
		}).systemRows;
		expect(t.column('Reason')).toEqual(rows.map((r) => r.note || null));
		expect(t.column('Reason').filter((r) => r !== null)).toHaveLength(2);
		expect(t.column('Head')).toEqual([12, null, 22, null]);
		expect(t.column('Converged')).toEqual([true, false, true, false]);
	});

	it('say why a curve is not in the file: being computed, failed or cancelled', () => {
		const input = fixtureInput('pump-transfer');
		const say = (state: unknown) => {
			const c = { ...input.cases[0]!, systemCurves: { P1: state } } as (typeof input.cases)[number];
			const about = readSheet(buildExport({ ...input, cases: [c] }), 'about');
			return about.rows.find(
				(r) => r[0] === 'Results' && r[1] === 'System curve of Transfer pump'
			)?.[2];
		};
		expect(say({ status: 'loading' })).toBe('Not included: being computed when exported');
		expect(say({ status: 'error', message: 'Busy' })).toBe('Not included: failed: Busy');
		expect(say({ status: 'cancelled', by: 'user' })).toBe('Not included: cancelled');
	});

	it('count a pump whose only ready curve is an overlay range as included, and say so (review V1)', () => {
		const input = fixtureInput('pump-transfer');
		const ready = input.cases[0]!.systemCurves.P1!;
		if (ready.status !== 'ready') throw new Error('not ready');
		// Only the curve another case's chart drew over its own range: 0 to 0.03 m³/s.
		const overlay = {
			status: 'ready',
			curve: { ...ready.curve, flowRange: { ...ready.curve.flowRange, min: 0, max: 0.03 } }
		};
		for (const cases of ['shown', 'all'] as const) {
			const c = {
				...input.cases[0]!,
				systemCurves: { 'P1\u00000\u00000.03': overlay }
			} as (typeof input.cases)[number];
			const bundle = buildExport({ ...input, options: { ...input.options, cases }, cases: [c] });
			const t = readSheet(bundle, 'system-curves');
			expect(t.rows).toHaveLength(ready.curve.points.length);
			expect(new Set(t.column('Pump id'))).toEqual(new Set(['P1']));
			const about = readSheet(bundle, 'about').rows;
			const item = (name: string) => about.filter((r) => r[1] === name).map((r) => r[2]);
			expect(item('System curves included')).toEqual(['Transfer pump']);
			expect(item('System curve of Transfer pump')).toEqual([
				"Included only over another case's chart range (Flow from and Flow to in System curves), where it was drawn for comparison; its default range is not in the file (not computed: open the pump’s chart to compute it)"
			]);
			expect(
				about.filter((r) => r[0] === 'Not in this file' && /System curve/.test(String(r[1])))
			).toEqual([]);
			expect(bundle.omitted.filter((o) => /System curve/.test(o.what))).toEqual([]);
		}
		// With the default range ready too, nothing more is said.
		const both = {
			...input.cases[0]!,
			systemCurves: { P1: ready, 'P1\u00000\u00000.03': overlay }
		} as (typeof input.cases)[number];
		const bundle = buildExport({ ...input, cases: [both] });
		expect(readSheet(bundle, 'system-curves').rows).toHaveLength(2 * ready.curve.points.length);
		const about = readSheet(bundle, 'about').rows;
		expect(about.filter((r) => r[1] === 'System curves included').map((r) => r[2])).toEqual([
			'Transfer pump'
		]);
		expect(about.filter((r) => r[1] === 'System curve of Transfer pump')).toEqual([]);
	});
});

describe('boundary ports (item 11)', () => {
	it('appear only for a boundary with more than one port', () => {
		expect(sheetIds(buildExport(fixtureInput('pump-transfer')))).not.toContain('boundary-ports');
		const t = readSheet(buildExport(fixtureInput('scenarios')), 'boundary-ports');
		expect(new Set(t.column('Boundary id'))).toEqual(new Set(['R1']));
		expect(t.rows).toHaveLength(6);
	});
});

describe('determinism (item 14)', () => {
	const saved = { tz: process.env.TZ, api: process.env.PUBLIC_API_URL };
	afterEach(() => {
		process.env.TZ = saved.tz;
		if (saved.api === undefined) delete process.env.PUBLIC_API_URL;
		else process.env.PUBLIC_API_URL = saved.api;
	});

	const bytes = async (format: 'xlsx' | 'csv') => {
		const bundle = buildExport(fixtureInput('pump-transfer', { format }));
		return blobBytes(await (format === 'xlsx' ? writeXlsx(bundle) : writeCsvZip(bundle)));
	};

	it('the bytes do not change with the time zone, PUBLIC_API_URL or the build', async () => {
		process.env.TZ = 'Pacific/Honolulu';
		process.env.PUBLIC_API_URL = 'https://one.example';
		const a = [await bytes('xlsx'), await bytes('csv')];
		process.env.TZ = 'Asia/Kathmandu';
		process.env.PUBLIC_API_URL = 'https://two.example';
		const b = [await bytes('xlsx'), await bytes('csv')];
		expect(a).toEqual(b);
	});

	it('About’s source link is the input’s build commit’s, never this build’s', () => {
		const input = fixtureInput('pump-transfer');
		const about = readSheet(buildExport(input), 'about');
		expect(about.rows.find((r) => r[1] === 'Web app source, at that commit')?.[2]).toBe(
			sourceLinks(input.appVersion).source
		);
		const other = { ...input, appVersion: 'f'.repeat(40) };
		expect(
			readSheet(buildExport(other), 'about').rows.find(
				(r) => r[1] === 'Web app source, at that commit'
			)?.[2]
		).toBe(sourceLinks('f'.repeat(40)).source);
	});
});
