/**
 * The export's snapshot (proposal export.md §2.1): what exportInput takes from the workspace's
 * public getters, with the real ProjectStore and a fake solver (testing/workspace.ts): the cases
 * the choice exports, each response by Compare's rule, its staleness, the projects as sent and as
 * solved, its system curves, the Compare rows, the goal seek and the page's facts.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { version } from '$app/environment';
import { TopologyError } from '../../api/client';
import { serverSourceHref } from '../../components/links';
import { pumpTransferSolved, response, systemCurveResponse } from '../../testing/results';
import { testWorkspace } from '../../testing/workspace';
import { defaultRows } from '../compare';
import { CANONICAL_ORIGIN } from '../encoding';
import { pumpTransferExample } from '../examples';
import { withScenarios } from '../scenarios';
import { exportInput, pageFacts } from './input';
import type { ExportOptions } from './model';

const NOW = new Date('2026-10-25T12:32:05Z');
const PAGE = {
	appVersion: 'abc',
	serverSource: 'https://api.test/source',
	origin: 'https://x.test/'
};
const SHOWN: ExportOptions = { cases: 'shown', format: 'xlsx', units: 'display', link: true };
const savedTz = process.env.TZ;

afterEach(() => {
	process.env.TZ = savedTz;
});

function scenarioProject() {
	return withScenarios(pumpTransferExample(), [
		{
			id: 'S1',
			name: 'Winter',
			overrides: [{ kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 4 }]
		}
	]);
}

describe('the snapshot', () => {
	it('takes the page’s time and offset, the facts given and the current project', async () => {
		process.env.TZ = 'Asia/Kolkata';
		const ws = testWorkspace(pumpTransferExample(), {
			solver: { solve: async () => response(pumpTransferSolved()) }
		});
		await ws.store.solve();
		const input = exportInput(ws, SHOWN, NOW, PAGE);
		expect(input.now).toBe(NOW);
		expect(input.utcOffsetMinutes).toBe(330);
		expect(input.options).toBe(SHOWN);
		expect([input.appVersion, input.serverSource, input.origin]).toEqual([
			'abc',
			'https://api.test/source',
			'https://x.test'
		]);
		expect(input.project).toBe(ws.store.project);
		expect(input.prefs).toBe(ws.displayUnits);
		expect(input.loadedMethodVersion).toBe(ws.store.loadedMethodVersion);
		expect(input.library).toEqual({ materials: {}, fittings: {}, nominalSizes: [] });
		const [c] = input.cases;
		expect(input.cases).toHaveLength(1);
		expect(c).toMatchObject({
			id: null,
			name: 'Base case',
			status: 'solved',
			stale: false,
			error: null
		});
		expect(c!.response).toBe(ws.store.results.response);
		expect(c!.sent).toBe(ws.store.sentProjectFor(null));
		expect(c!.inputs).toBe(ws.store.caseInputs(null));
	});

	it('exports the case shown, or every case with scenarios', async () => {
		const ws = testWorkspace(scenarioProject(), {
			solver: { solve: async () => response(pumpTransferSolved()) }
		});
		await ws.store.solveAll();
		ws.setCase('S1');
		expect(exportInput(ws, SHOWN, NOW, PAGE).cases.map((c) => c.id)).toEqual(['S1']);
		const all = exportInput(ws, { ...SHOWN, cases: 'all' }, NOW, PAGE);
		expect(all.cases.map((c) => [c.id, c.name])).toEqual([
			[null, 'Base case'],
			['S1', 'Winter']
		]);
		expect(all.shownCase).toBe('S1');
		expect(all.cases[1]!.inputs).toBe(ws.store.caseInputs('S1'));
		// The Compare tab's rows: its defaults, as CompareView computes them, or the rows chosen.
		const solved = all.cases.map((c) => c.response!.solvedState);
		expect(all.compareRows).toEqual(defaultRows(ws.store.project, solved));
		ws.compareRows = [{ quantity: 'status' }];
		expect(exportInput(ws, SHOWN, NOW, PAGE).compareRows).toBe(ws.compareRows);
	});

	it('takes a case’s response by Compare’s rule: none for a failed case, which says so', async () => {
		let fail = false;
		const ws = testWorkspace(pumpTransferExample(), {
			solver: {
				solve: async () => {
					if (fail) throw new TopologyError('No fixed head', []);
					return response(pumpTransferSolved());
				}
			}
		});
		await ws.store.solve();
		ws.store.update((d) => {
			d.connections[0]!.piping.pipes[0]!.length = 7;
		}, 'edit');
		expect(exportInput(ws, SHOWN, NOW, PAGE).cases[0]).toMatchObject({
			status: 'stale',
			stale: true
		});
		fail = true;
		await ws.store.solve();
		const c = exportInput(ws, SHOWN, NOW, PAGE).cases[0]!;
		expect(c).toMatchObject({
			status: 'failed',
			response: null,
			stale: false,
			error: 'No fixed head',
			keptResponse: true,
			sent: null,
			inputs: null,
			systemCurves: {}
		});
	});

	it('takes the case’s system curves, as computed, and the finished goal seek', async () => {
		const curve = systemCurveResponse('P1');
		const ws = testWorkspace(pumpTransferExample(), {
			solver: {
				solve: async () => response(pumpTransferSolved()),
				systemCurve: async () => curve
			}
		});
		await ws.store.solve();
		ws.store.loadSystemCurve('P1');
		await new Promise((resolve) => setTimeout(resolve, 0));
		const input = exportInput(ws, SHOWN, NOW, PAGE);
		expect(input.cases[0]!.systemCurves).toEqual({ P1: { status: 'ready', curve } });
		expect(input.goalSeek).toBeNull();
	});
});

describe('the page’s facts', () => {
	it('are the build’s version, the server’s source link and the origin', () => {
		expect(pageFacts()).toEqual({
			appVersion: version,
			serverSource: serverSourceHref(),
			origin: CANONICAL_ORIGIN
		});
	});
});
