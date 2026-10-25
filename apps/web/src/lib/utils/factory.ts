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
	IdealReferenceNode,
	IsolationValve,
	PipeConnection,
	PipeDefinition,
	PipingSegment,
	Plug,
	Port,
	PortDirection,
	Project,
	Pump,
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
	| ControlValve['valveType'];

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
	'fcv'
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
	fcv: 'Flow-control valve (FCV)'
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
	fcv: 'FCV'
};

/** Id prefixes: R1, N1, PL1, AF1, T1, Y1, P1, V1; connections L1; pump curves C1. */
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
	fcv: 'V'
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
}

/** Values the user enters before a component is added: those its kind has no default for. */
export type EnteredValues = Pick<ComponentOptions, 'flow'>;

/** Why a component of `kind` cannot be added with `values` yet (a sentence), or null. */
export function missingEntry(kind: ComponentKind, values: EnteredValues): string | null {
	return kind === 'assigned_flow' && values.flow === undefined
		? 'Enter the flow: an assigned-flow node has no default flow.'
		: null;
}

/** Thrown when an assigned-flow node is created without the flow the user entered. */
export class MissingFlowError extends Error {
	constructor() {
		super('An assigned-flow node needs the flow the user enters: it has no default.');
		this.name = 'MissingFlowError';
	}
}

/**
 * A new component with the port ids its type requires (see the API models) and defaults:
 * - reservoir: one port 'port_1', liquid level 0 m, surface open to air (0 Pa gauge);
 * - reference node: one port, 0 Pa gauge;
 * - assigned-flow node: one port, the flow given in `options.flow` (required: no flow is cited
 *   as a default, so the user enters it before the node is added; MissingFlowError otherwise);
 * - tee / wye: Crane loss model (the API default; Crane TP-410), wye angle 45°;
 * - pump: on, full speed, referring to a new curve id of its own that the user must still
 *   define, or replace by picking a curve already in the library (no curve is invented, and a
 *   new pump never takes another pump's curve by itself);
 * - valves: active; resistance omitted, so the solver supplies it (isolation valves: the Crane
 *   TP-410 full-bore, fully open K at the connected size; control valves: ideal when fully
 *   open, both per the API model docs; check valves: the solver's cited default for the valve
 *   type); check valve cracking pressure 0; control-valve setpoint 0 (for the user to set).
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
	const id = options.id ?? newId(project, ID_PREFIX[kind]);
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
				throw new MissingFlowError();
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
				curveId: newId(project, CURVE_PREFIX, [id]),
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
