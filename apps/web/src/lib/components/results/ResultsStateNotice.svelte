<!--
	Whether the results shown are current: out of date (the project changed after the solve, in a
	way that can change the results), or kept from an earlier solve because the latest one failed:
	of this same project (offers to solve again, e.g. after a network error), or of an earlier
	version of it (the failure is about the current project, so solving again cannot help until it
	is fixed). Shown with the results and inside an element's trace, so values are never shown
	without it. After a cancelled solve, the failed one is the last solve that finished.
-->
<script lang="ts">
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	/** `values`: wording for the values of one element (the trace view). */
	let { values = false }: { values?: boolean } = $props();
	const ws = useWorkspace();
	const results = $derived(ws.store.results);
	const these = $derived(values ? 'These values are' : 'The results below are');
	const lastSolve = $derived(results.cancelled ? 'The last solve that finished' : 'The last solve');
	/** A solve in flight, of any case (another case's goes on after a case switch). */
	const busy = $derived(!!ws.store.run || ws.store.solvingCase !== undefined);
	/** The latest solve was of the current project and failed; the response is from before. */
	const failedNow = $derived(!!results.error && !results.errorStale && !!results.response);
</script>

{#if failedNow && results.stale}
	<div
		class="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
	>
		<Icon name="alert" class="size-4 shrink-0" />
		<p class="min-w-0 flex-1 basis-48">
			{lastSolve} failed{values ? '' : ' (see above)'}. {these} from an earlier version of the project,
			before your last changes.
		</p>
	</div>
{:else if failedNow}
	<div
		class="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
	>
		<Icon name="alert" class="size-4 shrink-0" />
		<p class="min-w-0 flex-1 basis-48">
			{lastSolve} failed. {these} from the previous solve of this same project.
		</p>
		<button type="button" class="btn" aria-disabled={busy} onclick={() => !busy && void ws.solve()}>
			<Icon name="play" class="size-4" /> Solve again
		</button>
	</div>
{:else if results.stale && (results.response || results.error)}
	<div
		class="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
	>
		<Icon name="alert" class="size-4 shrink-0" />
		<p class="min-w-0 flex-1 basis-48">
			Results are out of date: the project changed after this solve. {#if values}These values are
				from before the change.{/if} Solve again to update the results.
		</p>
		<button type="button" class="btn" aria-disabled={busy} onclick={() => !busy && void ws.solve()}>
			<Icon name="play" class="size-4" /> Solve again
		</button>
	</div>
{/if}
