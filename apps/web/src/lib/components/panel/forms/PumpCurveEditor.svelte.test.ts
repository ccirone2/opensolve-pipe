/**
 * A new pump curve is created once its third complete point is entered; the entry table is then
 * replaced by the curve's own. Entering that last value with Enter, after which the browser
 * reports a change on the field as it is removed, must store the curve once and read nothing
 * from the removed table (Svelte's derived_inert warning).
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';

afterEach(() => {
	vi.restoreAllMocks();
});

async function enter(field: HTMLElement, text: string) {
	field.focus();
	await fireEvent.input(field, { target: { value: text } });
	await fireEvent.keyDown(field, { key: 'Enter' });
}

/**
 * Chrome reports a change on a focused text field whose value changed when the field is removed
 * from the page, before it is detached; jsdom does not. Simulate it.
 */
function changeOnRemoval() {
	const remove = Element.prototype.remove;
	vi.spyOn(Element.prototype, 'remove').mockImplementation(function (this: Element) {
		const active = document.activeElement;
		if (active instanceof HTMLInputElement && this.contains(active)) {
			active.dispatchEvent(new Event('change', { bubbles: true }));
		}
		remove.call(this);
	});
}

describe('PumpCurveEditor', () => {
	it('creates the curve on the third point without warnings', async () => {
		const warn = vi.spyOn(console, 'warn');
		changeOnRemoval();
		const project = pumpTransferExample();
		project.pumpLibrary = [];
		const ws = testWorkspace(project);
		ws.nav.jumpTo('P1');
		render(WorkspaceView, { workspace: ws });
		const curve = within(screen.getByRole('region', { name: 'Pump curve' }));
		const points: [string, string][] = [
			['0', '20'],
			['10', '16'],
			['15', '11']
		];
		let last: HTMLElement | undefined;
		for (const [i, [q, h]] of points.entries()) {
			await enter(curve.getByRole('textbox', { name: `Point ${i + 1} flow (L/s)` }), q);
			last = curve.getByRole('textbox', { name: `Point ${i + 1} head (m)` });
			await enter(last, h);
		}
		expect(ws.project.pumpLibrary).toHaveLength(1);
		expect(ws.project.pumpLibrary[0]!.points).toEqual([
			{ flow: 0, head: 20 },
			{ flow: 0.01, head: 16 },
			{ flow: 0.015, head: 11 }
		]);
		// The entry table is gone (its focused field reported a change as it went).
		expect(last!.isConnected).toBe(false);
		expect(warn.mock.calls.map((c) => String(c[0]))).not.toContainEqual(
			expect.stringMatching(/derived_inert/)
		);
		expect(ws.store.undoLabel).toBe('add pump curve');
	});

	it('stores the manufacturer data the design checks read, an allowable region with both ends', async () => {
		const ws = testWorkspace(pumpTransferExample());
		ws.nav.jumpTo('P1');
		render(WorkspaceView, { workspace: ws });
		const curve = within(screen.getByRole('region', { name: 'Pump curve' }));
		const details = curve.getByText('Manufacturer data (optional)').closest('details')!;
		expect(details.open).toBe(false);
		const field = (name: RegExp) => within(details).getByRole('textbox', { name });
		const stored = () => ws.project.pumpLibrary[0]!;

		// One end alone is kept on the page, not stored: the API needs both.
		const low = field(/^Allowable operating region, lowest flow/);
		await enter(low, '6');
		expect(stored().allowableOperatingRegion).toBeUndefined();
		const high = field(/^Allowable operating region, highest flow/);
		expect(high).toHaveAccessibleDescription(/Enter both ends of the allowable operating region\./);
		// The upper end below the lower one is refused, and says why.
		await enter(high, '5');
		expect(high).toHaveAccessibleDescription(/Must be greater than 6 L\/s\./);
		expect(stored().allowableOperatingRegion).toBeUndefined();
		await enter(high, '26');
		expect(stored().allowableOperatingRegion).toEqual({
			flowMin: expect.closeTo(0.006, 15),
			flowMax: expect.closeTo(0.026, 15)
		});
		expect(high).not.toHaveAttribute('aria-invalid');

		await enter(field(/^Minimum continuous stable flow/), '4');
		await enter(field(/^Minimum thermal flow/), '3');
		await enter(field(/^Motor rated power/), '5.5');
		expect(stored()).toMatchObject({
			minimumContinuousStableFlow: expect.closeTo(0.004, 15),
			minimumThermalFlow: expect.closeTo(0.003, 15),
			motorRatedPower: expect.closeTo(5500, 9)
		});
		expect(ws.store.undoLabel).toBe('change motor rated power');
		// Clearing a value removes it.
		await enter(field(/^Motor rated power/), '');
		expect('motorRatedPower' in stored()).toBe(false);
	});

	it('keeps the manufacturer data section open while the user clears the last value', async () => {
		const ws = testWorkspace(pumpTransferExample());
		ws.nav.jumpTo('P1');
		render(WorkspaceView, { workspace: ws });
		const curve = within(screen.getByRole('region', { name: 'Pump curve' }));
		const details = curve.getByText('Manufacturer data (optional)').closest('details')!;
		details.open = true;
		await fireEvent(details, new Event('toggle'));
		const thermal = within(details).getByRole('textbox', { name: /^Minimum thermal flow/ });
		await enter(thermal, '3');
		await enter(thermal, '');
		expect('minimumThermalFlow' in ws.project.pumpLibrary[0]!).toBe(false);
		expect(details.open).toBe(true);
	});
});
