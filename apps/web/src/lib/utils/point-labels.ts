/**
 * The point labels' placer (owner, 2026-11-12, nit 5; Q1 "Shapes go too";
 * docs/proposals/pumps-nits.md item 5, rule 7; slice 5c): one pure placePointLabels for both
 * charts, as placeCurveLabels is for the curves' labels (pump-group-chart.ts): the charts' plugins
 * call it with Chart.js's pixels and `ctx.measureText`, the tests with a fixed-width `measure`.
 *
 * Pumps are named dots, the group point the word "Group" and every other case a ring tagged with
 * its number, so a label is how a point is told apart: none is drawn over another label or over a
 * mark it does not name, none leaves the plot, and none is dropped silently. A label the placer
 * cannot place is returned by its item's index, so the notes name it with its values
 * (notLabelledNote), never only count it.
 *
 * Point labels come before curve labels (rule 7): the charts place these first and keep the curve
 * labels clear of their boxes and leaders, D24's curve labels (placeCurveLabels' obstacles) and
 * then the group system curve's tag, placed last (pump-chart-config.ts; review DOTS-LABELS-B1).
 * The labels are drawn with a halo of the surface colour, POINT_LABEL_HALO px wide, so a label
 * reads over a curve; the gap between labels keeps two halos apart.
 *
 * A leaf module (type imports only), as chart-marks.ts is: the chart's chunk (pump-chart-config.ts)
 * draws with it and the page's notes word its left-out points with notLabelledNote, and it carries
 * no page code into the chunk.
 */
import type { CaseNumber } from './pump-chart';
import type { PxBox } from './pump-group-chart';

/**
 * A point to label, in the chart's pixels: its centre and `r`, its mark's extent from the centre
 * (its radius and half its border), so its mark's box is the centre ± r.
 * - `group`: the station's duty, the ink dot; `text` its label ("Group", "Group (crossing)"),
 *   `short` the label it takes where `text` has no place ("Group": review DOTS-LABELS-B6).
 * - `member`: a pump's point (a dot, or the diamond while held at zero flow), named as typed.
 * - `ring`: another case's ring; `numbers` its cases' numbers (drawn in a box, fillLabel) and
 *   `name`, where the chart names it beside the box (desktop and the image), its cases' words.
 */
export type PointLabelItem =
	| { kind: 'group'; x: number; y: number; r: number; text: string; short?: string }
	| { kind: 'member'; x: number; y: number; r: number; id: string; name: string }
	| { kind: 'ring'; x: number; y: number; r: number; numbers: CaseNumber[]; name?: string };

/** A line from a far label to its mark (px). */
export interface PointLabelLeader {
	x1: number;
	y1: number;
	x2: number;
	y2: number;
}

/** A label placed by placePointLabels. */
export interface PlacedPointLabel {
	text: string;
	kind: PointLabelItem['kind'];
	/** The items it names, by their index in the input: more than one when they share it. */
	items: number[];
	/** The text's left end and its baseline (px: textAlign 'left', textBaseline 'alphabetic'). */
	x: number;
	y: number;
	/** The text's box: from the font's size above the baseline to a quarter of it below. */
	box: PxBox;
	/** From its box to its mark's edge, for a far label; null for a near one. */
	leader: PointLabelLeader | null;
}

/** The labels drawn, and the items without one (by index, ascending) for the notes to name. */
export interface PointLabelPlacement {
	labels: PlacedPointLabel[];
	leftOut: number[];
}

/** A near label's box is this far clear of its mark (px). */
export const POINT_LABEL_NEAR = 2;
/** A far label's box is this far clear of its mark (px), joined to it by a leader. */
export const POINT_LABEL_FAR = 14;
/** The leader's width (px). */
export const POINT_LABEL_LEADER = 1;
/** Labels are at least this far apart (px): two halos never touch. */
export const POINT_LABEL_GAP = 4;
/** The halo drawn round a label's text, in the surface colour (px, the stroke's width). */
export const POINT_LABEL_HALO = 3;
/** Members whose points are this close or closer share one label (px). */
export const POINT_LABEL_CLUSTER = 12;
/** A ring number with no place of its own joins a ring label this close or closer (px). */
export const POINT_LABEL_JOIN = 40;

/**
 * The points within `within` px of one another, chained (single link: a point joins a group when
 * it is that close to any point of it), as groups of indices: each group ascending, the groups in
 * order of their first index.
 */
export function clusterPoints(
	points: readonly { x: number; y: number }[],
	within: number
): number[][] {
	const parent = points.map((_, i) => i);
	const root = (i: number): number => {
		while (parent[i] !== i) i = parent[i] = parent[parent[i]!]!;
		return i;
	};
	for (let a = 0; a < points.length; a++)
		for (let b = a + 1; b < points.length; b++) {
			const p = points[a]!;
			const q = points[b]!;
			if (Math.hypot(p.x - q.x, p.y - q.y) <= within) parent[root(b)] = root(a);
		}
	const groups = new Map<number, number[]>();
	points.forEach((_, i) => {
		const r = root(i);
		groups.set(r, [...(groups.get(r) ?? []), i]);
	});
	return [...groups.values()].sort((a, b) => a[0]! - b[0]!);
}

/** Boxes overlap (touching edges do not). */
const overlaps = (a: PxBox, b: PxBox) =>
	a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

/** The space between two boxes (px): 0 or less where they overlap. */
const gapBetween = (a: PxBox, b: PxBox) =>
	Math.max(a.left - b.right, b.left - a.right, a.top - b.bottom, b.top - a.bottom);

/** A point's distance to a box (0 inside it or on its edge). */
const distance = (box: PxBox, x: number, y: number) =>
	Math.hypot(Math.max(box.left - x, 0, x - box.right), Math.max(box.top - y, 0, y - box.bottom));

/**
 * A segment passes through a box's inside (Liang–Barsky; running along an edge does not): a
 * leader across a label or a mark. The pump chart's short labels ask it of the rings' leaders.
 */
export function leaderCrosses(line: PointLabelLeader, b: PxBox): boolean {
	const e = 1e-9;
	const box = { left: b.left + e, right: b.right - e, top: b.top + e, bottom: b.bottom - e };
	const dx = line.x2 - line.x1;
	const dy = line.y2 - line.y1;
	let t0 = 0;
	let t1 = 1;
	for (const [p, q] of [
		[-dx, line.x1 - box.left],
		[dx, box.right - line.x1],
		[-dy, line.y1 - box.top],
		[dy, box.bottom - line.y1]
	] as const) {
		if (p === 0) {
			if (q < 0) return false;
			continue;
		}
		const t = q / p;
		if (p < 0) t0 = Math.max(t0, t);
		else t1 = Math.min(t1, t);
		if (t0 > t1) return false;
	}
	return t0 < t1;
}

const markBox = (it: PointLabelItem): PxBox => ({
	left: it.x - it.r,
	right: it.x + it.r,
	top: it.y - it.r,
	bottom: it.y + it.r
});

/**
 * A ring label's text: its cases' numbers ascending in the box, "Base" first ("[1, 5]"), as
 * pump-chart.ts caseTagText writes the box (equal by test), here so the chunk needs no page code.
 */
const ringTag = (numbers: readonly CaseNumber[]) =>
	`[${[...numbers].sort((a, b) => (a === b ? 0 : a === 'Base' ? -1 : b === 'Base' ? 1 : a - b)).join(', ')}]`;

/**
 * Where the points' labels go (rule 7), pure. `items` in the order they are placed: this case's
 * (the Group, then its members, a held one among them), then the rings in number order; each
 * label clear of `obstacles` (the marks it does not label: the pump chart's operating point,
 * shutoff dash, BEP crosses and duty dots) and of every item's mark but its own. `size` is the
 * font's size (px): a label's box runs from `size` above its baseline to a quarter of it below,
 * `measure(text)` wide (a ring's "[…]" is drawn in a box as wide as the bracketed text).
 * - Eight places are tried round the point, its box POINT_LABEL_NEAR px clear of the mark: right,
 *   left, above, below, then the four corners. Then the same eight POINT_LABEL_FAR px clear, where
 *   a leader joins label and mark, taken only where the leader crosses no other mark or label.
 * - A place is taken only inside the plot, POINT_LABEL_GAP px or more from every label placed,
 *   over no mark but its own and over no point's centre, and strictly nearer its own point than
 *   any other point of its kind (a tie names neither point).
 * - Members within POINT_LABEL_CLUSTER px of one another (clusterPoints) share one label: their
 *   names where they fit, else "All pumps" (the cluster holds every member), else "{k} pumps".
 * - Rings within POINT_LABEL_CLUSTER px of one another share one label too, their numbers in one
 *   box ("[1, 5, 6]"): rings that coincide have no place nearer one than the other, so apart they
 *   would have none (the lineups' cases 1, 5 and 6 on the pump chart, 0.1 to 2.3 px apart).
 * - A ring tries "[n] name" where it has a name (a ring of one case), then "[n]". Once every ring
 *   has tried, each one without a place, in order, joins the nearest ring label within
 *   POINT_LABEL_JOIN px of one of its rings, which is placed again with the numbers of both
 *   ("[1, 5]"); where the joined label has no place either, the ring is left out and the label
 *   stays as it was.
 * - The Group tries its `text`, then its `short` where it has one ("Group (crossing)", then
 *   "Group": review DOTS-LABELS-B6), as members and rings try shorter labels.
 * - A place is also clear of every leader drawn before it (review DOTS-LABELS-A1).
 * - The items are placed in the order given. Where that leaves a pump's label out, they are placed
 *   once more with the pumps left out moved before the other pumps (just after the Group), and
 *   that placement is taken where it leaves strictly fewer items out in all, rings included; else
 *   the given order's stands (review DOTS-LABELS-B7: greedy, Pump PA's label took the only places
 *   of the held Pump PB's, at the plot's left edge, although both fit).
 * - Any item still without a label is left out, by index, for the notes to name with its values.
 */
export function placePointLabels(
	items: readonly PointLabelItem[],
	obstacles: readonly PxBox[],
	plot: PxBox,
	measure: (text: string) => number,
	size: number
): PointLabelPlacement {
	const height = size * 1.25;
	const marks = items.map(markBox);

	/** The eight boxes of a `width` px label `clear` px off the mark of `it`, in the order tried. */
	const places = (it: PointLabelItem, clear: number, width: number): PxBox[] => {
		const d = it.r + clear;
		// A corner's box touches the circle of radius d round the point at its corner.
		const c = d / Math.SQRT2;
		const at = (left: number, top: number): PxBox => ({
			left,
			right: left + width,
			top,
			bottom: top + height
		});
		return [
			at(it.x + d, it.y - height / 2),
			at(it.x - d - width, it.y - height / 2),
			at(it.x - width / 2, it.y - d - height),
			at(it.x - width / 2, it.y + d),
			at(it.x + c, it.y - c - height),
			at(it.x - c - width, it.y - c - height),
			at(it.x + c, it.y + c),
			at(it.x - c - width, it.y + c)
		];
	};

	/**
	 * The first place for `text` naming the items `own` (of one kind), near before far, round each
	 * of its points in turn, clear of the `labels` placed; `replacing`, a label it would replace, is
	 * not in its way. Null: none.
	 */
	const placeText = (
		labels: readonly PlacedPointLabel[],
		own: readonly number[],
		kind: PointLabelItem['kind'],
		text: string,
		replacing: PlacedPointLabel | null = null
	): PlacedPointLabel | null => {
		const width = measure(text);
		const others = labels.filter((l) => l !== replacing);
		const foreign = [...marks.filter((_, i) => !own.includes(i)), ...obstacles];
		const rivals = items.filter((it, i) => it.kind === kind && !own.includes(i));
		for (const far of [false, true]) {
			for (const anchor of own) {
				const it = items[anchor]!;
				for (const box of places(it, far ? POINT_LABEL_FAR : POINT_LABEL_NEAR, width)) {
					if (
						box.left < plot.left ||
						box.right > plot.right ||
						box.top < plot.top ||
						box.bottom > plot.bottom
					)
						continue;
					if (foreign.some((m) => overlaps(m, box))) continue;
					if (others.some((l) => gapBetween(l.box, box) < POINT_LABEL_GAP)) continue;
					// Nor across a leader drawn before it (review DOTS-LABELS-A1): the leader would seem to
					// run from this label's box.
					if (others.some((l) => l.leader && leaderCrosses(l.leader, box))) continue;
					if (items.some((p) => distance(box, p.x, p.y) <= 0)) continue;
					const mine = Math.min(...own.map((i) => distance(box, items[i]!.x, items[i]!.y)));
					if (rivals.some((p) => distance(box, p.x, p.y) <= mine)) continue;
					let leader: PointLabelLeader | null = null;
					if (far) {
						// From the box's point nearest the mark's centre to the mark's edge.
						const x1 = Math.min(Math.max(it.x, box.left), box.right);
						const y1 = Math.min(Math.max(it.y, box.top), box.bottom);
						const length = Math.hypot(x1 - it.x, y1 - it.y);
						leader = {
							x1,
							y1,
							x2: it.x + ((x1 - it.x) * it.r) / length,
							y2: it.y + ((y1 - it.y) * it.r) / length
						};
						const line = leader;
						if (foreign.some((m) => leaderCrosses(line, m))) continue;
						if (others.some((l) => leaderCrosses(line, l.box))) continue;
					}
					return {
						text,
						kind,
						items: [...own],
						x: box.left,
						y: box.top + size,
						box,
						leader
					};
				}
			}
		}
		return null;
	};

	/** The first of `texts` that has a place among `labels`, or null. */
	const placeFirst = (
		labels: readonly PlacedPointLabel[],
		own: readonly number[],
		kind: PointLabelItem['kind'],
		texts: string[]
	) => {
		for (const text of texts) {
			const placed = placeText(labels, own, kind, text);
			if (placed) return placed;
		}
		return null;
	};

	/** The items of `kind` in clusters (clusterPoints), as their indices in `items`. */
	const clustersOf = (kind: 'member' | 'ring') => {
		const of = items.flatMap((it, i) => (it.kind === kind ? [i] : []));
		return clusterPoints(
			of.map((i) => items[i]!),
			POINT_LABEL_CLUSTER
		).map((group) => group.map((k) => of[k]!));
	};
	const memberCount = items.filter((it) => it.kind === 'member').length;
	const clusters = [...clustersOf('member'), ...clustersOf('ring')];
	const numbersOf = (own: readonly number[]) =>
		own.flatMap((k) => (items[k] as Extract<PointLabelItem, { kind: 'ring' }>).numbers);

	/** The labels placed taking the items in `sequence` (their indices), and those left out. */
	const pass = (sequence: readonly number[]): PointLabelPlacement => {
		const labels: PlacedPointLabel[] = [];
		const leftOut: number[] = [];
		/** Rings without a place of their own, in order: they join a ring label after every ring. */
		const unplaced: number[][] = [];
		const done = new Set<number>();
		for (const i of sequence) {
			const it = items[i]!;
			if (done.has(i)) continue;
			const own = it.kind === 'group' ? [i] : clusters.find((c) => c.includes(i))!;
			for (const k of own) done.add(k);
			let texts: string[];
			if (it.kind === 'group')
				texts = it.short && it.short !== it.text ? [it.text, it.short] : [it.text];
			else if (it.kind === 'member') {
				const names = own.map(
					(k) => (items[k] as Extract<PointLabelItem, { kind: 'member' }>).name
				);
				texts = [names.join(', ')];
				if (own.length > 1) {
					if (own.length === memberCount) texts.push('All pumps');
					texts.push(`${own.length} pumps`);
				}
			} else {
				const tag = ringTag(numbersOf(own));
				texts = own.length === 1 && it.name ? [`${tag} ${it.name}`, tag] : [tag];
			}
			const placed = placeFirst(labels, own, it.kind, texts);
			if (placed) labels.push(placed);
			else if (it.kind === 'ring') unplaced.push(own);
			else leftOut.push(...own);
		}
		// A ring with no place of its own: its numbers join the nearest ring label, within reach of
		// one of its rings, and that label is placed again; else it is left out.
		for (const own of unplaced) {
			const reach = (l: PlacedPointLabel) =>
				Math.min(
					...l.items.flatMap((k) =>
						own.map((i) => Math.hypot(items[k]!.x - items[i]!.x, items[k]!.y - items[i]!.y))
					)
				);
			const nearest = labels
				.filter((l) => l.kind === 'ring')
				.map((label) => ({ label, d: reach(label) }))
				.filter((n) => n.d <= POINT_LABEL_JOIN)
				.sort((a, b) => a.d - b.d)[0];
			const both = nearest ? [...nearest.label.items, ...own].sort((a, b) => a - b) : [];
			const joined = nearest
				? placeText(labels, both, 'ring', ringTag(numbersOf(both)), nearest.label)
				: null;
			if (joined) labels[labels.indexOf(nearest!.label)] = joined;
			else leftOut.push(...own);
		}
		return { labels, leftOut: leftOut.sort((a, b) => a - b) };
	};

	const given = items.map((_, i) => i);
	const first = pass(given);
	// A pump's label left out: once more, the members' places in the order filled again with those
	// left out first, the other items keeping theirs (review DOTS-LABELS-B7); taken only where
	// strictly fewer items are left out in all.
	const late = first.leftOut.filter((i) => items[i]!.kind === 'member');
	const members = given.filter((i) => items[i]!.kind === 'member');
	const refilled = [...late, ...members.filter((i) => !late.includes(i))];
	let k = 0;
	const sequence = given.map((i) => (items[i]!.kind === 'member' ? refilled[k++]! : i));
	if (sequence.every((i, at) => i === given[at])) return first;
	const second = pass(sequence);
	return second.leftOut.length < first.leftOut.length ? second : first;
}

/** A point whose label is left out, as the notes name it (rule 7: never only counted). */
export interface NotLabelledPoint {
	/**
	 * Who it is: "Group", "Pump PA", "Pump PB, held at zero flow", "case 2, Pump PB off", or a
	 * curve's tag, "Group system curve".
	 */
	name: string;
	/**
	 * Its mark: a point (the Group's, a pump's), another case's ring, or a curve's end, where its
	 * tag goes (review DOTS-LABELS-B1: "Group system curve, its end at 85.21 L/s and 50 m").
	 */
	mark: 'point' | 'ring' | 'end';
	/** Where it is, in display units with their unit: "40.75 L/s", "23.68 m". */
	flow: string;
	head: string;
}

/**
 * The notes' sentence naming each point whose label is left out (rule 7), in the chart's order,
 * with its values: "Not labelled on the chart: Pump PA, its point at 37.37 L/s and 29.55 m; case
 * 2, Pump PB off, its ring at 40.75 L/s and 23.68 m." Null when every point is labelled.
 */
export function notLabelledNote(points: readonly NotLabelledPoint[]): string | null {
	if (!points.length) return null;
	const named = points.map((p) => `${p.name}, its ${p.mark} at ${p.flow} and ${p.head}`);
	return `Not labelled on the chart: ${named.join('; ')}.`;
}
