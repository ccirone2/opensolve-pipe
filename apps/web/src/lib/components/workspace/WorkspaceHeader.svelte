<!--
	Project name, undo / redo, solve, share and settings: one row from 640 px, two rows on phones
	held upright. Buttons that become unavailable (Undo, Redo, Solve) use aria-disabled rather than
	disabled, so keyboard focus stays on them. While a solve runs, Solve shows a spinner (with its
	label "Solving…" only for screen readers below 24rem, where the label and Cancel do not both fit)
	and Cancel (PRD §4.2), to its left, stops it; when Cancel goes with the focus on it (the solve
	cancelled or answered), Solve takes the focus. Solve keeps one width whether it is solving or
	not (both labels take their place in it, one of them invisible), so neither control appears
	under the pointer where the other was; below 22.5rem, where Cancel would not fit beside a
	labelled Solve, Solve shows its icon only, as Share and Settings do on phones. The second click
	of a double click (or double tap) does nothing, so it neither cancels the solve the first
	started nor starts another after Cancel. Keyboard activation (a click with detail 0) is not
	affected.
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import { homeHref } from '$lib/components/links';
	import Icon from '$lib/components/ui/Icon.svelte';
	import TextField from '$lib/components/ui/TextField.svelte';
	import { stringLimits } from '$lib/utils/schema-bounds';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import SettingsDialog from './SettingsDialog.svelte';
	import ShareButton from './ShareButton.svelte';

	const ws = useWorkspace();
	const store = ws.store;
	let settings = $state(false);

	const id = $props.id();
	const undoText = $derived(store.undoLabel ? `Undo ${store.undoLabel}` : 'Undo');
	const redoText = $derived(store.redoLabel ? `Redo ${store.redoLabel}` : 'Redo');
	const empty = $derived(!ws.project.components.length);
	const solving = $derived(store.results.solving);
	const canSolve = $derived(!solving && !empty);
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
		if (solving) return;
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
				onchange={(v) =>
					!!v &&
					ws.edit((p) => {
						p.metadata.name = v;
					}, 'rename project')}
			/>
		</div>
		<div role="toolbar" aria-label="Project" class="flex w-full items-center gap-1 sm:w-auto">
			<button
				type="button"
				class="btn btn-quiet btn-icon"
				aria-label={undoText}
				title={undoText}
				aria-disabled={!store.canUndo}
				onclick={() => store.undo()}
			>
				<Icon name="undo" />
			</button>
			<button
				type="button"
				class="btn btn-quiet btn-icon"
				aria-label={redoText}
				title={redoText}
				aria-disabled={!store.canRedo}
				onclick={() => store.redo()}
			>
				<Icon name="redo" />
			</button>
			<span class="flex-1"></span>
			{#if solving}
				<!-- The server stops a solve whose client has gone (D10); the results shown before stay. -->
				<button
					bind:this={cancelButton}
					type="button"
					class="btn btn-icon sm:w-auto sm:px-3"
					aria-label="Cancel solve"
					onclick={cancel}
				>
					<Icon name="close" /><span class="hidden sm:inline">Cancel</span>
				</button>
			{/if}
			<button
				bind:this={solveButton}
				type="button"
				class="btn btn-primary"
				aria-disabled={!canSolve}
				aria-describedby={empty ? `${id}-solve-reason` : undefined}
				title={empty ? 'Add a component to the network first.' : undefined}
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
			</button>
			{#if empty}
				<span id="{id}-solve-reason" class="sr-only">Add a component to the network first.</span>
			{/if}
			<ShareButton compact />
			<button
				type="button"
				class="btn btn-icon sm:w-auto sm:px-3"
				aria-label="Settings"
				onclick={() => (settings = true)}
			>
				<Icon name="settings" /><span class="hidden sm:inline">Settings</span>
			</button>
		</div>
	</div>
</header>

{#if settings}
	<SettingsDialog onclose={() => (settings = false)} />
{/if}
