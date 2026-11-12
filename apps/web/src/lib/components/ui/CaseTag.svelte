<!--
	A case's number in a small box (owner, 2026-11-12, nit 5: "I don't like the use of special
	characters to designate pumps and groups"; Q2 "By list place"; docs/proposals/pumps-nits.md item
	5, slice 5b, rule 4): "Base" for the base case, else its scenario's place in the Scenarios list
	(pump-chart.ts caseTags), the same number on both charts and in every list, table and heading of
	the Pumps tab. The canvases draw the same box (pump-chart-config.ts fillLabel).

	The box is seen and hidden from screen readers, which hear its number from visually hidden words
	before it instead, "Case 3:" or "Cases 4, 5 and 6:" (caseTagWords), so a checkbox's name keeps its
	visible words after them (WCAG 2.5.3, Label in Name). The base case's "Base" is wholly hidden:
	"Base case" beside it says it. `hidden` hides any box wholly, where the words beside it already
	name its cases. The words after the tag go after it, outside it, with one space between them (a
	space inside the hidden words does not survive the accessible name's computation).
-->
<script lang="ts">
	import { caseTagText, caseTagWords, type CaseNumber } from '$lib/utils/pump-chart';

	interface Props {
		/** The case's number (caseTags), or several in one box (a merged ring's). */
		tag: CaseNumber | readonly CaseNumber[];
		/** Hidden wholly from screen readers: the words beside it already name its cases. */
		hidden?: boolean;
	}

	let { tag, hidden = false }: Props = $props();

	const tags = $derived<readonly CaseNumber[]>(Array.isArray(tag) ? tag : [tag as CaseNumber]);
	const numbers = $derived(tags.filter((t): t is number => t !== 'Base'));
	/** "3", "4, 5, 6", "Base": Base first, then ascending. */
	const text = $derived(caseTagText(tags));
	/** The words heard: none for the base case alone ("Base case" beside it says it). */
	const words = $derived.by(() => {
		if (hidden || !numbers.length) return '';
		const said = caseTagWords(numbers);
		return tags.includes('Base') ? `Base case and ${said.replace(/^C/, 'c')}` : said;
	});
	/** The box (pumps-nits.md item 5: the tags design's box): white, a slate edge, bold numbers. */
	const BOX =
		'inline-flex h-4 min-w-4.5 shrink-0 items-center justify-center rounded-[3px] border border-slate-600 bg-white px-1 text-[0.6875rem] leading-none font-semibold whitespace-nowrap text-slate-800 tabular-nums';
</script>

{#if words}<span data-case-tag class="inline-flex shrink-0 align-text-bottom"
		><span class="sr-only">{words}</span><span aria-hidden="true" class={BOX}>{text}</span></span
	>{:else}<span data-case-tag aria-hidden="true" class={[BOX, 'align-text-bottom']}>{text}</span
	>{/if}
