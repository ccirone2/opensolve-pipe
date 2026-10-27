<!--
	Panel navigator (SDD §3.1.1, TSD §8.1): walks the port graph one component at a time.
	Breadcrumb of the path taken, the current component's panels, Previous / Next, the path
	chooser at branches and loops, and a jump-to list of every component.
-->
<script lang="ts">
	import Icon from '$lib/components/ui/Icon.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import {
		ENTRY_KINDS,
		missingEntries,
		type ComponentKind,
		type EnteredValues,
		type MissingEntry
	} from '$lib/utils/factory';
	import { componentById, onwardFreePort, type NextOption } from '$lib/utils/graph';
	import { portLabel } from '$lib/utils/labels';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import Breadcrumb from './Breadcrumb.svelte';
	import ComponentPanel from './ComponentPanel.svelte';
	import JumpToDialog from './JumpToDialog.svelte';
	import { kindOptions } from './kinds';
	import NewComponentFields from './NewComponentFields.svelte';
	import PathChooser from './PathChooser.svelte';

	const ws = useWorkspace();
	const nav = ws.nav;

	let choosing = $state(false);
	let jumping = $state(false);
	let firstKind = $state<ComponentKind>('reservoir');
	/** Values entered for a kind with no default for them (see NewComponentFields). */
	let firstValues = $state<EnteredValues>({});
	let firstMissing = $state<readonly MissingEntry[]>([]);

	/** The current component, with the values of the case shown (the walk is the same in every case). */
	const current = $derived(
		nav.current ? (componentById(ws.project, nav.current.id) ?? nav.current) : undefined
	);
	const previous = $derived.by(() => {
		const step = nav.path[nav.path.length - 2];
		return step ? componentById(ws.project, step.componentId) : undefined;
	});
	const single = $derived.by((): NextOption | undefined => {
		const [only, ...rest] = nav.options;
		return only && !rest.length && !only.loop ? only : undefined;
	});
	const nextName = $derived(
		single ? (componentById(ws.project, single.otherId)?.name ?? single.otherId) : undefined
	);
	/**
	 * At the end of the path, a port that is not connected yet: Next opens it to connect it. The
	 * way onward: at a valve or pump that starts the walk, its outlet (see onwardFreePort).
	 */
	const openPort = $derived(
		current && !nav.options.length ? onwardFreePort(ws.project, current.id) : undefined
	);

	const nextDetail = $derived(
		nextName ??
			(nav.options.length
				? 'choose'
				: openPort
					? `connect ${portLabel(openPort.id).toLowerCase()}`
					: 'end of path')
	);

	function next() {
		if (!nav.options.length) {
			if (openPort) nav.showConnection(openPort.id);
			return;
		}
		if (nav.next() === 'choose') choosing = true;
	}

	function choose(option: NextOption) {
		choosing = false;
		nav.choose(option);
	}
</script>

<div class="flex h-full min-h-0 flex-col">
	{#if current}
		<div class="flex items-center gap-1 border-b border-slate-200 pr-1 pl-2">
			<Breadcrumb />
			<button
				type="button"
				class="btn btn-quiet shrink-0"
				aria-label="Jump to a component"
				onclick={() => (jumping = true)}
			>
				<Icon name="list" /><span class="hidden sm:inline">Jump to</span>
			</button>
		</div>

		<div class="min-h-0 flex-1 overflow-y-auto overscroll-contain">
			<ComponentPanel component={current} />
		</div>

		<nav
			aria-label="Walk the network"
			class="flex gap-2 border-t border-slate-200 bg-white p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]"
		>
			<button
				type="button"
				class="btn min-w-0 flex-1 justify-start"
				disabled={!previous}
				onclick={() => nav.previous()}
			>
				<Icon name="left" class="size-5 shrink-0" />
				<span class="truncate">
					Previous{#if previous}<span class="font-normal text-slate-600">: {previous.name}</span
						>{/if}
				</span>
			</button>
			<button
				type="button"
				class="btn min-w-0 flex-1 justify-end border-blue-700 text-blue-800"
				disabled={!nav.options.length && !openPort}
				onclick={next}
			>
				<!-- The space stays outside the inner span: Svelte drops whitespace at an element's start. -->
				<span class="truncate">Next: <span class="font-normal">{nextDetail}</span></span>
				<Icon name="right" class="size-5 shrink-0" />
			</button>
		</nav>
	{:else}
		<section class="mx-auto w-full max-w-lg space-y-4 px-4 py-8" aria-labelledby="empty-title">
			<h2 id="empty-title" class="text-xl font-semibold" tabindex="-1" data-current-heading>
				Start the network
			</h2>
			<p class="text-slate-700">
				Add the first component. A good start is a boundary: a reservoir or a fixed-pressure
				reference node. Every network needs at least one. Then add components after it, one at a
				time.
			</p>
			{#if ws.inScenario}
				<div class="flex flex-wrap items-center gap-2">
					<p class="min-w-0 flex-1 basis-48 text-slate-700">
						Switch to the base case to add a component: the layout of the network is the same in
						every scenario.
					</p>
					<button type="button" class="btn" onclick={() => ws.setCase(null)}>
						Switch to base case
					</button>
				</div>
			{:else}
				<form
					class="flex flex-wrap items-end gap-2"
					onsubmit={(event) => {
						event.preventDefault();
						firstMissing = missingEntries(firstKind, firstValues);
						if (!firstMissing.length) ws.addStandalone(firstKind, firstValues);
					}}
				>
					<SelectField
						label="First component"
						value={firstKind}
						options={kindOptions()}
						class="min-w-48 flex-1"
						onchange={(v) => {
							firstKind = v;
							firstMissing = [];
						}}
					/>
					{#if ENTRY_KINDS.includes(firstKind)}
						<div class="grid basis-full gap-3 sm:grid-cols-2">
							<NewComponentFields
								kind={firstKind}
								units={ws.units}
								bind:values={firstValues}
								bind:errors={firstMissing}
							/>
						</div>
					{/if}
					<button type="submit" class="btn btn-primary">
						<Icon name="plus" class="size-4" /> Add
					</button>
				</form>
			{/if}
		</section>
	{/if}
</div>

{#if choosing}
	<PathChooser options={nav.options} onchoose={choose} onclose={() => (choosing = false)} />
{/if}
{#if jumping}
	<JumpToDialog onclose={() => (jumping = false)} />
{/if}
