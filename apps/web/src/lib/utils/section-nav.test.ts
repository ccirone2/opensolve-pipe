/**
 * The section nav's pure parts (proposal pumps-results-layout.md §5.4): the marks by §5.2's
 * severities with their visually hidden words, the Tab stop clamped to the buttons drawn, and the
 * sideways scroll that keeps a row's current item and the next in view.
 */
import { describe, expect, it } from 'vitest';
import type { Flag } from '$lib/api/types';
import { flag as made } from '$lib/testing/results';
import {
	clampSection,
	flagSeverities,
	keepInViewLeft,
	SECTION_LABELS,
	SECTIONS,
	sectionMark
} from './section-nav';

describe('sectionMark (§5.4 Marks)', () => {
	it('gives each of the four marks, with words that start with a comma', () => {
		expect(sectionMark({ invalid: true })).toEqual({
			kind: 'invalid',
			words: ', has physically invalid values'
		});
		expect(sectionMark({ warning: true })).toEqual({ kind: 'warning', words: ', has warnings' });
		expect(sectionMark({ refused: true })).toEqual({ kind: 'refused', words: ', has a refusal' });
		expect(sectionMark({ failed: true })).toEqual({ kind: 'failed', words: ', a request failed' });
	});

	it('gives the worst: invalid, then warning, then a refusal, then a failed request', () => {
		expect(sectionMark({ invalid: true, warning: true, refused: true, failed: true })?.kind).toBe(
			'invalid'
		);
		expect(sectionMark({ warning: true, refused: true, failed: true })?.kind).toBe('warning');
		expect(sectionMark({ refused: true, failed: true })?.kind).toBe('refused');
	});

	it('gives none when nothing is marked', () => {
		expect(sectionMark({})).toBeNull();
		expect(
			sectionMark({ invalid: false, warning: false, refused: false, failed: false })
		).toBeNull();
	});
});

describe('flagSeverities', () => {
	const flag = (severity: Flag['severity']) =>
		made({ code: 'PUMP_OUTSIDE_CURVE', severity, message: 'm', componentId: 'P1' });

	it('reads invalid and warning; an info flag marks nothing', () => {
		expect(flagSeverities([])).toEqual({ invalid: false, warning: false });
		expect(flagSeverities([flag('info')])).toEqual({ invalid: false, warning: false });
		expect(flagSeverities([flag('info'), flag('warning')])).toEqual({
			invalid: false,
			warning: true
		});
		expect(flagSeverities([flag('invalid'), flag('warning')])).toEqual({
			invalid: true,
			warning: true
		});
		expect(sectionMark(flagSeverities([flag('info')]))).toBeNull();
	});
});

describe('the sections', () => {
	it('are in the tab’s reading order, each with its button’s words (§6.2)', () => {
		expect(SECTIONS.map((key) => SECTION_LABELS[key])).toEqual([
			'Per pump',
			'Pump chart',
			'Pumps together',
			'Station',
			'Group chart',
			'Add cases',
			'Running combinations'
		]);
	});
});

describe('clampSection (§5.4 One Tab stop)', () => {
	it('keeps the same section while its button is drawn', () => {
		expect(clampSection('station', ['per-pump', 'pump-chart', 'pumps-together', 'station'])).toBe(
			'station'
		);
	});

	it('else the nearest earlier one in reading order', () => {
		expect(clampSection('group-chart', ['per-pump', 'pump-chart', 'pumps-together'])).toBe(
			'pumps-together'
		);
		expect(
			clampSection('combinations', ['per-pump', 'pump-chart', 'pumps-together', 'station'])
		).toBe('station');
	});

	it('else the first drawn; none with no button', () => {
		expect(clampSection('per-pump', ['pump-chart', 'pumps-together'])).toBe('pump-chart');
		expect(clampSection(null, ['pump-chart', 'pumps-together'])).toBe('pump-chart');
		expect(clampSection('station', [])).toBeNull();
	});
});

describe('keepInViewLeft (the row-only scroll)', () => {
	const row = { scrollLeft: 0, clientWidth: 300, scrollWidth: 800, padStart: 4, padEnd: 12 };

	it('moves nothing when the item and the next are in view', () => {
		expect(keepInViewLeft(row, { left: 10, right: 90 }, { right: 180 })).toBeNull();
	});

	it('scrolls right until the next item’s end and the row’s end padding are in view', () => {
		// The next one ends at 400, plus 12 of padding: 412 − 300.
		expect(keepInViewLeft(row, { left: 250, right: 320 }, { right: 400 })).toBe(112);
	});

	it('scrolls left to the item’s start less the start padding', () => {
		expect(keepInViewLeft({ ...row, scrollLeft: 300 }, { left: 104, right: 180 }, null)).toBe(100);
	});

	it('puts the item’s start first when the two cannot both fit', () => {
		expect(keepInViewLeft(row, { left: 400, right: 600 }, { right: 790 })).toBe(396);
	});

	it('stays within the row’s scroll range', () => {
		expect(keepInViewLeft(row, { left: 700, right: 790 }, null)).toBe(500);
		expect(keepInViewLeft({ ...row, scrollLeft: 50 }, { left: 2, right: 60 }, null)).toBe(0);
	});
});
