<!--
	The current component (SDD §3.1.1): its name and type, the component actions, and two views —
	Properties (the per-type form and the ports) and Piping (the connection at a chosen port).
-->
<script lang="ts" module>
	import type { CheckValve, Component, ControlValve, IsolationValve } from '$lib/api/types';

	function isCheckValve(c: Component): c is CheckValve {
		return c.type === 'valve' && (c.valveType === 'check' || c.valveType === 'stop_check');
	}

	function isControlValve(c: Component): c is ControlValve {
		return (
			c.type === 'valve' &&
			(c.valveType === 'prv' || c.valveType === 'psv' || c.valveType === 'fcv')
		);
	}

	function isIsolationValve(c: Component): c is IsolationValve {
		return c.type === 'valve' && !isCheckValve(c) && !isControlValve(c);
	}
</script>

<script lang="ts">
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { kindLabel } from '$lib/utils/labels';
	import { componentSchema, schemaBounds, stringLimits } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import ComponentActions from './ComponentActions.svelte';
	import ConnectionPanel from './ConnectionPanel.svelte';
	import AssignedFlowForm from './forms/AssignedFlowForm.svelte';
	import BranchForm from './forms/BranchForm.svelte';
	import CheckValveForm from './forms/CheckValveForm.svelte';
	import ControlValveForm from './forms/ControlValveForm.svelte';
	import IsolationValveForm from './forms/IsolationValveForm.svelte';
	import PumpForm from './forms/PumpForm.svelte';
	import ReferenceNodeForm from './forms/ReferenceNodeForm.svelte';
	import ReservoirForm from './forms/ReservoirForm.svelte';
	import PortsEditor from './PortsEditor.svelte';

	let { component }: { component: Component } = $props();
	const ws = useWorkspace();
	const id = $props.id();
	const mode = $derived(ws.nav.mode);
	const schema = $derived(componentSchema(component));
	const TABS = [
		{ value: 'component', label: 'Properties' },
		{ value: 'connection', label: 'Piping' }
	] as const;

	function selectTab(next: 'component' | 'connection') {
		if (next === 'component') ws.nav.showComponent();
		else ws.nav.showConnection(ws.nav.activePortId ?? component.ports[0]?.id ?? '');
	}

	function tabKeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
			event.preventDefault();
			const next = mode === 'component' ? 'connection' : 'component';
			selectTab(next);
			document.getElementById(`${id}-tab-${next}`)?.focus();
		}
	}
</script>

<article class="space-y-4 px-3 py-4 sm:px-4" aria-labelledby="{id}-title">
	<header>
		<p class="text-sm text-slate-600">
			{kindLabel(component)} · <span class="font-mono">{component.id}</span>
		</p>
		<h2
			id="{id}-title"
			class="text-xl font-semibold break-words"
			tabindex="-1"
			data-current-heading
		>
			{component.name}
		</h2>
	</header>

	<ComponentActions {component} />

	<div
		role="tablist"
		aria-label="Edit {component.name}"
		class="flex border-b border-slate-200"
		tabindex="-1"
		onkeydown={tabKeydown}
	>
		{#each TABS as { value, label } (value)}
			<button
				type="button"
				role="tab"
				id="{id}-tab-{value}"
				aria-selected={mode === value}
				aria-controls="{id}-panel"
				tabindex={mode === value ? 0 : -1}
				class={[
					'-mb-px min-h-11 border-b-2 px-4 text-sm font-medium',
					mode === value
						? 'border-blue-700 text-blue-800'
						: 'border-transparent text-slate-600 hover:text-slate-900'
				]}
				onclick={() => selectTab(value)}
			>
				{label}
			</button>
		{/each}
	</div>

	<div id="{id}-panel" role="tabpanel" aria-labelledby="{id}-tab-{mode}" class="space-y-4">
		{#key component.id}
			{#if mode === 'component'}
				<div class="grid gap-4 sm:grid-cols-2">
					<TextField
						class="sm:col-span-2"
						label="Name"
						value={component.name}
						required
						maxlength={stringLimits(schema, 'name').maxLength}
						onchange={(v) =>
							!!v &&
							ws.editComponent(component.id, 'rename component', (c) => {
								c.name = v;
							})}
					/>
					<NumberField
						label="Elevation"
						value={component.elevation}
						category="length"
						units={ws.units}
						bounds={schemaBounds(schema, 'elevation')}
						hint="Above the project datum."
						onchange={(v) =>
							v !== null &&
							ws.editComponent(component.id, 'change elevation', (c) => {
								c.elevation = v;
							})}
					/>
					{#if component.type === 'reservoir'}
						<ReservoirForm {component} />
					{:else if component.type === 'reference_node'}
						<ReferenceNodeForm {component} />
					{:else if component.type === 'branch'}
						<BranchForm {component} />
					{:else if component.type === 'pump'}
						<PumpForm {component} />
					{:else if isCheckValve(component)}
						<CheckValveForm {component} />
					{:else if isControlValve(component)}
						<ControlValveForm {component} />
					{:else if isIsolationValve(component)}
						<IsolationValveForm {component} />
					{:else if component.type === 'assigned_flow'}
						<AssignedFlowForm {component} />
					{:else if component.type === 'plug'}
						<p class="hint sm:col-span-2">A closed end: no flow leaves through its port.</p>
					{/if}
					<div class="sm:col-span-2"><PortsEditor {component} /></div>
				</div>
			{:else}
				<ConnectionPanel {component} />
			{/if}
		{/key}
	</div>
</article>
