<!--
	Goal seek (PRD §3.9, proposal goal-seek.md §6.3-§6.8, §6.13-§6.14): the results to reach and the
	inputs to change, with the result beside them from 1024 px (two columns, the result sticky) and
	below them on narrower screens, a bottom sheet on phones. It runs on the case shown, as Solve
	does; the setup is page state (kept across case switches and closing, reset by opening another
	project) and its fields are never locked in a scenario (they are not project values). One
	calculation request at a time: Run is unavailable, with the reason, while a solve runs, and
	while a goal seek runs it shows "Seeking…" with Cancel beside it. Closing the dialog does not
	cancel a run (the header's Cancel does); its end is then said by a workspace notice, and with
	the dialog open by the footer's live region. When the run ends with the focus on Run or Cancel,
	the Result heading takes it.
-->
<script lang="ts">
	import { onDestroy, tick, untrack } from 'svelte';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { provideFieldMode } from '$lib/components/ui/field-mode';
	import { finishedGoalSeek } from '$lib/state/project.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import {
		currentOrificeResult,
		GOAL_SEEK_BUDGET_S,
		goalKey,
		newVariable,
		orificePipeDiameter,
		rowIssues,
		runProblems,
		variableKey,
		foundValueTexts,
		type GoalDraft,
		type VariableChoice,
		type VariableDraft
	} from '$lib/utils/goal-seek';
	import { goalSeekLimits } from '$lib/utils/model-rules';
	import { componentById } from '$lib/utils/graph';
	import { inletBore } from '$lib/utils/orifice';
	import GoalCard from './goal-seek/GoalCard.svelte';
	import GoalSeekResult from './goal-seek/GoalSeekResult.svelte';
	import NewGoalForm from './goal-seek/NewGoalForm.svelte';
	import NewVariableForm from './goal-seek/NewVariableForm.svelte';
	import VariableCard from './goal-seek/VariableCard.svelte';

	const ws = useWorkspace();
	const store = ws.store;
	const id = $props.id();
	// The setup is page state, not project values: nothing here is locked in a scenario.
	provideFieldMode({ scenario: false });

	const limits = goalSeekLimits();
	const hasScenarios = $derived(ws.scenarios.length > 0);
	const caseId = $derived(store.activeCase);
	const caseName = $derived(ws.caseName(caseId));
	const setup = $derived(ws.goalSeekSetup);
	const seek = $derived(store.goalSeek);
	const running = $derived(seek?.status === 'running');
	const finished = $derived(finishedGoalSeek(seek));

	// A trace's prefill opens the goal form at once; it is used once (Add goal and Cancel clear
	// it), so a later Add goal opens on the first element.
	let addingGoal = $state(!!untrack(() => ws.goalSeekPrefill));
	let addingVariable = $state(false);

	const problems = $derived(runProblems(setup, ws.project, store.calculating, ws.displayUnits));
	const reason = $derived(running ? '' : (problems[0] ?? ''));
	const goalLimit = $derived(setup.goals.length >= limits.goals);
	const variableLimit = $derived(setup.variables.length >= limits.variables);

	// The run's elapsed seconds (aria-hidden: the live region says the start and the end only).
	let now = $state(Date.now());
	$effect(() => {
		if (!running) return;
		now = Date.now();
		const timer = setInterval(() => (now = Date.now()), 1000);
		return () => clearInterval(timer);
	});
	const elapsed = $derived(
		seek?.status === 'running' ? Math.max(0, Math.floor((now - seek.run.startedAt) / 1000)) : 0
	);

	/** Input problems the last failed run's server located at a variable or goal, by row key. */
	const cardIssues = $derived.by((): Record<string, string> => {
		const error = finished?.status === 'failed' ? finished.error : null;
		if (!finished || error?.kind !== 'validation') return {};
		return rowIssues(finished.run.request, error.details, error.message, {
			project: ws.labelsProject,
			units: ws.units
		});
	});

	let runButton: HTMLButtonElement | undefined = $state();
	let cancelButton: HTMLButtonElement | undefined = $state();
	let resultHeading: HTMLHeadingElement | undefined = $state();
	let addGoalButton: HTMLButtonElement | undefined = $state();
	let addVariableButton: HTMLButtonElement | undefined = $state();

	// The live region: the start and the outcome of a run while the dialog is open.
	let announcement = $state('');
	let lastStatus: string | undefined = untrack(() => store.goalSeek?.status);
	let focusResult = false;
	$effect.pre(() => {
		const status = seek?.status;
		untrack(() => {
			if (status === lastStatus) return;
			const was = lastStatus;
			lastStatus = status;
			if (status === 'running') {
				announcement = `Goal seek running on ${ws.caseWords(caseId)}.`;
				return;
			}
			if (was !== 'running') return;
			const active = document.activeElement;
			focusResult =
				active === runButton || active === cancelButton || !active || active === document.body;
			announcement = outcomeAnnouncement();
			if (focusResult) {
				void tick().then(() => {
					resultHeading?.focus();
					resultHeading?.scrollIntoView?.({ block: 'start' });
				});
			}
		});
	});

	function outcomeAnnouncement(): string {
		const s = store.goalSeek;
		if (!s || s.status === 'cancelled') return 'Goal seek cancelled.';
		if (s.status === 'failed') return `Goal seek failed: ${s.error?.message ?? 'no answer'}.`;
		if (s.status !== 'done' || !s.response) return '';
		if (!s.response.result.met) return 'Goal not met; see the result.';
		// Each value found by its variable, never by its override (a whole rating or fluid).
		const values = foundValueTexts(s.response, ws.goalSeekWords(s.run)).join(', ');
		const title = s.response.result.goals.length === 1 ? 'Goal met' : 'Goals met';
		return values ? `${title}: ${values}.` : `${title}.`;
	}

	function setGoals(goals: readonly GoalDraft[]) {
		ws.goalSeekSetup = { ...ws.goalSeekSetup, goals };
	}

	function setVariables(variables: readonly VariableDraft[]) {
		ws.goalSeekSetup = { ...ws.goalSeekSetup, variables };
	}

	/** Focus the first field of the last card of a list (a row just added). */
	async function focusLast(selector: string) {
		await tick();
		const cards = document.querySelectorAll<HTMLElement>(selector);
		cards[cards.length - 1]?.querySelector<HTMLInputElement>('input')?.focus();
	}

	async function addGoal(goal: GoalDraft) {
		setGoals([...setup.goals, goal]);
		addingGoal = false;
		ws.goalSeekPrefill = null;
		await focusLast('[data-goal-card]');
	}

	async function removeGoal(goal: GoalDraft) {
		setGoals(setup.goals.filter((g) => goalKey(g) !== goalKey(goal)));
		await tick();
		addGoalButton?.focus();
	}

	/** The case's last converged solve: what default bounds of a resistance on its default need. */
	function kOpenOf(choice: VariableChoice): number | null {
		const response = store.results.response;
		if (choice.target.kind !== 'component' || !response?.solvedState.converged) return null;
		return response.solvedState.valveResults[choice.target.componentId]?.kOpen ?? null;
	}

	/** An orifice plate's result in the case's last converged solve, unless out of date. */
	function orificeOf(choice: VariableChoice) {
		if (choice.target.kind !== 'component') return null;
		return currentOrificeResult(store.results, choice.target.componentId);
	}

	/** An orifice plate's D: as its form resolves it for the case now, else the current solve's. */
	function pipeDiameterOf(choice: VariableChoice): number | null {
		if (choice.target.kind !== 'component') return null;
		const inlet = inletBore(ws.project, choice.target.componentId, ws.library);
		return orificePipeDiameter(inlet, orificeOf(choice));
	}

	async function addVariable(choice: VariableChoice) {
		const fluid = ws.project.fluid;
		const info = fluid.kind === 'builtin' ? ws.library.fluid(fluid.fluidId) : undefined;
		const target = choice.target;
		const plate =
			target.kind === 'component' &&
			componentById(ws.project, target.componentId)?.type === 'orifice';
		const variable = newVariable(ws.project, choice, {
			kOpen: kOpenOf(choice),
			kOpenStale: store.results.stale,
			sizes: ws.library,
			...(plate ? { pipeDiameter: pipeDiameterOf(choice), orifice: orificeOf(choice) } : {}),
			...(info ? { fluid: info } : {})
		});
		setVariables([...setup.variables, variable]);
		addingVariable = false;
		await focusLast('[data-variable-card]');
	}

	async function removeVariable(variable: VariableDraft) {
		setVariables(setup.variables.filter((v) => variableKey(v) !== variableKey(variable)));
		await tick();
		addVariableButton?.focus();
	}

	async function openGoalForm() {
		if (goalLimit) return;
		addingGoal = true;
	}

	async function closeGoalForm() {
		addingGoal = false;
		ws.goalSeekPrefill = null;
		await tick();
		addGoalButton?.focus();
	}

	async function closeVariableForm() {
		addingVariable = false;
		await tick();
		addVariableButton?.focus();
	}

	/** Run, unless a reason applies (checked at click time); the second click of a double does nothing. */
	function run(event?: MouseEvent) {
		if (event && event.detail > 1) return;
		if (running || problems.length) return;
		void ws.runGoalSeek();
	}

	function cancel(event: MouseEvent) {
		if (event.detail > 1) return;
		store.cancelGoalSeek();
	}

	// Closing returns the focus to the opener (Dialog); when the opener is gone (a trace sheet
	// closed for this dialog), the Results pane's Goal seek button takes it.
	onDestroy(() => {
		queueMicrotask(() => {
			const active = document.activeElement;
			if (!active || active === document.body) {
				document.querySelector<HTMLElement>('[data-goal-seek-button]')?.focus();
			}
		});
	});
</script>

<Dialog title="Goal seek" onclose={() => ws.closeGoalSeek()} xl>
	<div class="lg:grid lg:grid-cols-2 lg:items-start lg:gap-6">
		<div class="min-w-0 space-y-4">
			<p class="text-sm text-slate-700">
				Finds the input values that make results reach their targets. Each trial is a full solve of
				the {hasScenarios ? 'case' : 'project'}; nothing in the project changes until you apply the
				values.
			</p>
			{#if hasScenarios}
				<p class="text-sm text-slate-700">
					Case
					<span
						class={[
							'ml-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium break-words',
							caseId === null ? 'bg-slate-200 text-slate-800' : 'bg-teal-700 text-white'
						]}>{caseName}</span
					>
					(the case shown; switch it in the case bar)
				</p>
			{/if}

			<section class="space-y-2" aria-labelledby="{id}-goals">
				<div class="flex flex-wrap items-center gap-2">
					<h3 id="{id}-goals" class="section-title flex-1">
						Results to reach ({setup.goals.length})
					</h3>
					<button
						bind:this={addGoalButton}
						type="button"
						class="btn"
						aria-disabled={goalLimit || addingGoal}
						aria-describedby={goalLimit ? `${id}-goal-limit` : undefined}
						onclick={openGoalForm}
					>
						<Icon name="plus" class="size-4" /> Add goal
					</button>
					{#if goalLimit}
						<span id="{id}-goal-limit" class="sr-only"
							>A goal seek takes at most {limits.goals} goals.</span
						>
					{/if}
				</div>
				{#each setup.goals as goal, j (goalKey(goal))}
					<GoalCard
						{goal}
						number={j + 1}
						issue={cardIssues[`g:${goalKey(goal)}`] ?? null}
						onchange={(next) => setGoals(setup.goals.map((g, k) => (k === j ? next : g)))}
						onremove={() => removeGoal(goal)}
					/>
				{/each}
				{#if addingGoal}
					<NewGoalForm prefill={ws.goalSeekPrefill} onadd={addGoal} oncancel={closeGoalForm} />
				{/if}
			</section>

			<section class="space-y-2" aria-labelledby="{id}-variables">
				<div class="flex flex-wrap items-center gap-2">
					<h3 id="{id}-variables" class="section-title flex-1">
						Inputs to change ({setup.variables.length})
					</h3>
					<button
						bind:this={addVariableButton}
						type="button"
						class="btn"
						aria-disabled={variableLimit || addingVariable}
						aria-describedby={variableLimit ? `${id}-variable-limit` : undefined}
						onclick={() => !variableLimit && (addingVariable = true)}
					>
						<Icon name="plus" class="size-4" /> Add variable
					</button>
					{#if variableLimit}
						<span id="{id}-variable-limit" class="sr-only"
							>A goal seek takes at most {limits.variables} variables.</span
						>
					{/if}
				</div>
				{#each setup.variables as variable, i (variableKey(variable))}
					<VariableCard
						{variable}
						number={i + 1}
						issue={cardIssues[`v:${variableKey(variable)}`] ?? null}
						onchange={(next) => setVariables(setup.variables.map((v, k) => (k === i ? next : v)))}
						onremove={() => removeVariable(variable)}
					/>
				{/each}
				{#if addingVariable}
					<NewVariableForm onadd={addVariable} oncancel={closeVariableForm} />
				{/if}
			</section>
		</div>

		<section
			class="mt-4 min-w-0 space-y-2 lg:sticky lg:top-0 lg:mt-0"
			aria-labelledby="{id}-result"
		>
			<h3
				bind:this={resultHeading}
				id="{id}-result"
				tabindex="-1"
				class="section-title scroll-mt-2"
			>
				Result
			</h3>
			{#if seek?.status === 'running'}
				<p class="text-sm text-slate-700">Running…</p>
			{:else}
				{#if seek?.status === 'cancelled'}
					<p
						class="flex items-start gap-2 rounded-md border border-slate-300 bg-slate-50 p-3 text-sm text-slate-800"
					>
						<Icon name="info" class="mt-0.5 size-4 shrink-0" />
						<span>Goal seek cancelled. Nothing in the project changed.</span>
					</p>
				{/if}
				{#if finished}
					<GoalSeekResult
						{finished}
						onclose={() => ws.closeGoalSeek()}
						onrun={() => run()}
						runReason={problems[0] ?? ''}
					/>
				{:else if !seek}
					<p class="text-sm text-slate-700">Add a goal and a variable, then Run goal seek.</p>
				{/if}
			{/if}
		</section>
	</div>

	{#snippet footer()}
		<p
			id="{id}-status"
			class="min-w-0 basis-full self-center text-sm break-words text-slate-700 sm:mr-auto sm:flex-1 sm:basis-auto"
		>
			{#if seek?.status === 'running'}
				Running on {ws.caseWords(seek.run.caseId)}…
				<span aria-hidden="true">{elapsed} s.</span>
				A goal seek stops by itself after at most {GOAL_SEEK_BUDGET_S} s.
			{:else}
				{reason}
			{/if}
		</p>
		<p class="sr-only" role="status">{announcement}</p>
		<button type="button" class="btn" onclick={() => ws.closeGoalSeek()}>Close</button>
		{#if running}
			<button
				bind:this={cancelButton}
				type="button"
				class="btn"
				aria-label={hasScenarios && seek?.status === 'running'
					? `Cancel goal seek on ${ws.caseName(seek.run.caseId)}`
					: 'Cancel goal seek'}
				onclick={cancel}
			>
				<Icon name="close" class="size-4" /> Cancel
			</button>
		{/if}
		<button
			bind:this={runButton}
			type="button"
			class="btn btn-primary"
			aria-disabled={running || problems.length > 0}
			aria-describedby={reason ? `${id}-status` : undefined}
			title={reason || undefined}
			onclick={run}
		>
			<Icon
				name={running ? 'spinner' : 'play'}
				class={['size-4', running && 'motion-safe:animate-spin']}
			/>
			<!-- Both labels in one grid cell: the button keeps the wider one's width. -->
			<span class="grid">
				<span class={['col-start-1 row-start-1', running && 'invisible']} aria-hidden={running}
					>Run goal seek</span
				>
				<span class={['col-start-1 row-start-1', !running && 'invisible']} aria-hidden={!running}
					>Seeking…</span
				>
			</span>
			{#if hasScenarios}<span class="sr-only"> on {caseName}</span>{/if}
		</button>
	{/snippet}
</Dialog>
