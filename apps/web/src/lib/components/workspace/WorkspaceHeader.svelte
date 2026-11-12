<!--
	Project name, undo / redo, solve, share and settings: one row from 640 px, two rows on phones
	held upright. Buttons that become unavailable (Undo, Redo, Solve) use aria-disabled rather than
	disabled, so keyboard focus stays on them. While a solve runs, Solve shows a spinner (with its
	label "Solving…" only for screen readers below 24rem, where the label and Cancel do not both fit)
	and Cancel (PRD §4.2), to its left, stops it; when Cancel goes with the focus on it (the solve
	cancelled or answered), Solve takes the focus, or the Scenarios menu's Solve all while that menu
	is open (below). Solve keeps one width whether it is solving or not (both labels take their
	place in it, one of them invisible), so neither control appears under the pointer where the
	other was; below 22.5rem, where Cancel would not fit beside a labelled Solve, Solve shows its
	icon only, as Share does on phones (Settings below 768 px and Scenarios below 1024 px, so the
	project name keeps its room in the one row from 640 px). The second click of a double click (or
	double tap) does nothing, so it neither cancels the solve the first started nor starts another
	after Cancel. Keyboard activation (a click with detail 0) is not affected.

	Scenarios (proposal scenario-manager.md §6.2): the Scenarios button, right after the project
	name (it ends the first row on phones), opens the scenario manager, or once the project has
	scenarios the Scenarios menu (CaseMenu), and counts the scenarios. It is offered once the
	network has a component, or the project has scenarios.
	Solve solves the case shown; once the project has scenarios its accessible name names the case
	("Solve Winter"). While Solve all runs, Solve shows its spinner and Cancel stops the run. A solve
	goes on after a case switch: Solve keeps its spinner and Cancel, which then names the case it
	stops ("Cancel solving Winter"), whichever case is shown.

	One Solve, one Solve all (build-density.md §19; the owner, 2026-11-12): Solve is this header's,
	always in view; Solve all is the Scenarios menu's first control, with Ctrl/⌘+Shift+Enter, and no
	pane repeats either. While a case's results are missing or out of date (and the network has a
	component), the Scenarios badge turns amber and shows ▶ and that count instead of the teal
	scenario count, counting down as Solve all answers each case; the button's name and title say
	it ("Scenarios (6), 7 cases to solve"). The word and the inline badge show from 1024 px (from
	768 to 1023 px the button is an icon with the corner badge, as on phones), so the project name
	keeps its room while a solve runs. Its spinner keeps Icon's 20 px.

	The menu follows its button in the page (one wrapper holds both), so Tab goes Scenarios → menu
	→ the Project toolbar and Shift+Tab from the menu's first control returns to Scenarios; under
	the header on phones, under its button from 640 px. It closes on Escape in it or on its button
	(the focus back on Scenarios), a case chosen, a press outside, the focus leaving it, its button
	and Cancel (WCAG 2.4.11: never left open over the control that has the focus; a focusout to
	nowhere, a window switch, does not count) and a run that ran to its end. A press on Cancel is
	not outside: a cancelled or stopped run keeps it open with its line saying so (build-density.md
	§13 item 4), and the focus, which the press gave Cancel, goes back into it, to Solve all (which
	resumes the run), when Cancel goes, so Escape and a Tab past it still close it. While it is
	closed, the header says Solve all's progress, and once a cancel made while it was closed, for
	screen readers (never again at a later close: one announcement per message); a network stop
	raises an alert naming the cases left, which goes when Solve all runs again or nothing is left
	to solve (with the menu open, its own line says each).

	Short landscape screens (at most 20 rem tall, at least 35.5 rem wide): the header is one row
	pinned to the top, so Solve is always in view, above the panes' layers (z-[45]: the trace's
	side panel, z-40, scrolls under it from 1024 px); its height is measured into `--header-h` for
	`scroll-padding-top` (routes/layout.css) and the menu's height. Narrower short windows (400 %
	zoom) scroll as one page (build-density.md §11 item 14, WCAG 1.4.10).

	The fluid chip (Water · 20 °C, the case's fluid) keeps the fluid every result depends on in
	view and opens the settings at the Fluid section. It is shown from 1024 px: below that the
	project name needs the room, and the fluid is in Settings and first in the results' Summary.

	Ctrl/⌘+Enter solves from anywhere in the workspace but a dialog (Workspace.svelte); Solve says
	so in its tooltip and aria-keyshortcuts. Ctrl/⌘+Shift+Enter runs Solve all once the project has
	scenarios; the Scenarios title and the menu's Solve all say so.

	Goal seek (proposal goal-seek.md §6.8): while one runs, Solve is unavailable with the reason (no
	spinner: it is not solving) and Cancel ("Cancel goal seek") stops the goal seek, also with its
	dialog closed. One request at a time: Solve reads the store's `calculating`.

	The project library (CLAUDE.md D22; proposal project-library.md §6.1): Library, before the fluid
	chip, opens its dialog; an icon, labelled from 1280 px (at 1024 px the label would leave the
	project name about 50 px while a solve runs). Below 1024 px, while a solve or goal seek runs,
	Cancel takes its place, which keeps the row's fit (320 px upright; the project name's room in
	the one row from 640 px); below 640 px the two are the same width, so Solve, Share and Settings
	do not move. Cancel takes Library's focus with its place (a solve started with Ctrl+Enter while
	Library has the focus), so the focus never falls to the page, and gives it back to Library when
	it goes. When Cancel goes, Library comes back under the pointer, so its click ignores the
	second click of a double click (or double tap), as Solve's and Cancel's do: a double click on
	Cancel does not open the library. The library is also opened from the pickers that use it and
	from a trace.
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { homeHref } from '$lib/components/links';
	import Icon from '$lib/components/ui/Icon.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { fluidChipText } from '$lib/utils/labels';
	import { stringLimits } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { calculatingReason } from '$lib/utils/goal-seek';
	import CaseMenu from './CaseMenu.svelte';
	import ProjectLibrary from './ProjectLibrary.svelte';
	import ScenarioManager from './ScenarioManager.svelte';
	import SettingsDialog from './SettingsDialog.svelte';
	import ShareButton from './ShareButton.svelte';

	const ws = useWorkspace();
	const store = ws.store;
	const count = $derived(ws.scenarios.length);
	/** The case Solve solves, for its accessible name once the project has scenarios. */
	const caseLabel = $derived(count ? ` ${ws.caseName(store.activeCase)}` : '');

	const id = $props.id();
	const undoText = $derived(store.undoLabel ? `Undo ${store.undoLabel}` : 'Undo');
	const redoText = $derived(store.redoLabel ? `Redo ${store.redoLabel}` : 'Redo');
	const empty = $derived(!ws.project.components.length);
	/** The case's fluid in a few words, in display units ("Water · 20 °C"). */
	const fluidText = $derived(fluidChipText(ws.project.fluid, ws.units));
	const running = $derived(!!store.run);
	/** A solve in flight, of the case shown or another (D10: it can always be cancelled). */
	const solvingCase = $derived(store.solvingCase);
	const solving = $derived(solvingCase !== undefined || running);
	/** A goal seek in flight: Cancel stops it; Solve waits (one request at a time). */
	const seeking = $derived(store.calculating === 'goalSeek');
	const cancelLabel = $derived(
		seeking
			? 'Cancel goal seek'
			: running
				? 'Cancel solving all cases'
				: solvingCase !== undefined && solvingCase !== store.activeCase
					? `Cancel solving ${ws.caseName(solvingCase)}`
					: 'Cancel solve'
	);
	const canSolve = $derived(store.calculating === null && !empty);
	/** Why Solve is unavailable, said with it: an empty network, or a goal seek running. */
	const solveReason = $derived(
		empty
			? 'Add a component to the network first.'
			: seeking
				? calculatingReason('goalSeek', 'solve', true)
				: ''
	);
	/**
	 * The cases Solve all would solve, for the Scenarios badge (build-density.md §19): none on an
	 * empty network, where Solve all cannot run (the teal scenario count stays).
	 */
	const toSolve = $derived(count && !empty ? ws.solveAllState.count : 0);
	const toSolveText = $derived(`${toSolve} case${toSolve === 1 ? '' : 's'} to solve`);
	const scenariosName = $derived(
		count ? `Scenarios (${count})${toSolve ? `, ${toSolveText}` : ''}` : 'Scenarios'
	);
	const scenariosTitle = $derived(
		count
			? `Case shown: ${ws.caseName(store.activeCase)}${
					toSolve ? ` · ${toSolveText} (Solve all: Ctrl+Shift+Enter or ⌘+Shift+Enter)` : ''
				}`
			: undefined
	);
	/**
	 * The Scenarios menu (CaseMenu, build-density.md §13, §19): Solve all and the case shown, once
	 * the project has scenarios; without any, the button opens the manager.
	 */
	let casesOpen = $state(false);
	let scenariosButton: HTMLButtonElement | undefined = $state();
	/** The button and its menu, one after the other in the page. */
	let casesArea: HTMLElement | undefined = $state();
	let casesPanel: HTMLElement | undefined = $state();
	const casesId = `${id}-cases`;
	/**
	 * A cancel of Solve all made with the menu closed, said once by the header (below): set when
	 * the stop comes, gone when the menu opens (its own line says it) or the next calculation
	 * starts, so no later close of the menu says it again (one announcement per message). Its
	 * state stays in the store's runStop; this is the event.
	 */
	let cancelSaid = $state('');
	/**
	 * Said for screen readers while the menu is closed (its own line says each when open): Solve
	 * all's progress, then a cancel, once. A network stop is an alert instead (below): one
	 * announcement per message.
	 */
	const runText = $derived.by(() => {
		const run = store.run;
		if (run) {
			return `Solving ${run.index + 1} of ${run.cases.length}: ${ws.caseName(run.cases[run.index] ?? null)}…`;
		}
		return cancelSaid;
	});
	$effect(() => {
		if (solving || seeking) cancelSaid = '';
	});

	/** The manager on the tab last used (CLAUDE.md D24, proposal pump-lineups.md §8.1). */
	function openManager() {
		casesOpen = false;
		ws.openManager();
	}

	async function toggleCases() {
		if (!count) {
			openManager();
			return;
		}
		casesOpen = !casesOpen;
		if (casesOpen) {
			cancelSaid = '';
			await tick();
			// Solve all when it can run (the step the menu is opened for), else the case shown.
			(
				casesPanel?.querySelector<HTMLElement>('[data-solve-all]:not([aria-disabled="true"])') ??
				casesPanel?.querySelector<HTMLElement>('select')
			)?.focus();
		}
	}

	function closeCases(focusButton: boolean) {
		casesOpen = false;
		if (focusButton) scenariosButton?.focus();
	}

	/** Escape closes it from anywhere in it or on its button (Shift+Tab from Solve all). */
	function casesKeydown(event: KeyboardEvent) {
		if (event.key !== 'Escape' || !casesOpen) return;
		event.preventDefault();
		closeCases(true);
	}

	/**
	 * Outside the menu: not in it or its button (which toggles it), nor the header's Cancel, so a
	 * pointer cancel keeps the run's line in sight (build-density.md §13 item 4, §19).
	 */
	const outsideCases = (node: Node) =>
		!casesArea?.contains(node) && !(cancelButton && cancelButton.contains(node));

	// Closed by a press outside it.
	$effect(() => {
		if (!casesOpen) return;
		const outside = (event: PointerEvent) => {
			if (outsideCases(event.target as Node)) closeCases(false);
		};
		document.addEventListener('pointerdown', outside);
		return () => document.removeEventListener('pointerdown', outside);
	});
	/**
	 * Closed when the focus leaves it and its button, or Cancel (which a press keeps it open for),
	 * for the page (WCAG 2.4.11: a Tab past "Manage scenarios…" left it open over the control
	 * focused). No relatedTarget (a window switch, the panel hidden, Cancel gone) is not a move away.
	 */
	function casesFocusout(event: FocusEvent) {
		const to = event.relatedTarget;
		if (casesOpen && to instanceof Node && outsideCases(to)) closeCases(false);
	}
	// A Solve all that ran to its end closes the menu (its results are in the panes); one that was
	// cancelled or stopped keeps it open, with its line saying so.
	let wasRunning = false;
	$effect(() => {
		const now = !!store.run;
		if (wasRunning && !now && !untrack(() => store.runStop)) casesOpen = false;
		wasRunning = now;
	});
	// No scenarios left (all deleted): nothing to choose.
	$effect(() => {
		if (!count) casesOpen = false;
	});
	/**
	 * A network error stopped Solve all with the menu closed: an alert says so and names the cases
	 * left, which the badge keeps counting (build-density.md §19). With the menu open its line says
	 * it, so nothing is raised. Only a new stop: not one there when the header was drawn. The
	 * alert goes when Solve all runs again (a new stop, none, comes with each run) or nothing is
	 * left to solve (the cases it names solved with Solve): an error notice otherwise stays until
	 * dismissed, and would name cases no longer left. A cancel made with the menu closed is said
	 * once (cancelSaid).
	 */
	let seenStop = untrack(() => store.runStop);
	/** The id of the notice the last network stop raised, while it may still be shown. */
	let stopAlert = 0;
	function dismissStopAlert() {
		if (stopAlert && untrack(() => ws.notice?.id) === stopAlert) ws.dismissNotice();
		stopAlert = 0;
	}
	$effect(() => {
		if (!toSolve) dismissStopAlert();
	});
	$effect(() => {
		const stop = store.runStop;
		if (stop === seenStop) return;
		seenStop = stop;
		const open = untrack(() => casesOpen);
		cancelSaid =
			stop?.reason === 'cancelled' && !open
				? 'Solve all was cancelled: the cases not solved keep what they had.'
				: '';
		dismissStopAlert();
		if (stop?.reason !== 'network' || open) return;
		const left = untrack(() => store.casesToSolve().length);
		const message = stop.message.trim();
		const said = message
			? `Solve all stopped after a network error: ${message}${/[.!?…]$/.test(message) ? '' : '.'}`
			: 'Solve all stopped after a network error.';
		const rest = left
			? ` Solve all, in the Scenarios menu, solves ${left === 1 ? 'the case left' : `the ${left} cases left`}.`
			: '';
		ws.notify('error', said + rest);
		stopAlert = untrack(() => ws.notice?.id ?? 0);
	});

	/**
	 * The header's height, measured into `--header-h` on the root element (a pinned bar's height is
	 * measured, never a constant: ui-guide): `scroll-padding-top` keeps a focused control clear of
	 * the row pinned on short landscape screens (routes/layout.css), and the menu fits under it.
	 */
	let headerElement: HTMLElement | undefined = $state();
	$effect(() => {
		const header = headerElement;
		if (!header || typeof ResizeObserver === 'undefined') return;
		const root = document.documentElement;
		const observer = new ResizeObserver(() =>
			root.style.setProperty('--header-h', `${header.offsetHeight}px`)
		);
		observer.observe(header);
		return () => {
			observer.disconnect();
			root.style.removeProperty('--header-h');
		};
	});

	let solveButton: HTMLButtonElement | undefined = $state();
	let cancelButton: HTMLButtonElement | undefined = $state();

	/** A click after the first of a double click (or double tap): `detail` counts them. */
	const repeated = (event: MouseEvent) => event.detail > 1;

	function solve(event: MouseEvent) {
		if (canSolve && !repeated(event)) void ws.solve();
	}

	function cancel(event: MouseEvent) {
		if (!repeated(event)) store.cancelSolve();
	}

	let libraryButton: HTMLButtonElement | undefined = $state();
	/** Cancel took the focus from Library, whose place it took: Library takes it back. */
	let cancelFromLibrary = false;
	const shown = (element: HTMLElement) => element.getClientRects().length > 0;

	$effect.pre(() => {
		if (solving || seeking) {
			// Before the DOM hides Library (below 1024 px) as a calculation starts: if it has the
			// focus, Cancel, which takes its place, takes the focus, rather than <body>.
			const library = untrack(() => libraryButton);
			if (library && document.activeElement === library) {
				void tick().then(() => {
					if (shown(library) || !cancelButton) return;
					cancelButton.focus();
					cancelFromLibrary = true;
				});
			}
			return;
		}
		// Before the DOM drops Cancel at the end of a calculation: if it has the focus, Solve takes
		// it, or Library when Cancel had taken the focus from it. With the Scenarios menu still
		// open (a press on Cancel keeps it open, and gives Cancel the focus), its Solve all takes
		// it, inside the menu: on Solve, outside it, the menu would stay open over the controls a
		// Tab then reaches, and Escape would not reach it (WCAG 2.4.11). A run that ran to its end
		// has closed the menu by then.
		const cancel = untrack(() => cancelButton);
		const back = cancelFromLibrary;
		cancelFromLibrary = false;
		if (cancel && document.activeElement === cancel) {
			void tick().then(() => {
				const inMenu = casesOpen
					? casesPanel?.querySelector<HTMLElement>('[data-solve-all]')
					: undefined;
				const library = libraryButton;
				if (inMenu) inMenu.focus();
				else if (back && library && shown(library)) library.focus();
				else solveButton?.focus();
			});
		}
	});
</script>

<!-- Pinned, one row, on short landscape screens (build-density.md §19), above the panes' layers:
	the trace's side panel (z-40, later in the page) scrolls under it, not over Solve. -->
<header
	bind:this={headerElement}
	class="relative border-b border-slate-200 bg-white short:min-[35.5rem]:sticky short:min-[35.5rem]:top-0 short:min-[35.5rem]:z-[45]"
>
	<!-- 44 px controls (touch targets, held by the e2e suite) with 2 px around them: two rows on
		a phone, one from 640 px (build-density.md §7), and one with no room around it on a short
		landscape screen (§19: at most 48 px, 15 % of 320). -->
	<div
		class="flex flex-wrap items-center gap-x-2 gap-y-0.5 px-2 py-0.5 sm:flex-nowrap short:min-[35.5rem]:flex-nowrap short:min-[35.5rem]:py-0"
	>
		<a href={homeHref()} class="btn btn-quiet btn-icon" aria-label="OpenSolve Pipe home">
			<Icon name="home" />
		</a>
		<div class="min-w-0 flex-1 basis-40">
			<TextField
				label="Project name"
				hideLabel
				value={ws.project.metadata.name}
				required
				maxlength={stringLimits('ProjectMetadata', 'name').maxLength}
				inputClass="border-transparent font-semibold hover:border-slate-300 focus:border-slate-400"
				shared
				onchange={(v) =>
					!!v &&
					ws.edit((p) => {
						p.metadata.name = v;
					}, 'rename project')}
			/>
		</div>
		<!-- Offered once there is a network to vary, or scenarios to manage. The menu follows its
			button in the page (Tab order), under the header below 640 px (the wrapper is not
			positioned there), under its button from 640 px. -->
		{#if !empty || count}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				bind:this={casesArea}
				class="shrink-0 sm:relative"
				onfocusout={casesFocusout}
				onkeydown={casesKeydown}
			>
				<button
					bind:this={scenariosButton}
					type="button"
					class={[
						'btn btn-icon relative shrink-0 lg:w-auto lg:px-3',
						ws.inScenario && 'border-teal-600 bg-teal-50 text-teal-950'
					]}
					aria-expanded={count ? casesOpen : undefined}
					aria-controls={count ? casesId : undefined}
					title={scenariosTitle}
					aria-label={scenariosName}
					onclick={() => void toggleCases()}
				>
					<!-- Its label from 1024 px: from 640 px the one row also holds Cancel with its
						text, and the amber badge is wider than the teal (build-density.md §19). -->
					<Icon
						name={running ? 'spinner' : 'layers'}
						class={['size-5', running && 'motion-safe:animate-spin']}
					/><span class="hidden lg:inline">Scenarios</span>
					{#if count}
						<!-- The count of cases to solve, amber with ▶ (not by colour alone, WCAG 1.4.1),
							else the teal scenario count; the button's name says both. In the pinned
							row (no room above the button) 1 px higher than the button, not 4, so the
							screen's top edge does not cut it. -->
						<span
							class={[
								'absolute -top-1 -right-1 flex min-w-5 items-center justify-center gap-px rounded-full px-1 text-xs leading-5 font-semibold lg:static short:min-[35.5rem]:-top-px',
								toSolve
									? 'bg-amber-400 text-amber-950 lg:bg-amber-100 lg:text-amber-900'
									: 'bg-teal-700 text-white lg:bg-teal-100 lg:text-teal-900'
							]}
							aria-hidden="true"
							>{#if toSolve}<Icon
									name="play"
									class="size-2.5 shrink-0 fill-current"
								/>{toSolve}{:else}{count}{/if}</span
						>
					{/if}
				</button>
				{#if count}
					<!-- The Scenarios menu: over the panes; Escape (on the wrapper), a press outside
						or the focus leaving closes it. z-40: above the panes' sticky chrome, the
						Pumps tab's pinned section nav (z-[35]) and the tables' sticky cells (z-30), so
						none takes a press meant for it (pumps-results-layout.md §5.4); the trace panel
						and a sheet's backdrop (z-40, later in the page) still draw over it, as before,
						but on a short screen, where the pinned header (z-[45]) holds it above them.
						There it scrolls within what is left under the header. -->
					<div
						bind:this={casesPanel}
						id={casesId}
						hidden={!casesOpen}
						class="absolute top-full z-40 mt-1 w-[min(26rem,calc(100vw-1rem))] rounded-lg border border-slate-200 bg-white p-3 shadow-lg max-sm:right-2 sm:left-0 short:max-h-[calc(100dvh-var(--header-h,3rem)-0.5rem)] short:overflow-y-auto"
					>
						<CaseMenu onmanage={openManager} onchoose={() => closeCases(true)} />
					</div>
				{/if}
			</div>
		{/if}
		<div
			role="toolbar"
			aria-label="Project"
			class="flex w-full items-center gap-1 sm:w-auto short:min-[35.5rem]:w-auto"
		>
			<button
				type="button"
				class="btn btn-quiet btn-icon"
				aria-label={undoText}
				title={undoText}
				aria-disabled={!store.canUndo}
				onclick={() => ws.undo()}
			>
				<Icon name="undo" />
			</button>
			<button
				type="button"
				class="btn btn-quiet btn-icon"
				aria-label={redoText}
				title={redoText}
				aria-disabled={!store.canRedo}
				onclick={() => ws.redo()}
			>
				<Icon name="redo" />
			</button>
			<span class="flex-1"></span>
			<!-- The project library (CLAUDE.md D22), next to the fluid. Labelled from 1280 px; below
				1024 px, while a calculation runs, Cancel takes its place (below 640 px the same
				width, so Solve does not move). A repeated click is ignored, as Solve's and Cancel's:
				when Cancel goes, Library comes back under the pointer. -->
			<button
				bind:this={libraryButton}
				type="button"
				class={[
					'btn btn-quiet btn-icon xl:w-auto xl:px-3',
					(solving || seeking) && 'max-lg:hidden'
				]}
				aria-label="Project library"
				title="Project library: pipe specs and resistances with their sources"
				aria-haspopup="dialog"
				onclick={(event) => {
					if (!repeated(event)) ws.openLibrary();
				}}
			>
				<Icon name="book" /><span class="hidden xl:inline">Library</span>
			</button>
			<!-- The fluid every result depends on, in view; it opens its settings. From 1024 px only:
				below that the header's rows have no room left for it beside the project name. -->
			<button
				type="button"
				class="btn btn-quiet hidden min-w-0 px-2 text-sm font-normal text-slate-700 lg:inline-flex"
				aria-label="Fluid: {fluidText}"
				title="Fluid: {fluidText}"
				onclick={() => {
					ws.settingsSection = 'fluid';
					ws.settingsOpen = true;
				}}
			>
				<Icon name="droplet" class="size-4 shrink-0 text-sky-700" />
				<span class="max-w-[14rem] truncate">{fluidText}</span>
			</button>
			{#if solving || seeking}
				<!-- The server stops a solve whose client has gone (D10); the results shown before stay. -->
				<button
					bind:this={cancelButton}
					type="button"
					class="btn btn-icon sm:w-auto sm:px-3"
					aria-label={cancelLabel}
					onclick={cancel}
					onfocusout={casesFocusout}
				>
					<Icon name="close" /><span class="hidden sm:inline">Cancel</span>
				</button>
			{/if}
			<button
				bind:this={solveButton}
				type="button"
				class="btn btn-primary"
				data-solve-button
				aria-disabled={!canSolve}
				aria-describedby={solveReason ? `${id}-solve-reason` : undefined}
				aria-keyshortcuts="Control+Enter Meta+Enter"
				title={solveReason || 'Solve (Ctrl+Enter or ⌘+Enter)'}
				onclick={solve}
			>
				<Icon
					name={solving ? 'spinner' : 'play'}
					class={['size-4', solving && 'motion-safe:animate-spin']}
				/>
				<!-- Both labels in one grid cell: the button keeps the wider one's width (below 24rem
					Solve's: Solving… is then for screen readers only; below 22.5rem, both are). -->
				<span class="grid max-[22.5rem]:sr-only">
					<span class={['col-start-1 row-start-1', solving && 'invisible']} aria-hidden={solving}
						>Solve</span
					>
					<span
						class={['col-start-1 row-start-1 max-[24rem]:sr-only', !solving && 'invisible']}
						aria-hidden={!solving}>Solving…</span
					>
				</span>
				{#if caseLabel}<span class="sr-only">{caseLabel}</span>{/if}
			</button>
			{#if solveReason}
				<span id="{id}-solve-reason" class="sr-only">{solveReason}</span>
			{/if}
			<ShareButton compact />
			<!-- Its label from 768 px (the Scenarios button's from 1024 px, build-density.md §19): at
				640 px the one row also holds Cancel with its text, and the project name needs its
				room. -->
			<button
				type="button"
				class="btn btn-icon md:w-auto md:px-3"
				aria-label="Settings"
				onclick={() => (ws.settingsOpen = true)}
			>
				<Icon name="settings" /><span class="hidden md:inline">Settings</span>
			</button>
		</div>
	</div>
	{#if count}
		<p class="sr-only" role="status">{casesOpen ? '' : runText}</p>
	{/if}
</header>

{#if ws.settingsOpen}
	<SettingsDialog onclose={() => (ws.settingsOpen = false)} />
{/if}
{#if ws.libraryOpen}
	<ProjectLibrary onclose={() => ws.closeLibrary()} />
{/if}
{#if ws.managerOpen}
	<ScenarioManager onclose={() => ws.closeManager()} />
{/if}
