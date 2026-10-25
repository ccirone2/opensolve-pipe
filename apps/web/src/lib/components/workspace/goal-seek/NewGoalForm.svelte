<!--
	New goal (proposal goal-seek.md §6.4), inline in the dialog (never a nested dialog): an element
	(ports, pipe connections, pumps, valves, reservoirs and reference nodes, as x-goal-quantities
	names them), with a filter when there are more than six, and the result to reach, as radio
	buttons. A result already a goal, or one the case cannot give (an NPSH margin without NPSHr,
	NPSH without a vapor pressure), is shown unavailable with why. Add adds the goal (the dialog
	moves the focus to its Target); Cancel closes the form.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import type { GoalQuantity } from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { QUANTITIES } from '$lib/utils/compare';
	import {
		GOAL_GROUP_LABELS,
		GOAL_GROUPS,
		GOAL_QUANTITIES,
		goalChoices,
		goalElements,
		goalNeedProblem,
		hasGoal,
		newGoal,
		type GoalDraft,
		type GoalElement
	} from '$lib/utils/goal-seek';
	import type { ElementRef } from '$lib/utils/results';

	interface Props {
		/** The element to start on (Use in goal seek in a trace); the focus goes to the results. */
		prefill?: ElementRef | null;
		onadd: (goal: GoalDraft) => void;
		oncancel: () => void;
	}

	let { prefill = null, onadd, oncancel }: Props = $props();
	const ws = useWorkspace();
	const id = $props.id();

	const elements = $derived(goalElements(ws.labelsProject));
	let filter = $state('');
	const shown = $derived(
		filter.trim()
			? elements.filter((e) => e.label.toLowerCase().includes(filter.trim().toLowerCase()))
			: elements
	);

	/** The option a prefilled element starts on: its own group, else its first port. */
	function initial(): string {
		if (!prefill) return elements[0]?.value ?? '';
		if (prefill.kind === 'connection') return `connection\u0000${prefill.id}`;
		const own = elements.find((e) => e.group !== 'port' && e.elementId === prefill.id);
		const port = elements.find((e) => e.group === 'port' && e.elementId === prefill.id);
		return (own ?? port ?? elements[0])?.value ?? '';
	}

	let selected = $state(initial());
	const element = $derived<GoalElement | undefined>(elements.find((e) => e.value === selected));
	const choices = $derived(element ? goalChoices(ws.project, element) : []);
	const info = $derived(
		ws.project.fluid.kind === 'builtin' ? ws.library.fluid(ws.project.fluid.fluidId) : undefined
	);

	function unavailable(quantity: GoalQuantity): string | null {
		if (!element) return null;
		if (
			hasGoal(ws.goalSeekSetup, { quantity, elementId: element.elementId, portId: element.portId })
		)
			return 'already a goal';
		return goalNeedProblem(ws.project, quantity, element.elementId, info);
	}

	let quantity = $state<GoalQuantity | null>(null);
	// A result that does not apply to the element chosen (or is unavailable) is not kept.
	const chosen = $derived(
		quantity && choices.includes(quantity) && !unavailable(quantity) ? quantity : null
	);

	let resultGroup: HTMLFieldSetElement | undefined = $state();
	let selectElement: HTMLSelectElement | undefined = $state();
	onMount(() => {
		const focus = () => {
			if (prefill) resultGroup?.querySelector<HTMLInputElement>('input')?.focus();
			else selectElement?.focus();
		};
		focus();
		// Opened with the dialog (a trace's Use in goal seek): after the dialog's own opening focus.
		const timer = setTimeout(focus, 0);
		return () => clearTimeout(timer);
	});

	function add() {
		if (!element || !chosen) return;
		onadd(newGoal(element, chosen));
	}
</script>

<fieldset class="card space-y-3 border-blue-200 bg-blue-50/40 p-3">
	<legend class="px-1 text-sm font-semibold">New goal</legend>
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
	{#if elements.length}
		<div>
			<label for="{id}-element" class="label mb-1">Element</label>
			<select id="{id}-element" bind:this={selectElement} class="input pr-8" bind:value={selected}>
				{#each GOAL_GROUPS as group (group)}
					{@const options = shown.filter((e) => e.group === group)}
					{#if options.length}
						<optgroup label={GOAL_GROUP_LABELS[group]}>
							{#each options as option (option.value)}
								<option value={option.value}>{option.label}</option>
							{/each}
						</optgroup>
					{/if}
				{/each}
				{#if element && !shown.includes(element)}
					<option value={element.value}>{element.label}</option>
				{/if}
			</select>
		</div>
		<fieldset bind:this={resultGroup} class="space-y-1" aria-describedby="{id}-result-hint">
			<legend class="label mb-1">Result</legend>
			<div class="flex flex-wrap gap-x-4 gap-y-1">
				{#each choices as q (q)}
					{@const why = unavailable(q)}
					<label class={['flex min-h-11 items-center gap-2 text-sm', why && 'text-slate-500']}>
						<input
							type="radio"
							name="{id}-quantity"
							value={q}
							checked={chosen === q}
							aria-disabled={why ? 'true' : undefined}
							onclick={(event) => {
								if (why) event.preventDefault();
							}}
							onchange={() => {
								if (!why) quantity = q;
							}}
						/>
						{QUANTITIES[GOAL_QUANTITIES[q]].label}{#if why}&nbsp;({why}){/if}
					</label>
				{/each}
			</div>
			<p id="{id}-result-hint" class="hint">
				{choices.length ? 'Choose the result to bring to a target.' : 'Choose an element first.'}
			</p>
		</fieldset>
	{:else}
		<p class="text-sm text-slate-700">Add components to the network first.</p>
	{/if}
	<div class="flex flex-wrap gap-2">
		<button
			type="button"
			class="btn btn-primary"
			aria-disabled={!chosen}
			aria-describedby={chosen ? undefined : `${id}-add-reason`}
			onclick={add}>Add goal</button
		>
		<button type="button" class="btn" onclick={oncancel}>Cancel</button>
		{#if !chosen}
			<span id="{id}-add-reason" class="sr-only">Choose an element and a result first.</span>
		{/if}
	</div>
</fieldset>
