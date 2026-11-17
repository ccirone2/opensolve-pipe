<!--
	The Scenarios menu (proposal build-density.md §13, §19): opened from the header's Scenarios
	button once the project has scenarios. Solve all leads it: since §19 (the owner, 2026-11-12:
	"one Solve, one Solve all") it is the one Solve all of the page, the menu's first control, a
	primary button counting the cases it would solve ("Solve all (7)"), with Ctrl/⌘+Shift+Enter
	(Workspace.svelte), while the Scenarios badge counts them down in the header. Then its line, its
	progress, the case shown and the way into the scenario manager. The case bar under the header
	held these before §13; the case shown is still said where it matters (the Build pane's note in
	a scenario, the Results pane, Solve's name).
-->
<!--
	Solve all (scenario-manager.md §6.3; build-density.md §19). Its count shows only while it can
	run: during a run the badge carries the countdown, so no unavailable "Solve all (6)" sits beside
	"Solving 1 of 7". Its line is always its description: what it does while it can run; a reason
	that lasts (every case current, the rest with an error to fix first, an empty network) shown;
	one that passes (a solve, Solve all or a goal seek running) said and in its title, not shown
	(ui-guide). The reasons are one function's (utils/goal-seek.ts solveAllState) with the badge's
	and the shortcut's. A held Enter (the one that opened the menu) does not run it: its repeats are
	prevented. Solve all stays in place during a run (unavailable), so the focus stays on it; a
	run that ran to its end gives the focus to Solve when it was in the menu, and a cancelled or
	stopped one leaves it on Solve all, which resumes the run. The status line says the progress,
	a solve of another case than the one shown, a goal seek and how a stopped run ended; the header
	says the progress and a cancel while this menu is closed, and raises a network stop as an alert.
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	let { onmanage, onchoose }: { onmanage: () => void; onchoose?: () => void } = $props();
	const ws = useWorkspace();
	const store = ws.store;
	const id = $props.id();

	const scenario = $derived(ws.activeScenario);
	const run = $derived(store.run);
	/** A single solve in flight (of any case: it goes on after a case switch). */
	const solvingCase = $derived(run ? undefined : store.solvingCase);
	const goalSeek = $derived(store.calculating === 'goalSeek' ? store.goalSeek : null);
	/** Solve all now: its count, whether it can run and why not (the badge's and the keys' too). */
	const all = $derived(ws.solveAllState);

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

	/** A case chosen: shown, and the menu closes (the choice is what it was opened for). */
	function choose(value: string) {
		ws.setCase(value === '' ? null : value);
		onchoose?.();
	}

	function solveAll(event: MouseEvent) {
		// The second click of a double click does nothing (a click with detail 0 is a key's).
		if (all.canRun && event.detail <= 1) void ws.solveAll();
	}

	// A run that ran to its end (the header closes the menu): if the menu has the focus, Solve
	// takes it. A cancelled or stopped one keeps the menu open, and the focus where it is (on Solve
	// all, which resumes the run): moved out, it would close the menu (WorkspaceHeader's focusout).
	let area: HTMLElement | undefined = $state();
	let wasRunning = false;
	$effect.pre(() => {
		const running = !!run;
		const stop = untrack(() => store.runStop);
		if (wasRunning && !running && !stop && area?.contains(document.activeElement)) {
			queueMicrotask(() => document.querySelector<HTMLElement>('[data-solve-button]')?.focus());
		}
		wasRunning = running;
	});
</script>

<div bind:this={area} role="group" aria-label="Case" class="dense space-y-2">
	<button
		type="button"
		class="btn btn-primary w-full sm:w-auto"
		data-solve-all
		aria-disabled={!all.canRun}
		aria-describedby="{id}-line"
		aria-keyshortcuts="Control+Shift+Enter Meta+Shift+Enter"
		title={all.passing ? all.reason : 'Solve all (Ctrl+Shift+Enter or ⌘+Shift+Enter)'}
		onclick={solveAll}
		onkeydown={(event) => {
			// A held Enter repeats: the press that opened the menu must not run it.
			if (event.key === 'Enter' && event.repeat) event.preventDefault();
		}}
	>
		<Icon name="play" class="size-4" /> Solve all{#if all.canRun}{` (${all.count})`}{/if}
	</button>
	<p id="{id}-line" class={all.passing ? 'sr-only' : 'text-xs text-slate-600'}>
		{all.reason || all.hint}
	</p>
	<!-- Present before its text (a live region); empty, it takes no room (its margin collapses). -->
	<p role="status" class="text-sm break-words">
		{progress || seeking || other || stopped}
	</p>
	<div class="field border-t border-slate-200 pt-2">
		<label for="{id}-case" class="label">Case</label>
		<select
			id="{id}-case"
			class="input pr-8"
			value={store.activeCase ?? ''}
			onchange={(event) => choose(event.currentTarget.value)}
		>
			<option value="">Base case</option>
			{#each ws.scenarios as s (s.id)}
				<option value={s.id}>{s.name} ({ws.changesText(s)})</option>
			{/each}
		</select>
	</div>
	<p class="text-xs text-slate-600">
		{scenario
			? "Edits change only this scenario's values."
			: 'Edits change the base case and every scenario that does not set its own value.'}
	</p>
	<button type="button" class="btn btn-quiet text-blue-800" onclick={onmanage}>
		<Icon name="layers" class="size-4" /> Manage scenarios…
	</button>
</div>
