<script lang="ts">
	import { workspaceStore, activeSidebarTab, type SidebarTab } from '$lib/stores';
	import ComponentTree from './ComponentTree.svelte';
	import ProjectConfigPanel from './ProjectConfigPanel.svelte';
	import SystemResultsPanel from './SystemResultsPanel.svelte';

	interface Props {
		onOpenCommandPalette?: () => void;
		onSolve?: () => void;
	}

	let { onOpenCommandPalette, onSolve }: Props = $props();

	const tabs: { id: SidebarTab; label: string; icon: string }[] = [
		{ id: 'tree', label: 'Tree', icon: 'tree' },
		{ id: 'config', label: 'Config', icon: 'config' },
		{ id: 'results', label: 'Results', icon: 'results' }
	];

	function handleTabClick(tab: SidebarTab) {
		workspaceStore.setSidebarTab(tab);
	}

	// Keyboard shortcuts: Ctrl+1/2/3 for tabs
	function handleKeydown(event: KeyboardEvent) {
		if (event.ctrlKey || event.metaKey) {
			const tabIndex = parseInt(event.key) - 1;
			if (tabIndex >= 0 && tabIndex < tabs.length) {
				event.preventDefault();
				handleTabClick(tabs[tabIndex].id);
			}
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="flex h-full flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]">
	<!-- Tab Bar -->
	<div class="flex border-b border-[var(--color-border)]">
		{#each tabs as tab}
			<button
				type="button"
				onclick={() => handleTabClick(tab.id)}
				class="flex flex-1 items-center justify-center gap-1.5 border-b-2 py-2 text-[0.625rem] font-semibold uppercase tracking-wider transition-colors
					{$activeSidebarTab === tab.id
					? 'border-[var(--color-accent)] text-[var(--color-accent)]'
					: 'border-transparent text-[var(--color-text-subtle)] hover:text-[var(--color-text-muted)]'}"
				title="{tab.label} (Ctrl+{tabs.indexOf(tab) + 1})"
			>
				{#if tab.icon === 'tree'}
					<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6z" />
					</svg>
				{:else if tab.icon === 'config'}
					<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
						<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
					</svg>
				{:else}
					<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
					</svg>
				{/if}
				<span class="hidden lg:inline">{tab.label}</span>
			</button>
		{/each}
	</div>

	<!-- Tab Content -->
	<div class="flex-1 overflow-y-auto">
		{#if $activeSidebarTab === 'tree'}
			<ComponentTree {onOpenCommandPalette} />
		{:else if $activeSidebarTab === 'config'}
			<ProjectConfigPanel />
		{:else if $activeSidebarTab === 'results'}
			<SystemResultsPanel {onSolve} />
		{/if}
	</div>
</div>
