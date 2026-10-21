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
});
