/**
 * The Pumps tab's section nav, as a context (proposal pumps-results-layout.md §5.4 Buttons from
 * what is drawn): PumpsView provides it; each section registers its target while it is drawn
 * (from its mount to its destroy) with a getter for its mark, so the toolbar draws one button per
 * section drawn and never one whose target is gone. A component drawn without PumpsView (the
 * card's own tests) finds no context and registers nothing.
 */
import { getContext, setContext, untrack } from 'svelte';
import type { SectionKey, SectionMark } from '$lib/utils/section-nav';

/** A section drawn: its key, the element a press scrolls to and focuses, and its mark. */
export interface SectionTarget {
	key: SectionKey;
	/** Its heading (tabindex −1), or for Pumps together the card's toggle (§5.4 Targets). */
	target: HTMLElement;
	/** Its worst mark now (read where the button is drawn, so it follows the section). */
	mark: () => SectionMark | null;
}

export interface SectionNav {
	/** The nav is drawn (with the Pumps together card): "Back to the sections" is offered. */
	readonly shown: boolean;
	/** Register a section drawn; the function returned unregisters it. */
	register(section: SectionTarget): () => void;
	/** Focus the nav's current button ("Back to the sections", §5.4 The way back). */
	back(): void;
}

const KEY = Symbol('pumps-section-nav');

export function provideSectionNav(nav: SectionNav): void {
	setContext(KEY, nav);
}

export function useSectionNav(): SectionNav | undefined {
	return getContext<SectionNav | undefined>(KEY);
}

/**
 * Register this component's section while its target is drawn. Called once in a component's
 * script; `target` is read in an effect, so a bound element registers once it exists and
 * unregisters when it goes.
 */
export function registerSection(
	key: SectionKey,
	target: () => HTMLElement | null | undefined,
	mark: () => SectionMark | null = () => null
): void {
	const nav = useSectionNav();
	if (!nav) return;
	$effect(() => {
		const element = target();
		if (!element) return;
		// Untracked: registering reads and writes the list, which this effect must not follow.
		return untrack(() => nav.register({ key, target: element, mark }));
	});
}
