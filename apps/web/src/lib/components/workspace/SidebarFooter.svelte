<script lang="ts">
	import { canUndo, canRedo } from '$lib/stores';

	interface Props {
		onOpenCommandPalette?: () => void;
		onSolve?: () => void;
		onUndo?: () => void;
		onRedo?: () => void;
	}

	let { onOpenCommandPalette, onSolve, onUndo, onRedo }: Props = $props();
</script>

<div
	class="flex items-center gap-1 border-t border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1"
	role="toolbar"
	aria-label="Quick actions"
>
	<!-- Add Component -->
	<button
		type="button"
		onclick={() => onOpenCommandPalette?.()}
		class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
		title="Add component (Ctrl+K)"
		aria-label="Add component"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
		</svg>
	</button>

	<!-- Solve -->
	<button
		type="button"
		onclick={() => onSolve?.()}
		class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
		title="Solve network (Ctrl+Enter)"
		aria-label="Solve network"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M5.636 18.364a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728M9.172 15.172a4 4 0 010-5.656m5.656 0a4 4 0 010 5.656M12 12h.01" />
		</svg>
	</button>

	<div class="mx-0.5 h-4 w-px bg-[var(--color-border)]"></div>

	<!-- Undo -->
	<button
		type="button"
		onclick={() => onUndo?.()}
		disabled={!$canUndo}
		class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)] disabled:cursor-not-allowed disabled:opacity-30"
		title="Undo (Ctrl+Z)"
		aria-label="Undo"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" />
		</svg>
	</button>

	<!-- Redo -->
	<button
		type="button"
		onclick={() => onRedo?.()}
		disabled={!$canRedo}
		class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)] disabled:cursor-not-allowed disabled:opacity-30"
		title="Redo (Ctrl+Shift+Z)"
		aria-label="Redo"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M15 15l6-6m0 0l-6-6m6 6H9a6 6 0 000 12h3" />
		</svg>
	</button>
</div>
