/**
 * One mark spec for the canvas and the page's swatches (owner, 2026-11-12, nit 5; Q1 "Shapes go
 * too"; docs/proposals/pumps-nits.md item 5, rule 8; slice 5c): each point mark's radius, border,
 * fill and stroke, which both charts draw (pump-chart-config.ts) and the HTML legend's swatches
 * draw again (PumpGroupFigure.svelte), so a swatch is the mark it names; and the plot's surface
 * colour, the edge a dot is drawn with and the inside of a hollow mark, in place of white typed
 * where each mark is drawn. chart-marks.test.ts holds the charts to it.
 *
 * A leaf module (no imports): the chart's chunk and the page both import it, and it carries no
 * other code between them. Its colours equal pump-chart-config.ts CHART_COLORS (ink, slate) and
 * pump-group-chart.ts GROUP_INK and GROUP_OTHER, which the chart chunk and the page each hold.
 *
 * A dark theme, when there is one, takes its own steps rather than these flipped: slate-400 rings,
 * a light disc for the Group's dot, the halo and the surface set to the plot's background (the
 * design study's measurements; no code until then).
 */

/** A point mark: its radius and border width (px), its fill and its stroke (the border's colour). */
export interface ChartMark {
	radius: number;
	border: number;
	fill: string;
	stroke: string;
}

/** The plot's background on the light theme: a dot's 2 px edge, a hollow mark's inside. */
export const SURFACE = '#ffffff';

/**
 * The marks:
 * - `group`: the station's duty, the ink dot (rule 3), r 7 with its surface edge;
 * - `ring`: another case's duty, a slate ring (rule 4), r 10, 2 px, transparent inside;
 * - `member`: a pump's point on the group chart (rule 2), a dot r 6 with its surface edge, filled
 *   with its line's colour (memberMark);
 * - `held`: a pump held at zero flow (rule 5), the hollow diamond, r 7, 2 px, in ink on the pump
 *   chart and in its line's colour on the group chart (memberMark).
 */
export const CHART_MARKS: {
	readonly group: Readonly<ChartMark>;
	readonly ring: Readonly<ChartMark>;
	readonly member: Readonly<Omit<ChartMark, 'fill'>>;
	readonly held: Readonly<ChartMark>;
} = {
	group: { radius: 7, border: 2, fill: '#0f172a', stroke: SURFACE },
	ring: { radius: 10, border: 2, fill: 'transparent', stroke: '#475569' },
	member: { radius: 6, border: 2, stroke: SURFACE },
	held: { radius: 7, border: 2, fill: SURFACE, stroke: '#0f172a' }
};

/** A member's mark on the group chart in its line's colour: the dot, or the diamond while held. */
export function memberMark(color: string, held = false): ChartMark {
	return held ? { ...CHART_MARKS.held, stroke: color } : { ...CHART_MARKS.member, fill: color };
}
