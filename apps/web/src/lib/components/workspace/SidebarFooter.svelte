<script lang="ts">
	let showShortcuts = $state(false);

	const shortcuts = [
		{ keys: 'Ctrl+K', action: 'Add Component' },
		{ keys: 'Ctrl+Enter', action: 'Solve Network' },
		{ keys: 'Ctrl+Z', action: 'Undo' },
		{ keys: 'Ctrl+Shift+Z', action: 'Redo' },
		{ keys: 'Ctrl+Y', action: 'Redo (alt)' },
		{ keys: 'Ctrl+Shift+F', action: 'Toggle Focus Mode' },
		{ keys: 'Ctrl+1', action: 'Components Tab' },
		{ keys: 'Ctrl+2', action: 'Config Tab' },
		{ keys: 'Ctrl+3', action: 'Results Tab' },
		{ keys: 'Ctrl+4', action: 'Library Tab' },
		{ keys: 'Escape', action: 'Close Palette / Exit Focus' },
	];

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			showShortcuts = false;
		}
	}

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) {
			showShortcuts = false;
		}
	}
</script>

<div
	class="flex items-center border-t border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1"
>
	<button
		type="button"
		onclick={() => (showShortcuts = !showShortcuts)}
		class="flex h-7 items-center gap-1.5 rounded px-2 text-xs text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
		title="Keyboard shortcuts"
		aria-label="Keyboard shortcuts"
	>
		<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
		</svg>
		<span>Shortcuts</span>
	</button>
</div>

{#if showShortcuts}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
		onclick={handleBackdropClick}
		onkeydown={handleKeydown}
	>
		<div class="w-80 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
			<div class="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2.5">
				<h2 class="text-sm font-semibold text-[var(--color-text)]">Keyboard Shortcuts</h2>
				<button
					type="button"
					onclick={() => (showShortcuts = false)}
					class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-subtle)] hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
					aria-label="Close"
				>
					<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<div class="max-h-72 overflow-y-auto px-4 py-2">
				{#each shortcuts as shortcut}
					<div class="flex items-center justify-between py-1.5">
						<span class="text-xs text-[var(--color-text-muted)]">{shortcut.action}</span>
						<kbd class="rounded border border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[0.625rem] font-mono text-[var(--color-text-subtle)]">{shortcut.keys}</kbd>
					</div>
				{/each}
			</div>
		</div>
	</div>
{/if}
