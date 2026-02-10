<script lang="ts">
	import {
		WorkspaceToolbar,
		SidebarTabs,
		PropertyPanel,
		CommandPalette,
		StatusBar,
		BottomSheet,
		MobileNavBar,
		PumpCurveEditorPanel
	} from '$lib/components/workspace';
	import SchematicViewer from '$lib/components/schematic/SchematicViewer.svelte';
	import PanelNavigator from '$lib/components/panel/PanelNavigator.svelte';
	import ProjectConfigPanel from '$lib/components/workspace/ProjectConfigPanel.svelte';
	import ResultsPanel from '$lib/components/results/ResultsPanel.svelte';
	import ResultsViewerPanel from '$lib/components/results/ResultsViewerPanel.svelte';
	import ComponentTree from '$lib/components/workspace/ComponentTree.svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { get } from 'svelte/store';
	import { projectStore, components, metadata, navigationStore, workspaceStore, currentElementId, editingPumpCurveId, activeSidebarTab, activeResultsView } from '$lib/stores';
	import { solveNetwork, ApiError, NetworkError, TimeoutError } from '$lib/api';
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

	// Mobile state
	let isMobile = $state(false);
	let mobileTab = $state<'components' | 'settings' | 'results' | 'solve'>('components');
	let bottomSheetState = $state<'collapsed' | 'half' | 'full'>('collapsed');

	// Project name from metadata
	let projectName = $derived($metadata?.name || (encoded ? 'Project' : 'New Project'));

	// Check if project has components (can solve)
	let canSolve = $derived($components.length > 0);

	// Track if we've already loaded from URL to prevent re-loading
	let hasLoadedFromUrl = $state(false);

	// Detect mobile viewport
	$effect(() => {
		const mq = window.matchMedia('(max-width: 768px)');
		isMobile = mq.matches;
		const handler = (e: MediaQueryListEvent) => { isMobile = e.matches; };
		mq.addEventListener('change', handler);
		return () => mq.removeEventListener('change', handler);
	});

	// Open bottom sheet when component selected on mobile
	$effect(() => {
		if (isMobile && $currentElementId) {
			bottomSheetState = 'half';
		}
	});

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
			if (error instanceof NetworkError) {
				solveError = 'Could not reach the solver API. Please check your connection and try again.';
			} else if (error instanceof TimeoutError) {
				solveError = 'The solver request timed out. Try simplifying the network or try again later.';
			} else if (error instanceof ApiError) {
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

	// Focus mode state
	let focusModeActive = $derived($workspaceStore.focusMode);

	// Show pump curve editor in canvas when a curve is selected and Library tab is active
	let showPumpCurveEditor = $derived($editingPumpCurveId !== null && $activeSidebarTab === 'library');

	// Show results viewer panel in canvas when a results view is selected and Results tab is active
	let showResultsViewer = $derived($activeResultsView !== null && $activeSidebarTab === 'results');

	// Keyboard shortcuts
	function handleKeydown(event: KeyboardEvent) {
		// Ctrl+Z / Cmd+Z for undo, Ctrl+Shift+Z / Cmd+Shift+Z for redo
		if ((event.ctrlKey || event.metaKey) && event.key === 'z') {
			event.preventDefault();
			if (event.shiftKey) {
				projectStore.redo();
			} else {
				projectStore.undo();
			}
			return;
		}

		// Ctrl+Y / Cmd+Y for redo (alternative)
		if ((event.ctrlKey || event.metaKey) && event.key === 'y') {
			event.preventDefault();
			projectStore.redo();
			return;
		}

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

		// Ctrl+Shift+F for focus mode
		if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key === 'F') {
			event.preventDefault();
			workspaceStore.toggleFocusMode();
			return;
		}

		// Escape to close palette or exit focus mode
		if (event.key === 'Escape') {
			if (showCommandPalette) {
				showCommandPalette = false;
				return;
			}
			if (focusModeActive) {
				workspaceStore.setFocusMode(false);
				return;
			}
		}

		// Left/Right arrow keys to navigate components in schematic
		// Only when not typing in an input field and no modifiers
		if ((event.key === 'ArrowLeft' || event.key === 'ArrowRight') && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
			const tag = (event.target as HTMLElement)?.tagName;
			if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

			const comps = $components;
			if (comps.length === 0) return;

			const currentIndex = comps.findIndex((c) => c.id === $currentElementId);
			let newIndex: number | null = null;

			if (event.key === 'ArrowRight') {
				newIndex = currentIndex < 0 ? 0 : Math.min(currentIndex + 1, comps.length - 1);
			} else {
				newIndex = currentIndex < 0 ? comps.length - 1 : Math.max(currentIndex - 1, 0);
			}

			if (newIndex !== null) {
				event.preventDefault();
				navigationStore.navigateTo(comps[newIndex].id);
				if (!isInspectorOpen) {
					workspaceStore.setInspectorOpen(true);
				}
			}
		}
	}

	// Mobile tab switching
	function handleMobileTabChange(tab: 'components' | 'settings' | 'results' | 'solve') {
		mobileTab = tab;
		bottomSheetState = 'half';
	}

	// Workspace CSS class
	let workspaceClass = $derived(
		'workspace' +
		(focusModeActive ? ' focus-mode' : '') +
		(!isSidebarOpen || focusModeActive ? ' sidebar-collapsed' : '') +
		(!isInspectorOpen || focusModeActive ? ' inspector-collapsed' : '')
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

	<!-- Canvas: Schematic Viewer (always rendered) -->
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
			<SchematicViewer
				onComponentClick={handleSchematicComponentClick}
				selectedComponentId={$currentElementId}
				onZoomChange={(level) => workspaceStore.setCanvasZoom(level)}
			/>
		{/if}

		<!-- Pump Curve Editor: overlays left side of canvas, up to 800px -->
		{#if showPumpCurveEditor && $editingPumpCurveId}
			<div class="absolute inset-y-0 left-0 w-full max-w-[800px] border-r border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg">
				<PumpCurveEditorPanel curveId={$editingPumpCurveId} />
			</div>
		{/if}

		<!-- Results Viewer: overlays left side of canvas, up to 800px -->
		{#if showResultsViewer && $activeResultsView}
			<div class="absolute inset-y-0 left-0 w-full max-w-[800px] border-r border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg">
				<ResultsViewerPanel view={$activeResultsView} />
			</div>
		{/if}
	</div>

	<!-- Focus Mode Panel (desktop only, replaces sidebar + inspector) -->
	{#if focusModeActive && !isMobile}
		<div class="workspace-focus-panel">
			<div class="flex h-full flex-col border-t border-[var(--color-border)] bg-[var(--color-surface)]">
				<!-- Focus panel header -->
				<div class="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-1.5">
					<span class="section-heading">Focus Mode</span>
					<button
						type="button"
						onclick={() => workspaceStore.setFocusMode(false)}
						class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-subtle)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
						title="Exit focus mode (Esc)"
					>
						<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>
				<!-- PanelNavigator content -->
				<div class="min-h-0 flex-1 overflow-y-auto">
					<PanelNavigator />
				</div>
			</div>
		</div>
	{/if}

	<!-- Inspector: Property Panel (always rendered for CSS transition) -->
	<div class="workspace-inspector">
		<PropertyPanel onSolve={handleSolve} />
	</div>

	<!-- Status Bar -->
	<div class="workspace-statusbar">
		<StatusBar {isSolving} {solveError} />
	</div>
</div>

<!-- Mobile Bottom Sheet + Nav Bar (only on mobile) -->
{#if isMobile}
	<BottomSheet
		sheetState={bottomSheetState}
		onStateChange={(s) => (bottomSheetState = s)}
	>
		{#if $currentElementId && mobileTab === 'components'}
			<PanelNavigator />
		{:else if mobileTab === 'settings'}
			<ProjectConfigPanel />
		{:else if mobileTab === 'results'}
			<ResultsPanel />
		{:else}
			<ComponentTree />
		{/if}
	</BottomSheet>

	<MobileNavBar
		activeTab={mobileTab}
		onTabChange={handleMobileTabChange}
		onSolve={handleSolve}
		{isSolving}
	/>
{/if}

<!-- Command Palette (global overlay) -->
<CommandPalette
	open={showCommandPalette}
	onClose={() => (showCommandPalette = false)}
/>
