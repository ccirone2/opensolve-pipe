<!--
	Compare cases (proposal scenario-manager.md §6.12): chosen results of each case side by side,
	the base case first, with each scenario's difference from it under its value. Each column's
	header switches to its case and says where its results stand; a row's header opens that
	element's trace. A table from 30 rem of width (its first column sticks, the table scrolls
	sideways in its own box); below that, one card per row, with no sideways scrolling. Values come
	from each case's last solve (utils/compare.ts); a case that did not converge shows none, nor does
	one whose latest solve of the project failed or that a stopped run did not reach (what it had is
	from an earlier project), and values that are out of date are tinted. A row's header opens a
	trace only when the case shown has results (the trace is that case's). Solve all's progress is
	announced by the case bar alone.
-->
<script lang="ts">
	import Icon from '$lib/components/ui/Icon.svelte';
	import CaseStatusChip, {
		CASE_STATUS_LABELS
	} from '$lib/components/workspace/CaseStatusChip.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import {
		compareCells,
		defaultRows,
		rowElement,
		rowKey,
		rowLabel,
		rowUnit,
		type CompareColumn
	} from '$lib/utils/compare';
	import type { ElementRef } from '$lib/utils/results';
	import { calculatingReason } from '$lib/utils/goal-seek';
	import type { CaseId } from '$lib/utils/scenarios';
	import CompareRowsDialog from './CompareRowsDialog.svelte';

	/** Show a case's results (a column header was used): the owner shows them and moves the focus. */
	let { onshow }: { onshow?: (caseId: CaseId) => void } = $props();
	const ws = useWorkspace();
	const store = ws.store;
	const id = $props.id();
	let choosing = $state(false);

	const cases = $derived(store.caseIds);
	const statuses = $derived(cases.map((c) => store.caseStatus(c)));
	const columns = $derived(
		cases.map((caseId, i): CompareColumn & { caseId: CaseId; stale: boolean } => {
			const results = store.resultsFor(caseId);
			// Failed or not reached: a response kept is from an earlier version of the project.
			const none = statuses[i] === 'failed' || statuses[i] === 'not_reached';
			const response = none ? null : results.response;
			return {
				caseId,
				solved: response?.solvedState ?? null,
				converged: !!response && response.success && response.solvedState.converged,
				stale: !!response && results.stale
			};
		})
	);
	// The defaults depend on the scenarios: from the stored project (labelsProject does not follow
	// them).
	const rows = $derived(
		ws.compareRows ??
			defaultRows(
				store.project,
				columns.map((c) => c.solved)
			)
	);
	/** What Solve all solves now, and the cases it skips (an error of their own to fix first). */
	const toSolve = $derived(store.casesToSolve());
	const errors = $derived(store.casesWithErrors());
	const anyResults = $derived(columns.some((c) => c.solved));
	/** The case shown has results: a row's header opens that element's trace in them. */
	const traces = $derived(!!store.results.response);
	const table = $derived(
		rows.map((row) => ({
			row,
			key: rowKey(row),
			label: rowLabel(ws.labelsProject, row),
			unit: rowUnit(row, ws.displayUnits),
			element: rowElement(ws.labelsProject, row),
			cells: compareCells(row, columns, ws.labelsProject, ws.displayUnits)
		}))
	);
	const run = $derived(store.run);
	const progress = $derived(
		run
			? `Solving ${run.index + 1} of ${run.cases.length}: ${ws.caseName(run.cases[run.index] ?? null)}…`
			: ''
	);
	/** A request in flight (a solve, Solve all, a goal seek): one at a time. */
	const busyReason = $derived(calculatingReason(store.calculating, 'solve'));
	const canRun = $derived(!busyReason && toSolve.length > 0);

	/** "Winter", "Winter and Peak", "Winter, Peak and Night". */
	function names(list: readonly CaseId[]): string {
		const all = list.map((c) => ws.caseName(c));
		return all.length < 2 ? (all[0] ?? '') : `${all.slice(0, -1).join(', ')} and ${all.at(-1)}`;
	}

	function solveAll() {
		if (canRun) void ws.solveAll();
	}

	function show(caseId: CaseId) {
		ws.setCase(caseId);
		if (onshow) onshow(caseId);
		else ws.comparing = false;
	}

	function inspect(element: ElementRef) {
		if (traces) ws.inspect(element);
	}

	/** What a column header says about the case's results (the chip's words), for its cells. */
	const noValues = (i: number) =>
		statuses[i] === 'not_converged'
			? 'Did not converge: no values shown'
			: CASE_STATUS_LABELS[statuses[i] ?? 'not_solved'];
</script>

<section class="space-y-3" aria-labelledby="{id}-title">
	<div class="flex flex-wrap items-start gap-2">
		<div class="min-w-0 flex-1 basis-56">
			<h3 id="{id}-title" class="font-semibold">Compare cases</h3>
			<p class="text-sm text-slate-700">
				Chosen results of each case side by side. Under each scenario value is its difference from
				the base case.
			</p>
		</div>
		<div class="flex flex-wrap gap-2">
			<button type="button" class="btn" onclick={() => (choosing = true)}>Choose results…</button>
			<button
				type="button"
				class="btn"
				aria-disabled={!canRun}
				aria-describedby={busyReason ? `${id}-busy` : undefined}
				title={busyReason || undefined}
				onclick={solveAll}
			>
				<Icon name="play" class="size-4" /> Solve all
			</button>
			{#if busyReason}<span id="{id}-busy" class="sr-only">{busyReason}</span>{/if}
		</div>
	</div>
	<!-- Not a live region: the case bar announces the run's progress. -->
	<p class="text-sm text-slate-700 empty:hidden">{progress}</p>
	{#if toSolve.length && !run}
		<p
			class="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900"
		>
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
			<span
				>{toSolve.length} of {cases.length} cases have results that are missing or out of date. Solve
				all solves them, one after another.</span
			>
		</p>
	{/if}
	{#if errors.length && !run}
		<p
			class="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 p-2 text-sm text-red-900"
		>
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
			<span class="min-w-0 break-words"
				>{names(errors)} failed with an error to fix first: Solve all skips {errors.length === 1
					? 'it until its'
					: 'them until their'} inputs change.</span
			>
		</p>
	{/if}
	{#if !traces}
		<span id="{id}-notrace" class="sr-only"
			>Solve {ws.caseName(store.activeCase)} to open its traces.</span
		>
	{/if}

	{#if !anyResults}
		<div class="flex flex-wrap items-center gap-2 text-sm">
			<p class="text-slate-700">No case has results yet.</p>
			<button
				type="button"
				class="btn btn-primary"
				aria-disabled={!canRun}
				aria-describedby={busyReason ? `${id}-busy` : undefined}
				title={busyReason || undefined}
				onclick={solveAll}
			>
				<Icon name="play" class="size-4" /> Solve all
			</button>
		</div>
	{:else}
		<div class="@container">
			<!-- Wide: a table that scrolls sideways in its own box, its row headers sticking. -->
			<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
			<div
				class="hidden max-h-[70vh] overflow-auto rounded-md border border-slate-200 bg-white @min-[28rem]:block"
				role="region"
				aria-labelledby="{id}-caption"
				tabindex="0"
			>
				<table class="w-full text-sm">
					<caption id="{id}-caption" class="sr-only">Results by case</caption>
					<thead class="sticky top-0 z-10 bg-slate-50">
						<tr>
							<th
								scope="col"
								class="sticky left-0 z-20 min-w-36 border-r border-slate-200 bg-slate-50 px-2 py-1 text-left font-medium"
								>Result</th
							>
							{#each cases as caseId, i (caseId ?? '')}
								<th scope="col" class="min-w-28 px-2 py-1 text-right align-top font-medium">
									<button
										type="button"
										class="text-right text-blue-800 underline underline-offset-2"
										onclick={() => show(caseId)}>{ws.caseName(caseId)}</button
									>
									<div class="mt-1">
										<CaseStatusChip status={statuses[i] ?? 'not_solved'} short />
									</div>
								</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each table as line (line.key)}
							<tr class="border-t border-slate-100">
								<th
									scope="row"
									class="sticky left-0 border-r border-slate-200 bg-white px-2 py-1 text-left font-normal"
								>
									{#if line.element}
										{@const element = line.element}
										<button
											type="button"
											class="text-left text-blue-800 underline underline-offset-2"
											aria-disabled={!traces}
											aria-describedby={traces ? undefined : `${id}-notrace`}
											onclick={() => inspect(element)}>{line.label}</button
										>
									{:else}
										{line.label}
									{/if}
									{#if line.unit}<span class="text-slate-600"> ({line.unit})</span>{/if}
								</th>
								{#each line.cells as cell, i (i)}
									<td
										class={[
											'px-2 py-1 text-right align-top tabular-nums',
											columns[i]?.stale && 'bg-amber-50/60'
										]}
										title={cell.text === '—' ? noValues(i) : undefined}
									>
										<span class="inline-flex items-center gap-1">
											{#if cell.invalid}
												<Icon name="alert" class="size-3.5 text-red-700" /><span class="sr-only"
													>physically invalid:</span
												>
											{/if}
											{cell.text}
										</span>
										{#if cell.where}<span class="block text-xs text-slate-600">{cell.where}</span
											>{/if}
										{#if cell.diff}
											<span
												class={[
													'block text-xs',
													cell.diff.same ? 'text-slate-500' : 'text-slate-700'
												]}
												title={cell.diff.title}
												><span class="sr-only">difference from base </span>{cell.diff.text}</span
											>
										{:else if cell.baseText}
											<span class="block text-xs text-slate-600">base: {cell.baseText}</span>
										{/if}
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<!-- Narrow: one card per result. -->
			<div class="space-y-2 @min-[28rem]:hidden">
				{#each table as line (line.key)}
					<section class="card p-2" aria-labelledby="{id}-{line.key.replace(/\W/g, '_')}">
						<h4 id="{id}-{line.key.replace(/\W/g, '_')}" class="text-sm font-medium">
							{#if line.element}
								{@const element = line.element}
								<button
									type="button"
									class="text-left text-blue-800 underline underline-offset-2"
									aria-disabled={!traces}
									aria-describedby={traces ? undefined : `${id}-notrace`}
									onclick={() => inspect(element)}>{line.label}</button
								>
							{:else}
								{line.label}
							{/if}
							{#if line.unit}<span class="font-normal text-slate-600"> ({line.unit})</span>{/if}
						</h4>
						<dl class="mt-1 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-sm">
							{#each line.cells as cell, i (i)}
								<dt class="min-w-0 break-words text-slate-700">
									{ws.caseName(cases[i] ?? null)}
									{#if statuses[i] !== 'solved'}<span class="text-xs text-slate-500">
											({CASE_STATUS_LABELS[statuses[i] ?? 'not_solved'].toLowerCase()})</span
										>{/if}
								</dt>
								<dd class="text-right tabular-nums">
									<span class="inline-flex items-center gap-1">
										{#if cell.invalid}
											<Icon name="alert" class="size-3.5 text-red-700" /><span class="sr-only"
												>physically invalid:</span
											>
										{/if}
										{cell.text}
									</span>
									{#if cell.where}<span class="block text-xs text-slate-600">{cell.where}</span
										>{/if}
									{#if cell.diff}
										<span class="block text-xs text-slate-700" title={cell.diff.title}
											><span class="sr-only">difference from base </span>{cell.diff.text}</span
										>
									{:else if cell.baseText}
										<span class="block text-xs text-slate-600">base: {cell.baseText}</span>
									{/if}
								</dd>
							{/each}
						</dl>
					</section>
				{/each}
			</div>
		</div>
		<p class="text-xs text-slate-600">
			Differences are the scenario's value minus the base case's, in the units shown; “Same” means
			the values agree to the precision shown. A relative difference is given for flows, velocities,
			pump heads, head losses, power and speed only. Values are from each case's last solve; a case
			that did not converge shows none.
		</p>
	{/if}
</section>

{#if choosing}
	<CompareRowsDialog {rows} onclose={() => (choosing = false)} />
{/if}
