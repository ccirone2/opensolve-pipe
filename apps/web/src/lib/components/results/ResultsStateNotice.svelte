<!--
	Whether the results shown are current: out of date (the project changed after the solve, in a
	way that can change the results), or kept from an earlier solve because the latest one failed:
	of this same project (solving again can help, e.g. after a network error), or of an earlier
	version of it (the failure is about the current project, so solving again cannot help until it
	is fixed). Shown with the results and inside an element's trace, so values are never shown
	without it. After a cancelled solve, the failed one is the last solve that finished.

	One control per action, at the top (build-density.md §19): the notice says where Solve is, with
	the header's own icon and, on a fine pointer, its shortcut (ControlName, KeysHint), and has no
	button of its own. The one exception is `solve`: the trace's bottom sheet below 1024 px, a
	modal over the header (the header is inert behind it and Ctrl+Enter is ignored), keeps today's
	words and Solve again, so a phone can solve again without closing the trace (GOALS §4.7). Its
	Solve again is unavailable, with the reason, while any request runs (a solve, Solve all, a goal
	seek).
-->
<script lang="ts">
	import ControlName from '$lib/components/ui/ControlName.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import KeysHint from '$lib/components/ui/KeysHint.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { calculatingReason } from '$lib/utils/goal-seek';

	/**
	 * `values`: wording for the values of one element (the trace view). `solve`: Solve again in the
	 * notice, for a modal over the header (the trace's sheet below 1024 px, build-density.md §19).
	 */
	let { values = false, solve = false }: { values?: boolean; solve?: boolean } = $props();
	const ws = useWorkspace();
	const results = $derived(ws.store.results);
	const these = $derived(values ? 'These values are' : 'The results below are');
	const lastSolve = $derived(results.cancelled ? 'The last solve that finished' : 'The last solve');
	const id = $props.id();
	/** A request in flight: a solve of any case, Solve all or a goal seek (one at a time). */
	const busyReason = $derived(calculatingReason(ws.store.calculating, 'solve'));
	const busy = $derived(!!busyReason);
	/** The latest solve was of the current project and failed; the response is from before. */
	const failedNow = $derived(!!results.error && !results.errorStale && !!results.response);
</script>

{#snippet solveAgain()}
	<button
		type="button"
		class="btn"
		aria-disabled={busy}
		aria-describedby={busy ? `${id}-busy` : undefined}
		title={busyReason || undefined}
		onclick={() => !busy && void ws.solve()}
	>
		<Icon name="play" class="size-4" /> Solve again
	</button>
	{#if busy}<span id="{id}-busy" class="sr-only">{busyReason}</span>{/if}
{/snippet}

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
			{lastSolve} failed. {these} from the previous solve of this same project. {#if !solve}Press
				<ControlName control="solve" />, at the top<KeysHint keys="solve" />, to try again.{/if}
		</p>
		{#if solve}{@render solveAgain()}{/if}
	</div>
{:else if results.stale && (results.response || results.error)}
	<div
		class="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
	>
		<Icon name="alert" class="size-4 shrink-0" />
		<p class="min-w-0 flex-1 basis-48">
			Results are out of date: the project changed after this solve. {#if values}These values are
				from before the change.{/if}
			{#if solve}Solve again to update the results.{:else}Press <ControlName control="solve" />, at
				the top<KeysHint keys="solve" />, to update them.{/if}
		</p>
		{#if solve}{@render solveAgain()}{/if}
	</div>
{/if}
