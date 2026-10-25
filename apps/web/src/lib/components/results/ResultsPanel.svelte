<!--
	Results pane (design §5): what the last solve returned. Topology issues, validation errors or a
	network error; or the solve's status (with the convergence report when it did not converge),
	a notice when the results are out of date or the calculation methods changed, the physics
	flags by severity, and the results by view: Summary, Nodes, Links, Pumps, Valves, Branches,
	Boundaries, Assigned flows, Methods. Rows and flags open an element's results and trace, and
	point the navigator at it. Input problems the solver would also report are listed so they can
	be fixed first; solving is never blocked. After a cancelled solve, a note says so above what
	earlier solves left. Only the short status line is a live region.

	Tables are built once per solve and display units (and when names change), not on every edit,
	and a view stays rendered (hidden) once visited, so switching views is quick on large networks.

	With scenarios (proposal scenario-manager.md §6.11): the header names the case shown, two tabs
	switch between its results and Compare cases, and a card at the top says which case produced
	the results and lists the changes the server applied. Rows of elements the scenario changed say
	so, in every table; a scenario's invalid value is shown with the change that set it, and Reset
	to base. The case bar announces Solve all's progress; the status line here is the case shown's,
	and a case switch replaces it (the switch is announced once, by the workspace). Switching tab
	from a control that goes (a column header of Compare cases, the card's Compare cases) gives the
	focus to the tab shown.
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import type { Component, ControlValve } from '$lib/api/types';
	import SiteFooter from '$lib/components/SiteFooter.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { freePorts, isBoundary } from '$lib/utils/graph';
	import { componentName, portLabel } from '$lib/utils/labels';
	import { mediaQuery, WIDE_SCREEN } from '$lib/utils/media.svelte';
	import {
		assignedFlowTable,
		availableViews,
		markChanged,
		boundaryTable,
		branchBases,
		branchTable,
		nodeTable,
		valveTable,
		VIEW_LABELS,
		type ResultsView
	} from '$lib/utils/results';
	import { formatValue } from '$lib/utils/units';
	import {
		missingConcentrationText,
		topologyIssueViews,
		topologySummary,
		type IssueView
	} from '$lib/utils/issue-text';
	import { modelRuleIssues } from '$lib/utils/validate';
	import {
		lapsedChanges,
		overridesOf,
		changeFieldLabel,
		changeTargetLabel
	} from '$lib/utils/scenarios';
	import { scenarioProblems } from '$lib/utils/scenario-problems';
	import type { Override } from '$lib/api/types';
	import CompareView from './CompareView.svelte';
	import ConvergenceStatus from './ConvergenceStatus.svelte';
	import FlagsSummary from './FlagsSummary.svelte';
	import LinksView from './LinksView.svelte';
	import MethodsSummary from './MethodsSummary.svelte';
	import MethodVersionNotice from './MethodVersionNotice.svelte';
	import PumpsView from './PumpsView.svelte';
	import ResultsStateNotice from './ResultsStateNotice.svelte';
	import ResultsTable from './ResultsTable.svelte';
	import ScenarioCard from './ScenarioCard.svelte';
	import SummaryView from './SummaryView.svelte';
	import TraceView from './TraceView.svelte';

	const ws = useWorkspace();
	const id = $props.id();
	const results = $derived(ws.store.results);
	const response = $derived(results.response);
	const solved = $derived(response?.solvedState);
	/** The project has scenarios: results name their case, and Compare cases is offered. */
	const hasScenarios = $derived(ws.scenarios.length > 0);
	const caseId = $derived(ws.store.activeCase);
	const caseName = $derived(ws.caseName(caseId));
	const comparing = $derived(hasScenarios && ws.comparing);
	/** Elements the scenario of these results changed (the server's record). */
	const changed = $derived(
		new Set(
			(response?.scenario?.overrides ?? [])
				.filter((o) => o.state === 'applied')
				.flatMap((o) =>
					o.override.kind === 'component'
						? [o.override.componentId]
						: o.override.kind === 'pipe'
							? [o.override.connectionId]
							: []
				)
		)
	);

	let selectedView = $state<ResultsView>('summary');
	const views = $derived(solved ? availableViews(solved) : []);
	const view = $derived(views.includes(selectedView) ? selectedView : 'summary');

	/** Views rendered so far for this solve: they stay rendered (hidden) when another is shown. */
	let visited = $state<ResultsView[]>([]);
	let visitedFor: unknown = null;
	$effect.pre(() => {
		const current = view;
		const forSolve = solved;
		untrack(() => {
			if (visitedFor !== forSolve) {
				visitedFor = forSolve;
				visited = [current];
			} else if (!visited.includes(current)) {
				visited = [...visited, current];
			}
		});
	});
	const rendered = $derived(views.filter((v) => v === view || visited.includes(v)));

	// Built when first read (a view is shown), then only when the solve, the display units or a
	// name change: ws.labelsProject and ws.displayUnits stay the same across other edits.
	const nodes = $derived(
		solved ? markChanged(nodeTable(ws.labelsProject, solved, ws.displayUnits), changed) : null
	);
	const valves = $derived(
		solved ? markChanged(valveTable(ws.labelsProject, solved, ws.displayUnits), changed) : null
	);
	const branches = $derived(
		solved ? markChanged(branchTable(ws.labelsProject, solved, ws.displayUnits), changed) : null
	);
	const bases = $derived(solved ? branchBases(solved) : new Set());
	const boundaries = $derived(
		solved ? markChanged(boundaryTable(ws.labelsProject, solved, ws.displayUnits), changed) : null
	);
	// The flows as entered come from the case exactly as solved, which changes with the solve.
	const assignedFlows = $derived(
		solved
			? markChanged(
					assignedFlowTable(ws.labelsProject, solved, ws.displayUnits, ws.store.caseInputs()),
					changed
				)
			: null
	);

	const wide = mediaQuery(WIDE_SCREEN);

	const methodChanged = $derived(
		!!solved &&
			!!ws.store.loadedMethodVersion &&
			!!solved.methodVersion &&
			ws.store.loadedMethodVersion !== solved.methodVersion
	);

	function isControlValve(c: Component): c is ControlValve {
		return (
			c.type === 'valve' &&
			(c.valveType === 'prv' || c.valveType === 'psv' || c.valveType === 'fcv')
		);
	}

	/** Problems the solver will report too, found in the browser so they can be fixed first. */
	const inputProblems = $derived.by(() => {
		const project = ws.project;
		const problems: { text: string; componentId?: string; portId?: string }[] = [];
		if (project.components.length && !project.components.some(isBoundary)) {
			// An assigned-flow node fixes a flow, not a pressure (PRD §2.1): it is not that boundary.
			const assigned = project.components.some((c) => c.type === 'assigned_flow');
			problems.push({
				text:
					'The network needs at least one reservoir or reference node (a fixed-pressure boundary).' +
					(assigned ? ' Assigned-flow nodes fix a flow, not a pressure, so they do not count.' : '')
			});
		}
		for (const component of project.components) {
			for (const port of freePorts(project, component.id)) {
				problems.push({
					text: `${portLabel(port.id)} of ${component.name} is not connected or plugged.`,
					componentId: component.id,
					portId: port.id
				});
			}
			// A new control valve starts at setpoint 0, which is rarely what is meant.
			if (isControlValve(component) && component.status === 'active' && component.setpoint === 0) {
				problems.push({
					componentId: component.id,
					text:
						component.valveType === 'fcv'
							? `The flow setpoint of ${component.name} is ${formatValue(0, 'flow', ws.units)}, which shuts the line.`
							: `The pressure setpoint of ${component.name} is ${formatValue(0, 'pressure', ws.units, 4, { gauge: true })}.`
				});
			}
		}
		for (const issue of modelRuleIssues(project, ws.units)) {
			problems.push({
				text: issue.message,
				...(issue.componentId ? { componentId: issue.componentId } : {}),
				...(issue.portId ? { portId: issue.portId } : {})
			});
		}
		return problems;
	});

	/** The scenario shown: its changes that no longer apply, and values its targets reject. */
	const scenarioNotes = $derived.by(() => {
		const scenario = ws.activeScenario;
		if (!scenario) return { lapsed: 0, lapsedText: '', problems: [] as string[] };
		const lapsed = lapsedChanges(ws.store.project, scenario.id);
		const named = lapsed
			.slice(0, 3)
			.map((c) => `${changeTargetLabel(ws.store.project, c.override)}: ${c.message}`)
			.join('; ');
		const problems = scenarioProblems(ws.store.project, scenario.id, ws.units)
			// Model-rule problems of the case are listed above already (they read the case's values).
			.filter((p) => p.index === null || !lapsed.some((c) => c.index === p.index))
			.map((p) => {
				const o = p.index === null ? null : (overridesOf(scenario)[p.index] ?? null);
				return o
					? `The value ${scenario.name} sets for ${changeTargetLabel(ws.store.project, o)} ${changeFieldLabel(ws.store.project, o).toLowerCase()} is not valid: ${p.text}`
					: p.text;
			})
			.filter((text) => !inputProblems.some((i) => i.text === text));
		return {
			lapsed: lapsed.length,
			lapsedText: lapsed.length
				? `${scenario.name} has ${lapsed.length} change${lapsed.length === 1 ? '' : 's'} that no longer appl${lapsed.length === 1 ? 'ies' : 'y'} (${named}${lapsed.length > 3 ? '; …' : ''}).`
				: '',
			problems
		};
	});

	/**
	 * A scenario's invalid value, from a 400's issue location (body.project.scenarios.{s}.overrides
	 * .{j}...: the change that set it, in the project as it was sent), with what is wrong.
	 */
	function scenarioIssue(detail: string): { override: Override; text: string } | null {
		const match = /scenarios\.(\d+)\.overrides\.(\d+)[^:]*:\s*(.*)$/.exec(detail);
		if (!match) return null;
		const sent = ws.store.sentProjectFor(caseId, 'error');
		const override = sent?.scenarios?.[Number(match[1])]?.overrides?.[Number(match[2])];
		return override ? { override, text: match[3] ?? '' } : null;
	}

	/** Remove the active scenario's change of the same value (Reset to base). */
	function resetChange(override: Override) {
		const scenario = ws.activeScenario;
		if (!scenario) return;
		const same = (o: Override) =>
			o.field === override.field &&
			o.kind === override.kind &&
			JSON.stringify([
				(o as { componentId?: string }).componentId,
				(o as { connectionId?: string }).connectionId,
				(o as { pipeIndex?: number }).pipeIndex
			]) ===
				JSON.stringify([
					(override as { componentId?: string }).componentId,
					(override as { connectionId?: string }).connectionId,
					(override as { pipeIndex?: number }).pipeIndex
				]);
		ws.updateStored(
			(draft) => {
				const own = draft.scenarios?.find((s) => s.id === scenario.id);
				if (own) own.overrides = overridesOf(own).filter((o) => !same(o));
			},
			`reset ${changeFieldLabel(ws.store.project, override).toLowerCase()} in ${scenario.name}`
		);
	}

	/** The scenario's changes of the elements a topology issue names (Set by this scenario). */
	function issueChanges(index: number): Override[] {
		const scenario = ws.activeScenario;
		const error = results.error;
		if (!scenario || error?.kind !== 'topology') return [];
		const issue = error.issues[index];
		if (!issue) return [];
		const ids = new Set([...issue.componentIds, ...issue.connectionIds]);
		return overridesOf(scenario).filter(
			(o) =>
				(o.kind === 'component' && ids.has(o.componentId)) ||
				(o.kind === 'pipe' && ids.has(o.connectionId))
		);
	}

	/** The latest solve was of the current project and failed (any response is from before). */
	const failedNow = $derived(!!results.error && !results.errorStale);
	/**
	 * After a failed solve of the current project, results kept from an earlier version of it are
	 * shown only on request, below the error and the notice that says where they are from.
	 */
	let previousShownFor = $state.raw<unknown>(null);
	const previousHidden = $derived(
		failedNow && results.stale && !!response && previousShownFor !== results.error
	);

	/**
	 * A fluid error the browser can tell in the display unit (a glycol with no concentration),
	 * decided from the project as it was when the error arrived: it stays the same, in its own
	 * words, when the project changes afterwards (the error is then marked out of date).
	 */
	let fluidMemo: { error: unknown; text: string | null } = { error: null, text: null };
	const fluidText = $derived.by(() => {
		const error = results.error;
		if (fluidMemo.error !== error) {
			fluidMemo = {
				error,
				text: untrack(() => {
					if (error?.kind !== 'validation' || error.code !== 'FLUID_ERROR') return null;
					if (results.errorStale) return null;
					const fluid = ws.project.fluid;
					const info = fluid.kind === 'builtin' ? ws.library.fluid(fluid.fluidId) : undefined;
					return missingConcentrationText(fluid, info, ws.units);
				})
			};
		}
		return fluidMemo.text;
	});

	/**
	 * The topology issues as people read them (names, open ports), decided like fluidText from
	 * the project as it was when the error arrived.
	 */
	let issuesMemo: { error: unknown; views: IssueView[] } = { error: null, views: [] };
	const issueViews = $derived.by(() => {
		const error = results.error;
		if (issuesMemo.error !== error) {
			issuesMemo = {
				error,
				views:
					error?.kind === 'topology'
						? untrack(() =>
								topologyIssueViews(error.issues, ws.project, !results.errorStale, ws.units)
							)
						: []
			};
		}
		return issuesMemo.views;
	});

	/**
	 * The live status line: short, so a solve's outcome is announced without the lists. It is the
	 * case shown's (Solve all's progress is the case bar's to announce).
	 */
	const status = $derived.by(() => {
		if (results.solving) return 'Solving…';
		const of = hasScenarios ? ` of ${caseName}` : '';
		let last = '';
		if (results.error) last = `no results${results.errorStale ? ', out of date' : ''}`;
		else if (response && solved) {
			const outcome = response.success && solved.converged ? 'converged' : 'did not converge';
			last = `${outcome}${results.stale ? ', out of date' : ''}`;
		}
		// After a cancelled solve, what is shown is from the last solve that finished.
		if (results.cancelled)
			return last ? `Solve cancelled. Last finished solve${of}: ${last}` : 'Solve cancelled';
		return last ? `Last solve${of}: ${last}` : '';
	});

	/** WAI-ARIA tabs: arrow keys, Home and End move between the views. */
	function tabKeydown(event: KeyboardEvent) {
		const index = views.indexOf(view);
		const last = views.length - 1;
		const next =
			event.key === 'ArrowRight'
				? (index + 1) % views.length
				: event.key === 'ArrowLeft'
					? (index + last) % views.length
					: event.key === 'Home'
						? 0
						: event.key === 'End'
							? last
							: -1;
		const target = views[next];
		if (target === undefined) return;
		event.preventDefault();
		selectedView = target;
		document.getElementById(`${id}-tab-${target}`)?.focus();
	}

	const inspected = $derived(solved ? ws.inspected : null);
	/** On wide screens the trace is a panel over the results, which are inert under it. */
	const covered = $derived(!!inspected && wide.current);

	function focusViews() {
		document.getElementById(`${id}-tab-${view}`)?.focus();
	}

	/** Show the case's results or Compare cases, with the focus on that tab. */
	async function showTab(compare: boolean) {
		ws.comparing = compare;
		await tick();
		document.getElementById(`${id}-casetab-${compare ? 'compare' : 'case'}`)?.focus();
	}

	/** A solve in flight, of any case: starting another would cancel it. */
	const busy = $derived(!!ws.store.run || ws.store.solvingCase !== undefined);
</script>

<div class="relative flex h-full min-h-0 flex-col">
	<div
		class="flex min-h-[53px] items-center gap-2 border-b border-slate-200 px-3 py-1 sm:px-4"
		inert={covered}
	>
		<h2 class="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-base font-semibold">
			Results
			{#if hasScenarios}
				<span
					class={[
						'rounded-full px-2 py-0.5 text-xs font-medium break-words',
						caseId === null ? 'bg-slate-200 text-slate-800' : 'bg-teal-700 text-white'
					]}><span class="sr-only">of&nbsp;</span>{caseName}</span
				>
			{/if}
		</h2>
		{#key caseId}<p role="status" class="text-sm text-slate-600">{status}</p>{/key}
	</div>
	{#if hasScenarios}
		<div
			role="tablist"
			aria-label="Results of"
			class="flex border-b border-slate-200 px-3 sm:px-4"
			inert={covered}
		>
			{#each [false, true] as compare (compare)}
				<button
					type="button"
					role="tab"
					id="{id}-casetab-{compare ? 'compare' : 'case'}"
					aria-selected={comparing === compare}
					tabindex={comparing === compare ? 0 : -1}
					class={[
						'-mb-px min-h-11 border-b-2 px-3 text-sm font-medium',
						comparing === compare
							? 'border-teal-700 text-teal-900'
							: 'border-transparent text-slate-600 hover:text-slate-900'
					]}
					onclick={() => (ws.comparing = compare)}
					onkeydown={(event) => {
						if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
							event.preventDefault();
							ws.comparing = !compare;
							document.getElementById(`${id}-casetab-${compare ? 'case' : 'compare'}`)?.focus();
						}
					}}
				>
					{compare ? 'Compare cases' : caseName}
				</button>
			{/each}
		</div>
	{/if}

	<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-4 sm:px-4" inert={covered}>
		{#if comparing}
			<CompareView onshow={() => showTab(false)} />
		{:else}
			{#if hasScenarios && response && !previousHidden}
				<ScenarioCard scenario={response.scenario ?? null} oncompare={() => showTab(true)} />
			{/if}
			{#if ws.project.metadata.description}
				<section
					aria-labelledby="{id}-about"
					class="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
				>
					<h3 id="{id}-about" class="font-medium">About this project</h3>
					<p class="break-words whitespace-pre-line text-slate-700">
						{ws.project.metadata.description}
					</p>
				</section>
			{/if}
			{#if results.cancelled}
				<div
					class="flex items-start gap-2 rounded-md border border-slate-300 bg-slate-50 p-3 text-sm text-slate-800"
				>
					<Icon name="info" class="mt-0.5 size-4 shrink-0" />
					<p class="min-w-0 flex-1">
						{response || results.error
							? 'The solve was cancelled before it finished. What is shown below is from an earlier solve.'
							: 'The solve was cancelled before it finished, so there are no results yet.'}
					</p>
				</div>
			{/if}
			{#if !failedNow}<ResultsStateNotice />{/if}

			{#if results.error}
				<section
					class="space-y-2 rounded-lg border border-red-300 bg-red-50 p-3"
					aria-labelledby="{id}-error"
				>
					<h3 id="{id}-error" class="flex items-center gap-2 font-semibold text-red-900">
						<Icon name="alert" class="size-5" />
						{#if results.error.kind === 'topology'}
							The network cannot be solved yet
						{:else if results.error.kind === 'validation' && results.error.code === 'FLUID_ERROR'}
							The fluid properties cannot be calculated
						{:else if results.error.kind === 'validation'}
							The calculation server rejected the project
						{:else}
							No results
						{/if}
					</h3>
					{#if results.error.kind === 'topology'}
						<p class="text-sm text-red-900">{topologySummary(results.error.issues.length)}</p>
						<ul class="list-disc space-y-1 pl-5 text-sm text-red-900">
							{#each issueViews as issue, i (i)}
								{@const set = results.errorStale ? [] : issueChanges(i)}
								<li>
									{issue.text}
									{#each issue.links as link (link.componentId)}
										<button
											type="button"
											class="ml-1 min-h-11 text-blue-800 underline underline-offset-2"
											onclick={() => ws.show(link.componentId, link.portId)}
											>{componentName(ws.project, link.componentId)}</button
										>
									{/each}
									{#if set.length}
										<span class="block">
											Set by this scenario: {set
												.map(
													(o) =>
														`${changeTargetLabel(ws.store.project, o)} · ${changeFieldLabel(ws.store.project, o).toLowerCase()}`
												)
												.join('; ')}.
											<button
												type="button"
												class="btn btn-quiet px-2 text-blue-800"
												onclick={() => set.forEach(resetChange)}>Reset to base</button
											>
										</span>
									{/if}
								</li>
							{/each}
						</ul>
					{:else if results.error.kind === 'validation'}
						{@const error = results.error}
						{@const details = fluidText ? [] : error.details.filter((d) => d !== error.message)}
						<p class="text-sm text-red-900">{fluidText ?? error.message}</p>
						{#if details.length}
							<ul class="list-disc space-y-1 pl-5 text-sm break-words text-red-900">
								{#each details as detail, i (i)}
									{@const issue = scenarioIssue(detail)}
									{#if issue}
										{@const o = issue.override}
										<li>
											The value {caseName} sets for {changeTargetLabel(ws.store.project, o)}
											{changeFieldLabel(ws.store.project, o).toLowerCase()} is not valid: {issue.text}
											{#if !results.errorStale}
												<span class="inline-flex flex-wrap gap-1">
													{#if o.kind === 'component'}
														<button
															type="button"
															class="btn btn-quiet px-2 text-blue-800"
															onclick={() => ws.show(o.componentId)}>Show</button
														>
													{/if}
													<button
														type="button"
														class="btn btn-quiet px-2 text-blue-800"
														onclick={() => resetChange(o)}>Reset to base</button
													>
												</span>
											{/if}
										</li>
									{:else}
										<li>{detail}</li>
									{/if}
								{/each}
							</ul>
						{/if}
					{:else}
						<p class="text-sm text-red-900">{results.error.message}</p>
					{/if}
				</section>
			{/if}

			{#if failedNow}<ResultsStateNotice />{/if}

			{#if previousHidden}
				<button type="button" class="btn" onclick={() => (previousShownFor = results.error)}>
					<Icon name="right" class="size-4" /> Show the earlier results
				</button>
			{:else if response && solved}
				<ConvergenceStatus {response} />
				{#if methodChanged}
					<MethodVersionNotice
						previous={ws.store.loadedMethodVersion}
						current={solved.methodVersion}
					/>
				{/if}
				<FlagsSummary flags={solved.flags} onskip={focusViews} />
			{:else if !results.error && !results.solving}
				{#if hasScenarios && ws.project.components.length}
					<div class="flex flex-wrap items-center gap-2">
						<p class="min-w-0 flex-1 basis-48 break-words text-slate-700">
							{caseName} has not been solved yet{results.cancelled
								? ' (its solve was cancelled)'
								: ''}.
						</p>
						<!-- The case is named before; a name of up to 100 characters would not fit a phone. -->
						<button
							type="button"
							class="btn btn-primary"
							aria-disabled={busy}
							onclick={() => !busy && void ws.solve()}
						>
							<Icon name="play" class="size-4" /> Solve <span class="sr-only">{caseName}</span>
						</button>
						<button
							type="button"
							class="btn"
							aria-disabled={busy}
							onclick={() => !busy && void ws.solveAll()}
						>
							Solve all
						</button>
					</div>
				{:else if !ws.project.components.length}
					<p class="text-slate-700">
						Add a component in Build to start the network. Then Solve calculates its flows,
						pressures and pump operating points.
					</p>
				{:else if ws.store.loadedMethodVersion}
					<div class="space-y-2">
						<p class="text-slate-700">
							This project was opened without results: a link holds the project's inputs, not its
							results. Press Solve to calculate the flows, pressures and pump operating points (the
							project is sent to the calculation server, which does not keep it).
						</p>
						<button type="button" class="btn btn-primary" onclick={() => void ws.solve()}>
							<Icon name="play" class="size-4" /> Solve now
						</button>
					</div>
				{:else}
					<p class="text-slate-700">
						Press Solve to calculate the flows, pressures and pump operating points of the network.
					</p>
				{/if}
			{/if}

			{#if inputProblems.length || scenarioNotes.lapsed || scenarioNotes.problems.length}
				<section class="space-y-2" aria-labelledby="{id}-input">
					<h3 id="{id}-input" class="section-title">
						Inputs to check ({inputProblems.length +
							scenarioNotes.problems.length +
							(scenarioNotes.lapsed ? 1 : 0)})
					</h3>
					<ul class="space-y-1 text-sm text-slate-700">
						{#if scenarioNotes.lapsedText}
							<li class="flex items-start gap-2">
								<Icon name="alert" class="mt-3 size-4 shrink-0 text-amber-700" />
								<span class="min-w-0 flex-1 py-2.5">{scenarioNotes.lapsedText}</span>
								<button
									type="button"
									class="btn btn-quiet shrink-0 px-2 text-blue-800 underline underline-offset-2"
									onclick={() => {
										ws.managerFocus = caseId;
										ws.managerOpen = true;
									}}>Review</button
								>
							</li>
						{/if}
						{#each scenarioNotes.problems as text, i (i)}
							<li class="flex items-start gap-2">
								<Icon name="alert" class="mt-3 size-4 shrink-0 text-red-700" />
								<span class="min-w-0 flex-1 py-2.5">{text}</span>
							</li>
						{/each}
						{#each inputProblems.slice(0, 50) as problem, i (i)}
							<li class="flex items-start gap-2">
								<Icon name="alert" class="mt-3 size-4 shrink-0 text-amber-700" />
								<span class="min-w-0 flex-1 py-2.5">{problem.text}</span>
								{#if problem.componentId}
									{@const target = problem.componentId}
									<button
										type="button"
										class="btn btn-quiet shrink-0 px-2 text-blue-800 underline underline-offset-2"
										aria-label="Show: {problem.text}"
										onclick={() => ws.show(target, problem.portId)}>Show</button
									>
								{/if}
							</li>
						{/each}
					</ul>
				</section>
			{/if}

			{#if response && solved && !previousHidden}
				<div class="space-y-3">
					<div
						role="tablist"
						aria-label="Results view"
						tabindex="-1"
						class="flex flex-wrap gap-1.5"
						onkeydown={tabKeydown}
					>
						{#each views as v (v)}
							<button
								type="button"
								role="tab"
								id="{id}-tab-{v}"
								aria-selected={view === v}
								aria-controls={rendered.includes(v) ? `${id}-panel-${v}` : undefined}
								tabindex={view === v ? 0 : -1}
								class={[
									'min-h-11 rounded-full border px-3 text-sm font-medium whitespace-nowrap',
									view === v
										? 'border-blue-700 bg-blue-700 text-white'
										: 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100'
								]}
								onclick={() => (selectedView = v)}
							>
								{VIEW_LABELS[v]}
							</button>
						{/each}
					</div>

					{#each rendered as v (v)}
						<div
							id="{id}-panel-{v}"
							role="tabpanel"
							aria-labelledby="{id}-tab-{v}"
							class="space-y-2"
							hidden={v !== view}
						>
							{#if v === 'summary'}
								<SummaryView {solved} />
							{:else if v === 'nodes' && nodes}
								<ResultsTable
									table={nodes}
									caption="Results per component port"
									first="Component, port"
									onselect={(row) => ws.inspect(row.element)}
								/>
								<p class="text-xs text-slate-600">
									Pressure is static pressure; dynamic pressure is ½ρv², and total pressure is their
									sum. Gauge pressure (g) is relative to the atmosphere at the site,
									{formatValue(solved.atmosphericPressure, 'pressure', ws.displayUnits, 4, {
										absolute: true
									})}; absolute (a) is relative to vacuum. Velocity is in the pipe at the port,
									except at reservoir and reference-node ports, which show the boundary's still
									liquid: velocity 0, and HGL equal to EGL. Elevations, HGL and EGL are from the
									project datum.
								</p>
							{:else if v === 'links'}
								<LinksView {solved} {changed} />
							{:else if v === 'pumps'}
								<PumpsView {solved} {changed} />
							{:else if v === 'valves' && valves}
								<ResultsTable
									table={valves}
									caption="Results per valve"
									first="Valve"
									onselect={(row) => ws.inspect(row.element)}
								/>
								<p class="text-xs text-slate-600">
									Flow is positive from the valve's inlet to its outlet. Head loss (the drop in the
									energy grade line) and pressure drop (the static pressure difference) are inlet
									minus outlet, so they are negative when the flow runs from outlet to inlet. K is
									referred to the valve's connected inner diameter. A setpoint is shown for control
									valves.
								</p>
							{:else if v === 'branches' && branches}
								<ResultsTable
									table={branches}
									caption="Results per tee and wye"
									first="Branch"
									onselect={(row) => ws.inspect(row.element)}
								/>
								<div class="space-y-1 text-xs text-slate-600">
									<p>
										Port flows are positive into the fitting. K and loss are per path from the
										combined port to each other port; path loss = K·v²/(2g), with v the velocity K
										is on.
									</p>
									{#if bases.has('combined')}
										<p>
											Crane correlations (combined flow on the run): every K is on the combined-flow
											velocity. A leg with no flow has the K its head implies, on the same velocity.
										</p>
									{/if}
									{#if bases.has('own')}
										<p>
											Darby 3-K fallback (combined flow through a tee's branch, flagged): each run
											path's K is on that leg's own velocity, shown per port.
										</p>
									{/if}
									{#if bases.has('none')}
										<p>
											An ideal junction (loss model "ideal") or a branch without flow has no loss.
										</p>
									{/if}
								</div>
							{:else if v === 'boundaries' && boundaries}
								<ResultsTable
									table={boundaries}
									caption="Results per boundary"
									first="Boundary"
									onselect={(row) => ws.inspect(row.element)}
								/>
							{:else if v === 'assignedFlows' && assignedFlows}
								<ResultsTable
									table={assignedFlows}
									caption="Results per assigned-flow node"
									first="Assigned-flow node"
									onselect={(row) => ws.inspect(row.element)}
								/>
								<p class="text-xs text-slate-600">
									The assigned flow is as entered: a demand leaves the network at the node, a supply
									enters it, whatever the pressure there. Pressure is the static pressure at the
									port, with the velocity in the connected pipe (gauge, relative to the site's
									atmosphere; absolute, relative to vacuum); HGL is from the project datum. An
									absolute pressure below the fluid's vapor pressure is flagged: the liquid would
									flash.
								</p>
							{:else if v === 'methods'}
								<MethodsSummary
									methods={solved.trace.methods}
									projectName={ws.project.metadata.name}
									timestamp={solved.timestamp}
									converged={response.success && solved.converged}
									stale={results.stale}
									{...hasScenarios
										? {
												caseName: response.scenario
													? `scenario ${response.scenario.name} (${response.scenario.id})`
													: 'base case',
												...(response.scenario ? { scenarioName: response.scenario.name } : {})
											}
										: {}}
								/>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		{/if}
		<SiteFooter />
	</div>

	{#if inspected && solved}
		<TraceView element={inspected} {solved} onclose={() => ws.closeInspector()} />
	{/if}
</div>
