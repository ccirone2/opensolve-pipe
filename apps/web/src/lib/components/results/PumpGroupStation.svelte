<!--
	The Pumps together card's first section, "Station" (proposal pumps-results-layout.md §5.3, §9
	S2, S3): its answer first, then the group table. Presentation only: PumpGroupChart gives every
	value and PumpsView makes every request (CLAUDE.md D21).

	- The group curve's line (§5.3 Station, moved here from the figure, since the station's shares
	  and losses wait for it as the chart does): an always-present polite line, never role=status,
	  drawn empty before its first progress (two frames, §7 Live regions), its mark at its first
	  line, with its Cancel, Try again or Compute after it and described by it; the focus handovers
	  between them as before, the group chart's figure the fallback. While the curve is pending,
	  the sentence saying the shares and losses come with it.
	- The refusal, in words with the elements named and linked, each with the server's sentence.
	- The station's answer, the dl "The station" at 14 px with the values in bold.
	- The group table, a ResultsTable since S6a (§9 S6a; the owner's table rules, build-density.md
	  §14 to §18): sort by any column, Fields, Flagged only, a list below 640 px. A row per member,
	  its name with its slot symbol and a trace button, wrapping at 12 rem; for a flagged member a
	  flag line under its row at the box's visible width, each flag's pill (its icon and severity
	  word, flagTone's tint) followed by its text, read once and named by its pump (FlagLine, which
	  reads no workspace, in place of ResultsTable's FlagBadge), after the pump's values on a phone.
	  Its title is visible and names the box, a region and a Tab stop (§15 item 92).
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import type { Flag, TopologyIssue } from '$lib/api/types';
	import type { GroupNotes, GroupTable } from '$lib/utils/pump-group-chart';
	import { wordsText, type Words } from '$lib/utils/pump-groups';
	import type { Row, Table } from '$lib/utils/results';
	import { flagSeverities, sectionMark } from '$lib/utils/section-nav';
	import Icon from '$lib/components/ui/Icon.svelte';
	import FlagLine from './FlagLine.svelte';
	import IssueDetail from './IssueDetail.svelte';
	import ResultsTable from './ResultsTable.svelte';
	import { registerSection } from './section-nav.svelte';

	interface Props {
		/** The group table (groupTable): its columns, a row per member and the station's footer. */
		table: GroupTable;
		/** The case shown, in a project with scenarios: named in the table's caption. */
		caseName?: string;
		/** Open an element's results and trace. */
		oninspect?: (componentId: string) => void;
		/** A flag's words (names, display units). */
		flagText: (flag: Flag) => string;
		/** The shares and losses wait for the group curve: say so. */
		sharesPending?: boolean;
		/** The group curve's state as the notes tell it (groupNotes' `curve`). */
		curve?: GroupNotes['curve'];
		/** Why the pumps are not a station, or their group curve not defined, in words. */
		refusals?: readonly { issue: TopologyIssue; words: Words }[];
		/** Refused only for an active PRV or PSV inside: a station, its group curve not defined. */
		undefinedThere?: boolean;
		/** The group curve is being computed. */
		loading?: boolean;
		/** Compute it again (after a failure or a cancellation). */
		onretry?: () => void;
		/** Cancel it while it is computed. */
		oncancel?: () => void;
		/** The group chart's figure: the focus falls back to it, as it did when the line was there. */
		figure?: HTMLElement;
	}

	let {
		table,
		caseName,
		oninspect,
		flagText,
		sharesPending = false,
		curve = null,
		refusals = [],
		undefinedThere = false,
		loading = false,
		onretry,
		oncancel,
		figure
	}: Props = $props();
	const id = $props.id();

	/**
	 * The section nav's "Station" (§5.4): its mark, the members' worst flag in this table, else
	 * the refusal or the group curve's failed request, both drawn here since S3.
	 */
	let heading: HTMLElement | undefined = $state();
	registerSection(
		'station',
		() => heading,
		() =>
			sectionMark({
				...flagSeverities(table.rows.flatMap((row) => row.flags)),
				refused: curve?.kind === 'refused',
				failed: curve?.kind === 'error'
			})
	);

	/** The group curve's request: being computed, failed or cancelled (not computed). */
	const request = $derived(
		curve?.kind === 'loading' || curve?.kind === 'error' || curve?.kind === 'cancelled'
			? curve
			: null
	);
	/**
	 * The live line is drawn empty before its progress is said (§7 Live regions, F17; S1's rule,
	 * §15 item 24): the card mounts this section in the flush that asks for the group curve (the
	 * card opened), and a polite line inserted already holding its words is not announced. Two
	 * frames: the first one's callbacks run before it draws the empty line.
	 */
	let lineDrawn = $state(false);
	$effect(() => {
		let frame = requestAnimationFrame(() => {
			frame = requestAnimationFrame(() => (lineDrawn = true));
		});
		return () => cancelAnimationFrame(frame);
	});
	/** What the line says: its progress once the line has been drawn empty. */
	const line = $derived(request?.kind === 'loading' && !lineDrawn ? null : request);

	let cancelButton: HTMLButtonElement | undefined = $state();
	let retryButton: HTMLButtonElement | undefined = $state();
	// From Cancel to the button that computes the curve again (or the figure), and back.
	$effect.pre(() => {
		if (loading) return;
		const cancel = untrack(() => cancelButton);
		if (!cancel || document.activeElement !== cancel) return;
		void tick().then(() => (retryButton ?? figure)?.focus());
	});
	$effect.pre(() => {
		if (!loading) return;
		const retry = untrack(() => retryButton);
		if (!retry || document.activeElement !== retry) return;
		void tick().then(() => (cancelButton ?? figure)?.focus());
	});

	/**
	 * The group table as a results table (§9 S6a): a row per member in the table's order, keyed
	 * by its id; its slot (the chart's colour and marker) kept beside the name by the name's
	 * snippet. The title names the case shown, in a project with scenarios.
	 */
	const title = $derived(`The pumps in the group${caseName ? `, ${caseName}` : ''}`);
	const resultsTable = $derived<Table>({
		columns: table.columns,
		rows: table.rows.map((row): Row => ({
			key: row.id,
			element: { kind: 'component', id: row.id },
			name: row.name,
			detail: '',
			cells: row.cells,
			flags: [...row.flags]
		}))
	});
	const slots = $derived(new Map(table.rows.map((row) => [row.id, row.style])));
</script>

{#snippet words(list: Words)}
	{#each list as word, i (i)}{#if typeof word === 'string'}{word}{:else if oninspect}<button
				type="button"
				class="inline min-h-0 px-0.5 text-blue-800 underline underline-offset-2"
				onclick={() => oninspect(word.id)}>{word.name}</button
			>{:else}{word.name}{/if}{/each}
{/snippet}

<!-- A member's name (§5.3 Station; ui-guide, a button holding a name): its slot symbol, not
	underlined, in a column of its own (1 rem, as the members' grid reserves), so every name starts
	at one edge whatever the symbol's width; then its name, a trace button when one can open. Its
	own width its one line up to 12 rem, so the column is that wide and a long name wraps inside it
	(the table's overflow would otherwise give it its longest word). Below 640 px, a list (§5.5), it
	takes the line's width and wraps anywhere, a name with no space too. -->
{#snippet memberName(row: Row)}
	{@const slot = slots.get(row.key)}
	{#if oninspect}
		<button
			type="button"
			class="flex min-h-11 w-max max-w-48 items-center gap-1 px-1 text-left font-medium wrap-break-word text-blue-800 underline underline-offset-2 max-sm:w-auto max-sm:max-w-none max-sm:wrap-anywhere"
			onclick={() => oninspect(row.element.id)}
		>
			<span
				aria-hidden="true"
				class="w-4 shrink-0 text-center no-underline"
				style:color={slot?.color}>{slot?.symbol}</span
			><span class="min-w-0">{row.name}</span>
		</button>
	{:else}
		<span
			class="flex min-h-11 w-max max-w-48 items-center gap-1 px-1 font-medium wrap-break-word max-sm:w-auto max-sm:max-w-none max-sm:wrap-anywhere"
			><span aria-hidden="true" class="w-4 shrink-0 text-center" style:color={slot?.color}
				>{slot?.symbol}</span
			><span class="min-w-0">{row.name}</span></span
		>
	{/if}
{/snippet}

<!-- A flagged member's flag line (§5.3 Station): the pills and their text, read once. -->
{#snippet memberFlags(row: Row)}
	<FlagLine name={row.name} flags={row.flags} {flagText} />
{/snippet}

<!-- A plain div with its heading, not a landmark (§7); tabindex −1, the section nav's target. -->
<div class="space-y-3 border-t border-slate-200 pt-3" data-group-station>
	<h4
		bind:this={heading}
		id="{id}-heading"
		class="scroll-mt-[calc(var(--pumps-nav-h,0px)-var(--pumps-nav-pad,0px)+0.5rem)] text-sm font-semibold text-slate-900"
		tabindex="-1"
	>
		Station
	</h4>
	<!--
		The group curve's line (§5.3 Station, §5.3 markup rules): the row's first child an always-
		present polite line, empty when idle, its mark at its first line (§15 item 22); its button
		after it, outside it, described by it. Out of sight while it has nothing to say, so it takes
		no room, its line still in the accessibility tree.
	-->
	<div
		class={['flex flex-wrap items-center gap-x-3 gap-y-1', !line && 'sr-only']}
		data-group-curve-row
	>
		<span
			id="{id}-curve-state"
			data-group-curve-state
			aria-live="polite"
			aria-atomic="true"
			class={[
				'inline-flex items-start gap-1.5 text-xs',
				line?.kind === 'error' ? 'text-red-800' : 'text-slate-700'
			]}
			>{#if line?.kind === 'loading'}<Icon
					name="spinner"
					class="mt-px size-3.5 shrink-0 text-slate-500 motion-safe:animate-spin"
				/>{:else if line?.kind === 'error'}<Icon
					name="octagon"
					class="mt-px size-3.5 shrink-0 text-red-700"
				/>{/if}{line?.text ?? ''}</span
		>
		{#if request?.kind === 'loading' && oncancel}
			<button
				bind:this={cancelButton}
				type="button"
				class="btn btn-quiet px-2 text-blue-800"
				aria-label="Cancel the group curve"
				aria-describedby="{id}-curve-state"
				onclick={oncancel}>Cancel</button
			>
		{:else if (request?.kind === 'error' || request?.kind === 'cancelled') && onretry}
			<button
				bind:this={retryButton}
				type="button"
				class="btn btn-quiet px-2 text-blue-800"
				aria-describedby="{id}-curve-state"
				onclick={onretry}
			>
				{request.kind === 'error' ? 'Try again' : 'Compute the group curve'}
			</button>
		{/if}
	</div>
	{#if sharesPending}
		<p class="text-xs text-slate-700">
			The share of each pump and its loss on the way come with the group curve.
		</p>
	{/if}
	{#if curve?.kind === 'refused'}
		<!-- The refusal, visible (§5.3 Station): the sentence, then each reason with its elements
			named and linked and the server's own sentence under Details. -->
		<div class="space-y-1 text-sm" data-group-refusal>
			<p class="font-medium">{curve.text}</p>
			<ul
				class="list-disc space-y-1 pl-5"
				aria-label={undefinedThere
					? 'Why the group curve is not defined'
					: 'Why they do not form a station'}
			>
				{#each refusals as refusal, i (i)}
					<li>
						{@render words(refusal.words)}
						<IssueDetail detail={refusal.issue.message} subject={wordsText(refusal.words)} />
					</li>
				{/each}
			</ul>
		</div>
	{/if}
	{#if table.footer.length}
		<!-- The station's answer (§5.2 Answers: 14 px, the values in bold), before the table: the
			station as a whole, its two ports named; the card's one dl. -->
		<dl
			class="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-0.5 text-sm text-slate-700 max-sm:grid-cols-1 max-sm:gap-y-0"
			aria-label="The station"
		>
			{#each table.footer as answer, i (i)}
				<dt>{answer.label}:</dt>
				<dd
					class="text-right font-semibold text-slate-900 tabular-nums max-sm:mb-1 max-sm:text-left"
				>
					{answer.value}
				</dd>
			{/each}
		</dl>
	{/if}
	<!-- The group table (§5.3 Station, §9 S6a): a ResultsTable, so it sorts, chooses its fields
		and shows the flagged pumps only, as every results table does, and reads as a list below
		640 px. Its visible title names it and its box (a region and a Tab stop); each name its slot
		symbol and a trace button, wrapping at 12 rem; each flagged pump's flag line its pills and
		their text (FlagLine), not FlagBadge, which reads the workspace. -->
	<div class="space-y-1" data-group-table>
		<p id="{id}-table-title" class="text-xs font-semibold text-slate-700">{title}</p>
		<ResultsTable
			table={resultsTable}
			caption={title}
			first="Pump"
			fieldsKey="The pumps in the group"
			labelledby="{id}-table-title"
			name={memberName}
			flagLine={memberFlags}
		/>
	</div>
</div>
