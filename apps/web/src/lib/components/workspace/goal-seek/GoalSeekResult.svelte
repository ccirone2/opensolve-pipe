<!--
	A goal seek's result (proposal goal-seek.md §6.9-§6.11), rendered from the run's record (the
	request and project as sent, and the response), never from the live setup. It keeps its case:
	after a case switch it says which case it ran on, and Apply still names that case. A banner with
	an icon and words says the outcome (colour is never the only signal); then the values found (6
	significant digits, the exact SI value in the title and the report), the results reached, the
	notes in words, the physically invalid results at the values found, Apply (to the case it ran
	on, or as a new scenario; never a scenario run into the base), Copy report, and the trial solves
	and the method in closed details. A result goes out of date by its case's staleness key; Apply
	is then unavailable, with the reason, and Undo back to the run's project makes it current. A
	request error is shown with the Results pane's words: topology issues with Show, a fluid error,
	the server's input problems located at their variable or goal, a network error with Run again.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import type { Override } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import ResultsTable from '$lib/components/results/ResultsTable.svelte';
	import type { GoalSeekFinished } from '$lib/state/project.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { flagText } from '$lib/utils/flag-text';
	import {
		applyProblems,
		atValuesText,
		caseValueText,
		goalSeekGoalsTable,
		goalSeekReport,
		goalSeekTrialTable,
		noteText,
		outcomeText,
		requestIssues,
		runViews
	} from '$lib/utils/goal-seek';
	import IssueDetail from '$lib/components/results/IssueDetail.svelte';
	import { issueTextOptions, topologyIssueViews, topologySummary } from '$lib/utils/issue-text';
	import { componentName, fittingFallbackName } from '$lib/utils/labels';
	import {
		changeFieldLabel,
		changeTargetLabel,
		changes,
		changeTarget,
		overridesOf
	} from '$lib/utils/scenarios';

	interface Props {
		finished: GoalSeekFinished;
		/** Close the dialog (before showing an element in Build). */
		onclose: () => void;
		/** Run the goal seek again (a network error); `runReason` says why it cannot run now. */
		onrun: () => void;
		runReason: string;
	}

	let { finished, onclose, onrun, runReason }: Props = $props();
	const ws = useWorkspace();
	const store = ws.store;
	const id = $props.id();

	const run = $derived(finished.run);
	const response = $derived(finished.response);
	const words = $derived(ws.goalSeekWords(run, finished.stale));
	const views = $derived(runViews(words, run.request));
	const hasScenarios = $derived(ws.scenarios.length > 0);
	const runCase = $derived(ws.caseName(run.caseId));
	const otherCase = $derived(hasScenarios && run.caseId !== store.activeCase);
	const banner = $derived(response ? outcomeText(response, words, run.request) : null);
	const goalsTable = $derived(response ? goalSeekGoalsTable(response, words, run.request) : null);
	const trialTable = $derived(response ? goalSeekTrialTable(response, words, run.request) : null);
	const notes = $derived(
		response ? response.result.notes.map((n) => noteText(n, response, words, run.request)) : []
	);
	const solved = $derived(response?.solvedState ?? null);
	const invalidFlags = $derived.by(() => {
		if (!solved) return [];
		const valveTypes = Object.fromEntries(
			Object.entries(solved.valveResults).map(([vid, v]) => [vid, v.valveType])
		);
		return solved.flags
			.filter((f) => f.severity === 'invalid')
			.map((f) =>
				flagText(f, {
					project: ws.labelsProject,
					prefs: ws.displayUnits,
					fittingName: (type) => ws.library.fitting(type)?.name ?? fittingFallbackName(type),
					valveTypes
				})
			);
	});
	const atValues = $derived(solved ? atValuesText(solved.converged, invalidFlags) : '');

	const metAtStart = $derived(response?.result.stopReason === 'met_at_start');
	const caseReason = $derived(
		applyProblems(
			store.project,
			{ caseId: run.caseId, response, stale: finished.stale },
			'case',
			(c) => ws.caseName(c)
		)
	);
	const newReason = $derived(
		applyProblems(
			store.project,
			{ caseId: run.caseId, response, stale: finished.stale },
			'new',
			(c) => ws.caseName(c)
		)
	);
	const notOffered = $derived(
		run.caseId === null
			? hasScenarios
				? 'Not offered for an existing scenario: its other changes would give other results; run goal seek on that scenario.'
				: ''
			: `Not offered for the base case: the values were found with ${runCase}'s changes; in the base case they would give other results. Run goal seek on the base case to find base values.`
	);

	function apply(mode: 'case' | 'new') {
		if ((mode === 'case' ? caseReason : newReason) !== null) return;
		ws.applyGoalSeek(mode);
	}

	// Copy report, with the selected-textarea fallback of the methods summary.
	let copyStatus = $state<'idle' | 'copied' | 'manual'>('idle');
	let reportArea: HTMLTextAreaElement | undefined = $state();
	const report = $derived(
		response
			? goalSeekReport(response, run.request, {
					...words,
					projectName: ws.labelsProject.metadata.name,
					caseText: run.caseId === null ? 'base case' : `scenario ${runCase} (${run.caseId})`,
					startedAt: run.startedAt,
					stale: finished.stale,
					invalidFlags,
					converged: !!solved?.converged
				})
			: ''
	);

	async function copy() {
		try {
			if (!navigator.clipboard?.writeText) throw new Error('no clipboard');
			await navigator.clipboard.writeText(report);
			copyStatus = 'copied';
		} catch {
			copyStatus = 'manual';
			await tick();
			reportArea?.focus();
			reportArea?.select();
		}
	}

	// Request errors, in the Results pane's words.
	const error = $derived(finished.error);
	const issues = $derived(
		error?.kind === 'validation'
			? requestIssues(error.details, error.message, {
					project: ws.labelsProject,
					units: ws.units
				})
			: null
	);
	const issueViews = $derived(
		error?.kind === 'topology'
			? topologyIssueViews(
					error.issues,
					ws.project,
					!finished.stale,
					ws.units,
					issueTextOptions(ws.library)
				)
			: []
	);

	/** A scenario's invalid value (body.project.scenarios.{s}.overrides.{j}), as sent. */
	function scenarioIssue(
		detail: string
	): { override: Override; scenarioId: string; text: string } | null {
		const match = /scenarios\.(\d+)\.overrides\.(\d+)[^:]*:\s*(.*)$/.exec(detail);
		if (!match) return null;
		const scenario = run.project.scenarios?.[Number(match[1])];
		const override = scenario?.overrides?.[Number(match[2])];
		return scenario && override
			? { override, scenarioId: scenario.id, text: match[3] ?? '' }
			: null;
	}

	function resetChange(scenarioId: string, override: Override) {
		const target = changeTarget(override);
		const name = ws.caseName(scenarioId);
		ws.updateStored(
			(draft) => {
				const own = draft.scenarios?.find((s) => s.id === scenarioId);
				if (own)
					own.overrides = overridesOf(own).filter((o) => !changes(o, target, override.field));
			},
			`reset ${changeFieldLabel(store.project, override).toLowerCase()} in ${name}`
		);
	}

	function show(componentId: string, portId?: string) {
		onclose();
		ws.show(componentId, portId);
	}
</script>

<div class="space-y-3 text-sm">
	{#if otherCase}
		<p class="rounded-md border border-slate-300 bg-slate-50 p-2 break-words text-slate-800">
			This goal seek ran on {ws.caseWords(run.caseId)} (you are viewing {ws.caseWords(
				store.activeCase
			)}).
		</p>
	{/if}

	{#if error}
		<section
			class="space-y-2 rounded-lg border border-red-300 bg-red-50 p-3 text-red-900"
			aria-labelledby="{id}-error"
		>
			<h4 id="{id}-error" class="flex items-center gap-2 font-semibold">
				<Icon name="alert" class="size-5 shrink-0" />
				{#if error.kind === 'topology'}
					The network cannot be solved yet
				{:else if error.kind === 'validation' && error.code === 'FLUID_ERROR'}
					The fluid properties cannot be calculated
				{:else if error.kind === 'validation' && error.code === 'NOT_FOUND'}
					The calculation server did not find what the goal seek names
				{:else if error.kind === 'validation'}
					The calculation server rejected the goal seek
				{:else}
					No result
				{/if}
			</h4>
			{#if error.kind === 'topology'}
				<p>{topologySummary(error.issues.length)}</p>
				<ul class="list-disc space-y-1 pl-5">
					{#each issueViews as issue, i (i)}
						<li class="break-words">
							{issue.text}
							{#each issue.links as link, k (k)}
								<button
									type="button"
									class="ml-1 min-h-11 text-blue-800 underline underline-offset-2"
									onclick={() => show(link.componentId, link.portId)}
									>{link.label ?? componentName(ws.project, link.componentId)}</button
								>
							{/each}
							{#if issue.detail}
								<IssueDetail detail={issue.detail} />
							{/if}
						</li>
					{/each}
				</ul>
			{:else if error.kind === 'validation' && issues}
				<p class="break-words">{error.message}</p>
				{#if issues.variables.size || issues.goals.size || issues.other.length}
					<ul class="list-disc space-y-1 pl-5 break-words">
						{#each [...issues.variables] as [i, lines] (`v${i}`)}
							{#each lines as line, k (k)}
								<li>Variable {i + 1} ({views.variables[i]?.label ?? '—'}): {line}</li>
							{/each}
						{/each}
						{#each [...issues.goals] as [j, lines] (`g${j}`)}
							{#each lines as line, k (k)}
								<li>Goal {j + 1} ({views.goals[j]?.label ?? '—'}): {line}</li>
							{/each}
						{/each}
						{#each issues.other as detail, k (k)}
							{@const scenarioValue = scenarioIssue(detail)}
							{#if scenarioValue}
								{@const o = scenarioValue.override}
								<li>
									The value {ws.caseName(scenarioValue.scenarioId)} sets for {changeTargetLabel(
										store.project,
										o
									)}
									{changeFieldLabel(store.project, o).toLowerCase()} is not valid: {scenarioValue.text}
									{#if !finished.stale}
										<button
											type="button"
											class="btn btn-quiet px-2 text-blue-800"
											onclick={() => resetChange(scenarioValue.scenarioId, o)}>Reset to base</button
										>
									{/if}
								</li>
							{:else}
								<li>{detail}</li>
							{/if}
						{/each}
					</ul>
				{/if}
			{:else}
				<p class="break-words">{error.message}</p>
				<button
					type="button"
					class="btn"
					aria-disabled={!!runReason}
					title={runReason || undefined}
					onclick={() => !runReason && onrun()}
				>
					<Icon name="play" class="size-4" /> Run again
				</button>
			{/if}
		</section>
	{/if}

	{#if response && banner}
		<div
			class={[
				'space-y-1 rounded-lg border p-3',
				banner.tone === 'met'
					? 'border-emerald-300 bg-emerald-50 text-emerald-950'
					: banner.tone === 'notMet'
						? 'border-amber-300 bg-amber-50 text-amber-900'
						: 'border-red-300 bg-red-50 text-red-900'
			]}
		>
			<p class="flex items-center gap-2 font-semibold" data-goal-seek-outcome>
				<Icon name={banner.tone === 'met' ? 'check' : 'alert'} class="size-5 shrink-0" />
				{banner.title}
			</p>
			<p class="break-words">{banner.text}</p>
		</div>

		{#if finished.appliedCurrent && finished.applied}
			<p class="flex items-start gap-2 text-emerald-900">
				<Icon name="check" class="mt-0.5 size-4 shrink-0" />
				<span>Applied to {ws.caseWords(finished.applied.caseId)}.</span>
			</p>
		{:else if finished.stale}
			<p
				class="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-amber-900"
			>
				<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
				<span
					>Out of date: the project changed after this goal seek. Run it again to apply values that
					hold.</span
				>
			</p>
		{/if}

		{#if response.result.variables.some((v) => v.value !== null)}
			<section class="space-y-1" aria-labelledby="{id}-values">
				<h4 id="{id}-values" class="font-medium">Values found</h4>
				<dl class="space-y-1">
					{#each response.result.variables as v (v.index)}
						{@const view = views.variables[v.index]}
						{#if view && v.value !== null}
							<div class="break-words">
								<dt class="inline">{view.label} —</dt>
								<dd class="inline">
									<strong title="{v.value} (SI, as stored)">{view.text(v.value)}</strong>{v.atBound
										? `, at the ${v.atBound} bound`
										: ''}, was {caseValueText(words, v)}
								</dd>
							</div>
						{/if}
					{/each}
				</dl>
			</section>
		{/if}

		{#if goalsTable}
			<section class="space-y-1" aria-labelledby="{id}-reached">
				<h4 id="{id}-reached" class="font-medium">Results reached</h4>
				<ResultsTable table={goalsTable} caption="Results reached" first="Result" />
			</section>
		{/if}

		{#if notes.length}
			<section class="space-y-1" aria-labelledby="{id}-notes">
				<h4 id="{id}-notes" class="font-medium">Notes</h4>
				<ul class="list-disc space-y-1 pl-5">
					{#each notes as note, i (i)}<li class="break-words">{note}</li>{/each}
				</ul>
			</section>
		{/if}

		{#if atValues}
			<p class="break-words text-slate-700">At the values found: {atValues}</p>
		{/if}

		{#if !metAtStart && !(finished.appliedCurrent && finished.applied)}
			<div class="flex flex-wrap gap-2">
				<button
					type="button"
					class="btn btn-primary"
					aria-disabled={caseReason !== null}
					aria-describedby={caseReason ? `${id}-case-reason` : undefined}
					title={caseReason ?? undefined}
					aria-label={run.caseId === null ? 'Apply to base case' : `Apply to scenario ${runCase}`}
					onclick={() => apply('case')}
				>
					{run.caseId === null ? 'Apply to base case' : 'Apply to scenario'}
				</button>
				<button
					type="button"
					class="btn"
					aria-disabled={newReason !== null}
					aria-describedby={newReason ? `${id}-new-reason` : undefined}
					title={newReason ?? undefined}
					onclick={() => apply('new')}
				>
					Apply as new scenario
				</button>
			</div>
			<!-- A reason the out-of-date line above already says is for screen readers only. -->
			{#if caseReason}
				<p id="{id}-case-reason" class={finished.stale ? 'sr-only' : 'hint'}>{caseReason}</p>
			{/if}
			{#if newReason}
				<p
					id="{id}-new-reason"
					class={finished.stale || newReason === caseReason ? 'sr-only' : 'hint'}
				>
					{newReason}
				</p>
			{/if}
			{#if notOffered}<p class="hint">{notOffered}</p>{/if}
		{/if}

		<div class="space-y-2">
			<button type="button" class="btn" onclick={copy}>
				<Icon name="copy" class="size-4" /> Copy report
			</button>
			<p role="status" class="empty:hidden">
				{#if copyStatus === 'copied'}Copied to the clipboard.{:else if copyStatus === 'manual'}Copy
					the text below.{/if}
			</p>
			{#if copyStatus === 'manual'}
				<label class="block">
					<span class="label mb-1">Goal seek report as text</span>
					<textarea
						bind:this={reportArea}
						class="input h-48 font-mono text-xs"
						readonly
						value={report}></textarea>
				</label>
			{/if}
		</div>

		{#if trialTable}
			<details class="rounded-lg border border-slate-200 p-2">
				<summary class="min-h-11 cursor-pointer py-2 font-medium"
					>Trial solves ({trialTable.rows.length})</summary
				>
				<ResultsTable table={trialTable} caption="Trial solves" first="Trial" />
			</details>
		{/if}
		<details class="rounded-lg border border-slate-200 p-2">
			<summary class="min-h-11 cursor-pointer py-2 font-medium">Method</summary>
			<section class="space-y-1" aria-labelledby="{id}-method">
				<h4 id="{id}-method" class="font-semibold">{response.result.methods.title}</h4>
				<p class="text-xs text-slate-600">
					Every trial is a solve by OpenSolve Pipe calculation methods version {response.result
						.methodVersion}.
				</p>
				<ul class="list-disc space-y-1 pl-5 text-slate-800">
					{#each response.result.methods.items as item, j (j)}<li class="break-words">
							{item}
						</li>{/each}
				</ul>
				{#if response.result.methods.references.length}
					<p class="pt-1 text-xs font-medium text-slate-600">References</p>
					<ul class="space-y-0.5 pl-5 text-xs break-words text-slate-600">
						{#each response.result.methods.references as reference, j (j)}
							<li class="list-[square]">{reference}</li>
						{/each}
					</ul>
				{/if}
			</section>
		</details>
	{/if}
</div>
