<!--
	A pump's status as a pill (docs/proposals/pumps-nits.md item 2): the state word alone in a pill
	tinted by the state (PUMP_STATUS_TONES), any qualifier after it as plain text, so the cell says
	the label's words, word for word (pumpStatusLabel). No border, icon or glyph, so it never reads
	as a flag pill or a control; `leading-5` with no padding above or below keeps the row's 20 px
	line, and on a phone the qualifier wraps after the pill. One component for Results per pump's
	Status, the Pumps together card's group table and Running combinations' State (§11, leftover
	L22).
-->
<script lang="ts">
	import { PUMP_STATUS_TONES, type PumpStatusParts } from '$lib/utils/results';

	let { parts }: { parts: PumpStatusParts } = $props();
</script>

<span class="min-w-0"
	><span
		data-status-pill
		class={[
			'inline-block rounded-full px-2 align-top text-xs leading-5 font-medium whitespace-nowrap',
			PUMP_STATUS_TONES[parts.state]
		]}>{parts.word}</span
	>{parts.detail ? ` ${parts.detail}` : ''}</span
>
