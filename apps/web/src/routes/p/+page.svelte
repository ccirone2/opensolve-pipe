<!--
	The project page. The project is in the URL fragment (D3): it is read on arrival and whenever
	the fragment changes, decoded (migrating older links) and opened in the workspace. A page
	without a fragment starts a new project. Every edit rewrites the fragment (see ProjectStore).
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { afterNavigate, beforeNavigate } from '$app/navigation';
	import type { Project } from '$lib/api/types';
	import LinkErrorView from '$lib/components/workspace/LinkErrorView.svelte';
	import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
	import { LibraryStore } from '$lib/state/library.svelte';
	import { ProjectStore } from '$lib/state/project.svelte';
	import { Workspace } from '$lib/state/workspace.svelte';
	import { decodeProject, PROJECT_PATH } from '$lib/utils/encoding';
	import { createEmptyProject } from '$lib/utils/factory';
	import { LinkError } from '$lib/utils/link-error';

	let workspace = $state.raw<Workspace | null>(null);
	let linkError = $state.raw<LinkError | null>(null);
	let ready = $state(false);

	function open(hash: string) {
		const text = hash.replace(/^#/, '').trim();
		ready = true;
		if (workspace && text && text === workspace.store.encoded) {
			linkError = null;
			return;
		}
		let project: Project;
		try {
			project = text ? decodeProject(text) : createEmptyProject();
		} catch (error) {
			if (error instanceof LinkError) {
				linkError = error;
				return;
			}
			throw error;
		}
		linkError = null;
		if (!workspace) {
			const store = new ProjectStore(project);
			if (!text) store.load(project, { writeUrl: true });
			workspace = new Workspace(store, new LibraryStore());
		} else {
			workspace.store.load(project, { writeUrl: !text });
			workspace.nav.restart();
			workspace.closeInspector();
			workspace.pane = 'build';
		}
	}

	function backToProject() {
		if (!workspace) return;
		history.replaceState(history.state, '', `${PROJECT_PATH}#${workspace.store.encoded}`);
		linkError = null;
	}

	// Arrival, and navigations that reuse this page (e.g. a link to /p from /p#…).
	afterNavigate(() => open(location.hash));

	// Write a pending URL change before an in-app navigation (the Home link, for example), while
	// this page's history entry is still the current one, so Back reopens the project with the
	// edit. Not in onDestroy: by then the router has pushed the new entry. Not for Back/Forward
	// (popstate) either: the browser has already made another entry current, which a write
	// would overwrite.
	beforeNavigate(({ type }) => {
		if (type !== 'popstate') workspace?.store.flush();
	});

	onMount(() => {
		const onHashChange = () => open(location.hash);
		// Write a pending URL change before the page is hidden or closed.
		const flush = () => workspace?.store.flush();
		const onVisibility = () => {
			if (document.visibilityState === 'hidden') flush();
		};
		window.addEventListener('hashchange', onHashChange);
		window.addEventListener('pagehide', flush);
		document.addEventListener('visibilitychange', onVisibility);
		return () => {
			window.removeEventListener('hashchange', onHashChange);
			window.removeEventListener('pagehide', flush);
			document.removeEventListener('visibilitychange', onVisibility);
			workspace?.store.dispose();
		};
	});
</script>

<svelte:head>
	<title>
		{workspace && !linkError
			? `${workspace.store.project.metadata.name} · OpenSolve Pipe`
			: 'OpenSolve Pipe'}
	</title>
</svelte:head>

{#if linkError}
	<LinkErrorView error={linkError} onreturn={workspace ? backToProject : undefined} />
{:else if workspace}
	<WorkspaceView {workspace} />
{:else if ready}
	<p class="p-4 text-slate-700">Opening the project…</p>
{/if}
