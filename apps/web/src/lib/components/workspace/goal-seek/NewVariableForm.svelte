<!--
	New variable (proposal goal-seek.md §6.5), inline in the dialog: an element (pumps, control
	valves, valves for their resistance, reservoirs, reference nodes, assigned-flow nodes, each pipe
	of a connection, the fluid), with a filter when there are more than six, and the value to vary,
	as radio buttons: the numeric values of the scenario allow-list the case shown has
	(x-goal-variables; a flow setpoint only with flow control, a temperature only for a built-in
	fluid). Statuses, a pipe's size and material and the whole fluid are never variables. A value
	already a variable is unavailable. Add adds it with its default bounds (the dialog moves the
	focus to From).
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import {
		hasVariable,
		VARIABLE_GROUP_LABELS,
		VARIABLE_GROUPS,
		variableElements,
		variableFieldLabel,
		type VariableChoice
	} from '$lib/utils/goal-seek';

	interface Props {
		onadd: (choice: VariableChoice) => void;
		oncancel: () => void;
	}

	let { onadd, oncancel }: Props = $props();
	const ws = useWorkspace();
	const id = $props.id();

	/** The elements with values to vary, by group: a control valve's group is Control valves. */
	const elements = $derived(variableElements(ws.project, ws.labelsProject));

	let filter = $state('');
	const shown = $derived(
		filter.trim()
			? elements.filter((e) => e.label.toLowerCase().includes(filter.trim().toLowerCase()))
			: elements
	);
	let selected = $state('');
	const element = $derived(elements.find((e) => e.key === selected) ?? elements[0]);
	let chosenValue = $state<string | null>(null);
	const chosen = $derived(
		element?.choices.find((c) => c.value === chosenValue && !hasVariable(ws.goalSeekSetup, c)) ??
			null
	);

	let selectElement: HTMLSelectElement | undefined = $state();
	onMount(() => selectElement?.focus());

	function add() {
		if (chosen) onadd(chosen);
	}
</script>

<fieldset class="card space-y-3 border-blue-200 bg-blue-50/40 p-3">
	<legend class="px-1 text-sm font-semibold">New variable</legend>
	{#if !elements.length}
		<p class="text-sm text-slate-700">This network has no values goal seek can change yet.</p>
	{:else}
		{#if elements.length > 6}
			<div>
				<label for="{id}-filter" class="label mb-1">Filter</label>
				<input
					id="{id}-filter"
					class="input"
					type="search"
					autocomplete="off"
					bind:value={filter}
					placeholder="Part of a name"
				/>
			</div>
		{/if}
		<div>
			<label for="{id}-element" class="label mb-1">Element</label>
			<select
				id="{id}-element"
				bind:this={selectElement}
				class="input pr-8"
				value={element?.key ?? ''}
				onchange={(event) => {
					selected = event.currentTarget.value;
					chosenValue = null;
				}}
			>
				{#each VARIABLE_GROUPS as group (group)}
					{@const options = shown.filter((e) => e.group === group)}
					{#if options.length}
						<optgroup label={VARIABLE_GROUP_LABELS[group]}>
							{#each options as option (option.key)}
								<option value={option.key}>{option.label}</option>
							{/each}
						</optgroup>
					{/if}
				{/each}
				{#if element && !shown.includes(element)}
					<option value={element.key}>{element.label}</option>
				{/if}
			</select>
		</div>
		<fieldset class="space-y-1">
			<legend class="label mb-1">Value</legend>
			<div class="flex flex-wrap gap-x-4 gap-y-1">
				{#each element?.choices ?? [] as choice (choice.value)}
					{@const used = hasVariable(ws.goalSeekSetup, choice)}
					<label class={['flex min-h-11 items-center gap-2 text-sm', used && 'text-slate-500']}>
						<input
							type="radio"
							name="{id}-value"
							value={choice.value}
							checked={chosen?.value === choice.value}
							aria-disabled={used ? 'true' : undefined}
							onclick={(event) => {
								if (used) event.preventDefault();
							}}
							onchange={() => {
								if (!used) chosenValue = choice.value;
							}}
						/>
						{variableFieldLabel(ws.project, choice)}{#if used}&nbsp;(already a variable){/if}
					</label>
				{/each}
			</div>
		</fieldset>
	{/if}
	<div class="flex flex-wrap gap-2">
		<button
			type="button"
			class="btn btn-primary"
			aria-disabled={!chosen}
			aria-describedby={chosen ? undefined : `${id}-add-reason`}
			onclick={add}>Add variable</button
		>
		<button type="button" class="btn" onclick={oncancel}>Cancel</button>
		{#if !chosen}
			<span id="{id}-add-reason" class="sr-only">Choose an element and a value first.</span>
		{/if}
	</div>
</fieldset>
