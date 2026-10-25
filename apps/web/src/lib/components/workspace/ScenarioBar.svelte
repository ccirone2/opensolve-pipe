<!--
	The case bar (proposal scenario-manager.md §6.3): shown only when the project has scenarios,
	between the header and the panes (across both on wide screens, above the Build and Results
	tabs on phones, so it is in view in every pane). It names the case being edited, says where
	edits go (teal in a scenario: colour is never the only signal), switches the case (page state,
	announced) and runs Solve all, with its progress on a line of its own (the one live region that
	announces it), and says when a solve of another case than the one shown is running. Solve all
	stays in place during a run (unavailable), so the focus stays on it; the run's end gives the
	focus to Solve. Below 640 px the sentence is hidden: the colour, the menu's text and the Build
	banner carry it. While a goal seek runs, Solve all is unavailable with the reason, and the
	status line says which case it runs on.
-->
<script lang="ts">
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { calculatingReason } from '$lib/utils/goal-seek';

	const ws = useWorkspace();
	const store = ws.store;
	const id = $props.id();

	const scenario = $derived(ws.activeScenario);
	const run = $derived(store.run);
	const toSolve = $derived(store.casesToSolve());
	const errors = $derived(store.casesWithErrors());
	const empty = $derived(!ws.project.components.length);
	/** A single solve in flight (of any case: it goes on after a case switch). */
	const solvingCase = $derived(run ? undefined : store.solvingCase);
	const goalSeek = $derived(store.calculating === 'goalSeek' ? store.goalSeek : null);
	const canRun = $derived(store.calculating === null && toSolve.length > 0 && !empty);

	function names(list: readonly (string | null)[]): string {
		const all = list.map((c) => ws.caseName(c));
		return all.length < 2 ? (all[0] ?? '') : `${all.slice(0, -1).join(', ')} and ${all.at(-1)}`;
	}

	const reason = $derived(
		empty
			? 'Add a component to the network first.'
			: goalSeek
				? calculatingReason('goalSeek', 'solve')
				: run
					? 'Solve all is running; Cancel in the header stops it.'
					: solvingCase !== undefined
						? `A solve of ${ws.caseName(solvingCase)} is running; Cancel in the header stops it.`
						: toSolve.length
							? ''
							: errors.length
								? `Every case is solved except ${names(errors)}, which ${errors.length === 1 ? 'has' : 'have'} an error to fix first.`
								: "Every case's results are current."
	);
	const progress = $derived.by(() => {
		if (!run) return '';
		const current = run.cases[run.index];
		return `Solving ${run.index + 1} of ${run.cases.length}: ${ws.caseName(current ?? null)}…`;
	});
	/** A solve of a case other than the one shown (the header's Solve is about the case shown). */
	const other = $derived(
		solvingCase !== undefined && solvingCase !== store.activeCase
			? `Solving ${ws.caseName(solvingCase)}…`
			: ''
	);
	const seeking = $derived(
		goalSeek?.status === 'running'
			? `Goal seek running on ${ws.caseWords(goalSeek.run.caseId)}…`
			: ''
	);
	const stopped = $derived(
		!run && store.runStop?.reason === 'network'
			? `Solve all stopped after a network error: ${store.runStop.message}`
			: !run && store.runStop?.reason === 'cancelled'
				? 'Solve all was cancelled: the cases not solved keep what they had.'
				: ''
	);

	function choose(value: string) {
		ws.setCase(value === '' ? null : value);
	}

	function solveAll(event: MouseEvent) {
		if (canRun && event.detail <= 1) void ws.solveAll();
	}

	// The end of a run: if its button area has the focus, Solve takes it.
	let area: HTMLElement | undefined = $state();
	let wasRunning = false;
	$effect.pre(() => {
		const running = !!run;
		if (wasRunning && !running && area?.contains(document.activeElement)) {
			queueMicrotask(() => document.querySelector<HTMLElement>('[data-solve-button]')?.focus());
		}
		wasRunning = running;
	});
</script>

{#if ws.scenarios.length}
	<div
		class={[
			'flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-l-4 px-2 py-1 sm:px-3',
			scenario
				? 'border-b-teal-200 border-l-teal-600 bg-teal-50 text-teal-950'
				: 'border-b-slate-200 border-l-slate-300 bg-slate-50 text-slate-800'
		]}
		role="group"
		aria-label="Case"
	>
		<div class="flex min-w-0 flex-1 items-center gap-2 sm:flex-none">
			<label for="{id}-case" class="text-sm font-medium">Case</label>
			<select
				id="{id}-case"
				class="input min-w-0 flex-1 py-1 pr-8 sm:w-64 sm:flex-none"
				value={store.activeCase ?? ''}
				onchange={(event) => choose(event.currentTarget.value)}
			>
				<option value="">Base case</option>
				{#each ws.scenarios as s (s.id)}
					<option value={s.id}>{s.name} ({ws.changesText(s)})</option>
				{/each}
			</select>
		</div>
		<p class="hidden min-w-0 flex-1 text-sm sm:block">
			{scenario
				? "Edits change only this scenario's values."
				: 'Edits change the base case and every scenario that does not set its own value.'}
		</p>
		<div bind:this={area} class="flex items-center gap-2">
			<button
				type="button"
				class="btn"
				aria-disabled={!canRun}
				aria-describedby="{id}-hint"
				title={reason || undefined}
				onclick={solveAll}
			>
				<Icon name="play" class="size-4" /> Solve all
			</button>
			<span id="{id}-hint" class="sr-only">
				{reason ||
					`Solves each case whose results are missing or out of date, one after another: up to ${toSolve.length} solve${toSolve.length === 1 ? '' : 's'}.`}
			</span>
		</div>
		<!-- Its own line: a long case name never squeezes the Case menu or the sentence. -->
		<p role="status" class="basis-full text-sm break-words empty:hidden">
			{progress || seeking || other || stopped}
		</p>
	</div>
{/if}
