/**
 * Pump groups (CLAUDE.md D20, proposal pump-groups.md §4 and §6.2): the groups the Pumps together
 * card suggests, found on the topology as solved, and the words for the reasons the API gives
 * when the pumps do not form a station (422 NOT_A_STATION).
 *
 * The suggestion only picks members. The API is the authority on the station (its inlet S and
 * outlet D) and its arrangement (§5.2); a suggestion it refuses says why in words. Two kinds of
 * group are found:
 * - pumps on one chain of two-port elements (pumps, valves and equipment joined by connections),
 *   all facing the same way, with no active PRV or PSV between them and each end of the chain
 *   leading on to a fixed head, an assigned flow, another pump or the other end (series);
 * - pumps whose chains lie between one pair of junctions (S, D) whose removal cuts them off from
 *   every fixed head, assigned flow and other pump, each facing from S's side to D's (parallel:
 *   tee ladders and pumps drawing from one reservoir included), no active PRV or PSV inside
 *   (its setpoint is a pressure: the API refuses such a station). The candidates are the junctions
 *   within three junction hops of a pump's chain ends, at most 400 pairs for each pump's chain
 *   (nearest first; a pair tried for one chain is not tried again).
 *
 * Pure: never modifies the project.
 */
import type { Component, Project, TopologyIssue } from '../api/types';
import { componentById } from './graph';

/** At most this many pumps in a group (the API's limit and the chart's, MAX_CHART_CASES). */
export const MAX_GROUP_PUMPS = 6;
/** Junction hops from a pump's chain ends within which S and D are looked for (§4). */
export const SUGGESTION_HOPS = 3;
/** Pairs of candidate junctions tried at most (§4). */
export const SUGGESTION_PAIRS = 400;

/** A group the card offers: its pumps in component order, and how it was found. */
export interface GroupSuggestion {
	pumpIds: string[];
	/** 'series': one chain; 'parallel': between two junctions (the API may find it mixed). */
	kind: 'series' | 'parallel';
}

/** A chain of two-port elements between two junctions (or a free port). */
interface Chain {
	/** The junction at each end (null: a free port, or a loop of two-port elements). */
	ends: [string | null, string | null];
	/** The junction's port at each end. */
	endPorts: [string | null, string | null];
	/** Its pumps in walking order, `forward` when the pump delivers from end 0 to end 1. */
	pumps: { id: string; forward: boolean }[];
	/** Its active PRVs and PSVs: a station holding one has no group curve (the API refuses it). */
	pressureControls: string[];
	/** Its pumps' and pressure controls' ids in walking order (end 0 to end 1). */
	order: string[];
}

const TWO_PORT: ReadonlySet<Component['type']> = new Set(['pump', 'valve', 'equipment']);

/** A pump, valve or equipment item with its two ports: an element of a chain. */
function isTwoPort(component: Component): boolean {
	return TWO_PORT.has(component.type) && component.ports.length === 2;
}

/** An active PRV or PSV: its setpoint is a pressure, so no station may hold one (§5.6). */
function isPressureControl(component: Component): boolean {
	return (
		component.type === 'valve' &&
		'valveType' in component &&
		(component.valveType === 'prv' || component.valveType === 'psv') &&
		component.status === 'active'
	);
}

function isFixedHead(component: Component | undefined): boolean {
	return component?.type === 'reservoir' || component?.type === 'reference_node';
}

/** The connections at each port: `${componentId}\u0000${portId}` → the other end. */
function portLinks(project: Project): Map<string, { componentId: string; portId: string }> {
	const links = new Map<string, { componentId: string; portId: string }>();
	for (const c of project.connections) {
		links.set(`${c.fromComponentId}\u0000${c.fromPortId}`, {
			componentId: c.toComponentId,
			portId: c.toPortId
		});
		links.set(`${c.toComponentId}\u0000${c.toPortId}`, {
			componentId: c.fromComponentId,
			portId: c.fromPortId
		});
	}
	return links;
}

/**
 * Every chain of the project: from each port of a junction (any component that is not a
 * two-port element) along the connections and two-port elements to the next junction; then the
 * two-port elements no junction reaches (loops, or lines with free ends).
 */
function chainsOf(project: Project): Chain[] {
	const links = portLinks(project);
	const byId = new Map(project.components.map((c) => [c.id, c]));
	const visited = new Set<string>(); // junction ports and two-port elements walked
	const chains: Chain[] = [];

	/**
	 * Walk from a port of `from` (entering the component the connection there leads to); a
	 * two-port element met again (a loop with no junction) ends the walk.
	 */
	const walk = (fromId: string, fromPort: string) => {
		const pumps: Chain['pumps'] = [];
		const pressureControls: string[] = [];
		const order: string[] = [];
		const result = (end: string | null, endPort: string | null) => ({
			end,
			endPort,
			pumps,
			pressureControls,
			order
		});
		const seen = new Set<string>([fromId]);
		let at = links.get(`${fromId}\u0000${fromPort}`);
		while (at) {
			const component = byId.get(at.componentId);
			if (!component) return result(null, null);
			if (!isTwoPort(component)) return result(component.id, at.portId);
			if (seen.has(component.id)) return result(null, null);
			seen.add(component.id);
			visited.add(component.id);
			if (component.type === 'pump') {
				pumps.push({ id: component.id, forward: at.portId === 'suction' });
				order.push(component.id);
			}
			if (isPressureControl(component)) {
				pressureControls.push(component.id);
				order.push(component.id);
			}
			const exit = component.ports.find((p) => p.id !== at!.portId);
			if (!exit) return result(null, null);
			at = links.get(`${component.id}\u0000${exit.id}`);
		}
		return result(null, null);
	};

	for (const junction of project.components) {
		if (isTwoPort(junction)) continue;
		for (const port of junction.ports) {
			const key = `${junction.id}\u0000${port.id}`;
			if (visited.has(key) || !links.has(key)) continue;
			visited.add(key);
			const { end, endPort, pumps, pressureControls, order } = walk(junction.id, port.id);
			if (end && endPort) visited.add(`${end}\u0000${endPort}`);
			chains.push({
				ends: [junction.id, end],
				endPorts: [port.id, endPort],
				pumps,
				pressureControls,
				order
			});
		}
	}
	// Two-port elements no junction reaches: walk both ways from the first one met.
	for (const element of project.components) {
		if (!isTwoPort(element) || visited.has(element.id)) continue;
		visited.add(element.id);
		const [a, b] = element.ports;
		const back = walk(element.id, a!.id);
		const ahead = walk(element.id, b!.id);
		const self = element.type === 'pump' ? [{ id: element.id, forward: a!.id === 'suction' }] : [];
		// Walking back from port a, the pumps were met in the reverse order and facing.
		const pumps = [
			...back.pumps.reverse().map((p) => ({ id: p.id, forward: !p.forward })),
			...self,
			...ahead.pumps
		];
		const controls = isPressureControl(element) ? [element.id] : [];
		chains.push({
			ends: [back.end, ahead.end],
			endPorts: [back.endPort, ahead.endPort],
			pumps,
			pressureControls: [...back.pressureControls, ...controls, ...ahead.pressureControls],
			order: [
				...back.order.reverse(),
				...(self.length || controls.length ? [element.id] : []),
				...ahead.order
			]
		});
	}
	return chains;
}

/** Union-find over string keys. */
class Parts {
	readonly #parent = new Map<string, string>();
	find(key: string): string {
		let root = key;
		for (let up = this.#parent.get(root); up !== undefined && up !== root;) {
			root = up;
			up = this.#parent.get(root);
		}
		this.#parent.set(key, root);
		return root;
	}
	join(a: string, b: string): void {
		const ra = this.find(a);
		const rb = this.find(b);
		if (ra !== rb) this.#parent.set(ra, rb);
	}
}

/**
 * The groups suggested on `project` (the topology as solved) for the pumps with results
 * `pumpIds`: each group 2 to 6 of those pumps, in component order; the largest first, then by
 * their first pump's place in the project. The same group is suggested once.
 */
export function suggestGroups(project: Project, pumpIds: readonly string[]): GroupSuggestion[] {
	const withResult = new Set(pumpIds);
	const order = new Map(project.components.map((c, i) => [c.id, i]));
	const sorted = (ids: Iterable<string>) =>
		[...ids].sort((a, b) => (order.get(a) ?? Infinity) - (order.get(b) ?? Infinity));
	const chains = chainsOf(project);
	const found = new Map<string, GroupSuggestion>();
	const add = (ids: string[], kind: GroupSuggestion['kind']) => {
		if (ids.length < 2 || ids.length > MAX_GROUP_PUMPS) return;
		const pumpIds = sorted(ids);
		const key = pumpIds.join('\u0000');
		if (!found.has(key)) found.set(key, { pumpIds, kind });
	};

	const incident = new Map<string, number[]>(); // junction id → chain indexes
	chains.forEach((chain, i) => {
		for (const end of new Set(chain.ends)) {
			if (end === null) continue;
			incident.set(end, [...(incident.get(end) ?? []), i]);
		}
	});
	const byId = new Map(project.components.map((c) => [c.id, c]));
	/** Fixed heads and assigned flows: what a station's interior may not hold. */
	const barriers = new Set(
		project.components.filter((c) => isFixedHead(c) || c.type === 'assigned_flow').map((c) => c.id)
	);

	// Series: one chain, its pumps all facing the same way, each with a result, no active PRV or
	// PSV between the first and the last, and each end of the chain leading on (to a fixed head, an
	// assigned flow, another pump or the other end: else no flow passes through them).
	chains.forEach((chain, index) => {
		const { pumps, order: walked } = chain;
		if (pumps.length < 2 || !pumps.every((p) => withResult.has(p.id))) return;
		if (!pumps.every((p) => p.forward === pumps[0]!.forward)) return;
		const first = walked.indexOf(pumps[0]!.id);
		const last = walked.indexOf(pumps[pumps.length - 1]!.id);
		const between = (v: string) => first < walked.indexOf(v) && walked.indexOf(v) < last;
		if (chain.pressureControls.some(between)) return;
		const [a, b] = chain.ends;
		if (a === null || b === null) return;
		if (!leadsOn(chains, incident, barriers, index, a, b)) return;
		if (!leadsOn(chains, incident, barriers, index, b, a)) return;
		add(
			pumps.map((p) => p.id),
			'series'
		);
	});

	// Parallel: between a pair of junctions (S, D).
	const pumpChains = chains.filter((c) => c.pumps.some((p) => withResult.has(p.id)));
	// Only a branch or a boundary can be S or D (a one-port node passes no flow on).
	const canEnd = (id: string) => {
		const c = byId.get(id);
		return c?.type === 'branch' || isFixedHead(c);
	};
	const tried = new Set<string>();
	for (const chain of pumpChains) {
		// Candidates: junctions within SUGGESTION_HOPS of this chain's ends, nearest first.
		const distance = new Map<string, number>();
		let frontier = chain.ends.filter((e): e is string => e !== null);
		for (const id of frontier) distance.set(id, 0);
		for (let hop = 1; hop <= SUGGESTION_HOPS && frontier.length; hop++) {
			const next: string[] = [];
			for (const id of frontier) {
				for (const i of incident.get(id) ?? []) {
					for (const end of chains[i]!.ends) {
						if (end === null || distance.has(end)) continue;
						distance.set(end, hop);
						next.push(end);
					}
				}
			}
			frontier = next;
		}
		const candidates = [...distance.keys()]
			.filter(canEnd)
			.sort(
				(a, b) =>
					distance.get(a)! - distance.get(b)! ||
					(order.get(a) ?? Infinity) - (order.get(b) ?? Infinity)
			);
		let pairs = 0;
		for (let j = 1; j < candidates.length && pairs < SUGGESTION_PAIRS; j++) {
			for (let i = 0; i < j && pairs < SUGGESTION_PAIRS; i++, pairs++) {
				const [a, b] = [candidates[i]!, candidates[j]!].sort();
				const key = `${a}\u0000${b}`;
				if (tried.has(key)) continue;
				tried.add(key);
				const members = groupBetween(byId, barriers, chains, incident, withResult, a!, b!);
				if (members) add(members, 'parallel');
			}
		}
	}

	return [...found.values()].sort(
		(a, b) =>
			b.pumpIds.length - a.pumpIds.length ||
			(order.get(a.pumpIds[0]!) ?? Infinity) - (order.get(b.pumpIds[0]!) ?? Infinity)
	);
}

/**
 * Whether the network leads on from junction `start` without chain `excluded`: to a fixed head or
 * an assigned flow, a chain with a pump (another pump: the rest of the network), or `other`.
 */
function leadsOn(
	chains: readonly Chain[],
	incident: ReadonlyMap<string, number[]>,
	barriers: ReadonlySet<string>,
	excluded: number,
	start: string,
	other: string
): boolean {
	if (barriers.has(start)) return true;
	const seen = new Set([start]);
	const queue = [start];
	while (queue.length) {
		const at = queue.pop()!;
		for (const k of incident.get(at) ?? []) {
			if (k === excluded) continue;
			const chain = chains[k]!;
			if (chain.pumps.length) return true;
			for (const end of chain.ends) {
				if (end === null || seen.has(end)) continue;
				if (end === other || barriers.has(end)) return true;
				seen.add(end);
				queue.push(end);
			}
		}
	}
	return false;
}

/**
 * The pumps between junctions `s` and `d` (either way round), or null when there is no parallel
 * group there: with `s` and `d` removed, the parts that reach both, hold pumps (each with a
 * result) and no fixed head or assigned flow, are the group's; every other part is the rest of
 * the network (outside), but for a part that reaches only one of them and holds no fixed head,
 * assigned flow or pump (a plugged branch: inside). A tee whose ports lead into the station at
 * two or more places must lead out at exactly one, so its centre lies inside; a reservoir or
 * reference node is taken whole. The pumps must face from S's side to D's side, the sides the
 * group falls into with its pump chains removed (S and D joined without a pump: a bypass, not a
 * parallel group).
 */
function groupBetween(
	byId: ReadonlyMap<string, Component>,
	barriers: ReadonlySet<string>,
	chains: readonly Chain[],
	incident: ReadonlyMap<string, number[]>,
	withResult: ReadonlySet<string>,
	s: string,
	d: string
): string[] | null {
	interface Region {
		chains: number[];
		touchesS: boolean;
		touchesD: boolean;
		/**
		 * The rest of the network: it holds a fixed head or an assigned flow, or more pumps than a
		 * group (its walk stops there; a part met later that joins it is the rest too).
		 */
		outside: boolean;
		pumps: string[];
	}
	// The parts (with S and D removed) that reach S or D, each walked from a chain there.
	const regionOf = new Map<number, Region>();
	const regions: Region[] = [];
	for (const start of [...(incident.get(s) ?? []), ...(incident.get(d) ?? [])]) {
		if (regionOf.has(start)) continue;
		const region: Region = {
			chains: [],
			touchesS: false,
			touchesD: false,
			outside: false,
			pumps: []
		};
		regions.push(region);
		const queue = [start];
		regionOf.set(start, region);
		while (queue.length && !region.outside) {
			const i = queue.pop()!;
			const chain = chains[i]!;
			region.chains.push(i);
			region.pumps.push(...chain.pumps.map((p) => p.id));
			if (region.pumps.length > MAX_GROUP_PUMPS) region.outside = true;
			for (const end of chain.ends) {
				if (end === s) region.touchesS = true;
				else if (end === d) region.touchesD = true;
				else if (end !== null) {
					if (barriers.has(end)) region.outside = true;
					for (const k of incident.get(end) ?? []) {
						const other = regionOf.get(k);
						// Another part met: one whose walk stopped as the rest of the network.
						if (other && other !== region) region.outside = true;
						if (other) continue;
						regionOf.set(k, region);
						queue.push(k);
					}
				}
			}
		}
	}
	const group: Region[] = [];
	for (const region of regions) {
		const qualifies =
			region.touchesS &&
			region.touchesD &&
			!region.outside &&
			region.pumps.length > 0 &&
			region.pumps.every((p) => withResult.has(p));
		if (qualifies) group.push(region);
	}
	const members = group.flatMap((r) => r.pumps);
	if (members.length < 2 || members.length > MAX_GROUP_PUMPS) return null;
	const inside = new Set(group.flatMap((r) => r.chains));
	if ([...inside].some((i) => chains[i]!.pressureControls.length)) return null;
	// A part that reaches only S or only D lies inside the station when it holds no fixed head,
	// assigned flow or pump (a plugged branch); else it is the rest of the network.
	const dangling = new Set<number>();
	for (const region of regions) {
		if (region.touchesS === region.touchesD) continue;
		if (!region.outside && region.pumps.length === 0)
			for (const i of region.chains) dangling.add(i);
	}
	if ([...dangling].some((i) => chains[i]!.pressureControls.length)) return null;
	for (const x of [s, d]) {
		const component = byId.get(x);
		if (isFixedHead(component)) continue; // taken whole
		if (component?.type !== 'branch') return null;
		const ports = component.ports.map((port) => {
			const i = (incident.get(x) ?? []).find((k) =>
				chains[k]!.ends.some((end, e) => end === x && chains[k]!.endPorts[e] === port.id)
			);
			return i === undefined ? 'free' : inside.has(i) || dangling.has(i) ? 'inside' : 'outside';
		});
		const into = ports.filter((p) => p === 'inside').length;
		const out = ports.filter((p) => p === 'outside').length;
		if (out < 1 || (into >= 2 && out !== 1)) return null;
	}
	// Sides: S's and D's, joined by the group's chains without pumps.
	const sides = new Parts();
	for (const i of inside) {
		const chain = chains[i]!;
		const [a, b] = chain.ends;
		if (chain.pumps.length === 0 && a !== null && b !== null) sides.join(a, b);
	}
	if (sides.find(s) === sides.find(d)) return null;
	// Every pump faces the same way: from S's side to D's, or all the other way (the pair is then
	// read the other way round).
	const facing = new Set<number>();
	for (const i of inside) {
		const chain = chains[i]!;
		if (!chain.pumps.length) continue;
		const forward = chain.pumps[0]!.forward;
		if (!chain.pumps.every((p) => p.forward === forward)) return null;
		const [a, b] = chain.ends;
		const suction = forward ? a : b;
		const discharge = forward ? b : a;
		if (suction === null || discharge === null) return null;
		const side = (x: string) => sides.find(x);
		if (side(suction) === side(s) && side(discharge) === side(d)) facing.add(1);
		else if (side(suction) === side(d) && side(discharge) === side(s)) facing.add(-1);
		else return null;
	}
	return facing.size === 1 ? members : null;
}

/** The default group of the card: the first suggestion holding the pump viewed, else the first. */
export function defaultGroup(
	suggestions: readonly GroupSuggestion[],
	viewed: string | null
): string[] {
	const holding = viewed ? suggestions.find((s) => s.pumpIds.includes(viewed)) : undefined;
	return [...((holding ?? suggestions[0])?.pumpIds ?? [])];
}

// ---------------------------------------------------------------------------------------------
// Why the pumps do not form a station, in words (§6.2)
// ---------------------------------------------------------------------------------------------

/** A sentence with element names the card links to their results. */
export type Words = (string | { id: string; name: string })[];

/** "A", "A and B", "A, B and C" as words with names. */
function list(ids: readonly string[], name: (id: string) => string): Words {
	const words: Words = [];
	ids.forEach((id, i) => {
		if (i > 0) words.push(i === ids.length - 1 ? ' and ' : ', ');
		words.push({ id, name: name(id) });
	});
	return words;
}

/** The plain text of words (tests, and the image's notes). */
export function wordsText(words: Words): string {
	return words.map((w) => (typeof w === 'string' ? w : w.name)).join('');
}

/**
 * Why the pumps `members` do not form a station, for one issue of a NOT_A_STATION answer, told
 * with element names from `project`, the project the answer belongs to (as solved while results
 * are out of date: its topology tells DIFFERENT_BOUNDARIES' side): the issue's code worded by the
 * web, the ids it names linked. An unknown code keeps the server's sentence.
 */
export function refusalWords(
	issue: TopologyIssue,
	members: readonly string[],
	project: Project
): Words {
	const name = (id: string) => componentById(project, id)?.name ?? id;
	const ids = issue.componentIds;
	const pumps = list(members, name);
	const one = ids.length === 1;
	switch (issue.code) {
		case 'NO_SEPARATING_PORTS':
			// One place, or three or more (two places are a station's, or NO_WAY_THROUGH). The ids are
			// the places' components, each once: one id is one place or several ports of one
			// component, two or more are three places or more.
			return ids.length >= 2
				? [
						...pumps,
						' meet the rest of the network at more than two places, at ',
						...list(ids, name),
						': a station meets it at exactly two, its inlet and its outlet, with no other pump, reservoir, reference node or assigned flow between them.'
					]
				: one
					? [
							...pumps,
							' meet the rest of the network only at ',
							...list(ids, name),
							': a station meets it at exactly two places, its inlet and its outlet, so that flow passes through it.'
						]
					: [
							...pumps,
							' do not meet the rest of the network at exactly two places: a station meets it only at its inlet and its outlet.'
						];
		case 'NO_WAY_THROUGH':
			// Two places, but no way between them passes a member (the ids: the places' components).
			return [
				...pumps,
				members.length === 1 ? ' lies' : ' lie',
				' on no way between the two places where ',
				members.length === 1 ? 'it meets' : 'they meet',
				' the rest of the network, at ',
				...list(ids, name),
				': each sits in a loop or dead end of its own, so no flow passes through ',
				members.length === 1 ? 'it' : 'them',
				'; a station’s pumps lie between its inlet and its outlet.'
			];
		case 'FIXED_HEAD_INSIDE':
			return one
				? [
						...list(ids, name),
						' connects the pumps to a fixed head a third time: a station meets the rest of the network at exactly two places, its inlet and its outlet, with no reservoir or reference node between them.'
					]
				: [
						'The pumps meet the fixed heads of ',
						...list(ids, name),
						', one place more than a station has: it meets the rest of the network at exactly two places, its inlet and its outlet, with no reservoir or reference node between them.'
					];
		case 'ASSIGNED_FLOW_INSIDE':
			return [
				'The assigned flow at ',
				...list(ids, name),
				' enters or leaves the network between the pumps and the rest of it: a station holds no assigned flow between its inlet and its outlet.'
			];
		case 'OTHER_PUMP_INSIDE':
			return [
				...list(ids, name),
				one ? ' lies' : ' lie',
				' between the pumps and the rest of the network but ',
				one ? 'is' : 'are',
				' not in the group: tick ',
				one ? 'it' : 'them',
				' too, or choose other pumps.'
			];
		case 'DIFFERENT_BOUNDARIES':
			return [
				...pumps,
				` ${boundarySide(issue, members, project)} different reservoirs or reference nodes, `,
				...list(ids, name),
				', each through its own piping: a station has one inlet and one outlet, so they do not form one, even at equal levels (a scenario can change one).'
			];
		case 'MEMBERS_OPPOSED':
			// As many members face each way (the ids: every member facing a way), so the station's
			// inlet and outlet cannot be told apart.
			return [
				...list(ids, name),
				' face opposite ways between the station’s two places, as many each way, so its inlet and outlet cannot be told apart: a station’s pumps all deliver from its inlet to its outlet.'
			];
		case 'MEMBER_REVERSED':
			// A minority faces from the outlet to the inlet, against the rest (the ids: that minority).
			return [
				...list(ids, name),
				one ? ' faces' : ' face',
				' against the other pumps, from the station’s outlet to its inlet: a station’s pumps all deliver from its inlet to its outlet.'
			];
		case 'PRESSURE_CONTROL_INSIDE':
			return [
				...list(ids, name),
				' is inside the station and holds a pressure (an active PRV or PSV): its setpoint is a pressure, not a head difference, so the station alone has no group curve that depends on its rise only.'
			];
		default:
			return [issue.message];
	}
}

/**
 * Whether the boundaries a DIFFERENT_BOUNDARIES issue names are at the members' suctions ("draw
 * from") or discharges ("deliver to"), read from the members' own chains.
 */
function boundarySide(issue: TopologyIssue, members: readonly string[], project: Project): string {
	const chains = chainsOf(project);
	const ends = (side: 'suction' | 'discharge') =>
		new Set(
			chains.flatMap((chain) =>
				chain.pumps
					.filter((p) => members.includes(p.id))
					.map((p) => {
						const atStart = side === 'suction' ? p.forward : !p.forward;
						return atStart ? chain.ends[0] : chain.ends[1];
					})
			)
		);
	const named = (set: Set<string | null>) => issue.componentIds.every((id) => set.has(id));
	if (named(ends('suction'))) return 'draw from';
	if (named(ends('discharge'))) return 'deliver to';
	return 'draw from or deliver to';
}
