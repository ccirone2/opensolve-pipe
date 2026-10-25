<!--
	Project name, undo / redo, solve, share and settings: one row from 640 px, two rows on phones
	held upright. Buttons that become unavailable (Undo, Redo, Solve) use aria-disabled rather than
	disabled, so keyboard focus stays on them. While a solve runs, Solve shows a spinner (with its
	label "Solving…" only for screen readers below 24rem, where the label and Cancel do not both fit)
	and Cancel (PRD §4.2), to its left, stops it; when Cancel goes with the focus on it (the solve
	cancelled or answered), Solve takes the focus. Solve keeps one width whether it is solving or
	not (both labels take their place in it, one of them invisible), so neither control appears
	under the pointer where the other was; below 22.5rem, where Cancel would not fit beside a
	labelled Solve, Solve shows its icon only, as Share does on phones (Settings and Scenarios below
	768 px, so the project name keeps its room in the one row from 640 px). The second click
	of a double click (or double tap) does nothing, so it neither cancels the solve the first
	started nor starts another after Cancel. Keyboard activation (a click with detail 0) is not
	affected.

	Scenarios (proposal scenario-manager.md §6.2): the Scenarios button, right after the project
	name (it ends the first row on phones), opens the scenario manager and counts the scenarios.
	Solve solves the case shown; once the project has scenarios its accessible name names the case
	("Solve Winter"). While Solve all runs, Solve shows its spinner and Cancel stops the run. A solve
	goes on after a case switch: Solve keeps its spinner and Cancel, which then names the case it
	stops ("Cancel solving Winter"), whichever case is shown.

	Goal seek (proposal goal-seek.md §6.8): while one runs, Solve is unavailable with the reason (no
	spinner: it is not solving) and Cancel ("Cancel goal seek") stops the goal seek, also with its
	dialog closed. One request at a time: Solve reads the store's `calculating`.
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { homeHref } from '$lib/components/links';
	import Icon from '$lib/components/ui/Icon.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { stringLimits } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { calculatingReason } from '$lib/utils/goal-seek';
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

	// Before the DOM drops Cancel at the end of a solve: if it has the focus, Solve takes it.
	$effect.pre(() => {
		if (solving || seeking) return;
		const cancel = untrack(() => cancelButton);
		if (cancel && document.activeElement === cancel) void tick().then(() => solveButton?.focus());
	});
</script>

<header class="border-b border-slate-200 bg-white">
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1 px-2 py-1 sm:flex-nowrap">
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
		<button
			type="button"
			class="btn btn-icon relative shrink-0 md:w-auto md:px-3"
			aria-label={count ? `Scenarios (${count})` : 'Scenarios'}
			onclick={() => {
				ws.managerFocus = null;
				ws.managerOpen = true;
			}}
		>
			<!-- Its label from 768 px: at 640 px the one row also holds Cancel with its text. -->
			<Icon name="layers" /><span class="hidden md:inline">Scenarios</span>
			{#if count}
				<span
					class="absolute -top-1 -right-1 min-w-5 rounded-full bg-teal-700 px-1 text-center text-xs leading-5 font-semibold text-white md:static md:bg-teal-100 md:text-teal-900"
					aria-hidden="true">{count}</span
				>
			{/if}
		</button>
		<div role="toolbar" aria-label="Project" class="flex w-full items-center gap-1 sm:w-auto">
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
			{#if solving || seeking}
				<!-- The server stops a solve whose client has gone (D10); the results shown before stay. -->
				<button
					bind:this={cancelButton}
					type="button"
					class="btn btn-icon sm:w-auto sm:px-3"
					aria-label={cancelLabel}
					onclick={cancel}
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
				title={solveReason || undefined}
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
			<!-- Its label from 768 px, as the Scenarios button's: at 640 px the one row also holds
				Cancel with its text, and the project name needs its room. -->
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
</header>

{#if ws.settingsOpen}
	<SettingsDialog onclose={() => (ws.settingsOpen = false)} />
{/if}
{#if ws.managerOpen}
	<ScenarioManager
		onclose={() => {
			ws.managerOpen = false;
			ws.managerFocus = null;
		}}
	/>
{/if}
