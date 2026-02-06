<script lang="ts">
	import ThemeToggle from '../ThemeToggle.svelte';

	interface Props {
		projectName: string;
		isSolving?: boolean;
		canSolve?: boolean;
		isSidebarOpen?: boolean;
		isInspectorOpen?: boolean;
		onSolve?: () => void;
		onToggleSidebar?: () => void;
		onToggleInspector?: () => void;
		onOpenCommandPalette?: () => void;
		onEditName?: () => void;
	}

	let {
		projectName,
		isSolving = false,
		canSolve = true,
		isSidebarOpen = true,
		isInspectorOpen = true,
		onSolve,
		onToggleSidebar,
		onToggleInspector,
		onOpenCommandPalette,
		onEditName
	}: Props = $props();
</script>

<div class="flex h-full items-center border-b border-[var(--color-border)] bg-[var(--color-surface)] px-2">
	<!-- Left: Sidebar toggle + Logo + Project name -->
	<div class="flex items-center gap-1.5">
		<button
			type="button"
			onclick={onToggleSidebar}
			class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
			title={isSidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
			</svg>
		</button>

		<a href="/" class="flex items-center gap-1.5 rounded px-1.5 py-1 transition-colors hover:bg-[var(--color-surface-elevated)]" title="Home">
			<svg class="h-4 w-4 text-[var(--color-accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
			</svg>
		</a>

		<span class="mx-1 text-[var(--color-border)]">/</span>

		<button
			type="button"
			onclick={onEditName}
			class="max-w-[200px] truncate rounded px-1.5 py-0.5 text-sm font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-elevated)]"
			title="Click to rename project"
		>
			{projectName}
		</button>
	</div>

	<!-- Center: Actions -->
	<div class="ml-auto flex items-center gap-1.5">
		<!-- Add Component -->
		<button
			type="button"
			onclick={onOpenCommandPalette}
			class="inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)]"
			title="Add component (Ctrl+K)"
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
			</svg>
			<span class="hidden sm:inline">Add</span>
			<span class="kbd">K</span>
		</button>

		<div class="mx-1 h-4 w-px bg-[var(--color-border)]"></div>

		<!-- Solve -->
		<button
			type="button"
			onclick={onSolve}
			disabled={!canSolve || isSolving}
			title="Solve network (Ctrl+Enter)"
			class="inline-flex items-center gap-1.5 rounded bg-[var(--color-accent)] px-3 py-1 text-xs font-semibold text-[var(--color-accent-text)] transition-colors hover:bg-[var(--color-accent-hover)] disabled:cursor-not-allowed disabled:opacity-40"
		>
			{#if isSolving}
				<svg class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
				</svg>
				Solving
			{:else}
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M5.636 18.364a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728M9.172 15.172a4 4 0 010-5.656m5.656 0a4 4 0 010 5.656M12 12h.01" />
				</svg>
				Solve
			{/if}
		</button>

		<div class="mx-1 h-4 w-px bg-[var(--color-border)]"></div>

		<!-- Inspector toggle -->
		<button
			type="button"
			onclick={onToggleInspector}
			class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-elevated)] hover:text-[var(--color-text)] {isInspectorOpen ? 'bg-[var(--color-surface-elevated)] text-[var(--color-text)]' : ''}"
			title={isInspectorOpen ? 'Hide inspector' : 'Show inspector'}
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M9 4.5v15m6-15v15m-10.875 0h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125z" />
			</svg>
		</button>

		<ThemeToggle />
	</div>
</div>
