/**
 * The point labels' placer (owner, 2026-11-12, nit 5; Q1 "Shapes go too";
 * docs/proposals/pumps-nits.md item 5, rule 7; slice 5c): one pure placePointLabels for both
 * charts, tested as placeCurveLabels is (a fixed-width `measure`, no canvas), on the geometry the
 * running app gave in the one-off, lineups and condenser views at 454, 340 and 270 px
 * (__fixtures__/point-labels-geometry.json: every single-point mark's centre and the plot,
 * captured on web/pump-case-numbers with slice 5b's case numbers), each mark drawn as slice 5c
 * draws it: a member's dot r 6 with a 2 px edge (rule 2), the Group's ink dot r 7 with a 2 px edge
 * (rule 3), another case's slate ring r 10, 2 px (rule 4).
 *
 * The contract these tests hold (rule 7):
 * - `placePointLabels(items, obstacles, plot, measure, size)` places a label for each item, in
 *   the order given (this case's: the Group, then the members; then the rings in number order),
 *   clear of `obstacles` (marks it does not label: the pump chart's operating point, shutoff
 *   dash, BEP crosses and duty dots) and of every item's mark. An item's `r` is its mark's extent
 *   from its centre (its radius and half its border); a mark's box is its centre ± r.
 * - A label is text written left-aligned at (x, y), its baseline at y; its `box` is the text's,
 *   from `size` above the baseline to a quarter of it below, `measure(text)` wide, as
 *   pumpGroupConfig's textBox. "[…]" leads a ring's label: its case numbers, which fillLabel
 *   draws in a box as wide as the bracketed text.
 * - Eight places are tried round the point with the box 2 px clear of the mark (r + 2 from its
 *   centre), then eight at r + 14, where a 1 px leader joins label and mark; a far place is taken
 *   only where its leader runs clear of every other mark and label.
 * - A place is taken only inside the plot, clear of every label placed (at least 4 px apart) and
 *   of every mark but the item's own, and nearer the label's own point than any other point of its
 *   kind (strictly: a tie names neither).
 * - Members whose dots are 12 px apart or less (clusterPoints) share one label: their names where
 *   they fit, else "All pumps" (all the members drawn), else "{k} pumps".
 * - A ring tries "[n] name" (where its item has a name) and then "[n]"; one with no place joins
 *   the nearest ring label within 40 px, its numbers ascending ("[1, 5]"), the label placed again.
 * - Anything still without a place is left out, by index, so the notes can name it (never only
 *   counted): every item is named by exactly one label or left out.
 */
import { describe, expect, it } from 'vitest';
import geometry from './__fixtures__/point-labels-geometry.json';
import {
	clusterPoints,
	notLabelledNote,
	placePointLabels,
	type PlacedPointLabel,
	type PointLabelItem,
	type PointLabelPlacement
} from './point-labels';
import { caseTagText, type CaseNumber } from './pump-chart';
import type { PxBox } from './pump-group-chart';

/** The font's size on the screen (px): both charts' point labels (pumpGroupConfig, caseLabels). */
const SIZE = 12;
/** A text's width: 6 px a character, as testing/curve-family.ts drawnChart measures. */
const measure = (text: string) => text.length * 6;
/** Slice 5c's marks (rules 2 to 4): radius and border, the extent half the border past it. */
const MEMBER_R = 6 + 2 / 2;
const GROUP_R = 7 + 2 / 2;
const RING_R = 10 + 2 / 2;
/** Rule 7's distances (px): the near places' and the far ones' clearance, the labels' gap. */
const NEAR = 2;
const FAR = 14;
const GAP = 4;
/** Members this close share a label; a ring number joins a label this close (rule 7). */
const CLUSTER = 12;

interface Mark {
	kind: string;
	x: number;
	y: number;
	id?: string;
	name?: string;
	text?: string;
	numbers?: CaseNumber[];
	radius?: number;
	border?: number;
	label?: string;
}
interface Chart {
	width: number;
	plot: PxBox;
	marks: Mark[];
}
const VIEWS = geometry.views as unknown as Record<string, { pump: Chart; group: Chart }>;
const VIEW_NAMES = Object.keys(VIEWS);

/** What the placer is given for a chart: its items in rule 7's order and the other marks. */
function inputOf(chart: Chart): { items: PointLabelItem[]; obstacles: PxBox[] } {
	const items: PointLabelItem[] = [];
	const obstacles: PxBox[] = [];
	for (const m of chart.marks.filter((m) => m.kind === 'group'))
		items.push({ kind: 'group', x: m.x, y: m.y, r: GROUP_R, text: m.text! });
	for (const m of chart.marks.filter((m) => m.kind === 'member'))
		items.push({ kind: 'member', x: m.x, y: m.y, r: MEMBER_R, id: m.id!, name: m.name! });
	const rings = chart.marks
		.filter((m) => m.kind === 'ring')
		.sort((a, b) => Number(a.numbers![0]) - Number(b.numbers![0]));
	for (const m of rings)
		items.push({
			kind: 'ring',
			x: m.x,
			y: m.y,
			r: RING_R,
			numbers: m.numbers!,
			...(m.name ? { name: m.name } : {})
		});
	for (const m of chart.marks.filter((m) => !['group', 'member', 'ring'].includes(m.kind))) {
		const r = m.radius! + m.border! / 2;
		obstacles.push({ left: m.x - r, right: m.x + r, top: m.y - r, bottom: m.y + r });
	}
	return { items, obstacles };
}

const markBox = (it: PointLabelItem): PxBox => ({
	left: it.x - it.r,
	right: it.x + it.r,
	top: it.y - it.r,
	bottom: it.y + it.r
});
/** Boxes overlap (touching edges do not). */
const overlaps = (a: PxBox, b: PxBox) =>
	a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
/** The space between two boxes (px): 0 or less where they overlap. */
const gapBetween = (a: PxBox, b: PxBox) =>
	Math.max(a.left - b.right, b.left - a.right, a.top - b.bottom, b.top - a.bottom);
/** A point's distance to a box (0 inside it). */
const distance = (box: PxBox, x: number, y: number) =>
	Math.hypot(Math.max(box.left - x, 0, x - box.right), Math.max(box.top - y, 0, y - box.bottom));
/** A segment crosses a box's inside (Liang–Barsky, the edges themselves excluded). */
function crosses(x1: number, y1: number, x2: number, y2: number, b: PxBox): boolean {
	const e = 1e-9;
	const box = { left: b.left + e, right: b.right - e, top: b.top + e, bottom: b.bottom - e };
	let t0 = 0;
	let t1 = 1;
	const dx = x2 - x1;
	const dy = y2 - y1;
	for (const [p, q] of [
		[-dx, x1 - box.left],
		[dx, box.right - x1],
		[-dy, y1 - box.top],
		[dy, box.bottom - y1]
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

/** The words an item is named by in its label: a member's name, a ring's numbers. */
function memberTexts(items: readonly PointLabelItem[], named: readonly number[]): string[] {
	const members = items.filter((it) => it.kind === 'member');
	const names = named.map((i) => (items[i] as Extract<PointLabelItem, { kind: 'member' }>).name);
	return [
		names.join(', '),
		...(named.length > 1 && named.length === members.length ? ['All pumps'] : []),
		...(named.length > 1 ? [`${named.length} pumps`] : [])
	];
}

/**
 * Rule 7's checks on one placement, each failure naming where: every item named once or left out;
 * each label's text its items' words, its box its text's; inside the plot; no overlap with another
 * label (4 px apart at least) or a mark not its own; no label over a point's centre; nearer its own
 * point than any other of its kind; a near label without a leader, 2 px clear of its mark, a far one
 * 14 px clear with a leader from its box to its mark that runs clear of every other mark and label.
 */
function checkPlacement(
	where: string,
	items: readonly PointLabelItem[],
	obstacles: readonly PxBox[],
	plot: PxBox,
	placement: PointLabelPlacement
) {
	const { labels, leftOut } = placement;
	// Every item named by exactly one label, or left out: nothing is dropped silently.
	const named = [...labels.flatMap((l) => l.items), ...leftOut].sort((a, b) => a - b);
	expect(named, `${where}: every item once`).toEqual(items.map((_, i) => i));
	for (const label of labels) {
		const at = `${where}: "${label.text}"`;
		const own = label.items.map((i) => items[i]!);
		expect(new Set(own.map((it) => it.kind)).size, `${at} names one kind`).toBe(1);
		expect(label.kind, at).toBe(own[0]!.kind);
		// Its text: the Group's words, its members' names (or "All pumps", "{k} pumps"), or its
		// rings' numbers ascending in the box, a lone ring's name after them where it has one.
		if (label.kind === 'group') {
			expect(own, at).toHaveLength(1);
			expect(label.text, at).toBe((own[0] as Extract<PointLabelItem, { kind: 'group' }>).text);
		} else if (label.kind === 'member') {
			expect(memberTexts(items, label.items), at).toContain(label.text);
		} else {
			const rings = own as Extract<PointLabelItem, { kind: 'ring' }>[];
			const tags = `[${caseTagText(rings.flatMap((r) => r.numbers))}]`;
			const named = rings.length === 1 && rings[0]!.name ? [`${tags} ${rings[0]!.name}`] : [];
			expect([...named, tags], at).toContain(label.text);
		}
		// Its box: the text's, from the font's size above the baseline to a quarter below.
		const box = {
			left: label.x,
			right: label.x + measure(label.text),
			top: label.y - SIZE,
			bottom: label.y + SIZE / 4
		};
		for (const edge of ['left', 'right', 'top', 'bottom'] as const)
			expect(label.box[edge], `${at}: its box's ${edge}`).toBeCloseTo(box[edge], 6);
		// Inside the plot.
		expect(label.box.left, `${at} inside the plot's left edge`).toBeGreaterThanOrEqual(plot.left);
		expect(label.box.right, `${at} inside the plot's right edge`).toBeLessThanOrEqual(plot.right);
		expect(label.box.top, `${at} inside the plot's top`).toBeGreaterThanOrEqual(plot.top);
		expect(label.box.bottom, `${at} inside the plot's foot`).toBeLessThanOrEqual(plot.bottom);
		// Clear of every other label, 4 px apart at least.
		for (const other of labels) {
			if (other === label) continue;
			expect(gapBetween(label.box, other.box), `${at} and "${other.text}"`).toBeGreaterThanOrEqual(
				GAP
			);
		}
		// Clear of every mark not its own: the other items' and the obstacles.
		const foreign = [
			...items.flatMap((it, i) => (label.items.includes(i) ? [] : [{ box: markBox(it), i }])),
			...obstacles.map((box) => ({ box, i: -1 }))
		];
		for (const f of foreign)
			expect(overlaps(label.box, f.box), `${at} over item ${f.i}'s mark`).toBe(false);
		// Over no point's centre, its own or another's.
		for (const it of items)
			expect(distance(label.box, it.x, it.y), `${at} over a point`).toBeGreaterThan(0);
		// Nearer its own point than any other of its kind (strictly).
		const mine = Math.min(...own.map((it) => distance(label.box, it.x, it.y)));
		items.forEach((it, i) => {
			if (it.kind !== label.kind || label.items.includes(i)) return;
			expect(mine, `${at} nearer its own point than item ${i}`).toBeLessThan(
				distance(label.box, it.x, it.y)
			);
		});
		// Near, without a leader; or far, with one from its box to its mark, on a clear path.
		const nearest = own.reduce((a, b) =>
			distance(label.box, a.x, a.y) - a.r <= distance(label.box, b.x, b.y) - b.r ? a : b
		);
		const clearance = distance(label.box, nearest.x, nearest.y) - nearest.r;
		if (label.leader === null) {
			expect(clearance, `${at} near: 2 px clear of its mark`).toBeLessThanOrEqual(NEAR + 0.5);
		} else {
			expect(clearance, `${at} far: 14 px clear of its mark`).toBeGreaterThanOrEqual(FAR - 0.5);
			const { x1, y1, x2, y2 } = label.leader;
			expect(distance(label.box, x1, y1), `${at} leader starts at its box`).toBeLessThanOrEqual(
				0.5
			);
			const end = Math.min(...own.map((it) => Math.hypot(x2 - it.x, y2 - it.y) - it.r));
			expect(end, `${at} leader ends at its mark, not over it`).toBeGreaterThanOrEqual(-0.5);
			expect(end, `${at} leader ends at its mark`).toBeLessThanOrEqual(3);
			for (const f of foreign)
				expect(crosses(x1, y1, x2, y2, f.box), `${at} leader across item ${f.i}'s mark`).toBe(
					false
				);
			for (const other of labels) {
				if (other === label) continue;
				expect(crosses(x1, y1, x2, y2, other.box), `${at} leader across "${other.text}"`).toBe(
					false
				);
			}
		}
	}
}

function place(view: string, chart: 'pump' | 'group') {
	const c = VIEWS[view]![chart];
	const { items, obstacles } = inputOf(c);
	const placement = placePointLabels(items, obstacles, c.plot, measure, SIZE);
	return { c, items, obstacles, placement };
}
const textsOf = (labels: readonly PlacedPointLabel[]) => labels.map((l) => l.text);
/** The label naming item `i`, if any. */
const labelOf = (placement: PointLabelPlacement, i: number) =>
	placement.labels.find((l) => l.items.includes(i));

describe('placePointLabels on the captured charts (rule 7)', () => {
	it('holds the fixture the plan names: three views at 454, 340 and 270 px, both charts', () => {
		expect(VIEW_NAMES).toEqual([
			'one-off-454',
			'one-off-340',
			'one-off-270',
			'lineups-454',
			'lineups-340',
			'lineups-270',
			'condenser-454',
			'condenser-340',
			'condenser-270'
		]);
		for (const view of VIEW_NAMES) {
			expect(VIEWS[view]!.pump.width, view).toBe(Number(view.split('-').at(-1)));
			expect(VIEWS[view]!.group.marks.filter((m) => m.kind === 'member').length).toBeGreaterThan(1);
		}
	});

	for (const view of Object.keys(geometry.views))
		for (const chart of ['pump', 'group'] as const)
			it(`${view}, the ${chart} chart: no overlap, inside the plot, 4 px apart, each nearer its own point, leaders clear, nothing dropped silently`, () => {
				const { c, items, obstacles, placement } = place(view, chart);
				checkPlacement(`${view} ${chart}`, items, obstacles, c.plot, placement);
			});

	it('lineups, the pump chart at 454 px: the rings of cases 1 and 5 share one label, "[1, 5]"', () => {
		// Rings 5 and 6 are 0.1 px apart and ring 1 is 2.3 px from them: ring 5 has no place
		// nearer its own point than ring 1's or ring 6's, so it joins ring 1's label, its numbers
		// ascending, the label placed again. Ring 6, placed after it, finds a place of its own (the
		// design study's prototype drew "1, 5" and "6") or joins the same label ("[1, 5, 6]"), as
		// the places' geometry gives; either way it is named once (the checks above). At 340 and
		// 270 px the rings crowd the operating point and the BEP: there the checks above hold them.
		const { items, placement } = place('lineups-454', 'pump');
		const ring = (n: number) =>
			items.findIndex((it) => it.kind === 'ring' && it.numbers.includes(n));
		const joined = labelOf(placement, ring(1));
		expect(joined?.text).toMatch(/^\[1, 5(, 6)?\]$/);
		expect(joined!.items).toEqual(expect.arrayContaining([ring(1), ring(5)]));
		expect(labelOf(placement, ring(5))).toBe(joined);
	});

	it('lineups and condenser, the group chart: the members’ coincident dots share one label', () => {
		for (const view of [
			'lineups-454',
			'lineups-340',
			'lineups-270',
			'condenser-454',
			'condenser-340',
			'condenser-270'
		]) {
			const { items, placement } = place(view, 'group');
			const members = items.flatMap((it, i) => (it.kind === 'member' ? [i] : []));
			// Every member within 3.4 px of another (lineups) or 2.4 px (condenser): one cluster.
			expect(
				clusterPoints(
					members.map((i) => items[i]!),
					CLUSTER
				),
				view
			).toEqual([members.map((_, k) => k)]);
			const label = labelOf(placement, members[0]!);
			if (label) {
				expect(label.items, view).toEqual(members);
				expect(memberTexts(items, members), view).toContain(label.text);
			} else {
				// Left out together, never one name of several.
				expect(placement.leftOut, view).toEqual(expect.arrayContaining(members));
			}
			for (const l of placement.labels.filter((x) => x.kind === 'member'))
				expect(l.items, `${view}: "${l.text}"`).toEqual(members);
		}
		// At 454 px there is room for the label: the lineups' names whole, the condenser's
		// six long names as "All pumps".
		const lineups = place('lineups-454', 'group');
		expect(textsOf(lineups.placement.labels)).toContain('Pump P1, Pump P2, Pump P3, Pump P4');
		const condenser = place('condenser-454', 'group');
		expect(textsOf(condenser.placement.labels)).toContain('All pumps');
	});

	it('one-off, the group chart: each member named alone; at 454 and 340 px the Group, both pumps and every ring labelled', () => {
		for (const view of ['one-off-454', 'one-off-340', 'one-off-270']) {
			const { items, placement } = place(view, 'group');
			// Pump PA and Pump PB are 20 px apart or more: never one label.
			for (const l of placement.labels.filter((x) => x.kind === 'member'))
				expect(l.items, `${view}: "${l.text}"`).toHaveLength(1);
			if (view === 'one-off-270') continue;
			expect(textsOf(placement.labels), view).toEqual(
				expect.arrayContaining(['Group (crossing)', 'Pump PA', 'Pump PB'])
			);
			expect(placement.leftOut, view).toEqual([]);
			expect(placement.labels.flatMap((l) => l.items).length, view).toBe(items.length);
		}
	});

	it('a ring’s name follows its number where the whole label fits at a place (desktop), else its number alone', () => {
		// The one-off at 454 px: on the pump chart both rings are named (slice 5b drew "[2]" alone at
		// 1280 px: its name passed the plot's right edge); on the group chart rings 3 and 4, whose own
		// curves are not drawn (D24 §9.3).
		const pump = place('one-off-454', 'pump');
		expect(textsOf(pump.placement.labels).sort()).toEqual([
			'[2] Pump PB off',
			'[3] Delivery tank 5 m higher'
		]);
		const group = place('one-off-454', 'group');
		expect(textsOf(group.placement.labels)).toEqual(
			expect.arrayContaining(['[3] Delivery tank 5 m higher', '[4] Both pumps off'])
		);
		// Phones: the box alone (the item has no name to try).
		for (const view of ['one-off-340', 'one-off-270'])
			for (const l of place(view, 'pump').placement.labels)
				expect(l.text, view).toMatch(/^\[[^\]]+\]$/);
	});

	it('lineups, both charts at every width: rings that coincide share one label, and every ring is labelled', () => {
		// Rings within 12 px of one another share one label, as members do: cases 1, 5 and 6 on the
		// pump chart (0.1 to 2.3 px apart), cases 1 and 4–6 on the group chart (one ring for 4, 5
		// and 6, 1.5 px from ring 1). Apart, coincident rings have no place nearer one than the
		// other; one at a time, a ring left without a place joined a label 20 px away ("[2, 5, 6]")
		// or was left out (rings 5 and 6 at 340 px, ring 1 at 270 px).
		for (const width of [454, 340, 270]) {
			const pump = place(`lineups-${width}`, 'pump');
			expect(pump.placement.leftOut, `${width} pump`).toEqual([]);
			expect(textsOf(pump.placement.labels).sort(), `${width} pump`).toEqual([
				'[1, 5, 6]',
				'[2]',
				'[3]'
			]);
			const group = place(`lineups-${width}`, 'group');
			expect(group.placement.leftOut, `${width} group`).toEqual([]);
			expect(
				textsOf(group.placement.labels.filter((l) => l.kind === 'ring')).sort(),
				`${width} group`
			).toEqual(['[1, 4, 5, 6]', '[2]', '[3]']);
		}
	});
});

describe('placePointLabels, rule by rule (made-up points)', () => {
	const plot: PxBox = { left: 100, right: 300, top: 100, bottom: 300 };
	const member = (x: number, y: number, name: string): PointLabelItem => ({
		kind: 'member',
		x,
		y,
		r: MEMBER_R,
		id: name,
		name
	});
	const ring = (x: number, y: number, numbers: CaseNumber[], name?: string): PointLabelItem => ({
		kind: 'ring',
		x,
		y,
		r: RING_R,
		numbers,
		...(name ? { name } : {})
	});

	it('puts a free point’s label 2 px clear of its mark, to its right and centred on it, with no leader', () => {
		const items = [member(200, 200, 'Pump PA')];
		const placement = placePointLabels(items, [], plot, measure, SIZE);
		checkPlacement('free', items, [], plot, placement);
		const [label] = placement.labels;
		expect(label!.text).toBe('Pump PA');
		expect(label!.leader).toBeNull();
		expect(label!.box.left).toBeCloseTo(200 + MEMBER_R + NEAR, 5);
		expect(Math.abs((label!.box.top + label!.box.bottom) / 2 - 200)).toBeLessThanOrEqual(2);
	});

	it('tries the eight near places before any far one: blocked near, it is placed 14 px clear with a leader on a clear path', () => {
		// Every near place is blocked by a mark beside the point (left and right of it, 4 px clear
		// of its dot); the far places to the sides and the corners are blocked by taller marks
		// further out; above and below the point the far places are free, and their leaders pass
		// between the marks.
		const obstacles: PxBox[] = [
			{ left: 200 + MEMBER_R + 4, right: 260, top: 188, bottom: 212 },
			{ left: 140, right: 200 - MEMBER_R - 4, top: 188, bottom: 212 },
			{ left: 230, right: 260, top: 150, bottom: 250 },
			{ left: 140, right: 170, top: 150, bottom: 250 }
		];
		const items = [member(200, 200, 'Pump PA')];
		const placement = placePointLabels(items, obstacles, plot, measure, SIZE);
		checkPlacement('near blocked', items, obstacles, plot, placement);
		expect(placement.leftOut).toEqual([]);
		const [label] = placement.labels;
		expect(label!.leader).not.toBeNull();
		// Above or below it, its box centred on the point.
		expect(Math.abs((label!.box.left + label!.box.right) / 2 - 200)).toBeLessThanOrEqual(1);
	});

	it('joins a ring number with no place to the nearest ring label within 40 px only; beyond, it is left out', () => {
		// Ring 2 sits where nothing can be placed (a mark over the plot's right part); ring 1, 100 px
		// to its left, has room. 100 px apart: ring 2 does not join ring 1's label, it is left out.
		const items = [ring(150, 200, [1]), ring(250, 200, [2])];
		const obstacles: PxBox[] = [{ left: 190, right: 300, top: 100, bottom: 300 }];
		const placement = placePointLabels(items, obstacles, plot, measure, SIZE);
		checkPlacement('far apart', items, obstacles, plot, placement);
		expect(textsOf(placement.labels)).toEqual(['[1]']);
		expect(placement.leftOut).toEqual([1]);
	});

	it('names coincident members together: their names where they fit, else “All pumps”, else “{k} pumps”', () => {
		const three = [
			member(200, 200, 'Pump P1'),
			member(201, 200, 'Pump P2'),
			member(200, 202, 'Pump P3')
		];
		// Room for the names.
		const roomy = placePointLabels(three, [], plot, measure, SIZE);
		checkPlacement('roomy', three, [], plot, roomy);
		expect(roomy.labels.map((l) => [l.text, l.items])).toEqual([
			['Pump P1, Pump P2, Pump P3', [0, 1, 2]]
		]);
		// A plot 80 px wide: "Pump P1, Pump P2, Pump P3" (150 px) cannot fit, "All pumps" can.
		const narrow: PxBox = { left: 160, right: 240, top: 100, bottom: 300 };
		const all = placePointLabels(three, [], narrow, measure, SIZE);
		checkPlacement('narrow', three, [], narrow, all);
		expect(all.labels.map((l) => [l.text, l.items])).toEqual([['All pumps', [0, 1, 2]]]);
		// Two of three together (the third 60 px away): "2 pumps" where the names cannot fit.
		const some = [
			member(200, 200, 'Pump P1'),
			member(201, 200, 'Pump P2'),
			member(200, 260, 'Pump P3')
		];
		const two = placePointLabels(some, [], narrow, measure, SIZE);
		checkPlacement('two of three', some, [], narrow, two);
		expect(two.labels.map((l) => [l.text, l.items])).toEqual(
			expect.arrayContaining([['2 pumps', [0, 1]]])
		);
	});

	it('names rings that coincide in one label, their numbers ascending in one box', () => {
		const items = [ring(200, 200, [6]), ring(200.1, 200, [1]), ring(201, 202, [5], 'Pump P2 off')];
		const placement = placePointLabels(items, [], plot, measure, SIZE);
		checkPlacement('coincident rings', items, [], plot, placement);
		expect(placement.labels.map((l) => [l.text, l.items, l.leader])).toEqual([
			['[1, 5, 6]', [0, 1, 2], null]
		]);
	});

	// The placer writes a ring's box itself, so the chart's chunk carries no page code (a leaf
	// module, as chart-marks.ts): its box must read as the lists' boxes do, pump-chart.ts caseTagText,
	// "Base" first and then the numbers ascending, whatever order the rings come in.
	it('writes the rings’ box as the lists do (caseTagText): “Base” first, then the numbers ascending', () => {
		const numbers: CaseNumber[][] = [[12], ['Base'], [3], [1]];
		const items = numbers.map((n, i) => ring(200 + i * 0.5, 200, n));
		const placement = placePointLabels(items, [], plot, measure, SIZE);
		expect(placement.labels.map((l) => l.text)).toEqual([`[${caseTagText(numbers.flat())}]`]);
		expect(placement.labels[0]!.text).toBe('[Base, 1, 3, 12]');
	});

	it('lets a ring with no place join a ring label placed after it, once every ring has tried', () => {
		// Ring 1's places are all taken: those to its left by a mark over the plot's left part, those
		// to its right by ring 2's ring or by being nearer ring 2. Ring 2, 30 px to its right, is
		// labelled after it; ring 1 then joins its label, "[1, 2]", placed again.
		const items = [ring(150, 200, [1]), ring(180, 200, [2])];
		const obstacles: PxBox[] = [{ left: 100, right: 165, top: 100, bottom: 300 }];
		const placement = placePointLabels(items, obstacles, plot, measure, SIZE);
		checkPlacement('joins a later label', items, obstacles, plot, placement);
		expect(placement.labels.map((l) => [l.text, l.items])).toEqual([['[1, 2]', [0, 1]]]);
		expect(placement.leftOut).toEqual([]);
	});

	it('leaves a label out where it has no place, by index, so the notes can name it', () => {
		// A plot too small for any label: both items are left out, none dropped silently.
		const tiny: PxBox = { left: 190, right: 215, top: 190, bottom: 215 };
		const items = [member(200, 200, 'Pump PA'), ring(205, 205, [2], 'Pump PB off')];
		const placement = placePointLabels(items, [], tiny, measure, SIZE);
		checkPlacement('tiny', items, [], tiny, placement);
		expect(placement.labels).toEqual([]);
		expect([...placement.leftOut].sort()).toEqual([0, 1]);
	});
});

describe('notLabelledNote (rule 7: a label left out is named, never only counted)', () => {
	it('names each point left out with its values, in the chart’s order; none: no note', () => {
		expect(
			notLabelledNote([
				{ name: 'Pump PA', mark: 'point', flow: '37.37 L/s', head: '29.55 m' },
				{ name: 'case 2, Pump PB off', mark: 'ring', flow: '40.75 L/s', head: '23.68 m' }
			])
		).toBe(
			'Not labelled on the chart: Pump PA, its point at 37.37 L/s and 29.55 m; case 2, Pump PB off, its ring at 40.75 L/s and 23.68 m.'
		);
		expect(notLabelledNote([])).toBeNull();
	});
});

describe('clusterPoints (rule 7: members 12 px apart or less share one label)', () => {
	it('links points 12 px apart or less, in chains, by index', () => {
		const points = [
			{ x: 0, y: 0 },
			{ x: 10, y: 0 },
			{ x: 20, y: 0 },
			{ x: 32.5, y: 0 },
			{ x: 0, y: 12 }
		];
		// 0–1 and 1–2 are 10 px apart (0–2 20 px: one chain), 0–4 12 px; 2–3 12.5 px: apart.
		expect(clusterPoints(points, CLUSTER)).toEqual([[0, 1, 2, 4], [3]]);
		expect(clusterPoints([], CLUSTER)).toEqual([]);
	});
});
