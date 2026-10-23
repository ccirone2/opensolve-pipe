<!-- A project link that cannot be opened: what went wrong and what to do next. -->
<script lang="ts">
	import { homeHref, projectHref } from '$lib/components/links';
	import SiteFooter from '$lib/components/SiteFooter.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import type { LinkError } from '$lib/utils/link-error';

	interface Props {
		error: LinkError;
		/** Go back to the project that was open before this link, if any. */
		onreturn?: () => void;
	}

	let { error, onreturn }: Props = $props();

	const TITLES: Record<LinkError['kind'], string> = {
		corrupt: 'This link is damaged',
		newer_version: 'This link needs a newer version',
		invalid: 'This link does not hold a valid project'
	};
</script>

<main class="mx-auto max-w-2xl space-y-4 px-4 py-10">
	<h1 class="flex items-center gap-2 text-2xl font-semibold">
		<Icon name="alert" class="size-6 text-red-700" />
		{TITLES[error.kind]}
	</h1>
	<p class="text-slate-800">{error.message}</p>
	{#if error.problems.length}
		<ul class="list-disc space-y-1 pl-5 text-sm break-words text-slate-700">
			{#each error.problems.slice(0, 20) as problem, i (i)}
				<li>{problem}</li>
			{/each}
			{#if error.problems.length > 20}
				<li>… and {error.problems.length - 20} more.</li>
			{/if}
		</ul>
	{/if}
	<div class="flex flex-wrap gap-2 pt-2">
		{#if onreturn}
			<button type="button" class="btn btn-primary" onclick={onreturn}>
				Back to the open project
			</button>
		{/if}
		<a class={['btn', !onreturn && 'btn-primary']} href={projectHref()}>Start a new project</a>
		<a class="btn" href={homeHref()}>Home</a>
	</div>
	<div class="pt-6"><SiteFooter /></div>
</main>
