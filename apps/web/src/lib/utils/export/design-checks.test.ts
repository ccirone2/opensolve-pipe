/**
 * The export's Design checks sheet (CLAUDE.md D19), on the real API's results of the shared
 * fixture's `design-checks` case (export_input.py: every check on, US display units): after Flags,
 * one row per result in the screen's order (not met, met, not evaluated), each value and limit
 * `fromSI` of the API's number in the row's Unit (the API's double itself in SI base units), the
 * screen's words in the file's units, the server's message and source as reported, and an About
 * line only in a file that has the sheet. A case that did not converge has none.
 */
import { describe, expect, it } from 'vitest';
import type { DesignCheckResult } from '../../api/types';
import { CHECK_CATEGORIES, checkText, groupChecks } from '../design-checks';
import { displayUnit, fromSI, unitLabel } from '../units';
import { fixtureInput, FIXTURE_NAMES, readSheet, sheetIds } from './export-testing.testing';
import { buildExport, type ExportInput } from './model';

const solvedOf = (input: ExportInput) => input.cases[0]!.response!.solvedState;

describe('the Design checks sheet', () => {
	it('follows Flags, in the screen order, with display values fromSI of the API', () => {
		const input = fixtureInput('design-checks');
		const bundle = buildExport(input);
		const ids = sheetIds(bundle);
		expect(ids.indexOf('design-checks')).toBe(ids.indexOf('flags') + 1);
		const t = readSheet(bundle, 'design-checks');
		expect(t.headers).toEqual([
			'Solved at',
			'Results',
			'Outcome',
			'Check',
			'Element kind',
			'Element id',
			'Element',
			'Pipe #',
			'Pipes outside #',
			'Value',
			'Lower limit',
			'Upper limit',
			'Unit',
			'Limits from',
			'Result',
			'Message (as reported, SI)',
			'Limits from (as reported)'
		]);
		const results = solvedOf(input).designChecks;
		const ordered: DesignCheckResult[] = groupChecks(results).flatMap((g) => g.results);
		expect(t.rows).toHaveLength(results.length);
		expect(t.rows.map((r) => t.get(r, 'Outcome'))).toEqual([
			'Not met',
			'Not met',
			'Not met',
			'Met',
			'Met',
			'Met',
			'Met',
			'Not evaluated'
		]);
		const prefs = input.prefs;
		t.rows.forEach((row, i) => {
			const r = ordered[i]!;
			const unit = displayUnit(CHECK_CATEGORIES[r.check], prefs);
			const cell = (si: number | null | undefined) =>
				si === null || si === undefined ? null : fromSI(si, unit);
			expect(t.get(row, 'Element id')).toBe(r.componentId ?? r.connectionId);
			expect(t.get(row, 'Value')).toBe(cell(r.value));
			expect(t.get(row, 'Lower limit')).toBe(cell(r.limits.min));
			expect(t.get(row, 'Upper limit')).toBe(cell(r.limits.max));
			expect(t.get(row, 'Unit')).toBe(unitLabel(CHECK_CATEGORIES[r.check], unit) || null);
			expect(t.get(row, 'Result')).toBe(checkText(r, prefs));
			expect(t.get(row, 'Message (as reported, SI)')).toBe(r.message);
			expect(t.get(row, 'Limits from (as reported)')).toBe(r.source);
		});
		const motor = t.rows[0]!;
		expect(t.get(motor, 'Check')).toBe('Motor power');
		expect(t.get(motor, 'Element')).toBe('Transfer pump');
		expect(t.get(motor, 'Unit')).toBe('hp');
		expect(t.get(motor, 'Limits from')).toBe("the pump curve's manufacturer data");
		const pipe = t.rows[1]!;
		expect([t.get(pipe, 'Element kind'), t.get(pipe, 'Pipe #'), t.get(pipe, 'Unit')]).toEqual([
			'Connection',
			1,
			'ft/s'
		]);
		expect(t.get(pipe, 'Pipes outside #')).toBe('1'); // data: every pipe outside, one too
		const met = t.rows.find((r) => t.get(r, 'Element id') === 'L1')!;
		expect([t.get(met, 'Outcome'), t.get(met, 'Pipes outside #')]).toEqual(['Met', null]);
		expect(t.get(t.rows[3]!, 'Unit')).toBe('%');
		expect(t.get(t.rows[3]!, 'Limits from')).toBe('API 610 preset');
	});

	it('SI base units: every number cell is the API double', () => {
		const input = fixtureInput('design-checks', { units: 'si' });
		const t = readSheet(buildExport(input), 'design-checks');
		const ordered = groupChecks(solvedOf(input).designChecks).flatMap((g) => g.results);
		t.rows.forEach((row, i) => {
			const r = ordered[i]!;
			for (const [label, api] of [
				['Value', r.value],
				['Lower limit', r.limits.min],
				['Upper limit', r.limits.max]
			] as const) {
				if (api === null || api === undefined) expect(t.get(row, label)).toBeNull();
				else expect(Object.is(t.get(row, label), api), label).toBe(true);
			}
		});
	});

	it('is in a file only with design checks, and so is its About line', () => {
		const about = (input: ExportInput) => {
			const sheet = readSheet(buildExport(input), 'about');
			return sheet.rows.filter((row) => sheet.get(row, 'Item') === 'Design checks');
		};
		for (const name of FIXTURE_NAMES.filter((n) => n !== 'design-checks')) {
			const input = fixtureInput(name);
			expect(sheetIds(buildExport(input))).not.toContain('design-checks');
			expect(about(input), name).toEqual([]);
		}
		const [line] = about(fixtureInput('design-checks'));
		expect(line?.[2]).toMatch(/^Opt-in design practice the project turned on, not physics flags/);
		expect(line?.[2]).toContain("in the fractions' unit");
		const [si] = about(fixtureInput('design-checks', { units: 'si' }));
		expect(si?.[2]).toContain('a ratio with no unit, 1 at the best efficiency flow');
		expect(si?.[2]).toContain('give fractions in % and powers in kW');
	});

	it('has no rows for a case that did not converge', () => {
		const input = fixtureInput('design-checks');
		const failed: ExportInput = {
			...input,
			cases: input.cases.map((c) => ({
				...c,
				response: c.response && {
					...c.response,
					success: false,
					solvedState: { ...c.response.solvedState, converged: false }
				}
			}))
		};
		expect(sheetIds(buildExport(failed))).not.toContain('design-checks');
	});
});
