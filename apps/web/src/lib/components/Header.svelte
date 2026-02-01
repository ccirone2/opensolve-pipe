<script lang="ts">
	import ThemeToggle from './ThemeToggle.svelte';

	type ViewMode = 'panel' | 'results';

	interface Props {
		projectName?: string;
		viewMode?: ViewMode;
		onViewModeChange?: (mode: ViewMode) => void;
		showViewSwitcher?: boolean;
		onSolve?: () => void;
		isSolving?: boolean;
		canSolve?: boolean;
		showSchematic?: boolean;
		onSchematicToggle?: () => void;
	}

	let {
		projectName = 'OpenSolve Pipe',
		viewMode = 'panel',
		onViewModeChange,
		showViewSwitcher = false,
		onSolve,
		isSolving = false,
		canSolve = true,
		showSchematic = false,
		onSchematicToggle
	}: Props = $props();

	function handleViewModeChange(mode: ViewMode) {
		if (onViewModeChange) {
			onViewModeChange(mode);
		}
	}

	function handleSolve() {
		if (onSolve && canSolve && !isSolving) {
			onSolve();
		}
	}
</script>

<header class="sticky top-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm">
	<div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
		<div class="flex h-14 items-center justify-between">
			<!-- Left: Logo and Project Name -->
			<div class="flex items-center gap-3">
				<a href="/" class="flex items-center gap-2 text-[var(--color-text)] hover:text-[var(--color-text-muted)]">
					<svg
						class="h-6 w-6 text-[var(--color-accent)]"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
						/>
					</svg>
					<span class="text-lg font-semibold">{projectName}</span>
				</a>
			</div>

			<!-- Right: Schematic Toggle, Solve Button and View Mode Switcher -->
			<div class="flex items-center gap-3">
				{#if onSchematicToggle}
					<button
						type="button"
						onclick={onSchematicToggle}
						title={showSchematic ? 'Hide schematic' : 'Show schematic'}
						class="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-colors {showSchematic
							? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10 text-[var(--color-accent)]'
							: 'border-[var(--color-border)] bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)]'}"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"
							/>
						</svg>
						<span class="hidden sm:inline">Schematic</span>
					</button>
				{/if}

				{#if onSolve}
					<button
						type="button"
						onclick={handleSolve}
						disabled={!canSolve || isSolving}
						title="Solve network (Ctrl+Enter)"
						class="inline-flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-[var(--color-accent-text)] transition-colors hover:bg-[var(--color-accent-hover)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
					>
						{#if isSolving}
							<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
								<circle
									class="opacity-25"
									cx="12"
									cy="12"
									r="10"
									stroke="currentColor"
									stroke-width="4"
								></circle>
								<path
									class="opacity-75"
									fill="currentColor"
									d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
								></path>
							</svg>
							<span>Solving...</span>
						{:else}
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M13 10V3L4 14h7v7l9-11h-7z"
								/>
							</svg>
							<span>Solve</span>
						{/if}
					</button>
				{/if}

				{#if showViewSwitcher}
					<div class="inline-flex rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-1">
						<button
							type="button"
							class="rounded-md px-3 py-1.5 text-sm font-medium transition-colors {viewMode ===
							'panel'
								? 'bg-[var(--color-surface)] text-[var(--color-text)] shadow'
								: 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'}"
							onclick={() => handleViewModeChange('panel')}
						>
							Build
						</button>
						<button
							type="button"
							class="rounded-md px-3 py-1.5 text-sm font-medium transition-colors {viewMode ===
							'results'
								? 'bg-[var(--color-surface)] text-[var(--color-text)] shadow'
								: 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'}"
							onclick={() => handleViewModeChange('results')}
						>
							Results
						</button>
					</div>
				{/if}

				<ThemeToggle />
			</div>
		</div>
	</div>
</header>
