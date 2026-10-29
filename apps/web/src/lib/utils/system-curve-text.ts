/**
 * Why a system-curve point has no head, as people read it (D10; POST /api/v1/system-curve).
 * The API states it twice: a sentence (`message`, with element ids and SI values) and the same as
 * data (`reason`, with the ids and numbers the sentence quotes: `componentIds`,
 * `assignedFlowNodeIds`, `limitFlow`, `passedFlow`, `openHead`, `openHeadBound`, `startsTried`).
 * Here the reason is told from that data with element names and in the display units (for
 * `not_converged`, whose sentence can name elements and nodes its ids leave out, from the outer
 * loop's words), and the API's sentence is kept beside it (`detail`), so nothing it says is
 * lost. A point whose reason is null or a code this browser does not know, or whose data is not
 * as its code needs, keeps the API's sentence.
 *
 * Every number comes from the point; only units change. Names are the project's (an id that the
 * project does not have stays as the id, in quotes). The rule each kind of element follows (what
 * an FCV, PRV, PSV, check valve or pump lets through) is chosen by that element's kind in the
 * project as solved, as the API chooses it; when an element's kind is not known there, the API's
 * sentence is kept.
 *
 * A pump group's system curve (CLAUDE.md D21, slice 4b) has the same points and reasons, with the
 * station's inlet and outlet in place of the pump's suction and discharge and its rise in place
 * of the pump's head (`subject: 'station'`), as the API words them.
 */
import type { Component, Project, SystemCurveResponse, UnitPreferences } from '../api/types';
import { readableText } from './flag-text';
import { componentById } from './graph';
import { formatValue } from './units';

/** A point of a system curve: a pump's (D10), or a group's (no NPSHa: D21, slice 4b). */
type SystemCurvePoint = Omit<SystemCurveResponse['points'][number], 'npshAvailable'>;

/** What the reason of a point is told with. */
export interface SystemCurveTextContext {
	/** The project for names (the results' labels). */
	project: Project;
	/** The project as solved, for each element's kind (its rule); default `project`. */
	solved?: Project | null;
	units: UnitPreferences;
	/**
	 * What the flow is forced through: a pump (its system curve, the default) or a pump station
	 * (a group's system curve: its inlet and outlet, and its rise).
	 */
	subject?: 'pump' | 'station';
}

/** The words of a system curve's subject, as the API's (system_curve.py PUMP_WORDS, STATION_WORDS). */
interface Words {
	noun: string;
	/** The side the forced flow is drawn from. */
	inlet: string;
	/** The side it is delivered to. */
	outlet: string;
	/** What the curve's value is called. */
	head: string;
}
const WORDS: Readonly<Record<'pump' | 'station', Words>> = {
	pump: { noun: 'pump', inlet: 'suction', outlet: 'discharge', head: 'head' },
	station: { noun: 'station', inlet: 'inlet', outlet: 'outlet', head: 'rise' }
};

export interface SystemCurveNote {
	/** Why the point has no head, in names and display units ('' when it has a head). */
	text: string;
	/** The API's sentence, when `text` is told in the browser. */
	detail?: string;
}

/** The kinds of element a status rule closes, in the API's order (status.RULES). */
const RULE_KINDS = ['fcv', 'prv', 'psv', 'check', 'pump'] as const;
type RuleKind = (typeof RULE_KINDS)[number];

/** What each status rule that can close an element lets through, in words. */
const RULES: Readonly<Record<RuleKind, string>> = {
	fcv: 'an FCV passes neither reverse flow nor more than its flow setpoint',
	prv: 'a PRV passes no reverse flow, and no flow while the pressure its outlet side needs is above its setting',
	psv: 'a PSV passes no reverse flow, and no flow while the pressure at its inlet would fall below its setting',
	check: 'a check valve passes no reverse flow',
	pump: 'a pump passes no reverse flow, nor any flow against more than its shutoff head'
};

/** How a point was solved, by start (`startsTried`), in the order the API lists them. */
const STARTS: Readonly<Record<string, string>> = {
	solve: "the network's own solve",
	previous_point: "the last converged point's solution",
	initial: "the network's initial state",
	initial_open: 'that state with its control valves open'
};

const way = (w: Words) =>
	`a side of the ${w.noun} reaches no reservoir or reference node, nor the ${w.noun}'s other side, ` +
	'through elements that can open (every element but those closed by a status you set)';

/** The kind of rule that closes a component (null: none, or not a pump or valve). */
function ruleKind(component: Component | undefined): RuleKind | null {
	if (component?.type === 'pump') return 'pump';
	if (component?.type !== 'valve') return null;
	switch (component.valveType) {
		case 'fcv':
		case 'prv':
		case 'psv':
			return component.valveType;
		case 'check':
		case 'stop_check':
			return 'check';
		default:
			return null;
	}
}

/** "A", "A and B", "A, B and C" (or "A, B or C" with `word` 'or'). */
function andList(items: readonly string[], word = 'and'): string {
	return items.length < 2
		? (items[0] ?? '')
		: `${items.slice(0, -1).join(', ')} ${word} ${items[items.length - 1]}`;
}

function finite(value: number | null | undefined): value is number {
	return typeof value === 'number' && Number.isFinite(value);
}

/** Why the point has no head, in names and display units (see the module comment). */
export function systemPointNote(
	point: SystemCurvePoint,
	context: SystemCurveTextContext
): SystemCurveNote {
	if (point.head !== null) return { text: '' };
	const text = told(point, context);
	if (text === null || text === point.message) return { text: point.message };
	return { text, detail: point.message };
}

function told(point: SystemCurvePoint, context: SystemCurveTextContext): string | null {
	const { project, units } = context;
	const solved = context.solved ?? project;
	const w = WORDS[context.subject ?? 'pump'];
	const name = (id: string) => componentById(project, id)?.name ?? `“${id}”`;
	const names = (ids: readonly string[]) => andList(ids.map(name));
	const flow = (q: number) => formatValue(q, 'flow', units);
	/** The rules of the kinds of `ids`, in the API's order; null when a kind is not known. */
	const rules = (ids: readonly string[]): string | null => {
		const kinds = ids.map((id) => ruleKind(componentById(solved, id)));
		if (kinds.some((k) => k === null)) return null;
		return RULE_KINDS.filter((k) => kinds.includes(k))
			.map((k) => RULES[k])
			.join('; ');
	};
	const ids = point.componentIds ?? [];
	const zero = point.flow === 0;

	switch (point.reason) {
		case 'no_way_through':
			return zero
				? `At zero flow the ${w.head} across the ${w.noun} is undetermined: ${way(w)}.`
				: `No steady state carries this flow: ${way(w)}.`;
		case 'beyond_limit':
		case 'below_floor': {
			const ruled = ids.length ? rules(ids) : null;
			const { limitFlow: limit, passedFlow: passed } = point;
			if (ruled === null || !finite(limit) || !finite(passed)) return null;
			const which = ids.length === 1 ? 'which passes' : 'which together pass';
			const amount = (q: number) => (q > 0 ? `at most ${flow(q)}` : 'no flow');
			const assigned = point.assignedFlowNodeIds ?? [];
			const nodes =
				assigned.length === 1
					? `the assigned-flow node ${names(assigned)}, which takes or supplies its flow whatever the pressure`
					: `the assigned-flow nodes ${names(assigned)}, which take or supply their flows whatever the pressure`;
			if (point.reason === 'below_floor') {
				if (!assigned.length) return null;
				return (
					`No steady state carries this flow: every way from the ${w.noun}'s ${w.inlet} to its ${w.outlet}, ` +
					`through the network or a reservoir or reference node, passes ${names(ids)}, ${which} ` +
					`${amount(passed)} that way (${ruled}), and with the flows of ${nodes}, the ${w.noun} must ` +
					`pass at least ${flow(limit)}.`
				);
			}
			const back =
				`No steady state carries this flow: every way from the ${w.noun}'s ${w.outlet} back to its ` +
				`${w.inlet}, through the network or a reservoir or reference node, passes ${names(ids)}`;
			if (!assigned.length) return `${back}, ${which} ${amount(limit)} that way (${ruled}).`;
			const ending =
				limit < 0
					? `the ${w.noun} would have to pass ${flow(-limit)} in reverse: no forced flow from its ` +
						`${w.inlet} to its ${w.outlet}, zero included, has a steady state`
					: `the ${w.noun} can pass ${amount(limit)}`;
			return `${back}, ${which} ${amount(passed)} that way (${ruled}), and with the flows of ${nodes}, ${ending}.`;
		}
		case 'no_steady_state_found': {
			const starts = (point.startsTried ?? []).map((s) => STARTS[s]);
			if (!starts.length || starts.some((s) => s === undefined)) return null;
			let what = `the status rules leave a side of the ${w.noun} with no way to a reservoir or reference node`;
			if (ids.length) {
				const ruled = rules(ids);
				if (ruled === null) return null;
				what = `the status rules close ${names(ids)}, which leaves a side of the ${w.noun} with no way to a reservoir or reference node (${ruled})`;
			}
			return `No steady state found that carries this flow: ${what}; none is found from ${andList(starts as string[], 'or')}.`;
		}
		case 'free_level':
			return (
				`The ${w.head} across the ${w.noun} is undetermined: a side of the ${w.noun}${ids.length ? `, closed off by ${names(ids)},` : ''} ` +
				'is in a part of the network that carries flow but reaches no reservoir or reference ' +
				'node, so nothing fixes its pressure level.'
			);
		case 'closed_off': {
			const by = ids.length
				? `${names(ids)} ${ids.length === 1 ? 'closes' : 'close'} off a side of the ${w.noun}`
				: `a side of the ${w.noun} is closed off`;
			return (
				`The ${w.head} across the ${w.noun} is undetermined${zero ? ' at zero flow' : ''}: ${by}, and no ` +
				'reservoir or reference node fixes the pressure in the part closed off.'
			);
		}
		case 'valve_at_switch': {
			const valveId = ids.length === 1 ? ids[0] : undefined;
			const valve = valveId === undefined ? undefined : componentById(solved, valveId);
			const kind = valve?.type === 'valve' ? valve.valveType : null;
			const head = point.openHead;
			const side =
				point.openHeadBound === 'lower'
					? 'above'
					: point.openHeadBound === 'upper'
						? 'below'
						: null;
			const at =
				kind === 'fcv'
					? 'passes exactly its flow setpoint'
					: kind === 'prv'
						? 'has the pressure at its outlet at its setting'
						: kind === 'psv'
							? 'has the pressure at its inlet at its setting'
							: null;
			if (valveId === undefined || at === null || side === null || !finite(head)) return null;
			return (
				`The ${w.head} across the ${w.noun} is undetermined: at this flow ${name(valveId)} ${at}, so it ` +
				`could also hold the flow throttled, with any ${w.head} across the ${w.noun} at or ${side} ` +
				`${formatValue(head, 'head', units)} (its ${w.head} with the valve fully open), and no ` +
				`reservoir or reference node fixes the pressure between the valve and the ${w.noun}.`
			);
		}
		case 'not_converged': {
			const rest = /^not converged: (.+)$/s.exec(point.message)?.[1];
			if (!rest) return null;
			const words = readableText(rest, project, units);
			return `Its solve did not converge. ${words}${/[.!?]$/.test(words) ? '' : '.'}`;
		}
		case 'not_computed':
			return 'Not computed: the time allowed for the calculation ran out before this point was solved.';
		default:
			return null;
	}
}
