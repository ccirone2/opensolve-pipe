<!--
	The current component (SDD §3.1.1): its type and its name, edited in place, its key results
	from the last solve (ResultStrip), the component actions, and two views — Properties (the per-type form and the ports) and Piping (the
	connection at a chosen port).
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
	import TextField from '$lib/components/ui/TextField.svelte';
	import { kindLabel } from '$lib/utils/labels';
	import { componentSchema, stringLimits } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import ComponentActions from './ComponentActions.svelte';
	import ConnectionPanel from './ConnectionPanel.svelte';
	import FieldSections from './FieldSections.svelte';
	import AssignedFlowForm from './forms/AssignedFlowForm.svelte';
	import BranchForm from './forms/BranchForm.svelte';
	import CheckValveForm from './forms/CheckValveForm.svelte';
	import ControlValveForm from './forms/ControlValveForm.svelte';
	import EquipmentForm from './forms/EquipmentForm.svelte';
	import IsolationValveForm from './forms/IsolationValveForm.svelte';
	import OrificeForm from './forms/OrificeForm.svelte';
	import PumpForm from './forms/PumpForm.svelte';
	import ReliefValveForm from './forms/ReliefValveForm.svelte';
	import ResultStrip from './ResultStrip.svelte';
	import ScenarioBanner from './ScenarioBanner.svelte';

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

<article class="space-y-3 px-3 py-3 sm:px-4" aria-labelledby="{id}-title">
	<!-- The name is edited in place, as the project name is: the heading stays for structure and
		focus (hidden), and shows its focus on the field, so a keyboard user sees where it is. -->
	<header
		class="-mx-2 flex flex-wrap items-center gap-x-3 rounded-md px-2 has-[[data-current-heading]:focus-visible]:ring-2 has-[[data-current-heading]:focus-visible]:ring-blue-600"
	>
		<h2 id="{id}-title" class="sr-only" tabindex="-1" data-current-heading>
			{component.name}
		</h2>
		{#key component.id}
			<TextField
				class="-mx-2 min-w-0 flex-1 basis-48"
				label="Name"
				hideLabel
				value={component.name}
				required
				maxlength={stringLimits(schema, 'name').maxLength}
				inputClass="border-transparent text-xl font-semibold hover:border-slate-300 focus:border-slate-400"
				shared
				hint={ws.inScenario ? 'Names are the same in every case.' : undefined}
				onchange={(v) =>
					!!v &&
					ws.editComponent(component.id, 'rename component', (c) => {
						c.name = v;
					})}
			/>
		{/key}
		<p class="text-sm text-slate-600">
			{kindLabel(component)} · <span class="font-mono">{component.id}</span>
		</p>
	</header>

	<ResultStrip element={{ kind: 'component', id: component.id }} />

	{#if ws.inScenario}
		<ScenarioBanner />
	{/if}

	<!-- The views and the actions in one row where they fit; phones put the actions above. -->
	<div class="flex flex-wrap items-end gap-x-2 gap-y-2 border-b border-slate-200">
		<div
			role="tablist"
			aria-label="Edit {component.name}"
			class="flex"
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
						'-mb-px min-h-ctl border-b-2 px-4 text-sm font-medium',
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
		{#if !ws.inScenario}
			<div
				class="mb-1 flex min-w-0 flex-wrap justify-end max-sm:order-first max-sm:w-full sm:ml-auto"
			>
				<ComponentActions {component} />
			</div>
		{/if}
	</div>

	<div id="{id}-panel" role="tabpanel" aria-labelledby="{id}-tab-{mode}" class="space-y-4">
		{#key component.id}
			{#if mode === 'component'}
				{#if component.type === 'branch'}
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
				{:else if component.type === 'equipment'}
					<EquipmentForm {component} />
				{:else if component.type === 'orifice'}
					<OrificeForm {component} />
				{:else if component.type === 'relief_valve'}
					<ReliefValveForm {component} />
				{:else if component.type === 'plug'}
					<FieldSections {component}>
						{#snippet about()}A closed end: no flow leaves through its port.{/snippet}
					</FieldSections>
				{:else}
					<!-- A reservoir, a reference node: every field is drawn from the registry. -->
					<FieldSections {component} />
				{/if}
			{:else}
				<ConnectionPanel {component} />
			{/if}
		{/key}
	</div>
</article>
