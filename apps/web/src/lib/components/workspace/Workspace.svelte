<!--
	The workspace of an open project: header, the case bar (once the project has scenarios), and
	the Build (panel navigator) and Results panes — side by side on wide screens (≥ 1024 px), as
	tabs on narrow ones. It tells the fields below which case is shown (field-mode.ts): in a
	scenario only its values, names and display units can be edited.
-->
<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { provideFieldMode } from '$lib/components/ui/field-mode';
	import Icon from '$lib/components/ui/Icon.svelte';
	import PanelNavigator from '$lib/components/panel/PanelNavigator.svelte';
	import { provideLibrary } from '$lib/state/library.svelte';
	import { provideProjectStore } from '$lib/state/project.svelte';
	import { provideWorkspace, type Pane, type Workspace } from '$lib/state/workspace.svelte';
	import ResultsPanel from '$lib/components/results/ResultsPanel.svelte';
	import ScenarioBar from './ScenarioBar.svelte';
	import WorkspaceHeader from './WorkspaceHeader.svelte';

	let { workspace }: { workspace: Workspace } = $props();

	// The workspace object is fixed for the life of this component.
	const ws = provideWorkspace(untrack(() => workspace));
	provideProjectStore(ws.store);
	provideLibrary(ws.library);
	provideFieldMode({
		get scenario() {
			return ws.inScenario;
		}
	});
	const id = $props.id();

	onMount(() => {
		void ws.library.loadLibrary();
		void ws.library.loadFluids();
	});

	// Info notices fade after a while; errors stay until dismissed or replaced.
	$effect(() => {
		const notice = ws.notice;
		if (!notice || notice.kind !== 'info') return;
		const timer = setTimeout(() => {
			if (ws.notice?.id === notice.id) ws.dismissNotice();
		}, 6000);
		return () => clearTimeout(timer);
	});

	function editingText(target: EventTarget | null): boolean {
		return (
			target instanceof HTMLElement &&
			(target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
		);
	}

	function keydown(event: KeyboardEvent) {
		if (!(event.ctrlKey || event.metaKey) || event.altKey || editingText(event.target)) return;
		const key = event.key.toLowerCase();
		if (key === 'z' && !event.shiftKey) {
			event.preventDefault();
			ws.undo();
		} else if ((key === 'z' && event.shiftKey) || key === 'y') {
			event.preventDefault();
			ws.redo();
		}
	}

	/** What the Results tab marks (an icon and text): an error, invalid flags, or out of date. */
	const resultsState = $derived.by(
		(): { kind: 'error' | 'invalid' | 'stale'; text: string } | null => {
			const results = ws.store.results;
			const parts: string[] = [];
			if (results.error) parts.push('error');
			const solved = results.response?.solvedState;
			const invalid = solved ? solved.flags.filter((f) => f.severity === 'invalid').length : 0;
			if (solved && !(results.response?.success && solved.converged))
				parts.push('did not converge');
			else if (invalid) parts.push(`${invalid} physically invalid`);
			if (results.stale) parts.push('out of date');
			if (!parts.length) return null;
			const kind = results.error
				? 'error'
				: invalid || parts.includes('did not converge')
					? 'invalid'
					: 'stale';
			return { kind, text: parts.join(', ') };
		}
	);

	const PANES: readonly { value: Pane; label: string }[] = [
		{ value: 'build', label: 'Build' },
		{ value: 'results', label: 'Results' }
	];

	/** Arrow keys, Home and End move between the Build and Results tabs (WAI-ARIA tabs). */
	function tabKeydown(event: KeyboardEvent) {
		const index = PANES.findIndex((p) => p.value === ws.pane);
		const last = PANES.length - 1;
		const next =
			event.key === 'ArrowRight'
				? (index + 1) % PANES.length
				: event.key === 'ArrowLeft'
					? (index + last) % PANES.length
					: event.key === 'Home'
						? 0
						: event.key === 'End'
							? last
							: -1;
		const pane = PANES[next];
		if (!pane) return;
		event.preventDefault();
		ws.pane = pane.value;
		document.getElementById(`${id}-tab-${pane.value}`)?.focus();
	}
</script>

<svelte:window onkeydown={keydown} />

<div class="flex h-dvh flex-col bg-white">
	<WorkspaceHeader />
	<ScenarioBar />
	{#if ws.scenarios.length}
		<!-- Case switches are said here (a polite live region, present before its text). -->
		<p class="sr-only" role="status">{ws.announcement}</p>
	{/if}

	<main class="flex min-h-0 flex-1 flex-col">
		<h1 class="sr-only">{ws.project.metadata.name}</h1>
		<div
			role="tablist"
			aria-label="View"
			tabindex="-1"
			class="flex border-b border-slate-200 lg:hidden"
			onkeydown={tabKeydown}
		>
			{#each PANES as pane (pane.value)}
				<button
					type="button"
					role="tab"
					id="{id}-tab-{pane.value}"
					aria-selected={ws.pane === pane.value}
					aria-controls="{id}-{pane.value}"
					tabindex={ws.pane === pane.value ? 0 : -1}
					class={[
						'-mb-px min-h-11 flex-1 border-b-2 text-sm font-medium',
						ws.pane === pane.value
							? 'border-blue-700 text-blue-800'
							: 'border-transparent text-slate-600'
					]}
					onclick={() => (ws.pane = pane.value)}
				>
					{pane.label}
					{#if pane.value === 'results' && resultsState}
						<Icon
							name="alert"
							class={[
								'ml-1 inline size-4',
								resultsState.kind === 'stale' ? 'text-amber-700' : 'text-red-700'
							]}
						/>
						<span class="sr-only">({resultsState.text})</span>
					{/if}
				</button>
			{/each}
		</div>

		<div class="flex min-h-0 flex-1">
			<section
				id="{id}-build"
				aria-label="Build"
				class={[
					ws.pane === 'build' ? 'flex' : 'hidden',
					'min-w-0 flex-1 flex-col lg:flex lg:max-w-[52rem] lg:flex-[3] lg:border-r lg:border-slate-200'
				]}
			>
				<PanelNavigator />
			</section>
			<section
				id="{id}-results"
				aria-label="Results"
				class={[
					ws.pane === 'results' ? 'flex' : 'hidden',
					'min-w-0 flex-1 flex-col bg-slate-50/50 lg:flex lg:flex-[2]'
				]}
			>
				<ResultsPanel />
			</section>
		</div>

		{#if ws.notice}
			<div
				class="pointer-events-none fixed inset-x-0 bottom-20 z-10 flex justify-center px-4 lg:bottom-6"
			>
				<div
					role={ws.notice.kind === 'error' ? 'alert' : 'status'}
					class={[
						'pointer-events-auto flex max-w-lg items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-lg',
						ws.notice.kind === 'error'
							? 'border-red-300 bg-red-50 text-red-900'
							: 'border-slate-300 bg-white text-slate-800'
					]}
				>
					{#if ws.notice.kind === 'error'}<Icon name="alert" class="mt-0.5 size-4 shrink-0" />{/if}
					<span class="min-w-0 flex-1 py-2 break-words">{ws.notice.text}</span>
					<button
						type="button"
						class="btn btn-quiet btn-icon -my-1 -mr-2"
						aria-label="Dismiss"
						onclick={() => ws.dismissNotice()}
					>
						<Icon name="close" class="size-4" />
					</button>
				</div>
			</div>
		{/if}
	</main>
</div>
