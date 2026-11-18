/**
 * The charts' canvas legends made to fit (leftovers L17 and L18, docs/proposals/pumps-nits.md
 * §8.14 bullets 5 and 6; §11.5), pure: the charts' `generateLabels` call it with Chart.js's own
 * items and the legend's measured text, the tests with a fixed-width `measure`.
 *
 * Chart.js 4.5.1's horizontal legend lays each entry out as one line (Legend._fitRows): an entry
 * wider than its row ran past the canvas and was cut, and the legend is at most half the canvas
 * high (its layout's hBoxMaxHeight), so the rows past it were not drawn at all ("Case 3: 1 of 4
 * running (…)" cut at 390 px; the condenser's five rings listed as one at 320 px). Here an entry
 * too wide for a row is written on as many rows as it needs, and the other cases' entries can be
 * collapsed into one per family, each one's datasets toggled together.
 *
 * A leaf module (no imports), as point-labels.ts is: the chart's chunk draws with it.
 */

/** A legend entry as Chart.js gives it: its words, and its swatch's look. */
export interface FitItem {
	text: string;
	datasetIndex?: number;
	hidden?: boolean;
	fillStyle?: unknown;
	strokeStyle?: unknown;
	lineWidth?: number;
	lineDash?: number[];
	/** A collapsed entry's datasets, toggled together (CR-ENG-2). */
	datasetIndices?: number[];
}

/** The legend's measures, as Chart.js lays out a horizontal legend. */
export interface LegendMetrics {
	/** The legend's width (its `maxWidth`, the canvas's). */
	width: number;
	/** The most it is drawn high (its `maxHeight`, half the canvas: Chart.js clips the rest). */
	maxHeight: number;
	/** The swatch's width (`getBoxSize`: the font's size under usePointStyle). */
	boxWidth: number;
	/** The font's size: half of it lies between the swatch and the words. */
	fontSize: number;
	/** The labels' padding, between entries and round the rows. */
	padding: number;
	/** A row's height without its padding (`getBoxSize`'s itemHeight). */
	itemHeight: number;
	/** A text's width in the legend's font. */
	measure: (text: string) => number;
}

/** The room for an entry's words on a row of its own: the row less its padding and the swatch. */
export function wordsRoom(m: LegendMetrics): number {
	return m.width - 2 * m.padding - m.boxWidth - m.fontSize / 2;
}

/**
 * `text` in lines each at most `room` wide, filled greedily: broken at spaces, and inside a word
 * wider than a line (one character at a time). One line where it fits; never an empty line.
 */
export function wrapWords(text: string, room: number, measure: (text: string) => number): string[] {
	if (measure(text) <= room) return [text];
	const lines: string[] = [];
	let line = '';
	const push = () => {
		if (line) lines.push(line);
		line = '';
	};
	for (const word of text.split(' ')) {
		const joined = line ? `${line} ${word}` : word;
		if (measure(joined) <= room) {
			line = joined;
			continue;
		}
		push();
		if (measure(word) <= room) {
			line = word;
			continue;
		}
		// A word wider than a line: as many characters as fit, then the rest.
		for (const ch of word) {
			if (line && measure(line + ch) > room) push();
			line += ch;
		}
	}
	push();
	return lines;
}

/**
 * Each entry wider than its row on as many rows as it needs (wrapWords): its first row keeps its
 * swatch, each later one is an entry of its own with none (`continuation`: a transparent swatch
 * of no width of line, the same dataset and the same `hidden`, so a click on any row toggles its
 * curve and a hidden one is struck through on each row). Greedy lines fill a row, so the next
 * line never fits beside it: Chart.js starts each on a row of its own.
 */
export function wrapLegend<T extends FitItem>(items: readonly T[], m: LegendMetrics): T[] {
	const room = wordsRoom(m);
	if (room <= 0) return [...items];
	return items.flatMap((item) => {
		const [first, ...rest] = wrapWords(item.text, room, m.measure);
		if (!rest.length) return [item];
		return [
			{ ...item, text: first! },
			...rest.map((text) => ({
				...item,
				text,
				fillStyle: 'rgba(0, 0, 0, 0)',
				strokeStyle: 'rgba(0, 0, 0, 0)',
				lineWidth: 0,
				lineDash: []
			}))
		];
	});
}

/**
 * The legend's height as Chart.js 4.5.1 fits a horizontal legend (Legend._fitRows, then `fit`'s
 * 10 px): an entry starts a new row where it would not fit beside the row's entries with the
 * padding, every row an item's height and its padding high.
 */
export function legendHeight(items: readonly FitItem[], m: LegendMetrics): number {
	let rows = 0;
	let line = 0;
	items.forEach((item, i) => {
		const width = m.boxWidth + m.fontSize / 2 + m.measure(item.text);
		if (i === 0 || line + width + 2 * m.padding > m.width) {
			rows++;
			line = 0;
		}
		line += width + m.padding;
	});
	return rows * (m.itemHeight + m.padding) + 10;
}

/** A family of entries collapsed into one (`text`): those whose dataset `belongs`. */
export interface LegendFamily {
	text: string;
	belongs: (datasetIndex: number) => boolean;
	/** Its swatch's dashes (the family's line), where its entries are lines. */
	lineDash?: number[];
}

/**
 * Each family of two entries or more as one entry where its first was: its words `text`, the
 * first's swatch, every dataset of it (`datasetIndices`, toggled together) and hidden only while
 * every one is (`visible` tells, by dataset).
 */
export function collapseLegend<T extends FitItem>(
	items: readonly T[],
	families: readonly LegendFamily[],
	visible: (datasetIndex: number) => boolean
): T[] {
	let out = [...items];
	for (const family of families) {
		const members = out.filter((item) => family.belongs(item.datasetIndex ?? -1));
		if (members.length < 2) continue;
		const indices = members.map((item) => item.datasetIndex ?? -1);
		const merged: T = {
			...members[0]!,
			text: family.text,
			datasetIndices: indices,
			hidden: indices.every((i) => !visible(i)),
			...(family.lineDash ? { lineDash: [...family.lineDash] } : {})
		};
		out = out.flatMap((item) =>
			item === members[0] ? [merged] : members.includes(item) ? [] : [item]
		);
	}
	return out;
}
