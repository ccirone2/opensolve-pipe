/**
 * The Build form registry (proposal build-density.md §5): for every field a Build form sets, the
 * section (facet) it sits in, its tier (core: always shown; more: in the form's "More" disclosure,
 * which opens itself while it holds a set value, a scenario change or an error), its order, its
 * label and its help. A plain field (a number in one unit category, or a choice of the schema's
 * values) also declares how it is drawn, and the form draws it from here (RegistryField.svelte):
 * adding such a field to a component is this one entry.
 *
 * What a field is (its name, type, bounds, default, the values a choice may take, whether a
 * scenario may change it) is read from the generated schema (model-rules.ts, schema-bounds.ts),
 * never written here (CLAUDE.md D10); this file holds only presentation, a web concern. The test
 * beside it fails when a field of a schema reachable from Build has no entry, or an entry names
 * a field the schema lacks.
 */
import type { Component } from '../api/types';
import { KIND_LABELS } from './factory';
import {
	CHECK_STATUS_LABELS,
	CONTROL_STATUS_LABELS,
	ISOLATION_STATUS_LABELS,
	PUMP_STATUS_LABELS
} from './labels';
import { COMPONENT_SCHEMAS, schemaFields } from './model-rules';
import { areaLabel } from './relief';
import type { UnitCategory } from './units';

/**
 * The sections every type's fields sort into (the card sort, proposal build-density.md §3.4), in
 * form order: what the element does in this case (the values scenarios change most), what it is,
 * where it sits and how big it is, the fittings of a pipe, and the names that identify it.
 */
export const FACETS = {
	operation: 'Operation',
	rating: 'Rating',
	placement: 'Size and position',
	fittings: 'Fittings',
	identity: 'Identification'
} as const;
export type Facet = keyof typeof FACETS;
export const FACET_ORDER = Object.keys(FACETS) as Facet[];

/** core: shown; more: in the form's "More" disclosure (open while it holds a set value). */
export type Tier = 'core' | 'more';

/** A number in the project's display unit of its category (NumberField). */
export interface NumberInput {
	kind: 'number';
	category: UnitCategory;
	/** A gauge pressure (D4): labelled kPa(g), psig. */
	gauge?: boolean;
	/** Empty is allowed and stored as null. */
	optional?: boolean;
}

/** A choice of the values the schema allows (SelectField), each with its label. */
export interface ChoiceInput {
	kind: 'choice';
	labels: Readonly<Record<string, string>>;
}

/** The unit a field's value is shown in: its category, and a gauge pressure's marker (D4). */
export interface FieldUnit {
	category: UnitCategory;
	gauge?: boolean;
}

export interface FieldEntry {
	facet: Facet;
	tier: Tier;
	/**
	 * As the form, scenario notes, goal seek and the export name it; a function where it depends
	 * on the element (a PRV's setpoint), given none when the element no longer exists.
	 */
	label: string | ((component?: Component) => string);
	/**
	 * A number's unit where `input` does not give it (a field its form draws): what scenario
	 * changes, goal seek and the export show it in. Every number a scenario or goal seek may
	 * change has one (the test beside this file).
	 */
	unit?: FieldUnit | ((component?: Component) => FieldUnit);
	/** Static explanation: shown while the field has focus, always in its description. */
	help?: string;
	/** How the form draws it, for a plain field; absent: the type's form draws it. */
	input?: NumberInput | ChoiceInput;
	/** The undo step's name, where it is not "change <label>". */
	edit?: string;
	/** Its sub-fields are edited by its own editor (a union with a kind select, a list). */
	whole?: boolean;
	/** Whether it holds a value the user set, where isSet's rule does not fit (a list of ports). */
	isSet?: (value: unknown) => boolean;
}

type Entries = Readonly<Record<string, FieldEntry>>;

const ELEVATION: FieldEntry = {
	facet: 'placement',
	tier: 'core',
	label: 'Elevation',
	help: 'Above the project datum.',
	input: { kind: 'number', category: 'length' }
};

/** Ports: their nominal sizes (for new piping) and elevations, edited in the ports list. */
const PORTS: FieldEntry = {
	facet: 'placement',
	tier: 'more',
	label: 'Ports',
	whole: true,
	// Every port has a size (a suggestion for new piping); an elevation of its own is a value set.
	isSet: (ports) =>
		Array.isArray(ports) && ports.some((p) => p?.elevation !== undefined && p?.elevation !== null)
};

/** A valve's resistance: the default, a K, Cv or Kv, or a library entry (ResistanceField). */
const RESISTANCE: FieldEntry = { facet: 'rating', tier: 'core', label: 'Resistance', whole: true };

/** A status chosen from the schema's values, each with its label (utils/labels.ts). */
function status(labels: Readonly<Record<string, string>>, edit: string): FieldEntry {
	return {
		facet: 'operation',
		tier: 'core',
		label: 'Status',
		input: { kind: 'choice', labels },
		edit
	};
}

/** A valve's type within its schema (the API's valveType values), each named as a kind. */
const VALVE_TYPE: FieldEntry = {
	facet: 'rating',
	tier: 'core',
	label: 'Valve type',
	input: { kind: 'choice', labels: KIND_LABELS },
	edit: 'change valve type'
};

/**
 * By schema, in form order. The schema names are the API's (model-rules.ts COMPONENT_SCHEMAS,
 * and the pipe, port and pump curve schemas a component's forms also edit).
 */
export const FIELD_REGISTRY: Readonly<Record<string, Entries>> = {
	Reservoir: {
		liquidLevel: {
			facet: 'operation',
			tier: 'core',
			label: 'Liquid level',
			help: "Height of the liquid surface above the reservoir's elevation.",
			input: { kind: 'number', category: 'length' }
		},
		surfacePressure: {
			facet: 'operation',
			tier: 'more',
			label: 'Surface pressure',
			help: 'Gauge pressure on the liquid surface; 0 means open to the atmosphere.',
			input: { kind: 'number', category: 'pressure', gauge: true }
		},
		elevation: ELEVATION,
		ports: PORTS
	},
	IdealReferenceNode: {
		pressure: {
			facet: 'operation',
			tier: 'core',
			label: 'Pressure',
			help: "Fixed gauge pressure held at the port, like a large supply main or a closed loop's expansion tank.",
			input: { kind: 'number', category: 'pressure', gauge: true },
			edit: 'change reference pressure'
		},
		elevation: ELEVATION,
		ports: PORTS
	},
	Plug: { elevation: ELEVATION, ports: PORTS },
	AssignedFlow: {
		flow: { facet: 'operation', tier: 'core', label: 'Assigned flow', unit: { category: 'flow' } },
		elevation: ELEVATION,
		ports: PORTS
	},
	TeeBranch: {
		lossModel: { facet: 'rating', tier: 'more', label: 'Loss model' },
		elevation: ELEVATION,
		ports: PORTS
	},
	WyeBranch: {
		angle: {
			facet: 'placement',
			tier: 'core',
			label: 'Branch angle',
			help: 'Angle between the branch leg (outlet 2) and the run; the Crane correlation covers 30–60°.',
			input: { kind: 'number', category: 'angle' },
			edit: 'change wye angle'
		},
		lossModel: { facet: 'rating', tier: 'more', label: 'Loss model' },
		elevation: ELEVATION,
		ports: PORTS
	},
	Pump: {
		status: status(PUMP_STATUS_LABELS, 'change pump status'),
		control: { facet: 'operation', tier: 'core', label: 'Control' },
		'control.setpoint': {
			facet: 'operation',
			tier: 'core',
			label: 'Flow setpoint',
			unit: { category: 'flow' }
		},
		'control.minSpeed': {
			facet: 'operation',
			tier: 'core',
			label: 'Minimum speed',
			unit: { category: 'fraction' }
		},
		speed: {
			facet: 'operation',
			tier: 'core',
			label: (c) => (c?.type === 'pump' && c.control ? 'Maximum speed' : 'Speed'),
			unit: { category: 'fraction' }
		},
		curveId: { facet: 'rating', tier: 'core', label: 'Pump curve' },
		elevation: ELEVATION,
		ports: PORTS
	},
	IsolationValve: {
		status: status(ISOLATION_STATUS_LABELS, 'change valve status'),
		valveType: VALVE_TYPE,
		resistance: RESISTANCE,
		elevation: ELEVATION,
		ports: PORTS
	},
	CheckValve: {
		status: status(CHECK_STATUS_LABELS, 'change valve status'),
		valveType: VALVE_TYPE,
		crackingPressure: {
			facet: 'rating',
			tier: 'more',
			label: 'Cracking pressure',
			help: "The forward pressure across the valve that opens it, read on the energy grade line: the static pressure difference, inlet minus outlet, plus ρg × (inlet port elevation − outlet port elevation); 0 opens on any forward flow. For overpressure protection use a pressure relief valve: a check valve's fixed K does not follow API 520's capacity.",
			input: { kind: 'number', category: 'pressure', gauge: false }
		},
		resistance: RESISTANCE,
		elevation: ELEVATION,
		ports: PORTS
	},
	ControlValve: {
		status: status(CONTROL_STATUS_LABELS, 'change valve status'),
		setpoint: {
			facet: 'operation',
			tier: 'core',
			label: (c) =>
				c?.type !== 'valve'
					? 'Setpoint'
					: c.valveType === 'prv'
						? 'Outlet pressure setpoint'
						: c.valveType === 'psv'
							? 'Inlet pressure setpoint'
							: 'Flow setpoint',
			// An FCV holds a flow; a PRV or PSV a gauge pressure (D4).
			unit: (c) =>
				c?.type === 'valve' && c.valveType === 'fcv'
					? { category: 'flow' }
					: { category: 'pressure', gauge: true }
		},
		// Its own change: between a pressure and a flow valve the setpoint goes back to 0.
		valveType: { facet: 'rating', tier: 'core', label: 'Valve type' },
		resistance: RESISTANCE,
		elevation: ELEVATION,
		ports: PORTS
	},
	Equipment: {
		// The whole rating, as a scenario changes it (its kind is chosen as "Rated by").
		rating: { facet: 'rating', tier: 'core', label: 'Rating' },
		'rating.kind': { facet: 'rating', tier: 'core', label: 'Flow coefficient kind' },
		// A pressure difference: no gauge marker.
		'rating.pressureLoss': {
			facet: 'rating',
			tier: 'core',
			label: 'Rated pressure drop',
			unit: { category: 'pressure', gauge: false }
		},
		'rating.flow': {
			facet: 'rating',
			tier: 'core',
			label: 'Rated flow',
			unit: { category: 'flow' }
		},
		'rating.density': {
			facet: 'rating',
			tier: 'core',
			label: 'Rated fluid density',
			unit: { category: 'density' }
		},
		'rating.value': {
			facet: 'rating',
			tier: 'core',
			label: (c) =>
				c?.type === 'equipment' && c.rating.kind !== 'point' ? c.rating.kind : 'Flow coefficient',
			unit: { category: 'dimensionless' }
		},
		elevation: ELEVATION,
		ports: PORTS
	},
	Orifice: {
		boreDiameter: {
			facet: 'rating',
			tier: 'core',
			label: 'Bore diameter',
			unit: { category: 'diameter' }
		},
		taps: { facet: 'placement', tier: 'more', label: 'Pressure taps' },
		dischargeCoefficient: {
			facet: 'rating',
			tier: 'more',
			label: 'Discharge coefficient',
			unit: { category: 'dimensionless' }
		},
		elevation: ELEVATION,
		ports: PORTS
	},
	ReliefValve: {
		status: { facet: 'operation', tier: 'core', label: 'Status' },
		// A pressure difference, inlet minus outlet: no gauge marker.
		setPressure: {
			facet: 'rating',
			tier: 'core',
			label: 'Set pressure',
			unit: { category: 'pressure', gauge: false }
		},
		// The whole capacity, as a scenario changes it (its kind is chosen as "Capacity given by").
		capacity: { facet: 'rating', tier: 'core', label: 'Capacity' },
		'capacity.letter': { facet: 'rating', tier: 'core', label: 'API 526 orifice letter' },
		'capacity.area': {
			facet: 'rating',
			tier: 'core',
			label: (c) => areaLabel(c?.type === 'relief_valve' ? c.capacity.kind : null),
			unit: { category: 'area' }
		},
		'capacity.dischargeCoefficient': {
			facet: 'rating',
			tier: 'core',
			label: 'Rated coefficient of discharge (K)',
			unit: { category: 'dimensionless' }
		},
		'capacity.overpressure': {
			facet: 'rating',
			tier: 'core',
			label: 'Overpressure at full lift',
			unit: { category: 'fraction' }
		},
		elevation: ELEVATION,
		ports: PORTS
	},
	Port: {
		nominalSize: { facet: 'placement', tier: 'core', label: 'Port size' },
		elevation: { facet: 'placement', tier: 'core', label: 'Port elevation' },
		direction: { facet: 'placement', tier: 'core', label: 'Direction' }
	},
	PipeDefinition: {
		materialId: { facet: 'rating', tier: 'core', label: 'Material' },
		specId: { facet: 'rating', tier: 'core', label: 'Pipe spec' },
		schedule: { facet: 'rating', tier: 'core', label: 'Schedule' },
		nominalSize: { facet: 'placement', tier: 'core', label: 'Size' },
		length: { facet: 'placement', tier: 'core', label: 'Length', unit: { category: 'length' } },
		innerDiameter: { facet: 'rating', tier: 'more', label: 'Inner diameter override' },
		roughness: { facet: 'rating', tier: 'more', label: 'Roughness override' }
	},
	PumpCurve: {
		points: { facet: 'rating', tier: 'core', label: 'Head curve' },
		npshrCurve: { facet: 'rating', tier: 'core', label: 'NPSH required' },
		efficiencyCurve: { facet: 'rating', tier: 'more', label: 'Efficiency curve' },
		name: { facet: 'identity', tier: 'core', label: 'Curve name' },
		manufacturer: { facet: 'identity', tier: 'more', label: 'Manufacturer' },
		model: { facet: 'identity', tier: 'more', label: 'Model' },
		motorRatedPower: { facet: 'rating', tier: 'more', label: 'Motor rated power' },
		allowableOperatingRegion: {
			facet: 'rating',
			tier: 'more',
			label: 'Allowable operating region',
			whole: true
		},
		minimumContinuousStableFlow: {
			facet: 'rating',
			tier: 'more',
			label: 'Minimum continuous stable flow'
		},
		minimumThermalFlow: { facet: 'rating', tier: 'more', label: 'Minimum thermal flow' }
	}
};

/**
 * Fields no form section holds: the id and type, the name (edited in the panel's header), and
 * a branch's type (fixed when it is added).
 */
export const STRUCTURAL_FIELDS: ReadonlySet<string> = new Set(['id', 'type', 'name', 'branchType']);

/** A field's entry, or undefined. */
export function fieldEntry(schemaName: string, path: string): FieldEntry | undefined {
	return FIELD_REGISTRY[schemaName]?.[path];
}

/** A field's label for this element (or, with none, as any element would name it). */
export function labelOf(entry: FieldEntry, component?: Component): string {
	return typeof entry.label === 'function' ? entry.label(component) : entry.label;
}

/** A number's unit from its entry: its input's, else its own; null for a value with none. */
export function unitOf(entry: FieldEntry, component?: Component): FieldUnit | null {
	if (entry.input?.kind === 'number') {
		const { category, gauge } = entry.input;
		return gauge === undefined ? { category } : { category, gauge };
	}
	if (!entry.unit) return null;
	return typeof entry.unit === 'function' ? entry.unit(component) : entry.unit;
}

/**
 * A field's entry for an element, by the element's schema; for an element that no longer exists
 * (undefined), the first entry of that path in any component schema, then the pipe's and port's.
 */
export function entryFor(
	schemaName: string | null | undefined,
	path: string
): FieldEntry | undefined {
	if (schemaName) return fieldEntry(schemaName, path);
	for (const name of [...COMPONENT_SCHEMAS, 'PipeDefinition', 'Port']) {
		const entry = fieldEntry(name, path);
		if (entry) return entry;
	}
	return undefined;
}

/**
 * The fields of a schema with no registry entry: each top-level field, and each field inside an
 * object field (a pump's control, a capacity), unless an ancestor's entry is `whole`.
 */
export function unregisteredFields(schemaName: string): string[] {
	const entries = FIELD_REGISTRY[schemaName] ?? {};
	const whole = Object.entries(entries)
		.filter(([, e]) => e.whole)
		.map(([path]) => path);
	return schemaFields(schemaName)
		.map((f) => f.path)
		.filter((path) => !STRUCTURAL_FIELDS.has(path))
		.filter((path) => !whole.some((w) => path.startsWith(`${w}.`)))
		.filter((path) => !entries[path]);
}

/** Registry paths of a schema that the schema does not have (a field renamed or removed). */
export function staleEntries(schemaName: string): string[] {
	const paths = new Set(schemaFields(schemaName).map((f) => f.path));
	return Object.keys(FIELD_REGISTRY[schemaName] ?? {}).filter((path) => !paths.has(path));
}

/** A section of a form: a facet's fields of one tier, in registry order. */
export interface FormSection {
	facet: Facet;
	title: string;
	paths: string[];
}

/** The sections of a schema's fields of one tier, in facet order (empty sections left out). */
export function sectionsOf(schemaName: string, tier: Tier): FormSection[] {
	const entries = Object.entries(FIELD_REGISTRY[schemaName] ?? {});
	return FACET_ORDER.map((facet) => ({
		facet,
		title: FACETS[facet],
		paths: entries.filter(([, e]) => e.facet === facet && e.tier === tier).map(([p]) => p)
	})).filter((s) => s.paths.length > 0);
}

/** The value at a dotted path of an object (undefined where the path does not exist). */
export function valueAt(value: unknown, path: string): unknown {
	let node: unknown = value;
	for (const key of path.split('.')) {
		if (typeof node !== 'object' || node === null) return undefined;
		node = (node as Record<string, unknown>)[key];
	}
	return node;
}

/**
 * Whether a field holds a value the user set: present and not the schema's default. A field with
 * no default counts as set whenever it holds a value; a list, when it is not empty.
 */
export function isSet(schemaName: string, path: string, value: unknown): boolean {
	const own = fieldEntry(schemaName, path)?.isSet;
	if (own) return own(value);
	if (value === undefined || value === null) return false;
	if (Array.isArray(value)) return value.length > 0;
	const field = schemaFields(schemaName).find((f) => f.path === path);
	return !field || !('default' in field) || JSON.stringify(field.default) !== JSON.stringify(value);
}
