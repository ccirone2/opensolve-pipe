<!--
	One goal of the goal-seek setup (proposal goal-seek.md §6.4): a fieldset named by the result it
	reads ("Outlet of Far user tee · Pressure", as Compare names it), with its Target (required: no
	default, it is the user's question) and Tolerance (blank: the default) in the display unit of
	the quantity, a tolerance a difference (no gauge marker). The tolerance field's bounds are the
	schema's and the quantity's published minimum for the target (x-goal-quantities), so a
	tolerance it accepts is never one the API rejects; a target changed afterwards says so. The
	hint gives the last solve's value, the sign convention and the default tolerance. A connection's
	value is read on it as it is now, as its name and sign convention are (Compare's reading): the
	other sign after a reversal since the solve, none after an end moved or its pipes changed. A
	goal whose element or port no longer exists says so and blocks Run until it is removed.
-->
<script lang="ts">
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import {
		defaultToleranceText,
		goalHint,
		goalKey,
		goalLabel,
		goalLapse,
		goalSpec,
		lastSolveText,
		targetBounds,
		toleranceBounds,
		toleranceProblem,
		type GoalDraft
	} from '$lib/utils/goal-seek';

	interface Props {
		goal: GoalDraft;
		/** 1-based, as the API's issues and the result number goals. */
		number: number;
		onchange: (goal: GoalDraft) => void;
		onremove: () => void;
		/** What the last run's server said about this goal (an input problem), if anything. */
		issue?: string | null;
	}

	let { goal, number, onchange, onremove, issue = null }: Props = $props();
	const ws = useWorkspace();
	const id = $props.id();

	const lapse = $derived(goalLapse(ws.project, goal));
	const label = $derived(lapse ?? goalLabel(ws.labelsProject, goal));
	const spec = $derived(goalSpec(goal.quantity));
	const results = $derived(ws.store.results);
	const hint = $derived(
		lapse
			? ''
			: [
					lastSolveText(goal, results.response, results.stale, ws.displayUnits, {
						structure: ws.store.project,
						sent: results.stale ? ws.store.solvedProject : null
					}),
					goalHint(ws.labelsProject, goal),
					defaultToleranceText(goal.quantity, ws.displayUnits)
				]
					.filter(Boolean)
					.join(' ')
	);
	const toleranceError = $derived(toleranceProblem(goal, ws.displayUnits));
</script>

<fieldset
	class="card relative min-w-0 space-y-2 p-3"
	data-goal-card={goalKey(goal)}
	aria-describedby={hint ? `${id}-hint` : undefined}
>
	<legend class="float-left w-full pr-12 text-sm font-medium break-words">
		<span class="sr-only">Goal {number}: </span>{label}
	</legend>
	<button
		type="button"
		class="btn btn-quiet btn-icon absolute top-1 right-1"
		aria-label="Remove goal {label}"
		onclick={onremove}
	>
		<Icon name="trash" class="size-4" />
	</button>
	<div class="clear-both grid grid-cols-2 gap-3">
		<NumberField
			label="Target"
			value={goal.target}
			category={spec.category}
			gauge={!!spec.options.gauge}
			units={ws.displayUnits}
			bounds={targetBounds()}
			onchange={(target) => {
				if (target === null) return false;
				onchange({ ...goal, target });
			}}
		/>
		<NumberField
			label="Tolerance"
			value={goal.tolerance}
			category={spec.category}
			units={ws.displayUnits}
			optional
			placeholder="Default"
			bounds={toleranceBounds(goal.quantity, goal.target)}
			error={toleranceError}
			onchange={(tolerance) => onchange({ ...goal, tolerance })}
		/>
	</div>
	{#if hint}<p id="{id}-hint" class="hint">{hint}</p>{/if}
	{#if lapse}
		<p class="flex items-start gap-1 text-sm text-amber-900">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span
				>No longer applies: remove it, or undo the change that removed its element.</span
			>
		</p>
	{/if}
	{#if issue}
		<p class="flex items-start gap-1 text-sm break-words text-red-700">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span>{issue}</span>
		</p>
	{/if}
</fieldset>
