<script lang="ts">
	import Header from '$lib/components/Header.svelte';
	import { page } from '$app/stores';

	type ViewMode = 'panel' | 'results';

	// Get encoded project data from URL
	let encoded = $derived($page.params.encoded || '');

	// View mode state
	let viewMode: ViewMode = $state('panel');

	// Placeholder project name - will be decoded from URL in future
	let projectName = $derived(encoded ? 'Project View' : 'New Project');

	function handleViewModeChange(mode: ViewMode) {
		viewMode = mode;
	}
</script>

<svelte:head>
	<title>{projectName} - OpenSolve Pipe</title>
</svelte:head>

<div class="flex min-h-screen flex-col bg-gray-50">
	<Header
		{projectName}
		{viewMode}
		onViewModeChange={handleViewModeChange}
		showViewSwitcher={true}
	/>

	<main class="flex-1">
		{#if viewMode === 'panel'}
			<!-- Panel Navigator View -->
			<div class="mx-auto max-w-4xl p-4">
				<div class="rounded-lg bg-white p-6 shadow">
					<h2 class="mb-4 text-lg font-medium text-gray-800">Panel Navigator</h2>
					<p class="text-gray-600">
						Walk through your hydraulic system element by element. Edit properties, configure
						piping, and navigate the component chain.
					</p>

					{#if encoded}
						<div class="mt-4 rounded-md bg-blue-50 p-4">
							<p class="text-sm text-blue-700">
								<strong>Encoded Project Data:</strong>
								<code class="break-all text-xs">{encoded.slice(0, 100)}...</code>
							</p>
						</div>
					{:else}
						<div class="mt-4 rounded-md bg-yellow-50 p-4">
							<p class="text-sm text-yellow-700">
								No project data found. Create a new project or load an existing one.
							</p>
						</div>
					{/if}

					<!-- Placeholder for Panel Navigator -->
					<div
						class="mt-6 flex h-64 items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50"
					>
						<p class="text-gray-500">Panel Navigator will be implemented here</p>
					</div>
				</div>
			</div>
		{:else}
			<!-- Results View -->
			<div class="mx-auto max-w-4xl p-4">
				<div class="rounded-lg bg-white p-6 shadow">
					<h2 class="mb-4 text-lg font-medium text-gray-800">Results</h2>
					<p class="text-gray-600">
						View solved state with pressures, flows, velocities, and system curves.
					</p>

					<!-- Placeholder for Results Display -->
					<div
						class="mt-6 flex h-64 items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50"
					>
						<p class="text-gray-500">Results display will be implemented here</p>
					</div>
				</div>
			</div>
		{/if}
	</main>

	<!-- Mobile-friendly bottom navigation hint -->
	<div class="border-t border-gray-200 bg-white p-4 text-center text-sm text-gray-500 md:hidden">
		Swipe left/right to navigate components
	</div>
</div>
