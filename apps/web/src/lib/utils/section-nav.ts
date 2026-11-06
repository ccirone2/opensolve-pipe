/**
 * The Pumps tab's section nav (proposal pumps-results-layout.md §5.4): its sections in reading
 * order, their buttons' words, the mark a button carries, the Tab stop clamped to the buttons
 * drawn, and the sideways scroll that keeps a row's current item and the one after it in view.
 * Pure: the nav (PumpsNav.svelte) and the row (ScrollRow.svelte) read the page.
 */
import type { Flag } from '$lib/api/types';

/** The sections, in the tab's reading order (§5.3): each a button while it is drawn. */
export const SECTIONS = [
	'per-pump',
	'pump-chart',
	'pumps-together',
	'station',
	'group-chart',
	'add-cases',
	'combinations'
] as const;
export type SectionKey = (typeof SECTIONS)[number];

/** Each section's button words (§6.2 The nav). */
export const SECTION_LABELS: Readonly<Record<SectionKey, string>> = {
	'per-pump': 'Per pump',
	'pump-chart': 'Pump chart',
	'pumps-together': 'Pumps together',
	station: 'Station',
	'group-chart': 'Group chart',
	'add-cases': 'Add cases',
	combinations: 'Running combinations'
};

/** What a section holds that its button marks (§5.4 Marks), each by §5.2's severities. */
export interface SectionMarkInput {
	/** An invalid flag, or a value marked physically invalid. */
	invalid?: boolean;
	/** A warning flag. */
	warning?: boolean;
	/** A refusal (the server's: the pumps do not form a station, or no group curve there). */
	refused?: boolean;
	/** A request that failed. */
	failed?: boolean;
}

export type SectionMarkKind = keyof SectionMarkInput;

/** A button's mark: its icon's kind and the words its name adds after its label. */
export interface SectionMark {
	kind: SectionMarkKind;
	words: string;
}

/**
 * The words after a marked button's label in its name (§6.2), not shown. Each starts with a
 * comma, so it never runs into the label: "Running combinations, has warnings".
 */
export const SECTION_MARK_WORDS: Readonly<Record<SectionMarkKind, string>> = {
	invalid: ', has physically invalid values',
	warning: ', has warnings',
	refused: ', has a refusal',
	failed: ', a request failed'
};

/**
 * A section's worst mark (§5.4 Marks): the red octagon for an invalid flag or a physically invalid
 * value, else the amber alert for a warning flag, else ⬣ for a refusal or a failed request; none
 * otherwise. Never for a design check (D19: never a flag) or a note, which are not inputs here.
 */
export function sectionMark(input: SectionMarkInput): SectionMark | null {
	const kind = (['invalid', 'warning', 'refused', 'failed'] as const).find((k) => input[k]);
	return kind ? { kind, words: SECTION_MARK_WORDS[kind] } : null;
}

/** The severities among flags that mark a section: invalid and warning (info never marks). */
export function flagSeverities(flags: readonly Flag[]): { invalid: boolean; warning: boolean } {
	return {
		invalid: flags.some((f) => f.severity === 'invalid'),
		warning: flags.some((f) => f.severity === 'warning')
	};
}

/**
 * The Tab stop clamped to the buttons drawn (§5.4 One Tab stop): the same section if its button
 * is still there, else the nearest earlier one in reading order, else the first drawn; null with
 * no button.
 */
export function clampSection(
	key: SectionKey | null,
	drawn: readonly SectionKey[]
): SectionKey | null {
	if (!drawn.length) return null;
	if (key === null) return drawn[0]!;
	if (drawn.includes(key)) return key;
	for (let i = SECTIONS.indexOf(key) - 1; i >= 0; i--) {
		if (drawn.includes(SECTIONS[i]!)) return SECTIONS[i]!;
	}
	return drawn[0]!;
}

/** A row that scrolls sideways, as read from the page (px, the row's scroll coordinates). */
export interface RowExtent {
	scrollLeft: number;
	clientWidth: number;
	scrollWidth: number;
	/** The row's inline padding, kept clear at each end. */
	padStart: number;
	padEnd: number;
}

/**
 * Where a row scrolls so that its current item and the one after it are in view (§5.4 Where you
 * are; the view row's keep-in-view): `item` and `next` in the row's scroll coordinates (`next`
 * null at the row's end). The item's start wins when both cannot fit. Null when nothing moves.
 */
export function keepInViewLeft(
	row: RowExtent,
	item: { left: number; right: number },
	next: { right: number } | null
): number | null {
	const end = Math.max(item.right, next?.right ?? item.right) + row.padEnd;
	let left = row.scrollLeft;
	if (end > left + row.clientWidth) left = end - row.clientWidth;
	if (item.left - row.padStart < left) left = item.left - row.padStart;
	left = Math.min(Math.max(left, 0), Math.max(row.scrollWidth - row.clientWidth, 0));
	return Math.abs(left - row.scrollLeft) < 1 ? null : left;
}
