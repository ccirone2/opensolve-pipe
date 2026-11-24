/**
 * Pasting into a curve's table (proposal usability-entry.md §6): a column, or a table, fills it
 * from the row pasted into; a paste it cannot read changes nothing and says why.
 */
import { createEvent, fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { IMPERIAL_UNITS } from '$lib/utils/units';
import PointsTable, { type Point } from './PointsTable.svelte';

const ft = 0.3048;
const gpm = (231 * 0.0254 ** 3) / 60;

function table(rows: Point[] = [], onchange = vi.fn()) {
	render(PointsTable, {
		caption: 'Head curve',
		rows,
		x: { label: 'Flow', category: 'flow', bounds: { minimum: 0 } },
		y: { label: 'Head', category: 'head', bounds: {} },
		units: IMPERIAL_UNITS,
		minRows: 3,
		onchange
	});
	return onchange;
}

async function paste(input: HTMLElement, text: string) {
	const event = createEvent.paste(input);
	Object.defineProperty(event, 'clipboardData', { value: { getData: () => text } });
	await fireEvent(input, event);
	return event;
}

function close(actual: number | undefined, expected: number) {
	expect(Math.abs((actual ?? NaN) - expected)).toBeLessThanOrEqual(Math.abs(expected) * 1e-14);
}

describe('PointsTable paste', () => {
	it('fills an empty curve from a spreadsheet table with headings, and stores it', async () => {
		const onchange = table();
		const first = screen.getByRole('textbox', { name: 'Point 1 flow (gpm)' });
		const event = await paste(
			first,
			'Flow (gpm)\tHead (ft)\n0\t150\n300\t130\n500\t100\n600\t80\n'
		);
		expect(event.defaultPrevented).toBe(true);
		expect(onchange).toHaveBeenCalledOnce();
		const rows = onchange.mock.calls[0]?.[0] as Point[];
		expect(rows).toHaveLength(4);
		close(rows[1]?.x, 300 * gpm);
		close(rows[3]?.y, 80 * ft);
		expect(screen.getByText('Pasted 4 points: flow in gpm, head in ft.')).toBeInTheDocument();
		expect(screen.getByRole('textbox', { name: 'Point 4 head (ft)' })).toHaveValue('80');
	});

	it('fills one column from the row pasted into, keeping the other', async () => {
		const onchange = table([
			{ x: 0, y: 150 * ft },
			{ x: 300 * gpm, y: 130 * ft },
			{ x: 500 * gpm, y: 100 * ft }
		]);
		await paste(screen.getByRole('textbox', { name: 'Point 2 head (ft)' }), '131\n101\n');
		const rows = onchange.mock.calls[0]?.[0] as Point[];
		expect(rows).toHaveLength(3);
		close(rows[0]?.y ?? NaN, 150 * ft);
		close(rows[1]?.y, 131 * ft);
		close(rows[2]?.y, 101 * ft);
		close(rows[2]?.x, 500 * gpm);
		expect(screen.getByText('Pasted 2 values of head in ft.')).toBeInTheDocument();
	});

	it('pastes nothing for one bad cell, and says which', async () => {
		const onchange = table();
		await paste(screen.getByRole('textbox', { name: 'Point 1 flow (gpm)' }), '0\t150\nabc\t130');
		expect(onchange).not.toHaveBeenCalled();
		expect(
			screen.getByText(
				'Nothing was pasted: row 2, flow, “abc”: Enter a number, e.g. 12.5 or 1.2e-3.'
			)
		).toBeInTheDocument();
		expect(screen.getByRole('textbox', { name: 'Point 1 flow (gpm)' })).toHaveValue('');
	});

	it('leaves a single value to the field', async () => {
		const onchange = table();
		const event = await paste(screen.getByRole('textbox', { name: 'Point 1 flow (gpm)' }), '300');
		expect(event.defaultPrevented).toBe(false);
		expect(onchange).not.toHaveBeenCalled();
	});

	it('says that a column or a table can be pasted', () => {
		table();
		expect(
			screen.getByText(
				'Paste a column, or both columns with their headings, from a spreadsheet or data sheet.'
			)
		).toBeInTheDocument();
	});

	it('takes a pasted table as the curve from that point on, saying which points it removed', async () => {
		const onchange = table([
			{ x: 0, y: 40 * ft },
			{ x: 10 * gpm, y: 39 * ft },
			{ x: 20 * gpm, y: 38 * ft },
			{ x: 30 * gpm, y: 37 * ft },
			{ x: 40 * gpm, y: 30 * ft }
		]);
		await paste(screen.getByRole('textbox', { name: 'Point 1 flow (gpm)' }), '0\t30\n2\t28\n5\t24');
		const rows = onchange.mock.calls[0]?.[0] as Point[];
		expect(rows).toHaveLength(3);
		close(rows[2]?.x, 5 * gpm);
		close(rows[2]?.y, 24 * ft);
		expect(
			screen.getByText(
				'Pasted 3 points: flow in gpm, head in ft. The points after them (points 4 and 5) were removed.'
			)
		).toBeInTheDocument();
	});

	it('says which points keep their values when a column is shorter than the curve', async () => {
		const onchange = table([
			{ x: 0, y: 40 * ft },
			{ x: 10 * gpm, y: 39 * ft },
			{ x: 20 * gpm, y: 38 * ft },
			{ x: 30 * gpm, y: 37 * ft }
		]);
		await paste(screen.getByRole('textbox', { name: 'Point 1 head (ft)' }), '41\n40\n');
		const rows = onchange.mock.calls[0]?.[0] as Point[];
		expect(rows).toHaveLength(4);
		close(rows[1]?.y, 40 * ft);
		close(rows[3]?.y, 37 * ft);
		expect(
			screen.getByText('Pasted 2 values of head in ft. Points 3 and 4 keep their earlier head.')
		).toBeInTheDocument();
	});
});
