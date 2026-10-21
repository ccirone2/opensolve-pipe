/**
 * The project fluid in Settings: switching a built-in fluid to a custom one starts from the
 * properties the project used, the user's overrides included.
 */
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { BuiltinFluid, FluidInfo, FluidProperties } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';

/** Made-up calculated properties for the test (not data). */
const CALCULATED: FluidProperties = {
	name: 'Water',
	temperature: 293.15,
	concentration: null,
	density: 998,
	dynamicViscosity: 1e-3,
	kinematicViscosity: 1e-3 / 998,
	vaporPressure: 2300,
	sources: {}
};

async function openFluid(overrides: BuiltinFluid['overrides']) {
	const project = pumpTransferExample();
	project.fluid = { kind: 'builtin', fluidId: 'water', temperature: 293.15, overrides };
	const fluidProperties = vi.fn(() => Promise.resolve(CALCULATED));
	const ws = testWorkspace(project, { library: { fluidProperties } });
	render(WorkspaceView, { workspace: ws });
	await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
	// The calculated properties are fetched after a short pause, for the fluid's state without
	// the user's overrides (the library values, for checking).
	await screen.findByText('Calculated properties', {}, { timeout: 2000 });
	expect(fluidProperties).toHaveBeenCalledWith({
		kind: 'builtin',
		fluidId: 'water',
		temperature: 293.15
	});
	await fireEvent.change(screen.getByRole('combobox', { name: 'Fluid' }), {
		target: { value: 'custom' }
	});
	return ws;
}

describe('FluidSettings', () => {
	it('keeps the overrides when switching to a custom fluid', async () => {
		const ws = await openFluid({ density: 999.5, vaporPressure: 2500 });
		expect(ws.project.fluid).toEqual({
			kind: 'custom',
			name: 'Custom fluid',
			density: 999.5,
			dynamicViscosity: 1e-3,
			vaporPressure: 2500,
			temperature: 293.15
		});
	});

	it('uses the calculated properties where nothing is overridden', async () => {
		const ws = await openFluid(undefined);
		expect(ws.project.fluid).toEqual({
			kind: 'custom',
			name: 'Custom fluid',
			density: 998,
			dynamicViscosity: 1e-3,
			vaporPressure: 2300,
			temperature: 293.15
		});
	});

	it('asks for a glycol concentration in percent, without calling the server first', async () => {
		/** Made-up library entry: only the range matters here (test input, not data). */
		const glycol: FluidInfo = {
			id: 'ethylene_glycol',
			name: 'Ethylene glycol (aqueous)',
			temperatureRange: { min: 250, max: 373.15, unit: 'K' },
			concentrationRange: { min: 0, max: 0.6, unit: 'mass fraction' },
			freezingPoints: null,
			vaporPressureAvailable: false,
			source: 'test',
			notes: []
		};
		const fluidProperties = vi.fn(() =>
			Promise.resolve({
				...CALCULATED,
				name: 'Ethylene glycol',
				sources: {
					dynamicViscosity: { citation: 'made-up citation' },
					vaporPressure: { citation: 'not available' }
				}
			} as unknown as FluidProperties)
		);
		const project = pumpTransferExample();
		project.fluid = { kind: 'builtin', fluidId: 'ethylene_glycol', temperature: 293.15 };
		const ws = testWorkspace(project, {
			library: { fluidProperties, getFluids: () => Promise.resolve([glycol]) }
		});
		render(WorkspaceView, { workspace: ws });
		await fireEvent.click(screen.getByRole('button', { name: 'Settings' }));

		expect(
			await screen.findByText('Required for a glycol solution: a percentage by mass, 0 to 60 %.')
		).toBeInTheDocument();
		expect(
			screen.getByText(
				'Percentage of glycol in the solution, by mass (the property library covers 0 to 60 %).'
			)
		).toBeInTheDocument();
		expect(
			screen.getByText('Enter the glycol concentration to calculate the properties.')
		).toBeInTheDocument();
		expect(screen.queryByText(/mass fraction, 0 to 1/)).toBeNull();
		await new Promise((r) => setTimeout(r, 400));
		expect(fluidProperties).not.toHaveBeenCalled();

		// 0.3 typed as a fraction is 0.3 %: said to be almost water.
		const field = screen.getByRole('textbox', { name: /^Glycol concentration/ });
		await fireEvent.input(field, { target: { value: '0.3' } });
		await fireEvent.change(field);
		expect(ws.project.fluid).toMatchObject({ concentration: 0.003 });
		expect(
			screen.getByText(
				'0.3 % is almost water. This field is in percent: enter 30 for a 30 % solution.'
			)
		).toBeInTheDocument();

		await fireEvent.input(field, { target: { value: '30' } });
		await fireEvent.change(field);
		expect(ws.project.fluid).toMatchObject({ concentration: 0.3 });
		expect(screen.queryByText(/is almost water/)).toBeNull();
		await vi.waitFor(() =>
			expect(fluidProperties).toHaveBeenLastCalledWith({
				kind: 'builtin',
				fluidId: 'ethylene_glycol',
				temperature: 293.15,
				concentration: 0.3
			})
		);
		// The property sources are named, not keyed.
		expect(
			await screen.findByText('Dynamic viscosity: made-up citation', {}, { timeout: 2000 })
		).toBeInTheDocument();
		expect(screen.getByText('Vapor pressure: not available')).toBeInTheDocument();
	});
});
