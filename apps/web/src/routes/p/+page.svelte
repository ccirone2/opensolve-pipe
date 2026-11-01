<!--
	The project page. The project is in the URL fragment (D3): it is read on arrival and whenever
	the fragment changes, decoded (migrating older links) and opened in the workspace. A page
	without a fragment starts a new project. Every edit rewrites the fragment (see ProjectStore).
	Each link written or opened here is remembered in this browser for the home page's recent
	projects (utils/recent.ts), except an empty project and an example not yet changed.
-->
<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { afterNavigate, beforeNavigate } from '$app/navigation';
	import type { Project } from '$lib/api/types';
	import LinkErrorView from '$lib/components/workspace/LinkErrorView.svelte';
	import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
	import { LibraryStore } from '$lib/state/library.svelte';
	import { ProjectStore } from '$lib/state/project.svelte';
	import { Workspace } from '$lib/state/workspace.svelte';
	import { decodeProject, encodeProject, PROJECT_PATH } from '$lib/utils/encoding';
	import { EXAMPLES } from '$lib/utils/examples';
	import { rememberProject } from '$lib/utils/recent';
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

	/** The examples as published: opening one is not worth remembering until it is changed. */
	const examples = new Set(EXAMPLES.map((e) => encodeProject(e.create())));

	/** Remember the project as its link now stands (recent projects on this device). */
	function remember() {
		const store = workspace?.store;
		if (!store || linkError || !store.encoded) return;
		const { project, encoded } = store;
		if (project.components.length === 0 || examples.has(encoded)) return;
		rememberProject({
			id: project.id,
			name: project.metadata.name,
			encoded,
			savedAt: new Date().toISOString()
		});
	}

	// Each new link: opened, or written after an edit.
	$effect(() => {
		void workspace?.store.encoded;
		untrack(remember);
	});

	/** Write a pending URL change now, and remember it before the page goes. */
	function flushAndRemember() {
		workspace?.store.flush();
		remember();
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
		if (type !== 'popstate') flushAndRemember();
	});

	onMount(() => {
		const onHashChange = () => open(location.hash);
		// Write a pending URL change before the page is hidden or closed.
		const flush = flushAndRemember;
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
