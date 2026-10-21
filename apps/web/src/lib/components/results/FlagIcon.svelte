<!-- Icon for a flag severity: a red or amber warning triangle, or an info circle. Decorative. -->
<script lang="ts">
	import type { ClassValue } from 'svelte/elements';
	import Icon from '$lib/components/ui/Icon.svelte';
	import type { Severity } from '$lib/utils/results';

	let { severity, class: className = 'size-4' }: { severity: Severity; class?: ClassValue } =
		$props();
</script>

<Icon
	name={severity === 'info' ? 'info' : 'alert'}
	class={[
		className,
		'shrink-0',
		severity === 'invalid'
			? 'text-red-700'
			: severity === 'warning'
				? 'text-amber-700'
				: 'text-slate-600'
	]}
/>
