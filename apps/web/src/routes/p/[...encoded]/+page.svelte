<script lang="ts">
	import {
		WorkspaceToolbar,
		SidebarTabs,
		PropertyPanel,
		CommandPalette,
		StatusBar
	} from '$lib/components/workspace';
	import SchematicViewer from '$lib/components/schematic/SchematicViewer.svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { projectStore, components, metadata, navigationStore, workspaceStore } from '$lib/stores';
	import { solveNetwork, ApiError } from '$lib/api';
	import { encodeProject, tryDecodeProject } from '$lib/utils';

	// Get encoded project data from URL
	let encoded = $derived($page.params.encoded || '');

	// Layout state from workspace store
	let isSidebarOpen = $derived($workspaceStore.sidebarOpen);
	let isInspectorOpen = $derived($workspaceStore.inspectorOpen);
	let showCommandPalette = $state(false);

	// Project name editing
	let isEditingName = $state(false);
	let editedName = $state('');

	// Solve state
	let isSolving = $state(false);
	let solveError = $state<string | null>(null);

	// Loading state for URL decode
	let isLoading = $state(true);

	// Project name from metadata
	let projectName = $derived($metadata?.name || (encoded ? 'Project' : 'New Project'));

	// Check if project has components (can solve)
	let canSolve = $derived($components.length > 0);

	// Track if we've already loaded from URL to prevent re-loading
	let hasLoadedFromUrl = $state(false);

	// Load project from URL
	$effect(() => {
		if (encoded && !hasLoadedFromUrl) {
			const project = tryDecodeProject(encoded);
			if (project) {
				hasLoadedFromUrl = true;
				projectStore.load(project);
			}
		}
		isLoading = false;
	});

	// Handle component click from schematic
	function handleSchematicComponentClick(componentId: string) {
		navigationStore.navigateTo(componentId);
		if (!isInspectorOpen) {
			workspaceStore.setInspectorOpen(true);
		}
	}

	// Name editing
	function handleEditName() {
		editedName = projectName;
		isEditingName = true;
	}

	function saveProjectName() {
		if (editedName.trim()) {
			projectStore.updateMetadata({ name: editedName.trim() });
		}
		isEditingName = false;
	}

	function handleNameKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			event.preventDefault();
			saveProjectName();
		} else if (event.key === 'Escape') {
			isEditingName = false;
		}
	}

	// Solve
	async function handleSolve() {
		if (isSolving || !canSolve) return;

		isSolving = true;
		solveError = null;

		try {
			const project = get(projectStore);
			const result = await solveNetwork(project);
			projectStore.setResults(result);

			if (result.converged) {
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

	// Keyboard shortcuts
	function handleKeydown(event: KeyboardEvent) {
		// Ctrl+Enter or Cmd+Enter to solve
		if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
			event.preventDefault();
			handleSolve();
			return;
		}

		// Ctrl+K or Cmd+K for command palette
		if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
			event.preventDefault();
			showCommandPalette = !showCommandPalette;
			return;
		}

		// Escape to close palette
		if (event.key === 'Escape' && showCommandPalette) {
			showCommandPalette = false;
			return;
		}
	}

	// Workspace CSS class
	let workspaceClass = $derived(
		'workspace' +
		(!isSidebarOpen ? ' sidebar-collapsed' : '') +
		(!isInspectorOpen ? ' inspector-collapsed' : '')
	);
</script>

<svelte:window onkeydown={handleKeydown} />

<svelte:head>
	<title>{projectName} - OpenSolve Pipe</title>
</svelte:head>

<div class={workspaceClass}>
	<!-- Toolbar -->
	<div class="workspace-toolbar">
		{#if isEditingName}
			<!-- Inline name editor overlays the toolbar -->
			<div class="flex h-full items-center border-b border-[var(--color-border)] bg-[var(--color-surface)] px-2">
				<!-- svelte-ignore a11y_autofocus -->
				<input
					type="text"
					bind:value={editedName}
					onkeydown={handleNameKeydown}
					onblur={saveProjectName}
					class="w-64 rounded border border-[var(--color-border-focus)] bg-[var(--color-surface-elevated)] px-2 py-0.5 text-sm text-[var(--color-text)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent-muted)]"
					autofocus
				/>
			</div>
		{:else}
			<WorkspaceToolbar
				{projectName}
				{isSolving}
				{canSolve}
				{isSidebarOpen}
				{isInspectorOpen}
				onSolve={handleSolve}
				onToggleSidebar={() => workspaceStore.toggleSidebar()}
				onToggleInspector={() => workspaceStore.toggleInspector()}
				onOpenCommandPalette={() => (showCommandPalette = true)}
				onEditName={handleEditName}
			/>
		{/if}
	</div>

	<!-- Sidebar: Tabbed Navigation (always rendered for CSS transition) -->
	<div class="workspace-sidebar">
		<SidebarTabs
			onOpenCommandPalette={() => (showCommandPalette = true)}
			onSolve={handleSolve}
		/>
	</div>

	<!-- Canvas: Schematic Viewer -->
	<div class="workspace-canvas canvas-grid">
		{#if isLoading}
			<!-- Loading state for URL-encoded projects -->
			<div class="absolute inset-0 flex items-center justify-center">
				<div class="flex flex-col items-center gap-3">
					<svg class="h-8 w-8 animate-spin text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
					</svg>
					<p class="text-xs text-[var(--color-text-muted)]">Loading project...</p>
				</div>
			</div>
		{:else if $components.length === 0}
			<!-- Empty state overlay -->
			<div class="absolute inset-0 flex flex-col items-center justify-center gap-4">
				<div class="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]/80 p-8 text-center backdrop-blur-sm">
					<svg class="mx-auto h-12 w-12 text-[var(--color-text-subtle)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
					</svg>
					<h2 class="mt-3 text-base font-semibold text-[var(--color-text)]">Start Building</h2>
					<p class="mt-1 text-xs text-[var(--color-text-muted)]">
						Add components to design your hydraulic network
					</p>
					<div class="mt-4 flex justify-center gap-2">
						<button
							type="button"
							onclick={() => (showCommandPalette = true)}
							class="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-accent-text)] transition-colors hover:bg-[var(--color-accent-hover)]"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
							</svg>
							Add Component
							<span class="kbd text-[0.5rem] hidden sm:inline-flex">Ctrl+K</span>
						</button>
					</div>
				</div>
			</div>
		{:else}
			<SchematicViewer onComponentClick={handleSchematicComponentClick} />
		{/if}
	</div>

	<!-- Inspector: Property Panel (always rendered for CSS transition) -->
	<div class="workspace-inspector">
		<PropertyPanel onSolve={handleSolve} />
	</div>

	<!-- Status Bar -->
	<div class="workspace-statusbar">
		<StatusBar {isSolving} {solveError} />
	</div>
</div>

<!-- Command Palette (global overlay) -->
<CommandPalette
	open={showCommandPalette}
	onClose={() => (showCommandPalette = false)}
/>
