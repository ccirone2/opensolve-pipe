<!--
	Where a case's results stand (ProjectStore.caseStatus), as a chip with an icon and text: never
	colour alone. `short` (a narrow column's header) shows a long status in a few words, its full
	words for screen readers and as the chip's title.
-->
<script lang="ts" module>
	import type { CaseStatus } from '$lib/state/project.svelte';
	import { CASE_STATUS_LABELS as LABELS } from '$lib/utils/labels';

	/** The statuses in words; they live in utils/labels.ts, where a .ts module (the export) reads them. */
	export const CASE_STATUS_LABELS = LABELS;

	/** Short forms of the statuses too long for a narrow column's header. */
	export const CASE_STATUS_SHORT: Readonly<Partial<Record<CaseStatus, string>>> = {
		not_reached: 'Not reached'
	};
</script>

<script lang="ts">
	import Icon, { type IconName } from '$lib/components/ui/Icon.svelte';

	let { status, short = false }: { status: CaseStatus; short?: boolean } = $props();
	const shortText = $derived(short ? CASE_STATUS_SHORT[status] : undefined);

	const STYLES: Readonly<Record<CaseStatus, string>> = {
		solving: 'border-slate-300 bg-white text-slate-800',
		waiting: 'border-slate-300 bg-white text-slate-700',
		solved: 'border-green-300 bg-green-50 text-green-900',
		not_converged: 'border-red-300 bg-red-50 text-red-900',
		stale: 'border-amber-300 bg-amber-50 text-amber-900',
		failed: 'border-red-300 bg-red-50 text-red-900',
		cancelled: 'border-slate-300 bg-slate-50 text-slate-800',
		not_solved: 'border-slate-300 bg-slate-50 text-slate-700',
		not_reached: 'border-amber-300 bg-amber-50 text-amber-900'
	};
	const ICONS: Readonly<Record<CaseStatus, IconName>> = {
		solving: 'spinner',
		waiting: 'info',
		solved: 'check',
		not_converged: 'alert',
		stale: 'alert',
		failed: 'alert',
		cancelled: 'info',
		not_solved: 'info',
		not_reached: 'alert'
	};
</script>

<span
	class={[
		'inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
		STYLES[status]
	]}
	title={shortText ? CASE_STATUS_LABELS[status] : undefined}
>
	<Icon
		name={ICONS[status]}
		class={['size-3.5 shrink-0', status === 'solving' && 'motion-safe:animate-spin']}
	/>
	{#if shortText}
		<span class="min-w-0" aria-hidden="true">{shortText}</span>
		<span class="sr-only">{CASE_STATUS_LABELS[status]}</span>
	{:else}
		<span class="min-w-0">{CASE_STATUS_LABELS[status]}</span>
	{/if}
</span>
