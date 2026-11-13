<!--
	A header control named in a pane's words (build-density.md §19): one control per action, at the
	top, so a pane never repeats Solve or Solve all; its words name the control instead. The
	header's own icon (Solve's play, the Scenarios button's layers), at 1 em and hidden from screen
	readers, and the control's word, in one unbroken span, so the words match an icon-only button at
	320 px and never wrap between the icon and its word.
-->
<script lang="ts">
	import Icon, { type IconName } from './Icon.svelte';

	let { control }: { control: 'solve' | 'scenarios' } = $props();

	const CONTROLS: Readonly<Record<'solve' | 'scenarios', { icon: IconName; word: string }>> = {
		solve: { icon: 'play', word: 'Solve' },
		scenarios: { icon: 'layers', word: 'Scenarios' }
	};
	const named = $derived(CONTROLS[control]);
</script>

<span class="whitespace-nowrap"
	><Icon name={named.icon} class="inline size-[1em] align-[-0.125em]" /> {named.word}</span
>
