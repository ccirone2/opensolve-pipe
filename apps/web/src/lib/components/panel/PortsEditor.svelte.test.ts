/**
 * A connected port's size is only the default for new piping: the solver uses the connected
 * pipe. The port says which pipe size the solver uses, flags a port size that differs from it,
 * and offers to resize the pipe.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import type { PipeConnection } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { TEST_LIBRARY } from '$lib/testing/library';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { INCH } from '$lib/utils/units';

describe('PortsEditor', () => {
	it('flags a port size that differs from the connected pipe, and can resize the pipe', async () => {
		const ws = testWorkspace(pumpTransferExample(), {
			library: { getLibrary: () => Promise.resolve(TEST_LIBRARY) }
		});
		ws.nav.jumpTo('V1');
		render(WorkspaceView, { workspace: ws });
		const ports = within(await screen.findByRole('region', { name: 'Ports' }));
		const outlet = ports.getAllByRole('listitem')[1]!;
		const size = await within(outlet).findByRole('combobox', { name: 'Port size' });
		expect(
			within(outlet).getByText(
				'Default size for new piping here. The solver uses the connected pipe: NPS 3.'
			)
		).toBeInTheDocument();
		expect(within(outlet).queryByText(/changes no result/)).toBeNull();

		await fireEvent.change(size, { target: { value: String(6 * INCH) } });
		expect(
			within(outlet).getByText(
				'The connected pipe is NPS 3, not NPS 6: the solver uses the pipe, so this port size changes no result.'
			)
		).toBeInTheDocument();

		await fireEvent.click(within(outlet).getByRole('button', { name: 'Make the pipe NPS 6' }));
		const l3 = ws.project.connections.find((c) => c.id === 'L3') as PipeConnection;
		expect(l3.piping.pipes[0]!.nominalSize).toBeCloseTo(6 * INCH, 12);
		expect(within(outlet).queryByText(/changes no result/)).toBeNull();
	});
});
