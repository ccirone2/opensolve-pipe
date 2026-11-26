/**
 * What the Pumps together card's sections keep while a solve withdraws them
 * (proposals/open-defects-2.md F3, the owner's answer of 2026-11-26). Until the case shown's
 * curves have answered, Add cases and the two methods' disclosures are not drawn, so never with
 * another solve's results; when they come back they are as the user left them: the plan, the stop
 * order and the two methods open or closed, the fold rule going on from where it was, and the
 * focus on the same control (PumpGroupChart, by `data-focus-key`).
 *
 * Page state of one opening of the card: PumpGroupChart makes a new one each time the card is
 * opened, so a card closed and opened draws its sections anew, as before (pumps-results-layout.md
 * §5.3 The fold). The block's own lines ("Now ticked", its polite line) are not kept (§15 item
 * 127): they go with the drawing they report, as before.
 */
import type { LineupPreset } from '$lib/utils/pump-lineups';

/** The fold rule's reading of the plan (PumpLineupsBlock), at its last run. */
export interface FoldSeen {
	drawn: boolean;
	done: boolean;
	preset: LineupPreset;
	others: boolean;
}

/** The sections a solve withdraws, by their `data-card-section`. */
export type CardSection = 'add-cases' | 'group-methods' | 'system-methods';
export const CARD_SECTIONS: readonly CardSection[] = [
	'add-cases',
	'group-methods',
	'system-methods'
];
/** None of them drawn. */
export const NONE_DRAWN: Readonly<Record<CardSection, boolean>> = {
	'add-cases': false,
	'group-methods': false,
	'system-methods': false
};

export class CardSections {
	/** Add cases' plan disclosure (the fold rule's two moves, else the user's). */
	planOpen = $state(false);
	/** Its stop order (closed by default). */
	stopOpen = $state(false);
	/** "How the group curve is computed" (or "How this curve is computed"). */
	groupMethodsOpen = $state(false);
	/** "How the group system curve is computed". */
	systemMethodsOpen = $state(false);
	/**
	 * A solve took a section's answer away (a new response, its curves asked for again): the
	 * sections stay withdrawn until the case shown's curves have all answered, then come back
	 * together. Written by PumpGroupChart only. Until then, as before, each is drawn with its own
	 * answer (the card's first drawing).
	 */
	withdrawn = $state(false);
	/** The fold rule's last reading (not reactive): a block drawn back goes on from it. */
	seen: FoldSeen | null = null;
}

/**
 * A control's key in a withdrawn section, the same in the section drawn back: its
 * `data-focus-key`, or a preset segment's value (SegmentedField's radios). Null: not one the card
 * gives back (the focus then stays on the figure).
 */
export function focusKey(el: Element): string | null {
	if (!(el instanceof HTMLElement)) return null;
	if (el.dataset.focusKey) return el.dataset.focusKey;
	if (el instanceof HTMLInputElement && el.type === 'radio') return `radio:${el.value}`;
	return null;
}

/** The control of `section` with `key` in `root`, if it is drawn. */
export function controlOf(root: ParentNode, section: CardSection, key: string): HTMLElement | null {
	const at = root.querySelector(`[data-card-section="${section}"]`);
	if (!at) return null;
	const controls = at.querySelectorAll<HTMLElement>('[data-focus-key], input[type="radio"]');
	return [...controls].find((el) => focusKey(el) === key) ?? null;
}

/**
 * The nearest ancestor of `node` that scrolls down (the Results pane's scroller), else the page's
 * (PumpChart's rule for the switch it holds in place).
 */
export function scrollerOf(node: Element): Element {
	for (let el = node.parentElement; el; el = el.parentElement) {
		const y = getComputedStyle(el).overflowY;
		if ((y === 'auto' || y === 'scroll') && el.scrollHeight > el.clientHeight) return el;
	}
	return document.scrollingElement ?? document.documentElement;
}

/** Whether `pane` is the page's scroller (its scroll events fire at the document). */
function isPage(pane: Element): boolean {
	return pane === document.scrollingElement || pane === document.documentElement;
}

/** How far `node` lies below the top of `pane`'s box (the window's top for the page's scroller). */
export function offsetIn(pane: Element, node: Element): number {
	return node.getBoundingClientRect().top - (isPage(pane) ? 0 : pane.getBoundingClientRect().top);
}

/**
 * Where the user last saw the control that has the focus in a section a solve withdraws: its
 * offset in its pane, read as it takes the focus and again at each scroll of that pane
 * (proposals/open-defects-2.md F3, the offset held). Not reactive.
 *
 * A read in the flush that withdraws the section is not that: the flush has already changed the
 * DOM above the control (the pump chart's section asks for its system curve again, 1,246 →
 * 1,158 px) and Chromium anchors the scroll for it only at the frame's layout, so on the lineups
 * example that read put "Stop Pump P4 later" back 68 px high at 1280 × 800 (291 px; the user saw
 * 359) and 104 px at 390 × 844 (232; 336). Scroll anchoring's own adjustments fire a scroll
 * event, read after that frame's layout: the solving line's growth scrolled the pane from 6,384 to
 * 6,456 px, the button kept at 359 px. Measured in Chromium at both sizes, with the button's offset
 * read after every frame from the press to the withdrawal: no frame drew it anywhere but where
 * this record said.
 */
export class SeenOffset {
	#el: Element | null = null;
	#pane: Element | null = null;
	#offset = 0;
	/** At each scroll of the pane, while the control watched still has the focus. */
	#read = () => {
		if (this.#el && this.#pane && document.activeElement === this.#el) {
			this.#offset = offsetIn(this.#pane, this.#el);
		}
	};
	/** `el` has the focus: read where it is in `pane` now and at each of the pane's scrolls. */
	watch(el: Element, pane: Element) {
		if (pane !== this.#pane) {
			this.stop();
			(isPage(pane) ? window : pane).addEventListener('scroll', this.#read, { passive: true });
		}
		this.#el = el;
		this.#pane = pane;
		this.#offset = offsetIn(pane, el);
	}
	/** Nothing watched: the focus on no such control, or the card's body gone. */
	stop() {
		const pane = this.#pane;
		if (pane) (isPage(pane) ? window : pane).removeEventListener('scroll', this.#read);
		this.#el = this.#pane = null;
	}
	/** How far `el` lies below the top of `pane`: as last seen if it is the control watched. */
	offsetOf(el: Element, pane: Element): number {
		return el === this.#el && pane === this.#pane ? this.#offset : offsetIn(pane, el);
	}
}
