<!--
	A flag shown inline next to a result: icon and severity word (never color alone), with the
	flag's text (names, display units) for screen readers and as a tooltip.
-->
<script lang="ts">
	import type { Flag } from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { SEVERITY_LABELS } from '$lib/utils/results';
	import FlagIcon from './FlagIcon.svelte';

	let { flag }: { flag: Flag } = $props();
	const ws = useWorkspace();
	const text = $derived(ws.flagText(flag));
</script>

<span
	class={[
		'inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
		flag.severity === 'invalid'
			? 'border-red-300 bg-red-50 text-red-900'
			: flag.severity === 'warning'
				? 'border-amber-300 bg-amber-50 text-amber-900'
				: 'border-slate-300 bg-slate-50 text-slate-700'
	]}
	title={text}
>
	<FlagIcon severity={flag.severity} class="size-3.5" />
	{SEVERITY_LABELS[flag.severity]}<span class="sr-only">: {text}</span>
</span>
