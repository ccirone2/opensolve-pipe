<!--
	A row's flags on the line under it (proposal pumps-results-layout.md §5.3 Station and Flags,
	§9 S6a; ui-guide, A row's flags are a line under it): named by its element first, visually
	hidden, for table navigation, which reads the one-cell row without its name; then each flag
	its pill (its icon and severity word, flagTone's tint) and its sentence, visible and read once
	(no hidden copy, no title), the sentence its own element. A list, an item per flag, so a run of
	flags never reads as one run of notes (§15 item 149): one pattern for the card's two tables.
	Reads no workspace: the caller gives each flag's words, so the card's tests mount none.
-->
<script lang="ts">
	import type { Flag } from '$lib/api/types';
	import { flagTone, SEVERITY_LABELS } from '$lib/utils/results';
	import FlagIcon from './FlagIcon.svelte';

	interface Props {
		/** The element the flags are on, as its row names it. */
		name: string;
		flags: readonly Flag[];
		/** A flag's words (names, display units). */
		flagText: (flag: Flag) => string;
	}

	let { name, flags, flagText }: Props = $props();
</script>

<span class="sr-only">{name}, flags:</span>
<ul class="space-y-1">
	{#each flags as flag, i (i)}
		<li class="text-xs text-slate-700">
			<span
				class={[
					'mr-1 inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 align-middle font-medium whitespace-nowrap',
					flagTone(flag.severity)
				]}
				><FlagIcon severity={flag.severity} class="size-3.5" />{SEVERITY_LABELS[
					flag.severity
				]}</span
			>
			<span class="wrap-break-word" data-flag-text>{flagText(flag)}</span>
		</li>
	{/each}
</ul>
