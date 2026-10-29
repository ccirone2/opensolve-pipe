/**
 * The export and the Pumps together card (CLAUDE.md D21, proposal pump-groups.md §6.6): the
 * workbook is unchanged in slices 4a and 4b, and its About (and the dialog) list group curves and
 * group system curves among what is left out (slice 4c exports them), with the reason, whenever a
 * case of the file has two or more pumps with results.
 * The solve is the pump-group fixture's (a real API response).
 */
import { describe, expect, it } from 'vitest';
import type { Project, SolveResponse } from '../../api/types';
import fixture from '../__fixtures__/pump-groups-input.json';
import { GROUP_CURVES_ITEM, GROUP_CURVES_LEFT_OUT } from './context';
import { fixtureInput, readSheet } from './export-testing.testing';
import { buildExport, type ExportInput } from './model';

const parallel = (
	fixture.cases as unknown as { name: string; project: Project; solve: SolveResponse }[]
).find((c) => c.name === 'parallel-ideal')!;

/** The pump-transfer export input with the two-pump project and its solve in its place. */
function twoPumps(): ExportInput {
	const input = fixtureInput('pump-transfer');
	const [shown] = input.cases;
	return {
		...input,
		project: parallel.project,
		prefs: parallel.project.settings.units,
		goalSeek: null,
		cases: [
			{
				...shown!,
				response: parallel.solve,
				sent: parallel.project,
				inputs: parallel.project,
				systemCurves: {}
			}
		]
	};
}

describe('group curves in the export', () => {
	it('are listed as left out, group system curves too, with the reason, in About and in the dialog', () => {
		const bundle = buildExport(twoPumps());
		expect(GROUP_CURVES_ITEM).toBe('Group curves and group system curves');
		expect(readSheet(bundle, 'about').rows).toContainEqual([
			'Not in this file',
			'Group curves and group system curves',
			GROUP_CURVES_LEFT_OUT
		]);
		expect(bundle.omitted).toContainEqual({
			what: 'Group curves and group system curves',
			reason: GROUP_CURVES_LEFT_OUT
		});
		expect(GROUP_CURVES_LEFT_OUT).toBe(
			'not exported in this version: the Pumps together card under the pump chart draws them on request, and its Download image saves its chart'
		);
	});

	it('are not mentioned for a project with one pump', () => {
		const bundle = buildExport(fixtureInput('pump-transfer'));
		expect(readSheet(bundle, 'about').rows.filter((r) => r[1] === GROUP_CURVES_ITEM)).toEqual([]);
		expect(bundle.omitted.map((o) => o.what)).not.toContain(GROUP_CURVES_ITEM);
	});
});
