<script lang="ts">
	import type { Pump } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { CURVE_PREFIX, newId } from '$lib/utils/factory';
	import { PUMP_CONTROL_LABELS, PUMP_STATUS_LABELS } from '$lib/utils/labels';
	import { withOptional } from '$lib/utils/piping';
	import {
		completedControl,
		controlFieldBounds,
		draftProblem,
		EMPTY_CONTROL_DRAFT,
		speedBounds,
		type ControlDraft,
		type ControlField
	} from '$lib/utils/pump-control';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import PumpCurveEditor from './PumpCurveEditor.svelte';

	let { component }: { component: Pump } = $props();
	const ws = useWorkspace();

	/** A new curve being entered for this pump (not in the library until it has 3 points). */
	let creating = $state<string | null>(null);

	const library = $derived(ws.project.pumpLibrary);
	const curve = $derived(library.find((c) => c.id === component.curveId));
	const users = $derived(
		ws.project.components.filter((c) => c.type === 'pump' && c.curveId === component.curveId).length
	);
	const NEW = '__new__';
	const options = $derived([
		...library.map((c) => ({ value: c.id, label: `${c.name} (${c.id})` })),
		...(curve
			? []
			: [{ value: component.curveId, label: `${component.curveId} (not defined yet)` }]),
		{ value: NEW, label: 'New curve…' }
	]);

	/**
	 * A flow control being entered: held here, not in the project, until both values are entered
	 * and valid; then one edit writes it (utils/pump-control.ts). Null when none is being entered.
	 */
	let draft = $state<ControlDraft | null>(null);
	const control = $derived(component.control ?? null);
	const mode = $derived<keyof typeof PUMP_CONTROL_LABELS>(
		control ? control.mode : draft ? 'flow' : 'fixed'
	);
	const controlled = $derived(mode !== 'fixed');
	const problem = $derived(!control && draft ? draftProblem(component, draft) : null);

	function chooseMode(next: keyof typeof PUMP_CONTROL_LABELS) {
		if (next === 'fixed') {
			draft = null;
			if (component.control) {
				ws.editComponent<Pump>(component.id, 'switch pump to fixed speed', (c) =>
					withOptional(c, 'control', null)
				);
			}
		} else if (!component.control) {
			draft = { ...EMPTY_CONTROL_DRAFT };
		}
	}

	/** Store one control field: in the pump's control, or in the draft until it is complete. */
	function setControlField(field: ControlField, value: number): boolean {
		const current = component.control;
		if (current) {
			const label = field === 'setpoint' ? 'change flow setpoint' : 'change minimum speed';
			return ws.editComponent<Pump>(component.id, label, (c) => {
				c.control = { ...current, [field]: value };
			});
		}
		const next: ControlDraft = { ...(draft ?? EMPTY_CONTROL_DRAFT), [field]: value };
		const complete = completedControl(component, next);
		if (
			complete &&
			ws.editComponent<Pump>(component.id, 'switch pump to flow control', (c) => {
				c.control = complete;
			})
		) {
			draft = null;
		} else {
			draft = next;
		}
		return true;
	}

	const controlValue = (field: ControlField) => control?.[field] ?? draft?.[field] ?? null;
</script>

<SelectField
	label="Status"
	value={component.status}
	options={[
		{ value: 'on', label: PUMP_STATUS_LABELS.on },
		{ value: 'off', label: PUMP_STATUS_LABELS.off }
	]}
	onchange={(v) =>
		ws.editComponent<Pump>(component.id, 'change pump status', (c) => {
			c.status = v;
		})}
/>
<SelectField
	label="Control"
	value={mode}
	options={[
		{ value: 'fixed', label: PUMP_CONTROL_LABELS.fixed },
		{ value: 'flow', label: PUMP_CONTROL_LABELS.flow }
	]}
	hint={controlled
		? 'A drive (VFD) varies the speed, between the minimum and maximum speeds, to hold the flow through the pump.'
		: 'Flow control: a drive (VFD) varies the speed to hold the flow through the pump.'}
	onchange={chooseMode}
/>
{#if controlled}
	<NumberField
		label="Flow setpoint"
		value={controlValue('setpoint')}
		category="flow"
		units={ws.units}
		bounds={controlFieldBounds(component, 'setpoint', draft ?? undefined)}
		hint="Flow through the pump, suction to discharge, that the drive holds."
		onchange={(v) => v !== null && setControlField('setpoint', v)}
	/>
	<NumberField
		label="Minimum speed"
		value={controlValue('minSpeed')}
		category="fraction"
		units={ws.units}
		bounds={controlFieldBounds(component, 'minSpeed', draft ?? undefined)}
		hint="From the drive or pump data; there is no standard default. Below the maximum speed."
		onchange={(v) => v !== null && setControlField('minSpeed', v)}
	/>
{/if}
<NumberField
	label={controlled ? 'Maximum speed' : 'Speed'}
	value={component.speed}
	category="fraction"
	units={ws.units}
	bounds={speedBounds(component, draft)}
	hint={controlled
		? "Highest speed the drive runs the pump at, as a percentage of the curve's rated speed; at this speed the pump behaves as a fixed-speed pump."
		: "Fixed speed, as a percentage of the curve's rated speed (affinity laws)."}
	onchange={(v) =>
		v !== null &&
		ws.editComponent<Pump>(
			component.id,
			controlled ? 'change maximum speed' : 'change pump speed',
			(c) => {
				c.speed = v;
			}
		)}
/>
{#if problem}
	<p
		class="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 sm:col-span-2"
		role="status"
	>
		<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
		<span>
			{problem === 'incomplete'
				? 'Enter the flow setpoint and minimum speed to switch to flow control. Until then the pump runs at a fixed speed.'
				: 'The minimum speed must be below the maximum speed to switch to flow control. Until then the pump runs at a fixed speed.'}
		</span>
	</p>
{/if}
{#if controlled && component.status === 'off'}
	<p class="hint sm:col-span-2">This pump is off: its flow control is not applied.</p>
{/if}

<section class="space-y-3 border-t border-slate-200 pt-4 sm:col-span-2" aria-label="Pump curve">
	<SelectField
		label="Pump curve"
		value={creating ?? component.curveId}
		options={creating ? [...options, { value: creating, label: `${creating} (new)` }] : options}
		hint={curve && users > 1
			? `This curve is shared by ${users} pumps; changes apply to all of them.`
			: !curve && !creating && library.length
				? 'Pick a curve from the project library, or enter this pump’s own curve below.'
				: undefined}
		onchange={(v) => {
			if (v === NEW) {
				creating = newId(ws.project, CURVE_PREFIX);
			} else {
				creating = null;
				ws.editComponent<Pump>(component.id, 'change pump curve', (c) => {
					c.curveId = v;
				});
			}
		}}
	/>
	{#key creating ?? component.curveId}
		<PumpCurveEditor
			pump={component}
			curve={creating ? undefined : curve}
			curveId={creating ?? component.curveId}
			oncreated={() => (creating = null)}
		/>
	{/key}
</section>
