<script lang="ts">
	import { workspaceStore, activeSidebarTab, type SidebarTab } from '$lib/stores';
	import ComponentTree from './ComponentTree.svelte';
	import ProjectConfigPanel from './ProjectConfigPanel.svelte';
	import ResultsTab from '../results/ResultsTab.svelte';
	import LibraryTab from './LibraryTab.svelte';
	import SidebarFooter from './SidebarFooter.svelte';

	interface Props {
		onOpenCommandPalette?: () => void;
		onSolve?: () => void;
	}

	let { onOpenCommandPalette, onSolve }: Props = $props();

	const tabs: { id: SidebarTab; label: string }[] = [
		{ id: 'tree', label: 'Tree' },
		{ id: 'library', label: 'Library' },
		{ id: 'config', label: 'Config' },
		{ id: 'results', label: 'Results' }
	];

	function handleTabClick(tab: SidebarTab) {
		workspaceStore.setSidebarTab(tab);
	}

	// Keyboard shortcuts: Ctrl+1/2/3/4 for tabs
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

<div class="flex h-full border-r border-[var(--color-border)] bg-[var(--color-surface)]">
	<!-- Vertical Icon Tab Strip -->
	<div class="flex flex-col border-r border-[var(--color-border)] bg-[var(--color-surface-elevated)]">
		{#each tabs as tab, i}
			<button
				type="button"
				onclick={() => handleTabClick(tab.id)}
				class="group relative flex h-9 w-9 items-center justify-center transition-colors
					{$activeSidebarTab === tab.id
					? 'text-[var(--color-accent)]'
					: 'text-[var(--color-text-subtle)] hover:text-[var(--color-text-muted)]'}"
				title="{tab.label} (Ctrl+{i + 1})"
			>
				<!-- Active indicator bar -->
				{#if $activeSidebarTab === tab.id}
					<div class="absolute left-0 top-1 bottom-1 w-[2px] rounded-r bg-[var(--color-accent)]"></div>
				{/if}

				{#if tab.id === 'tree'}
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6z" />
					</svg>
				{:else if tab.id === 'library'}
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
					</svg>
				{:else if tab.id === 'config'}
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
						<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
					</svg>
				{:else}
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
					</svg>
				{/if}
			</button>
		{/each}
	</div>

	<!-- Tab Content + Footer -->
	<div class="flex flex-1 flex-col overflow-hidden">
		<div class="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
			{#if $activeSidebarTab === 'tree'}
				<ComponentTree {onOpenCommandPalette} />
			{:else if $activeSidebarTab === 'library'}
				<LibraryTab />
			{:else if $activeSidebarTab === 'config'}
				<ProjectConfigPanel />
			{:else if $activeSidebarTab === 'results'}
				<ResultsTab />
			{/if}
		</div>
		<SidebarFooter />
	</div>
</div>
