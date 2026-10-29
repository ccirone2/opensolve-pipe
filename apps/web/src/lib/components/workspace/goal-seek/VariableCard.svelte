<!--
	One variable of the goal-seek setup (proposal goal-seek.md §6.5): a fieldset named by the value
	it varies ("Transfer pump · Speed", as scenario changes name it), the case's value now (set by
	the scenario shown, or outside the bounds, said so), and its From and To bounds in display
	units. Their bounds are the field's own (the schema, a valve type's setpoint bounds, a
	controlled pump's maximum speed above its minimum) and each other's (x-ordered-fields: From
	below To); an entry outside them is refused at the field. The defaults are shown while both
	bounds are unchanged. A variable that no longer applies in the case shown says why and blocks
	Run until it is removed or the case is switched back.
-->
<script lang="ts">
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import {
		currentOrificeResult,
		defaultsText,
		nowText,
		variableBounds,
		variableKey,
		variableLabel,
		variableLapse,
		variableSpec,
		withCaseKind,
		type VariableDraft
	} from '$lib/utils/goal-seek';

	interface Props {
		variable: VariableDraft;
		/** 1-based, as the API's issues and the result number variables. */
		number: number;
		onchange: (variable: VariableDraft) => void;
		onremove: () => void;
		/** What the last run's server said about this variable (an input problem), if anything. */
		issue?: string | null;
	}

	let { variable, number, onchange, onremove, issue = null }: Props = $props();
	const ws = useWorkspace();

	const lapse = $derived(variableLapse(ws.project, variable));
	// Names from the labels project; a Cv's or Kv's kind, and an effective or actual area's,
	// from the case shown (as its value).
	const label = $derived(variableLabel(ws.labelsProject, withCaseKind(ws.project, variable)));
	const spec = $derived(variableSpec(ws.project, variable));
	const bounds = $derived(lapse ? { lower: {}, upper: {} } : variableBounds(ws.project, variable));
	/** The case's last converged solve: a valve's fully open K, for one on its default. */
	const kOpen = $derived.by(() => {
		const response = ws.store.results.response;
		if (variable.target.kind !== 'component' || !response?.solvedState.converged) return null;
		return response.solvedState.valveResults[variable.target.componentId]?.kOpen ?? null;
	});
	/** An orifice plate's result in the case's last converged solve, unless out of date (ISO's C). */
	const orifice = $derived(
		variable.target.kind === 'component'
			? currentOrificeResult(ws.store.results, variable.target.componentId)
			: null
	);
	const now = $derived(
		lapse
			? ''
			: nowText(ws.project, variable, {
					prefs: ws.displayUnits,
					kOpen,
					orifice,
					scenario: ws.activeScenario
				})
	);
	const defaults = $derived(lapse ? '' : defaultsText(ws.project, variable, ws.displayUnits));
</script>

<fieldset class="card relative min-w-0 space-y-2 p-3" data-variable-card={variableKey(variable)}>
	<legend class="float-left w-full pr-12 text-sm font-medium break-words">
		<span class="sr-only">Variable {number}: </span>{label}
	</legend>
	<button
		type="button"
		class="btn btn-quiet btn-icon absolute top-1 right-1"
		aria-label="Remove variable {label}"
		onclick={onremove}
	>
		<Icon name="trash" class="size-4" />
	</button>
	{#if now}<p class="clear-both text-sm break-words text-slate-700">{now}</p>{/if}
	<div class="clear-both grid grid-cols-2 gap-3">
		<NumberField
			label="From"
			value={variable.lower}
			category={spec.category}
			gauge={!!spec.options.gauge}
			units={ws.displayUnits}
			bounds={bounds.lower}
			onchange={(lower) => {
				if (lower === null) return false;
				onchange({ ...variable, lower });
			}}
		/>
		<NumberField
			label="To"
			value={variable.upper}
			category={spec.category}
			gauge={!!spec.options.gauge}
			units={ws.displayUnits}
			bounds={bounds.upper}
			onchange={(upper) => {
				if (upper === null) return false;
				onchange({ ...variable, upper });
			}}
		/>
	</div>
	{#if defaults}<p class="hint">{defaults}</p>{/if}
	{#if lapse}
		<p class="flex items-start gap-1 text-sm break-words text-amber-900">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span
				>No longer applies: {lapse}. Remove it, or switch back to the case where it applies.</span
			>
		</p>
	{/if}
	{#if issue}
		<p class="flex items-start gap-1 text-sm break-words text-red-700">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span>{issue}</span>
		</p>
	{/if}
</fieldset>
