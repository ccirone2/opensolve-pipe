<!--
	A case's box beside its name, as one unit (the owner's Q2 "By list place", nit 5, slice 5b;
	docs/proposals/pumps-nits.md §11.4, leftover L12; ui-guide, "A case is its number"): the box
	beside the name's first line, and every line of the name at one edge. Where the box was inline
	before a name, a name with no room left on the box's line started on the line under it, and a
	second line of a long name started under the box.

	One flex row: the box (CaseTag) in a `shrink-0` span, a space, then the name in a `min-w-0`
	span that wraps. The box's span is one line of the row's own font tall (`h-lh`) and centres the
	box in it, both spans at the row's top, so the box sits in the middle of the name's first line
	and never makes that line taller: a 16 px box on a 12 px text's 16 px line grew it to 17 px
	when it sat on the text's bottom, as CaseTag sets it in a run of words (§11.4, leftover L10).
	The name's span alone is aligned on its baseline (`self-baseline`), so the row's baseline is
	the name's and, inline, the name's words sit on the line of the words around it. The space
	(the template's own whitespace between the two spans, one text node) renders nothing between
	flex items; it keeps the words heard "Case 2: Winter" wherever the box's span is not laid out
	as a block (jsdom, a name computed from the markup), as CaseTag asks of the words after it.
	The Base box is drawn too: CaseTag hides it from screen readers, whose "Base case" beside it
	says it.

	Forms: `inline` in a run of words (an inline flex box, at most its line's width), `block` a line
	of its own, `column` with the box in the reserved 2.5 rem column of "Operating points by case"
	and "Other cases' station duties" (ui-guide, "A list of numbered lines keeps a column for the
	numbers"). The name's span inherits its cell's wrapping (`max-sm:wrap-anywhere` in a phone's
	list) and breaks an unbroken word from 640 px (`sm:wrap-break-word`), unless `nameClass` says.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { ClassValue } from 'svelte/elements';
	import type { CaseNumber } from '$lib/utils/pump-chart';
	import CaseTag from './CaseTag.svelte';

	interface Props {
		/** The case's number (caseTags): "Base", or its place in the Scenarios list. */
		tag: CaseNumber;
		/** The case's name; or `children`, its words with what follows them ("(shown)"). */
		name?: string;
		children?: Snippet;
		/** Inline in a run of words, a line of its own, or the box in a 2.5 rem column. */
		form?: 'inline' | 'block' | 'column';
		/** The name's span's classes, in place of `sm:wrap-break-word`. */
		nameClass?: ClassValue;
		/** The unit's own classes. */
		class?: ClassValue;
	}

	let {
		tag,
		name = '',
		children,
		form = 'inline',
		nameClass = 'sm:wrap-break-word',
		class: className
	}: Props = $props();
</script>

<span
	data-case-named
	class={[
		form === 'inline' ? 'inline-flex max-w-full align-baseline' : 'flex',
		'items-start gap-1',
		className
	]}
	><span class={['flex h-lh shrink-0 items-center', form === 'column' && 'w-10']}
		><CaseTag {tag} /></span
	>
	<span class={['min-w-0 self-baseline', nameClass]}
		>{#if children}{@render children()}{:else}{name}{/if}</span
	></span
>
