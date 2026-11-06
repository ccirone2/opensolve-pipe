<!--
	The scenario manager (proposal scenario-manager.md §6.4): the base case and each scenario, as
	cards. A scenario's card names it, describes it, lists its changes (each with its base value,
	Show and Remove), the changes that no longer apply (their element was deleted, or no longer has
	the value), and problems with its values; it can be shown, duplicated, moved and deleted. Every
	action is one undo step, made in the case shown; names, descriptions and order are labels and
	never make results out of date. A modal on wide screens, a bottom sheet on phones.

	Pump lineups (CLAUDE.md D24, proposal pump-lineups.md §8.1, slice L2): with two pumps or more, a
	tab row (Cases ({n}), Pump lineups; the Project library's pattern) and the dialog xl on both
	tabs, so its width never changes on a tab switch (on a phone the sheet's height neither); the
	Cases prose then capped at max-w-prose. The Cases view is drawn in one place with or without
	the tab row, so an undo that adds or removes it keeps the focus on a Cases control.
	The tab shown is derived: the one last used (page state) while the project has two pumps, else
	Cases; a scenario's card asked for always opens Cases. Each tab has its own footer. One polite
	status line and one alert line, outside the panels and above the footer, say what the actions
	of either tab did (renames, adds, undos, refusals), since the workspace notice sits behind the
	modal; Ctrl/⌘+Z, Ctrl/⌘+Shift+Z and Ctrl/⌘+Y on the manager's root (not in a text field) go
	through the same undo and redo as the Pump lineups footer's buttons, which say what they did.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import type { Override, Project, Scenario } from '$lib/api/types';
	import { focusCurrentHeading } from '$lib/components/panel/focus';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { URL_LENGTH_WARNING } from '$lib/utils/encoding';
	import { connectionById } from '$lib/utils/graph';
	import {
		hasLineupsTab,
		LINEUP_TABLE_WORDS,
		shownManagerTab,
		type ManagerTab
	} from '$lib/utils/lineup-table';
	import { changeElement, scenarioProblems } from '$lib/utils/scenario-problems';
	import {
		changeFieldLabel,
		changeStates,
		changeTarget,
		changeTargetLabel,
		changeValueText,
		copyName,
		LIMIT_TEXT,
		MAX_CHANGES,
		MAX_SCENARIOS,
		newScenarioId,
		newScenarioName,
		SCENARIO_DESCRIPTION_LIMIT,
		SCENARIO_NAME_LIMIT,
		valueOf,
		withScenarios
	} from '$lib/utils/scenarios';
	import { caseNameIn, useWorkspace } from '$lib/state/workspace.svelte';
	import type { UpdateLabel } from '$lib/state/project.svelte';
	import CaseStatusChip from './CaseStatusChip.svelte';
	import PumpLineups from './PumpLineups.svelte';

	let { onclose }: { onclose: () => void } = $props();
	const ws = useWorkspace();
	const store = ws.store;
	const id = $props.id();

	const scenarios = $derived(ws.scenarios);
	const full = $derived(scenarios.length >= MAX_SCENARIOS);

	// A scenario's card asked for always opens Cases (§8.1); it is then the tab last used.
	if (ws.managerFocus !== null) ws.managerTab = 'cases';
	/** The tab row: two pumps or more (§8.1). */
	const tabs = $derived(hasLineupsTab(store.project));
	/** The tab shown, derived (decision 26): the one last used while there are tabs, else Cases. */
	const tab = $derived(shownManagerTab(store.project, ws.managerTab));
	const TABS: readonly ManagerTab[] = ['cases', 'lineups'];
	/** The manager's lines are capped as the Cases prose is: on the Cases tab of the tab row. */
	const prose = $derived(tabs && tab === 'cases');

	let dialog: ReturnType<typeof Dialog> | undefined = $state();
	let lineups: ReturnType<typeof PumpLineups> | undefined = $state();
	/** The manager's polite status line and its alert line (§8.1), shared by both tabs. */
	let status = $state('');
	let alert = $state('');
	/** Increments with every message, so the same words said twice are announced twice. */
	let said = $state(0);
	function say(text: string) {
		status = text;
		alert = '';
		said++;
	}
	function warn(text: string) {
		alert = text;
		status = '';
		said++;
	}

	function selectTab(next: ManagerTab) {
		ws.managerTab = next;
	}

	function tabKeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
			event.preventDefault();
			const next = tab === 'cases' ? 'lineups' : 'cases';
			selectTab(next);
			document.getElementById(`${id}-tab-${next}`)?.focus();
		}
	}

	/**
	 * Undo or redo the last step, whichever it was (§8.9), saying what it did on the status line.
	 * The focus stays where it was: put back on the table's active cell when it was in the grid;
	 * on the dialog's title when the step took the project below two pumps while Pump lineups was
	 * shown (the tab row, the table and its footer are gone), or when what it was on is gone with
	 * nothing in its place (the Cases tab, when the tab row goes).
	 */
	async function history(step: 'undo' | 'redo') {
		const inGrid = lineups?.hasFocus() ?? false;
		const before = tab;
		const done = step === 'undo' ? ws.undoStep() : ws.redoStep();
		if (!done) return;
		say(done.text);
		await tick();
		const lost = !document.activeElement || document.activeElement === document.body;
		if (before === 'lineups' && tab === 'cases') dialog?.focusTitle();
		else if (inGrid) await lineups?.focusActive();
		else if (lost) dialog?.focusTitle();
	}

	function editingText(target: EventTarget | null): boolean {
		return (
			target instanceof HTMLElement &&
			(target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
		);
	}

	/**
	 * Ctrl/⌘+Z, Ctrl/⌘+Shift+Z and Ctrl/⌘+Y in the manager, except in a text field (§8.1), as the
	 * workspace's window shortcut is; kept from it, which would undo without a word in the manager.
	 */
	function keydown(event: KeyboardEvent) {
		if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
		const key = event.key.toLowerCase();
		if (key !== 'z' && key !== 'y') return;
		if (editingText(event.target)) return;
		event.preventDefault();
		event.stopPropagation();
		void history(key === 'z' && !event.shiftKey ? 'undo' : 'redo');
	}

	/**
	 * A manager's action as one undo step (updateStored's), said on the manager's own lines: the
	 * renames it made (§4.5) on the status line, a refusal on the alert line.
	 */
	function step(change: (draft: Project) => Project | void, label: UpdateLabel): boolean {
		const result = ws.updateStoredQuiet(change, label);
		if (!result.ok) {
			warn(result.text);
			return false;
		}
		say(result.renamed);
		return true;
	}

	const undoName = $derived(store.undoLabel ? LINEUP_TABLE_WORDS.undoNamed(store.undoLabel) : '');
	const redoName = $derived(store.redoLabel ? LINEUP_TABLE_WORDS.redoNamed(store.redoLabel) : '');

	/** Cards that are open: the one asked for, else the active scenario's. */
	let opened = $state<string[]>(
		[ws.managerFocus ?? store.activeCase].filter((v): v is string => !!v)
	);
	let deleting = $state<Scenario | null>(null);
	let listHeading: HTMLHeadingElement | undefined = $state();

	const valueText = (override: Override, value: unknown) =>
		changeValueText(store.project, override, value, ws.units, {
			materialName: (m) => ws.library.material(m)?.name,
			nominalSizes: ws.library.nominalSizes
		});

	function baseText(override: Override): string {
		const value = valueOf(store.project, changeTarget(override), override.field);
		return value === undefined ? '—' : valueText(override, value);
	}

	function toggle(scenarioId: string, open: boolean) {
		if (open === opened.includes(scenarioId)) return;
		opened = open ? [...opened, scenarioId] : opened.filter((s) => s !== scenarioId);
	}

	async function focusName(scenarioId: string) {
		await tick();
		const input = document.querySelector<HTMLInputElement>(
			`[data-scenario-name="${scenarioId}"] input`
		);
		input?.focus();
		input?.select();
	}

	function add() {
		if (full) return;
		const sid = newScenarioId(store.project);
		const scenario: Scenario = {
			id: sid,
			name: newScenarioName(store.project, sid),
			overrides: []
		};
		if (!step((p) => withScenarios(p, [...scenarios, scenario]), 'add scenario')) return;
		ws.setCase(sid);
		toggle(sid, true);
		void focusName(sid);
	}

	function duplicate(scenario: Scenario) {
		if (full) return;
		const sid = newScenarioId(store.project);
		const copy: Scenario = {
			...structuredClone(scenario),
			id: sid,
			name: copyName(scenario.name)
		};
		const index = scenarios.findIndex((s) => s.id === scenario.id);
		const next = [...scenarios.slice(0, index + 1), copy, ...scenarios.slice(index + 1)];
		if (!step((p) => withScenarios(p, next), `duplicate scenario ${scenario.name}`)) return;
		ws.setCase(sid);
		toggle(sid, true);
		void focusName(sid);
	}

	function edit(scenario: Scenario, label: string, change: (s: Scenario) => Scenario) {
		step(
			(p) =>
				withScenarios(
					p,
					scenarios.map((s) => (s.id === scenario.id ? change(s) : s))
				),
			`${label} ${scenario.name}`
		);
	}

	function move(scenario: Scenario, by: -1 | 1) {
		const index = scenarios.findIndex((s) => s.id === scenario.id);
		const to = index + by;
		if (to < 0 || to >= scenarios.length) return;
		const next = [...scenarios];
		next.splice(index, 1);
		next.splice(to, 0, scenario);
		step((p) => withScenarios(p, next), `move scenario ${scenario.name} ${by < 0 ? 'up' : 'down'}`);
	}

	async function remove(scenario: Scenario) {
		deleting = null;
		const next = scenarios.filter((s) => s.id !== scenario.id);
		if (!step((p) => withScenarios(p, next), `delete scenario ${scenario.name}`)) return;
		await tick();
		// With the tab row the heading is sr-only (the tab says it): the focus goes to the tab.
		if (tabs) document.getElementById(`${id}-tab-cases`)?.focus();
		else listHeading?.focus();
	}

	/**
	 * Remove changes of a scenario: its undo label names it as the step leaves it, since a name the
	 * app made follows its pumps (CLAUDE.md D24, proposal pump-lineups.md §4.5).
	 */
	function removeChanges(scenario: Scenario, indices: readonly number[], label: string) {
		step(
			(p) =>
				withScenarios(
					p,
					scenarios.map((s) =>
						s.id === scenario.id
							? { ...s, overrides: (s.overrides ?? []).filter((_, i) => !indices.includes(i)) }
							: s
					)
				),
			(after) => `${label} ${caseNameIn(after, scenario.id)}`
		);
	}

	async function showCase(scenarioId: string | null) {
		onclose();
		ws.setCase(scenarioId);
		await focusCurrentHeading();
	}

	/** Show a change in Build: its scenario, then its element (a pipe opens its piping). */
	async function showChange(scenarioId: string, override: Override) {
		onclose();
		ws.setCase(scenarioId);
		const element = changeElement(store.project, override);
		if (!element) {
			ws.settingsOpen = true;
			return;
		}
		if (element.kind === 'component') ws.show(element.id);
		else {
			const connection = connectionById(store.project, element.id);
			if (connection) ws.show(connection.fromComponentId, connection.fromPortId);
		}
		await focusCurrentHeading();
	}
</script>

<!-- The Cases tab (the manager as it was before the tab row): with the tab row (xl) its prose at
	max-w-prose, the cards full width (§8.1); without it, exactly as before. -->
{#snippet cases()}
	<div class="space-y-4">
		<p class={['text-slate-700', tabs && 'max-w-prose']}>
			A scenario keeps another operating or design case of this network, such as a pump off, a valve
			closed or a larger pipe, as a list of values changed from the base case. Editing the base case
			updates every scenario that does not set its own value. The layout of the network is the same
			in every scenario.
		</p>
		<h3
			bind:this={listHeading}
			id="{id}-list"
			tabindex="-1"
			class={tabs ? 'sr-only' : 'section-title'}
		>
			Cases ({scenarios.length + 1})
		</h3>

		<section class="card flex flex-wrap items-center gap-2 p-3" aria-labelledby="{id}-base">
			<div class="min-w-0 flex-1 basis-48">
				<h4 id="{id}-base" class="font-semibold">Base case</h4>
				<p class={['text-slate-700', tabs && 'max-w-prose']}>The network as built.</p>
			</div>
			<CaseStatusChip status={store.caseStatus(null)} />
			<button
				type="button"
				class="btn"
				aria-label="Show the base case"
				onclick={() => showCase(null)}>Show</button
			>
		</section>

		{#each scenarios as scenario, index (scenario.id)}
			{@const states = changeStates(store.project, scenario.id)}
			{@const live = states.filter((c) => c.state === 'applied')}
			{@const lapsed = states.filter((c) => c.state !== 'applied')}
			{@const problems = opened.includes(scenario.id)
				? scenarioProblems(store.project, scenario.id, ws.units)
				: []}
			<details
				class="card group"
				open={opened.includes(scenario.id)}
				ontoggle={(event) => toggle(scenario.id, event.currentTarget.open)}
			>
				<summary
					class="flex min-h-11 cursor-pointer list-none flex-wrap items-center gap-x-2 gap-y-1 p-3 [&::-webkit-details-marker]:hidden"
				>
					<Icon name="right" class="size-4 shrink-0 transition-transform group-open:rotate-90" />
					<span class="min-w-0 font-semibold break-words">{scenario.name}</span>
					<span class="font-mono text-xs text-slate-600">{scenario.id}</span>
					<span class="text-slate-700">{ws.changesText(scenario)}</span>
					{#if store.activeCase === scenario.id}<span
							class="rounded bg-teal-700 px-1.5 py-0.5 text-xs font-semibold text-white">Shown</span
						>{/if}
					<span class="ml-auto"><CaseStatusChip status={store.caseStatus(scenario.id)} /></span>
				</summary>
				<div class="space-y-4 border-t border-slate-200 p-3">
					<div data-scenario-name={scenario.id}>
						<TextField
							label="Name of scenario {scenario.id}"
							value={scenario.name}
							required
							shared
							maxlength={SCENARIO_NAME_LIMIT}
							onchange={(v) =>
								!!v &&
								v !== scenario.name &&
								edit(scenario, 'rename scenario', (s) => ({ ...s, name: v }))}
						/>
					</div>
					<TextField
						label="Description"
						multiline
						shared
						value={scenario.description}
						maxlength={SCENARIO_DESCRIPTION_LIMIT}
						hint="What this case is, for whoever reads its results (optional)."
						onchange={(v) =>
							edit(scenario, 'describe scenario', (s) => {
								const next = { ...s };
								if (v === null) delete next.description;
								else next.description = v;
								return next;
							})}
					/>

					<section class="space-y-2" aria-labelledby="{id}-{scenario.id}-changes">
						<h4 id="{id}-{scenario.id}-changes" class="font-medium">
							Changes ({live.length} of at most {MAX_CHANGES})
						</h4>
						{#if live.length}
							<ul class="divide-y divide-slate-100 rounded-md border border-slate-200">
								{#each live as change (change.index)}
									{@const o = change.override}
									{@const what = `${changeTargetLabel(store.project, o)} · ${changeFieldLabel(store.project, o)}`}
									<li class="flex flex-wrap items-center gap-x-3 gap-y-1 px-2 py-1.5">
										<div class={['min-w-0 flex-1 basis-56', tabs && 'max-w-prose']}>
											<p class="break-words">
												<span class="text-slate-700">{what}:</span>
												<strong>{valueText(o, o.value)}</strong>
												{#if change.invalid}<span class="text-red-800"
														>(not a pipe specification)</span
													>{/if}
											</p>
											<p class="text-xs text-slate-600">Base: {baseText(o)}</p>
										</div>
										<div class="flex gap-1">
											<button
												type="button"
												class="btn btn-quiet px-2 text-blue-800"
												aria-label="Show {what}"
												onclick={() => showChange(scenario.id, o)}>Show</button
											>
											<button
												type="button"
												class="btn btn-quiet px-2 text-red-800"
												aria-label="Remove the change of {what}"
												onclick={() =>
													removeChanges(scenario, [change.index], 'remove a change in')}
												>Remove</button
											>
										</div>
									</li>
								{/each}
							</ul>
						{:else}
							<p class={['text-slate-700', tabs && 'max-w-prose']}>
								No changes yet: it solves as the base case. Show it, then change values in Build or
								in Settings (the fluid).
							</p>
						{/if}
					</section>

					{#if lapsed.length}
						<section class="space-y-2" aria-labelledby="{id}-{scenario.id}-lapsed">
							<h4 id="{id}-{scenario.id}-lapsed" class="font-medium text-amber-900">
								No longer applies ({lapsed.length})
							</h4>
							<ul
								class="divide-y divide-amber-100 rounded-md border border-amber-300 bg-amber-50 text-amber-950"
							>
								{#each lapsed as change (change.index)}
									{@const o = change.override}
									{@const what = `${changeTargetLabel(store.project, o)} · ${changeFieldLabel(store.project, o)} ${valueText(o, o.value)}`}
									<li class="flex flex-wrap items-center gap-x-3 gap-y-1 px-2 py-1.5">
										<p class={['min-w-0 flex-1 basis-56 break-words', tabs && 'max-w-prose']}>
											{what}: no longer applies, ignored when solving ({change.message}).
										</p>
										<button
											type="button"
											class="btn btn-quiet px-2 text-red-800"
											aria-label="Remove the change of {what}"
											onclick={() => removeChanges(scenario, [change.index], 'remove a change in')}
											>Remove</button
										>
									</li>
								{/each}
							</ul>
							{#if lapsed.length > 1}
								<button
									type="button"
									class="btn"
									onclick={() =>
										removeChanges(
											scenario,
											lapsed.map((c) => c.index),
											'remove the changes that no longer apply in'
										)}
								>
									Remove the {lapsed.length} changes that no longer apply
								</button>
							{/if}
						</section>
					{/if}

					{#if problems.length}
						<section class="space-y-2" aria-labelledby="{id}-{scenario.id}-problems">
							<h4 id="{id}-{scenario.id}-problems" class="font-medium text-red-900">
								Problems ({problems.length})
							</h4>
							<ul class="space-y-1 text-red-900">
								{#each problems as problem, i (i)}
									{@const o =
										problem.index === null ? null : (scenario.overrides ?? [])[problem.index]}
									<li class="flex flex-wrap items-center gap-x-2">
										<Icon name="alert" class="size-4 shrink-0" />
										<span class={['min-w-0 flex-1 basis-48 break-words', tabs && 'max-w-prose']}>
											{#if o}
												The value {scenario.name} sets for {changeTargetLabel(store.project, o)}
												{changeFieldLabel(store.project, o).toLowerCase()} is not valid: {problem.text}
											{:else}
												{problem.text}
											{/if}
										</span>
										{#if o}
											<button
												type="button"
												class="btn btn-quiet px-2 text-blue-800"
												onclick={() => showChange(scenario.id, o)}>Show</button
											>
										{/if}
									</li>
								{/each}
							</ul>
						</section>
					{/if}

					<div class="flex flex-wrap gap-2" role="group" aria-label="Actions on {scenario.name}">
						<button
							type="button"
							class="btn"
							aria-label="Show {scenario.name}"
							onclick={() => showCase(scenario.id)}>Show</button
						>
						<button
							type="button"
							class="btn"
							aria-disabled={full}
							title={full ? LIMIT_TEXT : undefined}
							aria-describedby={full ? `${id}-full` : undefined}
							aria-label="Duplicate {scenario.name}"
							onclick={() => duplicate(scenario)}
						>
							<Icon name="copy" class="size-4" /> Duplicate
						</button>
						<button
							type="button"
							class="btn"
							aria-disabled={index === 0}
							aria-label="Move {scenario.name} up"
							onclick={() => move(scenario, -1)}
						>
							<Icon name="up" class="size-4" /> Move up
						</button>
						<button
							type="button"
							class="btn"
							aria-disabled={index === scenarios.length - 1}
							aria-label="Move {scenario.name} down"
							onclick={() => move(scenario, 1)}
						>
							<Icon name="down" class="size-4" /> Move down
						</button>
						<button
							type="button"
							class="btn btn-quiet text-red-800"
							aria-label="Delete {scenario.name}"
							onclick={() => (deleting = scenario)}
						>
							<Icon name="trash" class="size-4" /> Delete
						</button>
					</div>
				</div>
			</details>
		{/each}

		{#if full}<p id="{id}-full" class={['text-slate-700', tabs && 'max-w-prose']}>
				{LIMIT_TEXT}
			</p>{/if}
	</div>
{/snippet}

<Dialog
	bind:this={dialog}
	title="Scenarios"
	wide={!tabs}
	xl={tabs}
	tall={tabs}
	{onclose}
	onkeydown={keydown}
>
	<!-- A flex column with gaps, not space-y: the empty status and alert lines (display: none)
		then leave no margin under the last block shown, so the manager without the tab row is as
		tall as before L2, and the table keeps its room (§8.1, §8.2). -->
	<div class="flex flex-col gap-4 text-sm">
		{#if tabs}
			<div
				role="tablist"
				aria-label={LINEUP_TABLE_WORDS.tablist}
				class="flex border-b border-slate-200"
				tabindex="-1"
				onkeydown={tabKeydown}
			>
				{#each TABS as value (value)}
					<button
						type="button"
						role="tab"
						id="{id}-tab-{value}"
						aria-selected={tab === value}
						aria-controls="{id}-panel"
						tabindex={tab === value ? 0 : -1}
						class={[
							'-mb-px min-h-11 border-b-2 px-4 text-sm font-medium',
							tab === value
								? 'border-blue-700 text-blue-800'
								: 'border-transparent text-slate-600 hover:text-slate-900'
						]}
						onclick={() => selectTab(value)}
					>
						{value === 'cases'
							? LINEUP_TABLE_WORDS.casesTab(scenarios.length + 1)
							: LINEUP_TABLE_WORDS.lineupsTab}
					</button>
				{/each}
			</div>
		{/if}
		<!-- One place for the Cases view with or without the tab row: an undo or redo that crosses
			two pumps keeps its nodes, and so the focus (§8.9). -->
		<div
			id="{id}-panel"
			role={tabs ? 'tabpanel' : undefined}
			aria-labelledby={tabs ? `${id}-tab-${tab}` : undefined}
		>
			{#if tab === 'cases'}
				{@render cases()}
			{:else}
				<PumpLineups bind:this={lineups} onstatus={say} onalert={warn} />
			{/if}
		</div>
		{#if store.urlTooLong}
			<p
				class="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-900"
			>
				<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
				<span class={[tabs && 'max-w-prose']}>
					The link to this project is longer than {URL_LENGTH_WARNING.toLocaleString('en-US')} characters:
					some email and chat apps cut long links short. Its scenarios are part of it.
				</span>
			</p>
		{/if}
		<!-- The manager's lines (§8.1): what an action of either tab did, a refusal; each message
			drawn afresh (keyed), so the same words twice are said twice. As wide as the Pump
			lineups panel there, so a rename takes one line and the table keeps its six rows (§8.2);
			capped as the Cases prose is on the Cases tab. -->
		<p role="status" class={['break-words empty:hidden', prose && 'max-w-prose']}>
			{#key said}{status}{/key}
		</p>
		<p role="alert" class={['break-words text-red-800 empty:hidden', prose && 'max-w-prose']}>
			{#key said}{alert}{/key}
		</p>
	</div>
	{#snippet footer()}
		{#if tab === 'lineups'}
			<!-- The Pump lineups footer (§8.2): Undo and Redo of the last step, whichever it was
				(the header's are behind the dialog), named by it; New lineup; Done. -->
			<button
				type="button"
				class="btn"
				aria-label={undoName || undefined}
				aria-disabled={!store.canUndo}
				onclick={() => void history('undo')}
			>
				<Icon name="undo" class="size-4" />
				{LINEUP_TABLE_WORDS.undo}
			</button>
			<button
				type="button"
				class="btn"
				aria-label={redoName || undefined}
				aria-disabled={!store.canRedo}
				onclick={() => void history('redo')}
			>
				<Icon name="redo" class="size-4" />
				{LINEUP_TABLE_WORDS.redo}
			</button>
			<button
				type="button"
				class="btn"
				aria-disabled={full}
				title={full ? LIMIT_TEXT : undefined}
				aria-describedby={full ? `${id}-full` : undefined}
				onclick={() => {
					if (!full) void lineups?.addLineup();
				}}
			>
				<Icon name="plus" class="size-4" />
				{LINEUP_TABLE_WORDS.newLineup}
			</button>
			{#if full}<span id="{id}-full" class="sr-only">{LIMIT_TEXT}</span>{/if}
		{:else}
			<button
				type="button"
				class="btn"
				aria-disabled={full}
				title={full ? LIMIT_TEXT : undefined}
				aria-describedby={full ? `${id}-full` : undefined}
				onclick={add}
			>
				<Icon name="plus" class="size-4" /> New scenario
			</button>
		{/if}
		<button type="button" class="btn btn-primary" onclick={onclose}
			>{LINEUP_TABLE_WORDS.done}</button
		>
	{/snippet}
</Dialog>

{#if deleting}
	{@const target = deleting}
	{@const count = (target.overrides ?? []).length}
	<Dialog title="Delete scenario «{target.name}»?" onclose={() => (deleting = null)}>
		<p class="text-sm text-slate-700">
			Its {count} change{count === 1 ? '' : 's'} and its results are removed. You can undo this.
		</p>
		{#snippet footer()}
			<button type="button" class="btn" onclick={() => (deleting = null)}>Cancel</button>
			<button type="button" class="btn btn-danger" onclick={() => remove(target)}>Delete</button>
		{/snippet}
	</Dialog>
{/if}
