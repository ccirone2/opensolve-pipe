/**
 * Creating components, connections and projects with valid port ids and sensible defaults.
 *
 * Defaults are user inputs the person is expected to review, never sourced hydraulic data.
 * Inner diameters, roughness and loss coefficients are not set here: they come from the API's
 * library at solve time (pipe material + schedule + nominal size; Crane TP-410 K values for
 * fittings and valves whose resistance is omitted).
 */
import type {
	AssignedFlow,
	CheckValve,
	Component,
	ControlValve,
	Equipment,
	EquipmentRating,
	IdealReferenceNode,
	IsolationValve,
	Orifice,
	PipeConnection,
	PipeDefinition,
	PipingSegment,
	Plug,
	Port,
	PortDirection,
	Project,
	Pump,
	ReliefValve,
	Reservoir,
	TeeBranch,
	WyeBranch
} from '../api/types';
import { CURRENT_SCHEMA_VERSION } from './migrations';
import type { PortRef } from './graph';
import { INCH, SI_UNITS } from './units';

/** Every kind of component the UI can add, flat (valves by valve type). */
export type ComponentKind =
	| 'reservoir'
	| 'reference_node'
	| 'plug'
	| 'assigned_flow'
	| 'tee'
	| 'wye'
	| 'pump'
	| IsolationValve['valveType']
	| CheckValve['valveType']
	| ControlValve['valveType']
	| 'equipment'
	| 'orifice'
	| 'relief_valve';

export const COMPONENT_KINDS: readonly ComponentKind[] = [
	'reservoir',
	'reference_node',
	'plug',
	'assigned_flow',
	'tee',
	'wye',
	'pump',
	'gate',
	'ball',
	'butterfly',
	'globe',
	'check',
	'stop_check',
	'prv',
	'psv',
	'fcv',
	'equipment',
	'orifice',
	'relief_valve'
];

/** The component type each kind creates. */
export interface ComponentOfKind {
	reservoir: Reservoir;
	reference_node: IdealReferenceNode;
	plug: Plug;
	assigned_flow: AssignedFlow;
	tee: TeeBranch;
	wye: WyeBranch;
	pump: Pump;
	gate: IsolationValve;
	ball: IsolationValve;
	butterfly: IsolationValve;
	globe: IsolationValve;
	check: CheckValve;
	stop_check: CheckValve;
	prv: ControlValve;
	psv: ControlValve;
	fcv: ControlValve;
	equipment: Equipment;
	orifice: Orifice;
	relief_valve: ReliefValve;
}

/** Menu labels. */
export const KIND_LABELS: Readonly<Record<ComponentKind, string>> = {
	reservoir: 'Reservoir',
	reference_node: 'Reference node (fixed pressure)',
	plug: 'Plug / cap',
	assigned_flow: 'Assigned flow (demand or supply)',
	tee: 'Tee',
	wye: 'Wye (lateral)',
	pump: 'Pump',
	gate: 'Gate valve',
	ball: 'Ball valve',
	butterfly: 'Butterfly valve',
	globe: 'Globe valve',
	check: 'Check valve',
	stop_check: 'Stop-check valve',
	prv: 'Pressure-reducing valve (PRV)',
	psv: 'Pressure-sustaining valve (PSV)',
	fcv: 'Flow-control valve (FCV)',
	equipment: 'Equipment (rated pressure drop)',
	orifice: 'Orifice plate (ISO 5167-2)',
	relief_valve: 'Pressure relief valve (API 520, liquids)'
};

/** Short names used for default component names ("Gate valve V1"). */
const KIND_NAMES: Readonly<Record<ComponentKind, string>> = {
	reservoir: 'Reservoir',
	reference_node: 'Reference node',
	plug: 'Plug',
	assigned_flow: 'Assigned flow',
	tee: 'Tee',
	wye: 'Wye',
	pump: 'Pump',
	gate: 'Gate valve',
	ball: 'Ball valve',
	butterfly: 'Butterfly valve',
	globe: 'Globe valve',
	check: 'Check valve',
	stop_check: 'Stop-check valve',
	prv: 'PRV',
	psv: 'PSV',
	fcv: 'FCV',
	equipment: 'Equipment',
	orifice: 'Orifice',
	relief_valve: 'Relief valve'
};

/**
 * Id prefixes: R1, N1, PL1, AF1, T1, Y1, P1, V1, E1, O1, RV1; connections L1; pump curves C1. A
 * relief valve is never PRV or PSV: in this app those are EPANET's pressure-reducing and
 * pressure-sustaining valves (proposal pressure-relief-valve.md decision 26).
 */
export const ID_PREFIX: Readonly<Record<ComponentKind, string>> = {
	reservoir: 'R',
	reference_node: 'N',
	plug: 'PL',
	assigned_flow: 'AF',
	tee: 'T',
	wye: 'Y',
	pump: 'P',
	gate: 'V',
	ball: 'V',
	butterfly: 'V',
	globe: 'V',
	check: 'V',
	stop_check: 'V',
	prv: 'V',
	psv: 'V',
	fcv: 'V',
	equipment: 'E',
	orifice: 'O',
	relief_valve: 'RV'
};
export const CONNECTION_PREFIX = 'L';
export const CURVE_PREFIX = 'C';

/** The kind of an existing component. */
export function componentKind(component: Component): ComponentKind {
	switch (component.type) {
		case 'branch':
			return component.branchType;
		case 'valve':
			return component.valveType;
		default:
			return component.type;
	}
}

/** New ports and connections default to NPS 4 (4 in × 0.0254 m/in) when nothing else applies. */
export const DEFAULT_NOMINAL_SIZE = 4 * INCH;
/** Pipe material and schedule of new connections: ids in the API's pipe library. */
export const DEFAULT_MATERIAL_ID = 'carbon_steel';
export const DEFAULT_SCHEDULE = '40';
/** Length of the pipe in a new connection, m. */
export const DEFAULT_PIPE_LENGTH = 10;
/** Length of the pipe added by an insertion (downstream half) or a plug stub, m. */
export const SHORT_PIPE_LENGTH = 1;

/**
 * Ids in use: components, connections and pump curves (one namespace, so trace keys stay unique),
 * and every component or connection a scenario's change names, deleted ones included: a new
 * component never takes the id of a deleted one whose changes are kept, so those changes never
 * attach to it (proposal scenario-manager.md §6.7).
 */
export function usedIds(project: Project): Set<string> {
	const ids = new Set([
		...project.components.map((c) => c.id),
		...project.connections.map((c) => c.id),
		...project.pumpLibrary.map((c) => c.id)
	]);
	for (const scenario of project.scenarios ?? []) {
		for (const change of scenario.overrides ?? []) {
			if (change.kind === 'component') ids.add(change.componentId);
			if (change.kind === 'pipe') ids.add(change.connectionId);
		}
	}
	return ids;
}

/**
 * The first unused id `${prefix}${n}`, n = 1, 2, ... Besides usedIds, it avoids the curve ids
 * pumps refer to before the curve is defined, so a new curve or pump never shares another
 * pump's (still undefined) curve.
 */
export function newId(project: Project, prefix: string, alsoUsed: Iterable<string> = []): string {
	const used = usedIds(project);
	for (const c of project.components) if (c.type === 'pump') used.add(c.curveId);
	for (const id of alsoUsed) used.add(id);
	for (let n = 1; ; n++) {
		const id = `${prefix}${n}`;
		if (!used.has(id)) return id;
	}
}

/** A random project id (letters and digits). Uses getRandomValues, available in every context. */
export function newProjectId(): string {
	const bytes = new Uint8Array(9);
	crypto.getRandomValues(bytes);
	return `p${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
}

function port(id: string, nominalSize: number, direction: PortDirection): Port {
	return { id, nominalSize, direction };
}

export interface ComponentOptions {
	id?: string;
	name?: string;
	/** Elevation above the project datum, m (default 0). */
	elevation?: number;
	/** Nominal size of every port, m (default DEFAULT_NOMINAL_SIZE). */
	nominalSize?: number;
	/**
	 * An assigned-flow node's flow, m³/s (positive: a demand, leaving the network; negative: a
	 * supply, entering it). Required for that kind, which has no default; ignored by the others.
	 */
	flow?: number;
	/**
	 * An equipment item's rating, as the user enters it from the datasheet (RatingDraft: every
	 * value of its kind, SI; a Cv or Kv as entered). Required for that kind, which has no default
	 * (proposal equipment-pressure-drop.md decision 3); ignored by the others.
	 */
	rating?: RatingDraft;
	/**
	 * An orifice plate's bore diameter d, m, as the user enters it. Required for that kind, which
	 * has no default (proposal orifice-plate.md decision 2: no source gives a default bore);
	 * ignored by the others.
	 */
	boreDiameter?: number;
	/**
	 * A relief valve's set pressure, Pa (a difference, inlet minus outlet static), as the user
	 * enters it. Required for that kind, which has no default (proposal pressure-relief-valve.md
	 * §2.1); ignored by the others.
	 */
	setPressure?: number;
	/**
	 * A relief valve's capacity as the user enters it (CapacityDraft: its kind and the values
	 * entered, SI). Required for that kind, every value its kind needs (no default: decision 7);
	 * ignored by the others.
	 */
	capacity?: CapacityDraft;
	/**
	 * Ids a new id must not take besides usedIds (newId's alsoUsed): those page state names, such
	 * as a goal-seek setup's elements, so a row never moves to a new element (goal-seek.md §6.15).
	 */
	reserved?: Iterable<string>;
}

/** Values the user enters before a component is added: those its kind has no default for. */
export type EnteredValues = Pick<
	ComponentOptions,
	'flow' | 'rating' | 'boreDiameter' | 'setPressure' | 'capacity'
>;

/** Ids new elements must not take besides usedIds (see ComponentOptions.reserved). */
export interface NewIdOptions {
	reserved?: Iterable<string>;
}

/**
 * Kinds whose values have no default, entered where the component is added (before it exists):
 * an assigned-flow node's flow (D12), an equipment item's rating (decision 19), an orifice
 * plate's bore (proposal orifice-plate.md §6 W2) and a relief valve's set pressure and capacity
 * (proposal pressure-relief-valve.md W1). Every path that creates a component asks for them first.
 */
export const ENTRY_KINDS: readonly ComponentKind[] = [
	'assigned_flow',
	'equipment',
	'orifice',
	'relief_valve'
];

/** How a datasheet gives a rating: a pressure drop at a flow ('point'), a Cv or a Kv. */
export type RatingKind = EquipmentRating['kind'];

/** The kinds of rating, in the Rated by choice's order (the first is where it starts). */
export const RATING_KINDS: readonly RatingKind[] = ['point', 'Cv', 'Kv'];

/** A value of a rating (the API's field names): the point's three, or the coefficient. */
export type RatingField = 'pressureLoss' | 'flow' | 'density' | 'value';

/** The values each kind of rating holds, in the form's order. */
export const RATING_FIELDS: Readonly<Record<RatingKind, readonly RatingField[]>> = {
	point: ['pressureLoss', 'flow', 'density'],
	Cv: ['value'],
	Kv: ['value']
};

/**
 * A rating as it is being entered: its kind and the values entered so far (SI; a Cv or Kv as
 * entered). A value is never carried from one kind to another (a rated flow is not a Cv).
 */
export interface RatingDraft {
	kind: RatingKind;
	pressureLoss?: number;
	flow?: number;
	density?: number;
	value?: number;
}

/** A draft of a stored rating (every value of its kind). */
export function ratingDraft(rating: EquipmentRating): RatingDraft {
	return { ...rating };
}

/** The rating a draft makes once every value of its kind is entered (a finite number), or null. */
export function completeRating(draft: RatingDraft | undefined): EquipmentRating | null {
	if (!draft) return null;
	const finite = (field: RatingField) => {
		const v = draft[field];
		return typeof v === 'number' && Number.isFinite(v) ? v : null;
	};
	if (draft.kind === 'point') {
		const [pressureLoss, flow, density] = [
			finite('pressureLoss'),
			finite('flow'),
			finite('density')
		];
		if (pressureLoss === null || flow === null || density === null) return null;
		return { kind: 'point', pressureLoss, flow, density };
	}
	const value = finite('value');
	return value === null ? null : { kind: draft.kind, value };
}

/** A value the user still has to enter before a component is added: where, and what to say. */
export interface MissingEntry {
	/** The value's path on the component ('flow', 'rating.pressureLoss', 'rating.value'). */
	field: string;
	message: string;
}

/** What to say about each rating value that is not entered yet: the datasheet gives it. */
function ratingEntryMessage(kind: RatingKind, field: RatingField): string {
	switch (field) {
		case 'pressureLoss':
			return 'Enter the rated pressure drop from the datasheet: it has no default.';
		case 'flow':
			return 'Enter the rated flow from the datasheet: it has no default.';
		case 'density':
			return 'Enter the rated fluid density, or use one of the buttons: it has no default.';
		default:
			return `Enter the ${kind} from the datasheet: it has no default.`;
	}
}

/** What to say when an orifice plate's bore is not entered yet: no source gives a default. */
export const BORE_ENTRY_MESSAGE = 'Enter the orifice bore: it has no default.';

/** How a relief valve's capacity is given: an API 526 letter, an API 520 effective area, certified. */
export type CapacityKind = ReliefValve['capacity']['kind'];

/** The kinds of capacity, in the form's order (the first is where the choice starts). */
export const CAPACITY_KINDS: readonly CapacityKind[] = ['api526', 'effective', 'certified'];

/** A value of a capacity (the API's field names). */
export type CapacityField = 'letter' | 'area' | 'dischargeCoefficient' | 'overpressure';

/**
 * The values each kind of capacity holds, in the form's order; a certified capacity's
 * overpressure is optional (absent: ASME's, the default), so it is never missing.
 */
export const CAPACITY_FIELDS: Readonly<Record<CapacityKind, readonly CapacityField[]>> = {
	api526: ['letter'],
	effective: ['area'],
	certified: ['area', 'dischargeCoefficient', 'overpressure']
};

/** The values a kind of capacity cannot be stored without. */
const REQUIRED_CAPACITY_FIELDS: Readonly<Record<CapacityKind, readonly CapacityField[]>> = {
	api526: ['letter'],
	effective: ['area'],
	certified: ['area', 'dischargeCoefficient']
};

/**
 * A relief valve's capacity as it is being entered: its kind and the values entered so far (SI;
 * the letter as chosen). A value is never carried from one kind to another (an effective area is
 * not an actual area, and API 520's effective coefficient is never mixed with a rated one).
 */
export interface CapacityDraft {
	kind: CapacityKind;
	letter?: string;
	area?: number;
	dischargeCoefficient?: number;
	overpressure?: number;
}

/** A draft of a stored capacity (every value it holds). */
export function capacityDraft(capacity: ReliefValve['capacity']): CapacityDraft {
	const { overpressure, ...rest } = capacity as ReliefValve['capacity'] & {
		overpressure?: number | null;
	};
	return typeof overpressure === 'number' ? { ...rest, overpressure } : rest;
}

/**
 * The draft with `field` set to `value` (SI; a letter as chosen), or without it for null (a
 * certified overpressure back to ASME's default). A string is only ever a letter.
 */
export function withCapacityValue(
	draft: CapacityDraft,
	field: CapacityField,
	value: number | string | null
): CapacityDraft {
	const next: CapacityDraft = { ...draft };
	if (value === null) delete next[field];
	else if (field === 'letter') next.letter = String(value);
	else if (typeof value === 'number') next[field] = value;
	return next;
}

/** The capacity a draft makes once every value its kind needs is entered, or null. */
export function completeCapacity(draft: CapacityDraft | undefined): ReliefValve['capacity'] | null {
	if (!draft) return null;
	const finite = (field: 'area' | 'dischargeCoefficient' | 'overpressure') => {
		const v = draft[field];
		return typeof v === 'number' && Number.isFinite(v) ? v : null;
	};
	if (draft.kind === 'api526') {
		return draft.letter
			? {
					kind: 'api526',
					letter: draft.letter as Extract<ReliefValve['capacity'], { kind: 'api526' }>['letter']
				}
			: null;
	}
	const area = finite('area');
	if (area === null) return null;
	if (draft.kind === 'effective') return { kind: 'effective', area };
	const dischargeCoefficient = finite('dischargeCoefficient');
	if (dischargeCoefficient === null) return null;
	const overpressure = finite('overpressure');
	return overpressure === null
		? { kind: 'certified', area, dischargeCoefficient }
		: { kind: 'certified', area, dischargeCoefficient, overpressure };
}

/** What to say when a relief valve's set pressure is not entered yet: it has no default. */
export const SET_PRESSURE_ENTRY_MESSAGE = 'Enter the set pressure: it has no default.';

/** What to say about each capacity value that is not entered yet (W1). */
export function capacityEntryMessage(kind: CapacityKind, field: CapacityField): string {
	if (kind === 'api526' || field === 'letter') {
		return 'Choose an API 526 orifice letter, or enter an effective area or the certified area and coefficient: the capacity has no default.';
	}
	if (field === 'dischargeCoefficient') {
		return 'Enter the rated coefficient of discharge from the certification: the capacity has no default.';
	}
	return kind === 'effective'
		? 'Enter the API 520 effective area, or choose an API 526 orifice letter: the capacity has no default.'
		: 'Enter the certified actual orifice area: the capacity has no default.';
}

/**
 * Every value a component of `kind` cannot be added without, not yet in `values`, in the form's
 * order (one per empty field): an assigned-flow node's flow; each value of an equipment item's
 * rating, of the kind chosen (a rated point until another is chosen); an orifice plate's bore.
 * None for other kinds.
 */
export function missingEntries(kind: ComponentKind, values: EnteredValues): MissingEntry[] {
	if (kind === 'assigned_flow') {
		return values.flow === undefined || !Number.isFinite(values.flow)
			? [{ field: 'flow', message: 'Enter the flow: an assigned-flow node has no default flow.' }]
			: [];
	}
	if (kind === 'orifice') {
		return values.boreDiameter === undefined || !Number.isFinite(values.boreDiameter)
			? [{ field: 'boreDiameter', message: BORE_ENTRY_MESSAGE }]
			: [];
	}
	if (kind === 'relief_valve') {
		const missing: MissingEntry[] = [];
		if (values.setPressure === undefined || !Number.isFinite(values.setPressure)) {
			missing.push({ field: 'setPressure', message: SET_PRESSURE_ENTRY_MESSAGE });
		}
		const capacity = values.capacity ?? { kind: CAPACITY_KINDS[0]! };
		for (const field of REQUIRED_CAPACITY_FIELDS[capacity.kind]) {
			const v = capacity[field];
			const entered = field === 'letter' ? !!v : typeof v === 'number' && Number.isFinite(v);
			if (!entered) {
				missing.push({
					field: `capacity.${field}`,
					message: capacityEntryMessage(capacity.kind, field)
				});
			}
		}
		return missing;
	}
	if (kind !== 'equipment') return [];
	const draft = values.rating ?? { kind: 'point' };
	return RATING_FIELDS[draft.kind]
		.filter((field) => {
			const v = draft[field];
			return typeof v !== 'number' || !Number.isFinite(v);
		})
		.map((field) => ({
			field: `rating.${field}`,
			message: ratingEntryMessage(draft.kind, field)
		}));
}

/** Why a component of `kind` cannot be added with `values` yet (a sentence), or null. */
export function missingEntry(kind: ComponentKind, values: EnteredValues): string | null {
	return missingEntries(kind, values)[0]?.message ?? null;
}

const MISSING_ENTRY_TEXT = {
	assigned_flow: 'An assigned-flow node needs the flow the user enters: it has no default.',
	equipment:
		'An equipment item needs the rating the user enters from its datasheet: it has no default.',
	orifice: 'An orifice plate needs the bore the user enters: it has no default.',
	relief_valve:
		'A relief valve needs the set pressure and the capacity the user enters: they have no default.'
} as const;

/**
 * Thrown when a component is created without a value the user enters (it has no default): an
 * assigned-flow node's flow, an equipment item's rating, an orifice plate's bore, a relief valve's
 * set pressure and capacity.
 */
export class MissingEntryError extends Error {
	constructor(kind: keyof typeof MISSING_ENTRY_TEXT) {
		super(MISSING_ENTRY_TEXT[kind]);
		this.name = 'MissingEntryError';
	}
}

/**
 * A new component with the port ids its type requires (see the API models) and defaults:
 * - reservoir: one port 'port_1', liquid level 0 m, surface open to air (0 Pa gauge);
 * - reference node: one port, 0 Pa gauge;
 * - assigned-flow node: one port, the flow given in `options.flow` (required: no flow is cited
 *   as a default, so the user enters it before the node is added; MissingEntryError otherwise);
 * - tee / wye: Crane loss model (the API default; Crane TP-410), wye angle 45°;
 * - pump: on, full speed, referring to a new curve id of its own that the user must still
 *   define, or replace by picking a curve already in the library (no curve is invented, and a
 *   new pump never takes another pump's curve by itself);
 * - valves: active; resistance omitted, so the solver supplies it (isolation valves: the Crane
 *   TP-410 full-bore, fully open K at the connected size; control valves: ideal when fully
 *   open, both per the API model docs; check valves: the solver's cited default for the valve
 *   type); check valve cracking pressure 0; control-valve setpoint 0 (for the user to set);
 * - equipment: ports inlet and outlet, the rating given in `options.rating` (required, every value
 *   of its kind: no source gives a default rating, so the user enters it from the datasheet
 *   before the item is added; MissingEntryError otherwise);
 * - orifice plate: ports inlet and outlet, the bore given in `options.boreDiameter` (required: no
 *   source gives a default bore; MissingEntryError otherwise), ISO 5167-2's discharge coefficient
 *   (the cited default: no entered C) and no pressure taps (a restriction orifice, no reading);
 * - relief valve: ports inlet and outlet, active, the set pressure and capacity given in
 *   `options.setPressure` and `options.capacity` (required: neither has a default;
 *   MissingEntryError otherwise), a certified capacity's overpressure only where entered (absent:
 *   ASME's, the default).
 */
export function createComponent<K extends ComponentKind>(
	kind: K,
	project: Project,
	options: ComponentOptions = {}
): ComponentOfKind[K] {
	return buildComponent(kind, project, options) as ComponentOfKind[K];
}

function buildComponent(
	kind: ComponentKind,
	project: Project,
	options: ComponentOptions
): Component {
	const reserved = [...(options.reserved ?? [])];
	const id = options.id ?? newId(project, ID_PREFIX[kind], reserved);
	const name = options.name ?? `${KIND_NAMES[kind]} ${id}`;
	const elevation = options.elevation ?? 0;
	const size = options.nominalSize ?? DEFAULT_NOMINAL_SIZE;
	const base = { id, name, elevation };
	switch (kind) {
		case 'reservoir':
			return {
				...base,
				type: 'reservoir',
				liquidLevel: 0,
				surfacePressure: 0,
				ports: [port('port_1', size, 'bidirectional')]
			};
		case 'reference_node':
			return {
				...base,
				type: 'reference_node',
				referenceType: 'ideal',
				pressure: 0,
				ports: [port('port_1', size, 'bidirectional')]
			};
		case 'plug':
			return { ...base, type: 'plug', ports: [port('port_1', size, 'bidirectional')] };
		case 'assigned_flow':
			if (options.flow === undefined || !Number.isFinite(options.flow)) {
				throw new MissingEntryError('assigned_flow');
			}
			return {
				...base,
				type: 'assigned_flow',
				flow: options.flow,
				ports: [port('port_1', size, 'bidirectional')]
			};
		case 'tee':
			return {
				...base,
				type: 'branch',
				branchType: 'tee',
				lossModel: 'crane',
				ports: [
					port('run_inlet', size, 'bidirectional'),
					port('run_outlet', size, 'bidirectional'),
					port('branch', size, 'bidirectional')
				]
			};
		case 'wye':
			return {
				...base,
				type: 'branch',
				branchType: 'wye',
				angle: 45,
				lossModel: 'crane',
				ports: [
					port('inlet', size, 'bidirectional'),
					port('outlet_1', size, 'bidirectional'),
					port('outlet_2', size, 'bidirectional')
				]
			};
		case 'pump':
			return {
				...base,
				type: 'pump',
				curveId: newId(project, CURVE_PREFIX, [id, ...reserved]),
				speed: 1,
				status: 'on',
				ports: [port('suction', size, 'inlet'), port('discharge', size, 'outlet')]
			};
		case 'gate':
		case 'ball':
		case 'butterfly':
		case 'globe':
			return { ...base, type: 'valve', valveType: kind, status: 'active', ports: valvePorts(size) };
		case 'check':
		case 'stop_check':
			return {
				...base,
				type: 'valve',
				valveType: kind,
				status: 'active',
				crackingPressure: 0,
				ports: valvePorts(size)
			};
		case 'prv':
		case 'psv':
		case 'fcv':
			return {
				...base,
				type: 'valve',
				valveType: kind,
				status: 'active',
				setpoint: 0,
				ports: valvePorts(size)
			};
		case 'equipment': {
			const rating = completeRating(options.rating);
			if (!rating) throw new MissingEntryError('equipment');
			return { ...base, type: 'equipment', rating, ports: valvePorts(size) };
		}
		case 'orifice':
			if (options.boreDiameter === undefined || !Number.isFinite(options.boreDiameter)) {
				throw new MissingEntryError('orifice');
			}
			return {
				...base,
				type: 'orifice',
				boreDiameter: options.boreDiameter,
				ports: valvePorts(size)
			};
		case 'relief_valve': {
			const capacity = completeCapacity(options.capacity);
			if (options.setPressure === undefined || !Number.isFinite(options.setPressure) || !capacity) {
				throw new MissingEntryError('relief_valve');
			}
			return {
				...base,
				type: 'relief_valve',
				setPressure: options.setPressure,
				capacity,
				status: 'active',
				ports: valvePorts(size)
			};
		}
	}
}

function valvePorts(size: number): Port[] {
	return [port('inlet', size, 'inlet'), port('outlet', size, 'outlet')];
}

/** A library pipe: carbon steel, schedule 40, the given nominal size, 10 m long. */
export function defaultPipe(nominalSize: number, length = DEFAULT_PIPE_LENGTH): PipeDefinition {
	return { materialId: DEFAULT_MATERIAL_ID, schedule: DEFAULT_SCHEDULE, nominalSize, length };
}

export function defaultPiping(nominalSize: number, length = DEFAULT_PIPE_LENGTH): PipingSegment {
	return { pipes: [defaultPipe(nominalSize, length)], fittings: [] };
}

/** A new connection from one port to another, with a new id. Ports are not checked here. */
export function createConnection(
	project: Project,
	from: PortRef,
	to: PortRef,
	piping: PipingSegment,
	id: string = newId(project, CONNECTION_PREFIX)
): PipeConnection {
	return {
		id,
		fromComponentId: from.componentId,
		fromPortId: from.portId,
		toComponentId: to.componentId,
		toPortId: to.portId,
		piping
	};
}

/** The current time as an ISO 8601 timestamp (UTC). */
export function isoNow(): string {
	return new Date().toISOString();
}

export interface EmptyProjectOptions {
	id?: string;
	name?: string;
	/** ISO 8601 timestamp for created/modified (default: now). */
	now?: string;
}

/**
 * An empty project: SI display units, site at sea level, water at 20 °C (a default input the
 * user changes in Settings), Colebrook friction, and the API's default solver options.
 */
export function createEmptyProject(options: EmptyProjectOptions = {}): Project {
	const now = options.now ?? isoNow();
	return {
		schemaVersion: CURRENT_SCHEMA_VERSION,
		methodVersion: '',
		id: options.id ?? newProjectId(),
		metadata: { name: options.name ?? 'Untitled project', created: now, modified: now },
		settings: {
			units: { ...SI_UNITS },
			siteElevation: 0,
			solverOptions: { frictionMethod: 'colebrook', maxIterations: 100, tolerance: 1e-9 }
		},
		fluid: { kind: 'builtin', fluidId: 'water', temperature: 293.15 },
		components: [],
		connections: [],
		pumpLibrary: []
	};
}
