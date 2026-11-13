<!--
	Pumps together (CLAUDE.md D21, proposal pump-groups.md §6): a card under the pump chart, shown
	when two or more pumps have results; a disclosure, closed by default. Its members are chosen
	with checkboxes (page state, at most six), defaulting to the group suggested for the pump
	viewed, with the other suggested groups one button away. Opening it with two members or more
	asks for their group curve (POST /api/v1/pump-group-curve, for this solve and case), with
	progress and Cancel.

	The chart (the head panel only) draws each member's curve and solved point from its own result
	(exact, no request), the group curve from the API (the station solved alone between its two
	ports held a rise apart: ink, dashed where a pump runs beyond its data, gaps where a point has
	no flow) and the station's duty, an ink dot labelled "Group". The plain combined curve is not
	drawn (owner), and each pump's own system curve stays on its pump chart. When the API says the
	pumps do not form a station, the card says why in words with the elements named and linked,
	and still draws the members. Under the chart: the notes, how the curve is computed, the group
	table (from the solve, then the shares and losses from the duty) and the data table.

	Slice 4b (proposal §7): after the group curve's answer, the group system curve (the same
	request with curve 'system': the rest of the network between the station's inlet and outlet,
	at each station's flow), with its own progress, Cancel, failure and retry, drawn in the system
	orange with gaps where a point has no rise (the data table says why). The Group point is the
	two curves' crossing only when both duty checks agree. Where the group curve is refused only
	for an active PRV or PSV inside, the card says so and draws the group system curve all the
	same. "Read along the curves" steps over the group curve's samples, giving each member's flow
	and the station's at that rise exactly as the response does, and marks them on the chart.

	Slice 4d (one pump off, proposal §8 and §17), with pump lineups (CLAUDE.md D24 slice L1,
	proposal pump-lineups.md §7): under the group table, the Add cases block (PumpLineupsBlock: By
	number running or Each pump off, 4d's cases) adds in one step cases of the base case with pumps
	off (a parallel station only, while the base case is shown and current), its notice naming the
	Scenarios menu's Solve all (build-density.md §19: the block has none of its own); "Also show
	the other cases' station duties" draws each other case's duty as a slate ring tagged with its
	case's number (`tags`, pump-chart.ts caseTags: one number per case for the whole Pumps tab, in
	a box, CaseTag, in every list, table and heading; nit 5, slice 5b) ("Cases on this chart", in
	number order, at most six drawn, one lineup of each number running first), said to lie on the
	group system curve shown only when that case leaves the rest of the network as it is (D13
	allowing); "Running combinations" lists every case's members with a line saying which carry
	flow (D24 §7.10), a list on phones, with the extremes over the current cases (on screen only).
	Presentation only: the caller (PumpsView) computes every value and makes every request.

	Pump lineups slice L3 (CLAUDE.md D24, proposal pump-lineups.md §9): a ring's own group curve,
	where drawn, is a slate line labelled with its members running (placed on the canvas clear of
	the markers, labels and tags; the notes count the labels left out for space, the image its
	own), with the column "Its group curve" in "Other cases' station duties" and every point of
	each such curve in "Other cases' group curves", a list on phones.

	The card's sections (proposal pumps-results-layout.md §5.3, §9 S2): the members, then Station
	(PumpGroupStation: the group table and the station), Group chart (PumpGroupFigure: the figure,
	its actions under its legend, its notes, its reference and, after them, its data region; with
	the other cases' controls, PumpGroupOthers), Add cases (PumpLineupsBlock, since S4 a framed
	panel, §9 S4) and Running combinations (PumpGroupCombinations, with the extremes), the
	others each a plain div under an h4. The section components are presentation only and take
	their values from here; the card's props are as before. Closed, a second line under the
	heading says what opening it shows.

	The section nav (§5.4): the card's toggle is the target of the nav's "Pumps together" (so a
	press lands on the control, its expanded state announced), and each section registers its own
	heading; the card ends with "Back to the sections". Without PumpsView (this card's own tests)
	there is no nav, and neither is drawn.

	The members, the station and the group chart's reading (§5.3, §9 S3): the members a grid that
	never moves a name on tick, the server finder's hint the fieldset's description, a line while
	the members are the group suggested for the pump on the pump chart, and two groups found or
	more behind "Other groups found: {n}". Station opens with the group curve's line, the refusal
	and the station's answer, before the group table with its flag lines (PumpGroupStation). The
	group chart ends with the other cases under their h5 (PumpGroupOthers): the switch first, the
	cases, their own live line, "Compute them again" with its reason shown and "Go to Running
	combinations", then the ring notes cut as the owner answered (§12 item 1): the clip note,
	"How to read the rings" (the frame and the rule), the ring list one line per ring, "Not on the
	chart" and the left-out count.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import type { Flag, NodeResult, Project, UnitPreferences } from '$lib/api/types';
	import type { GroupCurveState, GroupSystemCurveState } from '$lib/state/project.svelte';
	import type { ChartImageSource } from '$lib/utils/export/chart-image';
	import {
		andList,
		groupChartData,
		groupNotes,
		groupTable,
		namesProject,
		type GroupMemberInput
	} from '$lib/utils/pump-group-chart';
	import {
		MAX_GROUP_PUMPS,
		pressureControlOnly,
		refusalWords,
		type GroupSuggestion
	} from '$lib/utils/pump-groups';
	import type {
		CombinationExtremes,
		CombinationsTable,
		OtherGroupCase
	} from '$lib/utils/pump-group-one-off';
	import { loadTableShown, type CaseNumber } from '$lib/utils/pump-chart';
	import Icon from '$lib/components/ui/Icon.svelte';
	import BackToSections from './BackToSections.svelte';
	import PumpGroupCombinations from './PumpGroupCombinations.svelte';
	import PumpGroupFigure from './PumpGroupFigure.svelte';
	import PumpGroupStation from './PumpGroupStation.svelte';
	import PumpLineupsBlock, { type LineupsBlockProps } from './PumpLineupsBlock.svelte';
	import { registerSection } from './section-nav.svelte';

	interface Props {
		/** Pumps with a result, in table order: each a box. */
		pumps: readonly Omit<GroupMemberInput, 'slot'>[];
		/** The boxes ticked by slot (null: a free slot); a slot is a member's colour and marker. */
		slots: readonly (string | null)[];
		/** Tick or untick: the new slots. */
		onslots?: (slots: (string | null)[]) => void;
		/** The groups suggested on the topology as solved. */
		suggestions?: readonly GroupSuggestion[];
		/**
		 * The pump on the pump chart, while the members are the group suggested for it (null: the
		 * user's own choice, or no group found holds it): the suggestion line names it (§5.3).
		 */
		suggestedFor?: string | null;
		/** The card is open (bindable: page state the caller keeps). */
		open?: boolean;
		/** The group curve of the members for this solve (undefined: not requested). */
		curve?: GroupCurveState;
		/** Compute it again (after a failure or a cancellation). */
		onretry?: () => void;
		/** Cancel it while it is computed. */
		oncancel?: () => void;
		/**
		 * The group system curve of the members for this solve (undefined: not requested; it is asked
		 * for after the group curve's answer).
		 */
		system?: GroupSystemCurveState;
		/** Compute the group system curve again (after a failure or a cancellation). */
		onretrysystem?: () => void;
		/** Cancel the group system curve while it is computed. */
		oncancelsystem?: () => void;
		prefs: UnitPreferences;
		/** Names (the labels project). */
		project: Project;
		/**
		 * The project the results belong to (as solved while they are out of date): topology
		 * (DIFFERENT_BOUNDARIES' side) and the names of elements deleted since. Default: `project`.
		 */
		solvedProject?: Project;
		/** Node results of the solve: the series inlet and discharge pressures. */
		nodes?: Readonly<Record<string, NodeResult>>;
		/** Why these results give no values (not converged, a failed or not reached case). */
		unavailable?: string | null;
		/** The results are out of date. */
		stale?: boolean;
		/** The case shown, in a project with scenarios. */
		caseName?: string;
		/** Open an element's results and trace. */
		oninspect?: (componentId: string) => void;
		/** A flag's words (names, display units). */
		flagText?: (flag: Flag) => string;
		/** What an image names and whether one can be made (as the pump chart's). */
		image?: ChartImageSource;
		/**
		 * The Add cases block (CLAUDE.md D24 slice L1, PumpLineupsBlock): its plan and the caller's
		 * changes (null: no block). Drawn while the card shows a station.
		 */
		lineups?: LineupsBlockProps | null;
		/** The other cases with values, each in its state (slice 4d). */
		otherCases?: readonly OtherGroupCase[];
		/**
		 * Every case's number (pump-chart.ts caseTags of the project), one for the whole Pumps tab:
		 * the cases' boxes in "Cases on this chart", the tables and the headings, ticked or not
		 * (owner, 2026-11-12, nit 5; docs/proposals/pumps-nits.md item 5, slice 5b).
		 */
		tags?: Readonly<Record<string, CaseNumber>>;
		/** The case shown's number: its "(shown)" tag. */
		caseTag?: CaseNumber;
		/**
		 * The members switched on in this case as solved (D24 §9.3: its curve's label while other
		 * cases' curves are drawn; null: not given).
		 */
		shownOn?: number | null;
		/** "Also show the other cases' station duties" is ticked. */
		othersOn?: boolean;
		/** Tick or untick it (absent: the project has no scenarios, no box). */
		onothers?: (on: boolean) => void;
		/** Tick or untick a case under "Cases on this chart". */
		onotherstick?: (key: string, on: boolean) => void;
		/** The other cases' duties being computed: settled of all on the chart (null: none). */
		othersProgress?: { done: number; total: number } | null;
		/** Cancel the other cases' requests. */
		oncancelothers?: () => void;
		/** Ask again for those cancelled by the user or failed. */
		onretryothers?: () => void;
		/**
		 * Why "Compute them again" is unavailable ('' when it can run): a calculation runs, and the
		 * store sends no curve request until it ends (calculatingReason's words).
		 */
		othersRetryReason?: string;
		/** "Running combinations": every case's members (null: no table). */
		combinations?: CombinationsTable | null;
		/** The extremes over the current cases (screen only): their lines and their table. */
		extremes?: CombinationExtremes | null;
	}

	let {
		pumps,
		slots,
		onslots,
		suggestions = [],
		suggestedFor = null,
		open = $bindable(false),
		curve: groupCurve,
		onretry,
		oncancel,
		system: systemCurve,
		onretrysystem,
		oncancelsystem,
		prefs,
		project: labels,
		solvedProject,
		nodes = {},
		unavailable = null,
		stale = false,
		caseName,
		oninspect,
		flagText = (flag) => flag.message,
		image,
		lineups = null,
		otherCases = [],
		tags = { '': 'Base' },
		caseTag = 'Base',
		shownOn = null,
		othersOn = false,
		onothers,
		onotherstick,
		othersProgress = null,
		oncancelothers,
		onretryothers,
		othersRetryReason = '',
		combinations = null,
		extremes = null
	}: Props = $props();
	const id = $props.id();

	/** The members: each ticked pump with a result, with its slot. */
	const members = $derived(
		slots.flatMap((pumpId, slot) => {
			const pump = pumpId === null ? undefined : pumps.find((p) => p.id === pumpId);
			return pump ? [{ ...pump, slot }] : [];
		})
	);
	const memberIds = $derived(members.map((m) => m.id));
	const ticked = (pumpId: string) => slots.includes(pumpId);
	const full = $derived(members.length >= MAX_GROUP_PUMPS);

	function setTicked(pumpId: string, on: boolean) {
		const next = [...slots];
		if (on) {
			// The first free slot: a member keeps its colour while it stays ticked.
			const free = next.indexOf(null);
			if (free >= 0) next[free] = pumpId;
			else next.push(pumpId);
		} else {
			const at = next.indexOf(pumpId);
			if (at >= 0) next[at] = null;
			while (next.length && next[next.length - 1] === null) next.pop();
		}
		onslots?.(next);
	}

	let alsoFound: HTMLElement | undefined = $state();
	let fieldset: HTMLElement | undefined = $state();
	/** The group chart's figure (PumpGroupFigure's): the focus falls back to it. */
	let figure: HTMLElement | undefined = $state();

	/**
	 * Show a group found: its button goes (the group shown is not offered), so the focus moves on
	 * to the next group offered (often the one shown before), else the chart, else a ticked box.
	 */
	function showSuggestion(pumpIds: readonly string[]) {
		onslots?.([...pumpIds]);
		void tick().then(() => {
			const next =
				alsoFound?.querySelector<HTMLElement>('button') ??
				figure ??
				fieldset?.querySelector<HTMLElement>('input:checked');
			next?.focus();
		});
	}

	const sameGroup = (ids: readonly string[]) =>
		ids.length === memberIds.length && ids.every((x) => memberIds.includes(x));
	const otherGroups = $derived(suggestions.filter((s) => !sameGroup(s.pumpIds)));
	const nameOf = (pumpId: string) => pumps.find((p) => p.id === pumpId)?.name ?? pumpId;

	/** Names: current ones, and those as solved of elements deleted since. */
	const project = $derived(namesProject(labels, solvedProject));

	const response = $derived(groupCurve?.status === 'ready' ? groupCurve.response : null);
	const shown = $derived(unavailable ? null : response);
	const systemResponse = $derived(systemCurve?.status === 'ready' ? systemCurve.response : null);
	const systemShown = $derived(unavailable ? null : systemResponse);
	/**
	 * The station and its duty: the group curve's response, else the group system curve's (the
	 * same station and the same duty, from the case's own solve), when the group curve is refused
	 * for an active PRV or PSV inside only.
	 */
	const stationShown = $derived(shown ?? (systemShown?.duty ? systemShown : null));
	/** The other cases, while the card shows a station (slice 4d). */
	const others = $derived(unavailable || !stationShown ? [] : otherCases);
	const data = $derived(groupChartData(members, prefs, shown, systemShown, others, shownOn));
	/**
	 * Curves whose labels the chart on screen left out for space (D24 §9.3), told by its drawing
	 * (the group chart's canvas); the image counts its own.
	 */
	let labelsLeftOut = $state(0);
	const notesWith = (leftOut: number) =>
		groupNotes({
			data,
			members,
			state: unavailable ? undefined : groupCurve,
			system: unavailable ? undefined : systemCurve,
			project,
			solved: solvedProject ?? labels,
			prefs,
			others,
			labelsLeftOut: leftOut
		});
	// Only while other cases' curves are drawn: a count kept from an earlier drawing never shows.
	const notes = $derived(notesWith(data.otherCurves.length ? labelsLeftOut : 0));
	/** Refused only for an active PRV or PSV inside: a station, whose group curve is not defined. */
	const undefinedThere = $derived(
		groupCurve?.status === 'refused' && pressureControlOnly(groupCurve.issues)
	);
	const refusals = $derived(
		groupCurve?.status === 'refused' && !unavailable
			? groupCurve.issues.map((issue) => ({
					issue,
					words: refusalWords(issue, memberIds, project, {
						solved: solvedProject ?? labels,
						boxes: pumps.map((p) => p.id)
					})
				}))
			: []
	);
	const arrangement = $derived(stationShown?.station.arrangement ?? null);
	const memberNames = $derived(
		(stationShown ? stationShown.station.memberIds : [...memberIds].sort(byTable)).map(nameOf)
	);
	function byTable(a: string, b: string) {
		return pumps.findIndex((p) => p.id === a) - pumps.findIndex((p) => p.id === b);
	}
	const table = $derived(groupTable(members, nodes, stationShown, prefs, project));
	const loading = $derived(groupCurve?.status === 'loading' && !unavailable);
	const systemLoading = $derived(systemCurve?.status === 'loading' && !unavailable);
	/** The other cases' duties are being computed (slice 4d). */
	const othersLoading = $derived(!!othersProgress && others.length > 0);
	/** Some case on the chart was cancelled by the user or failed: "Compute them again". */
	const othersRetry = $derived(othersOn && others.some((o) => o.onChart && o.retry));

	/**
	 * What the group chart's section keeps while it is drawn again (the card closed and opened,
	 * the values gone and back), as the card did before its sections were components: whether its
	 * data table is shown (remembered in this browser too, pumps-results-layout.md §9 S7), the
	 * curve tables opened or closed in it (§9 S7), and where "Read along the curves" was moved to
	 * (raw: the response is compared by identity, and a deep proxy would never equal it).
	 */
	let showTable = $state(loadTableShown('group'));
	let tablesOpen = $state<Record<string, boolean | undefined>>({});
	let reading = $state.raw<{ response: unknown; index: number } | null>(null);

	/**
	 * The closed card's line (proposal pumps-results-layout.md §5.3, §6.2): what opening it shows,
	 * Running combinations with scenarios (`onothers` is given only then). It describes the
	 * toggle, so the toggle's name still starts "Pumps together".
	 */
	const about = $derived(
		`The station's duty, the group curve, each pump's share and cases with fewer pumps running${onothers ? '; Running combinations' : ''}`
	);

	/** The toggle: the section nav's "Pumps together" lands on it (§5.4 Targets). */
	let toggle: HTMLElement | undefined = $state();
	registerSection('pumps-together', () => toggle);
</script>

<!--
	The card (proposal pumps-results-layout.md §5.3, §9 S2): its heading and toggle, the members,
	then its sections in reading order, each a plain div under an h4 with a rule above (§5.2):
	Station, Group chart, Add cases, Running combinations (§6.4 item 1).
-->
<section class="card space-y-3 p-3" aria-labelledby="{id}-heading" data-pumps-together>
	<div>
		<h3 id="{id}-heading" class="text-base font-semibold">
			<button
				bind:this={toggle}
				type="button"
				class="flex min-h-11 w-full scroll-mt-[calc(var(--pumps-nav-h,0px)-var(--pumps-nav-pad,0px)+0.5rem)] items-start gap-2 py-2.5 text-left"
				aria-expanded={open}
				aria-controls="{id}-body"
				aria-describedby={open ? undefined : `${id}-about`}
				onclick={() => (open = !open)}
			>
				<!-- It turns as the card opens, never with reduced motion (§5.3 markup rules). -->
				<Icon
					name="right"
					class={[
						'mt-1 size-4 shrink-0 transition-transform motion-reduce:transition-none',
						open && 'rotate-90'
					]}
				/>
				<!-- The heading's words whole on one line, the chevron beside its first; the members
					beside them where they fit, else on lines of their own under them (§5.3 item 3,
					§5.6). -->
				<span class="flex min-w-0 flex-wrap items-baseline gap-x-2">
					<span class="whitespace-nowrap">Pumps together</span>
					{#if !open && memberNames.length}<span class="text-xs font-normal text-slate-600"
							>({memberNames.join(', ')})</span
						>{/if}
				</span>
			</button>
		</h3>
		{#if !open}
			<!-- A second, muted line under the heading, the toggle's description (§5.3). -->
			<p id="{id}-about" class="-mt-1 pl-6 text-xs text-slate-600" data-pumps-together-about>
				{about}
			</p>
		{/if}
	</div>
	{#if open}
		<div id="{id}-body" class="space-y-3">
			<!-- Members (§5.3): the legend the fieldset's first child, so the group keeps its name; the
				server finder's hint its description (§6.2: kept visible, now also its description). -->
			<fieldset bind:this={fieldset} aria-describedby="{id}-finder">
				<legend class="text-xs font-medium text-slate-700">Pumps in the group</legend>
				<!-- An auto-fill grid, 13 rem at least (no container needed, §15 item 35): two columns in
					a 480 px pane, one on a phone; names wrap. -->
				<div class="grid grid-cols-[repeat(auto-fill,minmax(13rem,1fr))] gap-x-3">
					{#each pumps as pump (pump.id)}
						{@const on = ticked(pump.id)}
						{@const capped = !on && full}
						<!-- Capped (ui-guide): the box greyed, the name kept readable (slate-600). -->
						<label
							class={[
								'flex min-h-11 items-start gap-2 py-3 text-sm',
								capped && 'cursor-not-allowed text-slate-600'
							]}
						>
							<input
								type="checkbox"
								class={['mt-0.5 size-4 shrink-0', capped && 'opacity-45']}
								checked={on}
								aria-disabled={capped}
								aria-describedby={capped ? `${id}-full` : undefined}
								onclick={(event) => {
									if (capped) {
										event.preventDefault();
										return;
									}
									setTicked(pump.id, event.currentTarget.checked);
								}}
							/>
							<!-- A pump is its name (owner, 2026-11-12, nit 5; docs/proposals/pumps-nits.md
								item 5): no slot symbol, so nothing before the name moves it on tick. -->
							<span class="min-w-0 wrap-break-word">{pump.name}</span>
						</label>
					{/each}
				</div>
				{#if full && pumps.length > MAX_GROUP_PUMPS}
					<p id="{id}-full" class="hint">At most {MAX_GROUP_PUMPS} pumps in a group.</p>
				{/if}
				<p id="{id}-finder" class="hint">
					The calculation server finds the part of the network that holds them, between two places
					(its inlet and outlet), and whether they are in parallel or in series.
				</p>
			</fieldset>
			{#if suggestedFor}
				<!-- While the members are the group suggested for the pump on the pump chart (F29: its
					select also chooses the card's default members, and nothing said so). -->
				<p class="hint -mt-2" data-group-suggested>
					Suggested for {suggestedFor}, the pump on the pump chart above; tick pumps to choose your
					own.
				</p>
			{/if}
			{#if otherGroups.length}
				<!-- The other groups found (§5.3): one, its button; two or more, behind "Other groups
					found: {n}". Each button wraps (§9 S0, F10: `.btn` does not), so the pane never
					scrolls sideways; S0's one sentence comes first, saying what a button does before it
					is met, and describes each. Like the suggestion line, 4 px under what it follows: the
					members' block reads as one, before Station's rule. -->
				{#snippet alsoFoundButtons()}
					<p id="{id}-also-found" class="hint">Showing a group found replaces the pumps ticked.</p>
					<div bind:this={alsoFound} class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
						{#each otherGroups as other (other.pumpIds.join('\u0000'))}
							<button
								type="button"
								class="btn btn-quiet px-2 py-1.5 text-left wrap-anywhere whitespace-normal text-blue-800"
								aria-describedby="{id}-also-found"
								onclick={() => showSuggestion(other.pumpIds)}
								>Also found: {andList(other.pumpIds.map(nameOf))}</button
							>
						{/each}
					</div>
				{/snippet}
				{#if otherGroups.length > 1}
					<details class="group -mt-2" data-other-groups>
						<summary class="more-summary">
							<Icon
								name="right"
								class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
							/>
							Other groups found: {otherGroups.length}
						</summary>
						<div class="pb-1">{@render alsoFoundButtons()}</div>
					</details>
				{:else}
					<div class="-mt-2">{@render alsoFoundButtons()}</div>
				{/if}
			{/if}

			{#if unavailable}
				<p class="text-sm text-slate-700">{unavailable}</p>
			{:else if members.length}
				<!-- 1. Station (§5.3): its answer first (the group curve's line, the refusal, the station),
					then the group table, before the chart. -->
				<PumpGroupStation
					{table}
					{caseName}
					{oninspect}
					{flagText}
					sharesPending={!shown && groupCurve?.status !== 'refused' && members.length > 1}
					curve={notes.curve}
					{refusals}
					{undefinedThere}
					{loading}
					{onretry}
					{oncancel}
					{figure}
				/>
				<!-- 2. Group chart: the figure, its actions under its legend, its data after its
					reference (§5.1, §9 S2). -->
				<PumpGroupFigure
					bind:figure
					bind:showTable
					bind:tablesOpen
					bind:reading
					onlabels={(leftOut) => (labelsLeftOut = leftOut)}
					{members}
					{data}
					{shown}
					{systemShown}
					{stationShown}
					{notes}
					{notesWith}
					{refusals}
					{memberNames}
					{arrangement}
					{table}
					{project}
					solved={solvedProject ?? labels}
					{prefs}
					{nameOf}
					{caseName}
					{stale}
					{image}
					{loading}
					{systemLoading}
					{othersLoading}
					{othersRetry}
					{onretrysystem}
					{oncancelsystem}
					{others}
					{tags}
					{caseTag}
					{othersOn}
					{onothers}
					{onotherstick}
					{othersProgress}
					{oncancelothers}
					{onretryothers}
					{othersRetryReason}
					combinations={!!combinations && !!stationShown}
				/>
				{#if lineups && stationShown}
					<!-- 3. Add cases (D24 slice L1): the cases of the base case with pumps off, the one
						part that changes the project, after the group chart (§6.4 item 1), a framed
						panel in place of the rule every other h4 section has (§5.3, §9 S4). -->
					<PumpLineupsBlock {...lineups} />
				{/if}
				{#if combinations && stationShown}
					<!-- 4. Running combinations (slice 4d), with the extremes over the cases. -->
					<PumpGroupCombinations {combinations} {extremes} {flagText} {oninspect} />
				{/if}
			{:else}
				<p class="text-sm text-slate-700">Tick the pumps to see together.</p>
			{/if}
		</div>
	{/if}
	<!-- The card's last control (§5.3 item 3): the nav one Tab and a press away. -->
	<BackToSections />
</section>
