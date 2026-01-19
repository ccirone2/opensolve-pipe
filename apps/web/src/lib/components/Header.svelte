<script lang="ts">
	type ViewMode = 'panel' | 'results';

	interface Props {
		projectName?: string;
		viewMode?: ViewMode;
		onViewModeChange?: (mode: ViewMode) => void;
		showViewSwitcher?: boolean;
		onSolve?: () => void;
		isSolving?: boolean;
		canSolve?: boolean;
	}

	let {
		projectName = 'OpenSolve Pipe',
		viewMode = 'panel',
		onViewModeChange,
		showViewSwitcher = false,
		onSolve,
		isSolving = false,
		canSolve = true
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

<header class="sticky top-0 z-50 border-b border-gray-200 bg-white shadow-sm">
	<div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
		<div class="flex h-14 items-center justify-between">
			<!-- Left: Logo and Project Name -->
			<div class="flex items-center gap-3">
				<a href="/" class="flex items-center gap-2 text-gray-900 hover:text-gray-700">
					<svg
						class="h-6 w-6 text-blue-600"
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

			<!-- Right: Solve Button and View Mode Switcher -->
			<div class="flex items-center gap-3">
				{#if onSolve}
					<button
						type="button"
						onclick={handleSolve}
						disabled={!canSolve || isSolving}
						title="Solve network (Ctrl+Enter)"
						class="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
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
					<div class="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
						<button
							type="button"
							class="rounded-md px-3 py-1.5 text-sm font-medium transition-colors {viewMode ===
							'panel'
								? 'bg-white text-gray-900 shadow'
								: 'text-gray-600 hover:text-gray-900'}"
							onclick={() => handleViewModeChange('panel')}
						>
							Panel
						</button>
						<button
							type="button"
							class="rounded-md px-3 py-1.5 text-sm font-medium transition-colors {viewMode ===
							'results'
								? 'bg-white text-gray-900 shadow'
								: 'text-gray-600 hover:text-gray-900'}"
							onclick={() => handleViewModeChange('results')}
						>
							Results
						</button>
					</div>
				{/if}
			</div>
		</div>
	</div>
</header>
