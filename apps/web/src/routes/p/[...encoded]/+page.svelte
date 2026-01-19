<script lang="ts">
	import { onMount } from 'svelte';
	import Header from '$lib/components/Header.svelte';
	import { PanelNavigator } from '$lib/components/panel';
	import { ResultsPanel } from '$lib/components/results';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { projectStore, components, metadata } from '$lib/stores';
	import { solveNetwork, ApiError } from '$lib/api';
	import { encodeProject, tryDecodeProject } from '$lib/utils';

	type ViewMode = 'panel' | 'results';

	// Get encoded project data from URL
	let encoded = $derived($page.params.encoded || '');

	// View mode state
	let viewMode: ViewMode = $state('panel');

	// Solve state
	let isSolving = $state(false);
	let solveError = $state<string | null>(null);
	let solveSuccess = $state<{ time: number; iterations: number } | null>(null);

	// Project name from metadata
	let projectName = $derived($metadata?.name || (encoded ? 'Project' : 'New Project'));

	// Check if project has components (can solve)
	let canSolve = $derived($components.length > 0);

	// Load project from URL on mount
	onMount(() => {
		if (encoded) {
			const project = tryDecodeProject(encoded);
			if (project) {
				projectStore.load(project);
			}
		}
	});

	function handleViewModeChange(mode: ViewMode) {
		viewMode = mode;
	}

	async function handleSolve() {
		if (isSolving || !canSolve) return;

		isSolving = true;
		solveError = null;
		solveSuccess = null;

		try {
			const project = get(projectStore);
			const result = await solveNetwork(project);

			// Update store with results
			projectStore.setResults(result);

			// Show success message
			if (result.converged) {
				solveSuccess = {
					time: result.solve_time_seconds ?? 0,
					iterations: result.iterations ?? 0
				};

				// Switch to results view
				viewMode = 'results';

				// Update URL with new state (including results)
				await updateUrl();
			} else {
				solveError = result.error || 'Solution did not converge';
			}
		} catch (error) {
			if (error instanceof ApiError) {
				solveError = error.message;
			} else {
				solveError = 'An unexpected error occurred while solving';
			}
		} finally {
			isSolving = false;
		}
	}

	async function updateUrl() {
		try {
			const project = get(projectStore);
			const result = encodeProject(project);
			await goto(`/p/${result.encoded}`, { replaceState: true });
		} catch {
			// URL update failed - not critical
		}
	}

	// Keyboard shortcut handler
	function handleKeydown(event: KeyboardEvent) {
		// Ctrl+Enter or Cmd+Enter to solve
		if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
			event.preventDefault();
			handleSolve();
		}
	}

	// Auto-clear success message after 5 seconds
	$effect(() => {
		if (solveSuccess) {
			const timeout = setTimeout(() => {
				solveSuccess = null;
			}, 5000);
			return () => clearTimeout(timeout);
		}
	});
</script>

<svelte:window onkeydown={handleKeydown} />

<svelte:head>
	<title>{projectName} - OpenSolve Pipe</title>
</svelte:head>

<div class="flex min-h-screen flex-col bg-gray-50">
	<Header
		{projectName}
		{viewMode}
		onViewModeChange={handleViewModeChange}
		showViewSwitcher={true}
		onSolve={handleSolve}
		{isSolving}
		{canSolve}
	/>

	<!-- Toast Messages -->
	{#if solveError}
		<div class="fixed right-4 top-20 z-50 max-w-md animate-in fade-in slide-in-from-top-2">
			<div class="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 shadow-lg">
				<svg class="h-5 w-5 flex-shrink-0 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
				<div class="flex-1">
					<p class="text-sm font-medium text-red-800">Solve Failed</p>
					<p class="mt-1 text-sm text-red-600">{solveError}</p>
				</div>
				<button
					type="button"
					onclick={() => (solveError = null)}
					class="text-red-400 hover:text-red-600"
					aria-label="Dismiss error"
				>
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
		</div>
	{/if}

	{#if solveSuccess}
		<div class="fixed right-4 top-20 z-50 max-w-md animate-in fade-in slide-in-from-top-2">
			<div class="flex items-start gap-3 rounded-lg border border-green-200 bg-green-50 p-4 shadow-lg">
				<svg class="h-5 w-5 flex-shrink-0 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
				</svg>
				<div class="flex-1">
					<p class="text-sm font-medium text-green-800">Solution Converged</p>
					<p class="mt-1 text-sm text-green-600">
						{solveSuccess.iterations} iterations in {solveSuccess.time < 1 ? `${(solveSuccess.time * 1000).toFixed(0)} ms` : `${solveSuccess.time.toFixed(2)} s`}
					</p>
				</div>
				<button
					type="button"
					onclick={() => (solveSuccess = null)}
					class="text-green-400 hover:text-green-600"
					aria-label="Dismiss message"
				>
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
		</div>
	{/if}

	<main class="flex-1">
		{#if viewMode === 'panel'}
			<!-- Panel Navigator View -->
			<div class="mx-auto max-w-4xl p-4">
				<PanelNavigator />
			</div>
		{:else}
			<!-- Results View -->
			<div class="mx-auto max-w-4xl p-4">
				<div class="rounded-lg bg-white shadow">
					<ResultsPanel isLoading={isSolving} />
				</div>
			</div>
		{/if}
	</main>

	<!-- Mobile-friendly bottom navigation hint -->
	<div class="border-t border-gray-200 bg-white p-4 text-center text-sm text-gray-500 md:hidden">
		{#if viewMode === 'panel'}
			Swipe left/right to navigate components
		{:else}
			Scroll to view all results
		{/if}
	</div>
</div>

<style>
	@keyframes fade-in {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	@keyframes slide-in-from-top-2 {
		from {
			transform: translateY(-0.5rem);
		}
		to {
			transform: translateY(0);
		}
	}

	.animate-in {
		animation: fade-in 0.15s ease-out, slide-in-from-top-2 0.15s ease-out;
	}
</style>
