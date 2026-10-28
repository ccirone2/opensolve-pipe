<!--
	How one element's results were obtained (GOALS §4.2, design §5): whether the values are
	current and a solution at all, its flags, its result values, and the solver's trace — inputs
	with where each came from (user, default, library, computed), equations, correlations and
	data sources with citations, intermediate values in display units where the unit is known,
	and notes. A connection is headed as it was solved once its results are out of date (from →
	to, utils/results.ts resultsProject), as the Links table names it: its flow's sign, its pipe
	numbers and its trace refer to those ends, even after a reversal since the solve. A side panel
	over the results on wide screens (the results under it are inert while it is open); a dialog
	(bottom sheet) on narrow ones. In a project with scenarios it names the case solved and, for a
	scenario, lists the element's values the scenario changed, with their base values, from the
	server's record (proposal scenario-manager.md §6.11). Use in goal seek, on the Result values
	heading, opens the goal-seek dialog with a new goal on this element (proposal goal-seek.md
	§6.2); on narrow screens the trace, a sheet itself, closes first. A note or data source that
	names a project library entry (CLAUDE.md D21: 'project library pipe spec "…" (PS1)') links to
	it: the library opens with that entry in view (proposal project-library.md §6.4).
-->
<script lang="ts">
	import { onMount, tick } from 'svelte';
	import type { Flag, SolvedState, TraceInput } from '$lib/api/types';
	import { focusCurrentHeading } from '$lib/components/panel/focus';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { componentById, connectionById } from '$lib/utils/graph';
	import { mediaQuery, WIDE_SCREEN } from '$lib/utils/media.svelte';
	import {
		elementDescription,
		elementName,
		flagsForElement,
		resultsProject,
		rowsForElement,
		SEVERITY_LABELS,
		type ElementRef
	} from '$lib/utils/results';
	import { formatQuantity, traceName, traceTextValue } from '$lib/utils/trace';
	import {
		compareElementKind,
		defaultRows,
		ELEMENT_QUANTITIES,
		rowKey,
		type CompareRow
	} from '$lib/utils/compare';
	import { changeFieldLabel, changeValueText } from '$lib/utils/scenarios';
	import { libraryMentions, type LibraryMention } from '$lib/utils/project-library';
	import CellValue from './CellValue.svelte';
	import FlagIcon from './FlagIcon.svelte';
	import ResultsStateNotice from './ResultsStateNotice.svelte';

	interface Props {
		element: ElementRef;
		solved: SolvedState;
		onclose: () => void;
	}

	let { element, solved, onclose }: Props = $props();
	const ws = useWorkspace();
	const id = $props.id();
	const wide = mediaQuery(WIDE_SCREEN);

	const exists = $derived(
		element.kind === 'component'
			? !!componentById(ws.project, element.id)
			: !!connectionById(ws.project, element.id)
	);
	const name = $derived(elementName(ws.labelsProject, element));
	/** The heading: a connection as these results were solved (the ends its values refer to). */
	const title = $derived(
		element.kind === 'connection'
			? elementName(resultsProject(ws.labelsProject, solved), element)
			: name
	);
	const description = $derived(
		exists
			? elementDescription(ws.labelsProject, element)
			: `${element.kind === 'component' ? 'Component' : 'Pipe connection'} · ${element.id} · deleted`
	);
	const trace = $derived(solved.trace.elements[element.id]);
	const flags = $derived(flagsForElement(solved.flags, element));
	/** Physically invalid flags about the whole network (e.g. NOT_CONVERGED): they apply here too. */
	const networkFlags = $derived(
		solved.flags.filter((f) => f.severity === 'invalid' && !f.componentId && !f.connectionId)
	);
	const response = $derived(ws.store.results.response);
	const converged = $derived(
		response?.solvedState === solved ? response.success && solved.converged : solved.converged
	);
	// The case as solved gives the inputs some tables show as entered (an assigned flow).
	const inputs = $derived(
		ws.store.results.response?.solvedState === solved ? ws.store.caseInputs() : null
	);
	const hasScenarios = $derived(ws.scenarios.length > 0);
	/** The scenario these results are of (the server's record; null: the base case). */
	const scenario = $derived(
		ws.store.results.response?.solvedState === solved
			? (ws.store.results.response?.scenario ?? null)
			: null
	);
	/** The element's values the scenario changed, as the server applied them. */
	const changes = $derived(
		(scenario?.overrides ?? []).filter(
			(o) =>
				o.state === 'applied' &&
				(element.kind === 'component'
					? o.override.kind === 'component' && o.override.componentId === element.id
					: o.override.kind === 'pipe' && o.override.connectionId === element.id)
		)
	);
	/** The project as these results were solved, for each change's field and unit. */
	const solvedAs = $derived((scenario ? ws.store.solvedProject : null) ?? ws.labelsProject);
	const changeText = (record: (typeof changes)[number], value: unknown) =>
		changeValueText(solvedAs, record.override, value, ws.displayUnits, {
			materialName: (m) => ws.library.material(m)?.name,
			nominalSizes: ws.library.nominalSizes
		});
	/** A server text in pieces: plain text, and the project library entries it names. */
	function pieces(text: string): { text: string; mention?: LibraryMention }[] {
		const mentions = libraryMentions(text, ws.store.project);
		if (!mentions.length) return [{ text }];
		const parts: { text: string; mention?: LibraryMention }[] = [];
		let at = 0;
		for (const mention of mentions) {
			if (mention.index > at) parts.push({ text: text.slice(at, mention.index) });
			parts.push({ text: text.slice(mention.index, mention.index + mention.length), mention });
			at = mention.index + mention.length;
		}
		if (at < text.length) parts.push({ text: text.slice(at) });
		return parts;
	}

	/** "Liquid level", or for a pipe "Pipe 2 length": a connection may have several pipes. */
	const changeLabel = (record: (typeof changes)[number]) => {
		const label = changeFieldLabel(solvedAs, record.override);
		return record.override.kind === 'pipe'
			? `Pipe ${record.override.pipeIndex + 1} ${label.toLowerCase()}`
			: label;
	};

	/**
	 * Open goal seek with a new goal on this element. On phones the trace, a sheet itself, closes
	 * first (modals are never stacked), and the Results pane's Goal seek button is the dialog's
	 * opener: closing the dialog gives it the focus.
	 */
	async function useInGoalSeek() {
		const target = element; // read before closing: closing clears the inspected element
		if (!wide.current) {
			ws.closeInspector();
			await tick();
			document.querySelector<HTMLElement>('[data-goal-seek-button]')?.focus();
		}
		ws.openGoalSeek(target);
	}

	/** Add this element's main results to Compare cases. */
	function addToComparison() {
		const component = element.kind === 'component' ? componentById(ws.project, element.id) : null;
		const kind =
			element.kind === 'connection'
				? 'connection'
				: component
					? compareElementKind(component)
					: null;
		const quantities = kind ? ELEMENT_QUANTITIES[kind].slice(0, 2) : [];
		if (!quantities.length && component?.ports[0]) {
			quantities.push('portPressure');
		}
		const rows: CompareRow[] = quantities.map((quantity) => ({
			quantity,
			elementId: element.id,
			...(quantity === 'portPressure' && component?.ports[0]
				? { portId: component.ports[0].id }
				: {})
		}));
		// The rows shown now: the chosen ones, else the defaults (as Compare cases derives them,
		// from the stored project: they depend on the scenarios, which labelsProject does not
		// follow).
		const current =
			ws.compareRows ??
			defaultRows(
				ws.store.project,
				ws.store.caseIds.map((c) => ws.store.resultsFor(c).response?.solvedState ?? null)
			);
		const known = new Set(current.map(rowKey));
		ws.compareRows = [...current, ...rows.filter((r) => !known.has(rowKey(r)))];
		ws.notify('info', `${name} added to Compare cases.`);
	}
	const results = $derived(
		rowsForElement(ws.labelsProject, solved, ws.displayUnits, element, inputs)
	);

	const SOURCE_LABELS: Record<TraceInput['source'], string> = {
		user: 'User',
		default: 'Default',
		library: 'Library',
		computed: 'Computed'
	};
	const SOURCE_STYLES: Record<TraceInput['source'], string> = {
		user: 'border-blue-300 bg-blue-50 text-blue-900',
		default: 'border-slate-300 bg-slate-100 text-slate-800',
		library: 'border-emerald-300 bg-emerald-50 text-emerald-900',
		computed: 'border-violet-300 bg-violet-50 text-violet-900'
	};

	/** Point the navigator at the element, show Build, and move focus to what it shows. */
	function showInBuild() {
		const target = element; // read before closing: closing clears the inspected element
		ws.showElement(target);
		onclose();
		void focusCurrentHeading();
	}

	// Side panel: focus its heading when it opens, give focus back when it closes.
	let heading: HTMLHeadingElement | undefined = $state();
	onMount(() => {
		if (!wide.current) return;
		const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		heading?.focus();
		return () => {
			if (opener?.isConnected && opener.checkVisibility?.() !== false) opener.focus();
		};
	});

	function keydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.preventDefault();
			onclose();
		}
	}
</script>

{#snippet linked(text: string)}
	{#each pieces(text) as piece, i (i)}{#if piece.mention}{@const m = piece.mention}<button
				type="button"
				class="inline text-left break-words text-blue-800 underline underline-offset-2"
				title="Show it in the project library"
				onclick={() => ws.openLibrary({ list: m.list, show: m.id })}>{piece.text}</button
			>{:else}{piece.text}{/if}{/each}
{/snippet}

{#snippet sectionTitle(text: string, sid: string)}
	<h3 id="{id}-{sid}" class="section-title">{text}</h3>
{/snippet}

{#snippet flagItem(flag: Flag)}
	{@const text = ws.flagText(flag)}
	<li
		class={[
			'flex items-start gap-2 rounded-md border p-2',
			flag.severity === 'invalid'
				? 'border-red-300 bg-red-50'
				: flag.severity === 'warning'
					? 'border-amber-300 bg-amber-50'
					: 'border-slate-200 bg-white'
		]}
	>
		<FlagIcon severity={flag.severity} class="mt-0.5 size-4" />
		<span class="min-w-0 flex-1 break-words">
			<span class="font-medium">{SEVERITY_LABELS[flag.severity]}:</span>
			{text}
			{#if text !== flag.message}
				<span class="mt-1 block text-xs text-slate-600">
					Calculation server's message: {flag.message}
				</span>
			{/if}
		</span>
	</li>
{/snippet}

{#snippet caseChip()}
	{#if hasScenarios}
		<span
			class={[
				'ml-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium',
				scenario ? 'bg-teal-700 text-white' : 'bg-slate-200 text-slate-800'
			]}>{scenario ? `Scenario ${scenario.name}` : 'Base case'}</span
		>
	{/if}
{/snippet}

{#snippet body()}
	<div class="space-y-5 text-sm">
		{#if changes.length}
			<section
				class="space-y-1 rounded-md border border-l-4 border-teal-600 bg-teal-50 p-3 text-teal-950"
				aria-labelledby="{id}-changed"
			>
				<h3 id="{id}-changed" class="section-title text-teal-950">Changed by this scenario</h3>
				<ul class="list-disc space-y-1 pl-5">
					{#each changes as record (record.index)}
						<li class="break-words">
							{changeLabel(record)}:
							<strong>{changeText(record, record.value)}</strong>
							(base: {changeText(record, record.baseValue)})
						</li>
					{/each}
				</ul>
			</section>
		{/if}
		{#if !exists || !converged || ws.store.results.stale || ws.store.results.error}
			<div class="space-y-2">
				{#if !exists}
					<p class="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-900">
						{element.id} is no longer in the project: it was deleted after this solve. These are the values
						it had in that solve.
					</p>
				{/if}
				{#if !converged}
					<p
						class="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 p-3 font-medium text-red-900"
					>
						<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
						<span>
							This solve did not converge. The values below are from the last iteration: they are
							not a solution of the network. Do not use them.
						</span>
					</p>
				{/if}
				<ResultsStateNotice values />
			</div>
		{/if}

		{#if flags.length || networkFlags.length}
			<section class="space-y-2" aria-labelledby="{id}-flags">
				{@render sectionTitle(`Flags (${flags.length + networkFlags.length})`, 'flags')}
				<ul class="space-y-2">
					{#each flags as flag, i (i)}
						{@render flagItem(flag)}
					{/each}
				</ul>
				{#if networkFlags.length}
					<p class="text-xs font-medium text-slate-600">About the whole network:</p>
					<ul class="space-y-2">
						{#each networkFlags as flag, i (i)}
							{@render flagItem(flag)}
						{/each}
					</ul>
				{/if}
			</section>
		{/if}

		{#if results.length}
			<section class="space-y-2" aria-labelledby="{id}-results">
				<div class="flex flex-wrap items-center justify-between gap-2">
					{@render sectionTitle('Result values', 'results')}
					{#if exists}
						<button
							type="button"
							class="btn btn-quiet px-2 text-blue-800"
							aria-label="Use a result of {name} in goal seek"
							onclick={useInGoalSeek}>Use in goal seek</button
						>
					{/if}
				</div>
				{#each results as group (group.title)}
					{#each group.rows as row (row.key)}
						<div class="rounded-md border border-slate-200 bg-white p-2">
							{#if group.rows.length > 1 || group.title === 'Ports'}
								<h4 class="mb-1 font-medium">
									{group.title === 'Ports' ? row.detail : group.title}
								</h4>
							{/if}
							<dl class="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
								{#each group.table.columns as column (column.key)}
									{@const cell = row.cells[column.key] ?? '—'}
									<div class={['min-w-0', column.wrap && 'col-span-full']}>
										<dt class="text-xs text-slate-600">
											{column.label}{#if column.unit}&nbsp;({column.unit}){/if}
										</dt>
										<dd class={['break-words', column.numeric && 'tabular-nums']}>
											<CellValue {cell} />
										</dd>
									</div>
								{/each}
							</dl>
						</div>
					{/each}
				{/each}
			</section>
		{/if}

		{#if trace}
			{#if trace.inputs.length}
				<section class="space-y-2" aria-labelledby="{id}-inputs">
					{@render sectionTitle('Inputs', 'inputs')}
					<ul class="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">
						{#each trace.inputs as input, i (i)}
							{@const q = formatQuantity(
								input.name,
								typeof input.value === 'string'
									? traceTextValue(input.value, ws.labelsProject)
									: input.value,
								input.unit,
								ws.displayUnits
							)}
							<li class="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-2 py-1.5">
								<span class="min-w-0 flex-1 basis-40 break-words text-slate-700"
									>{traceName(input.name, ws.labelsProject, element.id)}</span
								>
								<span class="tabular-nums">
									{q.text}
									{#if q.si}<span class="text-xs text-slate-500">({q.si})</span>{/if}
								</span>
								<span
									class={[
										'rounded-full border px-1.5 py-0.5 text-xs font-medium',
										SOURCE_STYLES[input.source]
									]}>{SOURCE_LABELS[input.source] ?? input.source}</span
								>
							</li>
						{/each}
					</ul>
				</section>
			{/if}

			{#if trace.equations.length}
				<section class="space-y-2" aria-labelledby="{id}-equations">
					{@render sectionTitle('Equations', 'equations')}
					<ul class="space-y-1">
						{#each trace.equations as equation, i (i)}
							<li>
								<code
									class="block rounded-md bg-slate-100 px-2 py-1 font-mono text-xs break-words whitespace-pre-wrap"
									>{equation}</code
								>
							</li>
						{/each}
					</ul>
				</section>
			{/if}

			{#if trace.correlations.length}
				<section class="space-y-2" aria-labelledby="{id}-correlations">
					{@render sectionTitle('Correlations', 'correlations')}
					<ul class="space-y-2">
						{#each trace.correlations as reference, i (i)}
							<li>
								<p class="font-medium">{reference.name}</p>
								<p class="text-xs break-words text-slate-700">{reference.citation}</p>
							</li>
						{/each}
					</ul>
				</section>
			{/if}

			{#if trace.dataSources.length}
				<section class="space-y-2" aria-labelledby="{id}-sources">
					{@render sectionTitle('Data sources', 'sources')}
					<ul class="space-y-2">
						{#each trace.dataSources as reference, i (i)}
							<li>
								<p class="font-medium">{reference.name}</p>
								<p class="text-xs break-words text-slate-700">
									{@render linked(reference.citation)}
								</p>
							</li>
						{/each}
					</ul>
				</section>
			{/if}

			{#if trace.intermediates.length}
				<section class="space-y-2" aria-labelledby="{id}-intermediates">
					{@render sectionTitle('Intermediate values', 'intermediates')}
					<dl class="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">
						{#each trace.intermediates as value, i (i)}
							{@const q = formatQuantity(value.name, value.value, value.unit, ws.displayUnits)}
							<div class="flex flex-wrap items-baseline gap-x-2 px-2 py-1.5">
								<dt class="min-w-0 flex-1 basis-40 break-words text-slate-700">
									{traceName(value.name, ws.labelsProject, element.id)}
								</dt>
								<dd class="tabular-nums">
									{q.text}
									{#if q.si}<span class="text-xs text-slate-500">({q.si})</span>{/if}
								</dd>
							</div>
						{/each}
					</dl>
				</section>
			{/if}

			{#if trace.notes.length}
				<section class="space-y-2" aria-labelledby="{id}-notes">
					{@render sectionTitle('Notes', 'notes')}
					<ul class="list-disc space-y-1 pl-5">
						{#each trace.notes as note, i (i)}
							<li class="break-words">{@render linked(note)}</li>
						{/each}
					</ul>
				</section>
			{/if}
		{:else}
			<p class="rounded-md border border-slate-200 bg-slate-50 p-2 text-slate-700">
				This solve did not return a calculation trace for this element. The methods summary
				(Methods) describes how every element is calculated.
			</p>
		{/if}
	</div>
{/snippet}

{#if wide.current}
	<!-- A region over the results (not an <aside>: it sits inside the Results region). -->
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		role="region"
		aria-labelledby="{id}-title"
		class="absolute inset-0 z-40 flex flex-col border-l border-slate-200 bg-white shadow-xl"
		onkeydown={keydown}
	>
		<div class="flex items-start gap-2 border-b border-slate-200 py-1 pr-1 pl-4">
			<div class="min-w-0 flex-1 py-2">
				<h2
					bind:this={heading}
					id="{id}-title"
					tabindex="-1"
					class="text-base font-semibold break-words"
				>
					{title}
				</h2>
				<p class="text-xs break-words text-slate-600">{description}{@render caseChip()}</p>
			</div>
			{#if exists && hasScenarios}
				<button
					type="button"
					class="btn btn-quiet shrink-0 px-2 text-blue-800"
					onclick={addToComparison}
				>
					Add to comparison
				</button>
			{/if}
			{#if exists}
				<button
					type="button"
					class="btn btn-quiet shrink-0 px-2 text-blue-800"
					onclick={showInBuild}
				>
					Show in Build
				</button>
			{/if}
			<button type="button" class="btn btn-quiet btn-icon" aria-label="Close" onclick={onclose}>
				<Icon name="close" />
			</button>
		</div>
		<div class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
			{@render body()}
		</div>
	</div>
{:else}
	<Dialog {title} {onclose} wide>
		<p class="-mt-2 mb-3 text-xs break-words text-slate-600">
			{description}{@render caseChip()}
		</p>
		{#if exists && hasScenarios}
			<button
				type="button"
				class="btn btn-quiet -mt-2 mb-2 px-2 text-blue-800"
				onclick={addToComparison}
			>
				Add to comparison
			</button>
		{/if}
		{@render body()}
		{#snippet footer()}
			{#if exists}
				<button type="button" class="btn" onclick={showInBuild}>Show in Build</button>
			{:else}
				<button type="button" class="btn" onclick={onclose}>Close</button>
			{/if}
		{/snippet}
	</Dialog>
{/if}
