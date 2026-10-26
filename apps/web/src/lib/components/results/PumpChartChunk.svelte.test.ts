/**
 * The chart's chunk fails to load (a tab opened before a redeploy asks for files the new
 * deployment no longer has, or the connection dropped): the figure says so, naming both causes,
 * and how to recover, and shows its data table, instead of a blank chart (proposal export.md §9
 * item 3). The pump result is a made-up input.
 */
import { render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { pumpResult, systemCurveResponse } from '$lib/testing/results';
import { SI_UNITS } from '$lib/utils/units';
import PumpChart from './PumpChart.svelte';

vi.mock('./chart-setup', () => {
	throw new TypeError('Failed to fetch dynamically imported module');
});

describe('pump chart without its chunk', () => {
	it('says it could not be loaded and why it may be, how to recover, and shows the data table', async () => {
		render(PumpChart, {
			result: pumpResult(),
			name: 'Transfer pump',
			prefs: SI_UNITS,
			system: { status: 'ready', curve: systemCurveResponse() },
			image: {
				projectName: 'P',
				timestamp: '2026-10-25T12:32:05Z',
				methodVersion: '1.2.0',
				stale: false,
				unavailable: '',
				origin: 'https://opensolve-pipe.app',
				notify: () => {}
			}
		});
		expect(await screen.findByRole('alert')).toHaveTextContent(
			'This part of the app could not be loaded: the app may have been updated since this page opened, or the connection dropped. Reload the page (the project is in its link), then solve again. The table below lists its points.'
		);
		expect(screen.queryByRole('img')).toBeNull();
		expect(screen.getByRole('table', { name: 'Pump curve at 100 % speed' })).toBeInTheDocument();
		expect(screen.getByRole('table', { name: 'System curve' })).toBeInTheDocument();
		// No image can be made without the chart, and the table cannot be hidden.
		expect(screen.queryByRole('button', { name: /^Download image/ })).toBeNull();
		expect(screen.queryByRole('button', { name: /data table/ })).toBeNull();
	});
});
