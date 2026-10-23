<!--
	Project name, undo / redo, solve, share and settings: one row from 640 px, two rows on phones
	held upright. Buttons that become unavailable (Undo, Redo, Solve) use aria-disabled rather than
	disabled, so keyboard focus stays on them.
-->
<script lang="ts">
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
	const canSolve = $derived(!store.results.solving && !empty);

	function solve() {
		if (canSolve) void ws.solve();
	}
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
			<button
				type="button"
				class="btn btn-primary"
				aria-disabled={!canSolve}
				aria-describedby={empty ? `${id}-solve-reason` : undefined}
				title={empty ? 'Add a component to the network first.' : undefined}
				onclick={solve}
			>
				<Icon name="play" class="size-4" />
				{store.results.solving ? 'Solving…' : 'Solve'}
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
