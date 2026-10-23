/**
 * A library pipe shows the inner diameter and roughness the solver uses: roughness is per size
 * (Farshad & Rieke at that size's bore), not the material's representative average, and
 * switching the pipe to Custom starts from those same values so the switch changes no result.
 */
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import type { PipeConnection } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { TEST_LIBRARY as LIBRARY } from '$lib/testing/library';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';

function setup() {
	const ws = testWorkspace(pumpTransferExample(), {
		library: { getLibrary: () => Promise.resolve(LIBRARY) }
	});
	ws.nav.jumpTo('V1');
	ws.nav.showConnection('outlet');
	render(WorkspaceView, { workspace: ws });
	const l3 = () => ws.project.connections.find((c) => c.id === 'L3') as PipeConnection;
	return { ws, l3 };
}

describe('PipeSegmentForm', () => {
	it('shows the per-size roughness the solver uses, not the material average', async () => {
		setup();
		const roughness = await screen.findByText((_, el) =>
			Boolean(el?.tagName === 'P' && el.textContent?.trim().startsWith('Roughness'))
		);
		expect(roughness).toHaveTextContent(/^Roughness 0\.03512 mm$/);
		expect(screen.queryByText(/0\.036 mm/)).toBeNull();
	});

	it('labels a roughness override against the size value', async () => {
		const { ws } = setup();
		ws.editConnection('L3', 'change roughness', (c) => ({
			...c,
			piping: { ...c.piping, pipes: [{ ...c.piping.pipes[0]!, roughness: 5e-5 }] }
		}));
		const roughness = await screen.findByText((_, el) =>
			Boolean(el?.tagName === 'P' && el.textContent?.trim().startsWith('Roughness'))
		);
		expect(roughness).toHaveTextContent(/Roughness 0\.05 mm\s+\(override; library 0\.03512 mm\)/);
	});

	it('switching to Custom keeps the bore and per-size roughness', async () => {
		const { l3 } = setup();
		await screen.findByText(/^Roughness/);
		await fireEvent.change(screen.getByRole('combobox', { name: 'Material' }), {
			target: { value: 'custom' }
		});
		expect(l3().piping.pipes[0]).toEqual({
			materialId: 'custom',
			length: 60,
			innerDiameter: 0.07792,
			roughness: 3.512e-5
		});
	});
});
