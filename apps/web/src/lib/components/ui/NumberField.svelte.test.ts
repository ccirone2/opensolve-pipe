/**
 * Unit-aware numeric input (D4): shows SI values in the display unit, converts what is typed to
 * SI, checks bounds, and never stores NaN.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import { testWorkspace } from '$lib/testing/workspace';
import { pumpTransferExample } from '$lib/utils/examples';
import { IMPERIAL_UNITS, SI_UNITS, toSI } from '$lib/utils/units';
import NumberField from './NumberField.svelte';

async function type(input: HTMLElement, text: string) {
	await fireEvent.input(input, { target: { value: text } });
	await fireEvent.change(input);
}

describe('NumberField', () => {
	it('shows the SI value in the display unit and converts typed values to SI', async () => {
		const onchange = vi.fn();
		render(NumberField, {
			label: 'Liquid level',
			value: 3.048,
			category: 'length',
			units: IMPERIAL_UNITS,
			onchange
		});
		const input = screen.getByRole('textbox', { name: 'Liquid level (ft)' });
		expect(input).toHaveValue('10');
		expect(screen.getByText('ft')).toBeInTheDocument();

		await type(input, '12.5');
		expect(onchange).toHaveBeenCalledExactlyOnceWith(toSI(12.5, 'ft'));
		expect(onchange.mock.calls[0]?.[0]).toBeCloseTo(3.81, 12);
	});

	it('labels gauge pressures and converts psig to Pa', async () => {
		const onchange = vi.fn();
		render(NumberField, {
			label: 'Surface pressure',
			value: 0,
			category: 'pressure',
			gauge: true,
			units: IMPERIAL_UNITS,
			onchange
		});
		const input = screen.getByRole('textbox', { name: 'Surface pressure (psig)' });
		await type(input, '10');
		// 1 psi = 1 lbf/in² = 0.45359237 kg × 9.80665 m/s² / (0.0254 m)²
		expect(onchange.mock.calls[0]?.[0]).toBeCloseTo((10 * 0.45359237 * 9.80665) / 0.0254 ** 2, 9);
	});

	it('converts temperatures with an offset', async () => {
		const onchange = vi.fn();
		render(NumberField, {
			label: 'Temperature',
			value: 293.15,
			category: 'temperature',
			units: IMPERIAL_UNITS,
			onchange
		});
		const input = screen.getByRole('textbox', { name: /Temperature/ });
		expect(input).toHaveValue('68');
		await type(input, '212');
		expect(onchange.mock.calls[0]?.[0]).toBeCloseTo(373.15, 10);
	});

	it('rejects text that is not a number, without storing anything', async () => {
		const onchange = vi.fn();
		render(NumberField, {
			label: 'Length',
			value: 10,
			category: 'length',
			units: SI_UNITS,
			onchange
		});
		const input = screen.getByRole('textbox', { name: /Length/ });
		for (const text of ['abc', '1,5', '1e', 'NaN', 'Infinity', '--1']) {
			await type(input, text);
		}
		expect(onchange).not.toHaveBeenCalled();
		expect(input).toHaveAttribute('aria-invalid', 'true');
		expect(input).toHaveAccessibleDescription(/Enter a number/);
	});

	it('checks bounds in SI and reports them in the display unit', async () => {
		const onchange = vi.fn();
		render(NumberField, {
			label: 'Liquid level',
			value: 1,
			category: 'length',
			units: IMPERIAL_UNITS,
			bounds: { minimum: 0, maximum: 1000 },
			onchange
		});
		const input = screen.getByRole('textbox', { name: /Liquid level/ });
		await type(input, '-1');
		expect(screen.getByText('Must be at least 0 ft.')).toBeInTheDocument();
		await type(input, '4000');
		expect(screen.getByText('Must be at most 3280.84 ft.')).toBeInTheDocument();
		expect(onchange).not.toHaveBeenCalled();
		await type(input, '3000');
		expect(onchange).toHaveBeenCalledExactlyOnceWith(toSI(3000, 'ft'));
	});

	it('stores an emptied optional field as null, and refuses to empty a required one', async () => {
		const optional = vi.fn();
		render(NumberField, {
			label: 'Override',
			value: 0.1,
			category: 'diameter',
			units: SI_UNITS,
			optional: true,
			onchange: optional
		});
		await type(screen.getByRole('textbox', { name: /Override/ }), '  ');
		expect(optional).toHaveBeenCalledExactlyOnceWith(null);

		const required = vi.fn();
		render(NumberField, {
			label: 'Length',
			value: 10,
			category: 'length',
			units: SI_UNITS,
			onchange: required
		});
		await type(screen.getByRole('textbox', { name: /^Length/ }), '');
		expect(required).not.toHaveBeenCalled();
		expect(screen.getByText('Enter a value.')).toBeInTheDocument();
	});

	it('edits a component in the display units and stores SI', async () => {
		const ws = testWorkspace(pumpTransferExample());
		ws.store.update((p) => {
			p.settings.units = { ...IMPERIAL_UNITS };
		}, 'use US customary units');
		render(WorkspaceView, { workspace: ws });
		const build = within(screen.getByRole('region', { name: 'Build' }));
		const level = build.getByRole('textbox', { name: 'Liquid level (ft)' });
		expect(level).toHaveValue('9.84252'); // 3 m, to 6 significant digits

		await type(level, '10');
		const reservoir = ws.project.components.find((c) => c.id === 'R1');
		expect(reservoir).toMatchObject({ liquidLevel: toSI(10, 'ft') });
		expect(ws.project.settings.units.length).toBe('ft');
		expect(level).toHaveValue('10');
		expect(ws.store.undoLabel).toBe('change liquid level');

		const pressure = build.getByRole('textbox', { name: 'Surface pressure (psig)' });
		await type(pressure, '-20');
		// Below the schema minimum (-100 kPa gauge): refused before it reaches the project.
		expect(build.getByText(/Must be at least -14\.50\d* psig\./)).toBeInTheDocument();
		expect(ws.project.components.find((c) => c.id === 'R1')).toMatchObject({ surfacePressure: 0 });
	});

	it('shows 6 significant digits, and Enter on the shown text stores nothing', async () => {
		const onchange = vi.fn();
		render(NumberField, {
			label: 'Length',
			value: 3,
			category: 'length',
			units: IMPERIAL_UNITS,
			onchange
		});
		const input = screen.getByRole('textbox', { name: 'Length (ft)' });
		expect(input).toHaveValue('9.84252');
		// Storing the display would round 3 m to 2.99999990 m.
		await fireEvent.keyDown(input, { key: 'Enter' });
		await fireEvent.change(input);
		expect(onchange).not.toHaveBeenCalled();
	});

	it('Escape reverts edited text without letting a dialog close', async () => {
		const onchange = vi.fn();
		render(NumberField, {
			label: 'Site elevation',
			value: 0,
			category: 'length',
			units: SI_UNITS,
			onchange
		});
		const input = screen.getByRole('textbox', { name: 'Site elevation (m)' });
		await fireEvent.input(input, { target: { value: '123' } });
		const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
		input.dispatchEvent(escape);
		// A cancelled keydown is what keeps the <dialog> from treating Escape as a close request.
		expect(escape.defaultPrevented).toBe(true);
		await tick();
		expect(input).toHaveValue('0');
		expect(onchange).not.toHaveBeenCalled();
		// With nothing to revert, Escape is left to the dialog.
		const again = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
		input.dispatchEvent(again);
		expect(again.defaultPrevented).toBe(false);
	});

	it('announces an error and keeps it in view', async () => {
		const scrolled = vi.fn();
		const original = Element.prototype.scrollIntoView;
		Element.prototype.scrollIntoView = scrolled;
		try {
			render(NumberField, {
				label: 'Length',
				value: 10,
				category: 'length',
				units: SI_UNITS,
				onchange: vi.fn()
			});
			await type(screen.getByRole('textbox', { name: /Length/ }), 'abc');
			expect(screen.getByRole('alert')).toHaveTextContent('Enter a number, e.g. 12.5 or 1.2e-3.');
			expect(scrolled).toHaveBeenCalledWith({ block: 'nearest' });
		} finally {
			Element.prototype.scrollIntoView = original;
		}
	});

	it('shows an error its owner reports (a required value not entered), after its own', async () => {
		const onchange = vi.fn();
		const { rerender } = render(NumberField, {
			label: 'Flow',
			value: null,
			category: 'flow',
			units: SI_UNITS,
			error: 'Enter the flow first.',
			onchange
		});
		const input = screen.getByRole('textbox', { name: 'Flow (L/s)' });
		expect(input).toHaveValue('');
		expect(input).toHaveAttribute('aria-invalid', 'true');
		expect(input).toHaveAccessibleDescription('Enter the flow first.');
		expect(screen.getByRole('alert')).toHaveTextContent('Enter the flow first.');

		// Its own problem with the typed text comes first; the owner's shows again once it is gone.
		await type(input, 'abc');
		expect(screen.getByRole('alert')).toHaveTextContent('Enter a number, e.g. 12.5 or 1.2e-3.');
		await fireEvent.keyDown(input, { key: 'Escape' });
		expect(screen.getByRole('alert')).toHaveTextContent('Enter the flow first.');

		await type(input, '3');
		expect(onchange).toHaveBeenCalledExactlyOnceWith(toSI(3, 'L/s'));
		await rerender({ error: null });
		expect(screen.queryByRole('alert')).toBeNull();
		expect(input).not.toHaveAttribute('aria-invalid');
	});
});
