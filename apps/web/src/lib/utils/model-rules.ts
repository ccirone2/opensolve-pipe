/**
 * The API's model rules, read from the generated OpenAPI schema (src/lib/api/openapi.json, written
 * by `pnpm gen:types` from the Pydantic models, which are the source of truth). Nothing here is
 * written by hand, so a model change reaches the app by regenerating the schema, and the API test
 * tests/unit/test_schema_rules.py fails while the copy is out of date.
 *
 * Rules JSON Schema cannot express are published by the models as extensions:
 * - on each component schema, `x-port-ids` (the exact port ids of the type), `x-port-roles` (the
 *   role of each named port in the type's forward flow direction) and `x-port-count` (the exact
 *   number of ports when only that is fixed);
 * - on `Fitting`, `x-required-parameters` (fields each fitting type needs), `x-reducer-types`
 *   (fittings between two pipes), `x-entrance-types` and `x-exit-types`;
 * - on `ControlValve`, `x-setpoint-bounds` (an FCV's setpoint is a flow);
 * - on `ReliefValve`, `x-relief-data` (API 526's letters and effective areas, API 520's effective
 *   coefficient of discharge, ASME's liquid overpressure and its 15 psi scope);
 * - on a component schema, `x-ordered-fields` (pairs of fields whose values must be ordered, such
 *   as a speed-controlled pump's minimum speed below its speed, the maximum);
 * - on `Scenario`, `x-override-fields` (the values a scenario may change, by target schema: the
 *   allow-list of the scenario manager, PRD §3.8);
 * - on `GoalSeekRequest`, `x-goal-variables` (the numeric allow-list values goal seek may vary, by
 *   target schema, with the schema that bounds each number and its search scale),
 *   `x-goal-quantities` (the results a goal may name, with their default-tolerance rules) and
 *   `x-goal-seek-rules` (the request's list rules), and `x-ordered-fields` on each goal-seek
 *   variable schema (its lower bound below its upper), PRD §3.9;
 * - on `PipeDefinition` and `Fitting`, `x-reference-fields` (a field that refers to a project
 *   library entry, the fields the entry stands in for and those required without it), and on
 *   `PipeSpec` and `ResistanceSpec`, `x-fields-by-value` (the fields one field's value requires or
 *   forbids) and `x-ordered-fields` (a spec's inner diameter below its outer), CLAUDE.md D22.
 *
 * The rest is what the schema states anyway: which schema a component is validated against (the
 * members of the `Project.components` union, by type refined by branchType or valveType, as the
 * API's discriminator), and the bound on the number of ports.
 */
import openapi from '../api/openapi.json';
import type { Fitting, FittingType } from '../api/types';
import type { Bounds } from './schema-bounds';

type JsonObject = Record<string, unknown>;

function isRecord(value: unknown): value is JsonObject {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

const SCHEMAS = openapi.components.schemas as unknown as Record<string, unknown>;

function schema(name: string): JsonObject {
	const found = SCHEMAS[name];
	if (!isRecord(found)) throw new Error(`Schema ${name} is missing from openapi.json`);
	return found;
}

function property(schemaName: string, name: string): JsonObject {
	const properties = schema(schemaName).properties;
	const found = isRecord(properties) ? properties[name] : undefined;
	return isRecord(found) ? found : {};
}

function stringList(value: unknown, what: string): string[] {
	if (!Array.isArray(value) || !value.every((v) => typeof v === 'string')) {
		throw new Error(`openapi.json: ${what} is not a list of strings`);
	}
	return value;
}

/** Schema names of the members of a union (oneOf of $refs) in openapi.json. */
function unionMembers(union: JsonObject): string[] {
	const members = Array.isArray(union.oneOf) ? union.oneOf : [];
	return members
		.map((m) => (isRecord(m) && typeof m.$ref === 'string' ? m.$ref.split('/').pop() : null))
		.filter((name): name is string => !!name);
}

/**
 * Whether schema `name` is a member of a union a value is told apart in by its `kind` (a fluid, an
 * equipment rating, a relief valve's capacity): a value held by such a schema must be of that
 * member (holderSchema).
 */
function kindUnionOf(name: string): 'fluid' | 'rating' | 'capacity' | null {
	if ([...FLUID_SCHEMAS.values()].includes(name)) return 'fluid';
	if ([...RATING_SCHEMAS.values()].includes(name)) return 'rating';
	if ([...CAPACITY_SCHEMAS.values()].includes(name)) return 'capacity';
	return null;
}

/**
 * Whether `holder` (an object found at a value's path) is a holder of schema `name`, as the API's
 * holder test (`isinstance`, services/scenarios.plan_override) decides it: a member of a union
 * told apart by `kind` (a fluid, an equipment rating, a relief valve's capacity) must be that
 * member; any other holder (a component, a pump's control) need only exist.
 */
export function holdsSchema(holder: unknown, name: string): boolean {
	if (!isRecord(holder)) return false;
	const union = kindUnionOf(name);
	if (union === 'fluid') return fluidSchemaName(holder.kind) === name;
	if (union === 'rating') return ratingSchemaName(holder.kind) === name;
	if (union === 'capacity') return capacitySchemaName(holder.kind) === name;
	return true;
}

/** Every `x-` extension keyword used in the schemas (annotations, not validation keywords). */
export function schemaExtensions(): string[] {
	const found = new Set<string>();
	const walk = (node: unknown) => {
		if (Array.isArray(node)) node.forEach(walk);
		else if (isRecord(node)) {
			for (const [key, value] of Object.entries(node)) {
				if (key.startsWith('x-')) found.add(key);
				else walk(value);
			}
		}
	};
	walk(openapi.components.schemas);
	return [...found].sort();
}

// ---------------------------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------------------------

/** The component schemas, in the order of the `Project.components` union. */
export const COMPONENT_SCHEMAS: readonly string[] = unionMembers(
	isRecord(property('Project', 'components').items)
		? (property('Project', 'components').items as JsonObject)
		: {}
);

interface ComponentTag {
	schema: string;
	type: unknown;
	branchType: unknown;
	valveTypes: readonly unknown[] | null;
}

const COMPONENT_TAGS: readonly ComponentTag[] = COMPONENT_SCHEMAS.map((name) => {
	const valveType = property(name, 'valveType');
	return {
		schema: name,
		type: property(name, 'type').const,
		branchType: property(name, 'branchType').const,
		valveTypes: Array.isArray(valveType.enum) ? valveType.enum : null
	};
});

/** What identifies a component's schema: its type, refined by branchType or valveType. */
export interface ComponentTagged {
	type?: unknown;
	branchType?: unknown;
	valveType?: unknown;
}

/**
 * The schema a component (or a record shaped like one) is validated against, as the API's
 * discriminator picks it; null when none matches.
 */
export function componentSchemaName(value: ComponentTagged): string | null {
	const tag = COMPONENT_TAGS.find(
		(t) =>
			t.type === value.type &&
			(t.branchType === undefined || t.branchType === value.branchType) &&
			(t.valveTypes === null || t.valveTypes.includes(value.valveType))
	);
	return tag?.schema ?? null;
}

/** The fluid schemas of the `Project.fluid` union, by their `kind`. */
const FLUID_SCHEMAS: ReadonlyMap<unknown, string> = new Map(
	unionMembers(property('Project', 'fluid')).map((name) => [property(name, 'kind').const, name])
);

/** The schema a fluid definition is validated against, by its kind; null when none matches. */
export function fluidSchemaName(kind: unknown): string | null {
	return FLUID_SCHEMAS.get(kind) ?? null;
}

/**
 * The rating schemas of the `Equipment.rating` union, by each `kind` a member allows: its `kind`
 * const (a rated point) or enum (Cv and Kv share one schema), read from the members, never copied
 * (proposal equipment-pressure-drop.md decision 22, §6.4).
 */
const RATING_SCHEMAS: ReadonlyMap<unknown, string> = new Map(
	unionMembers(property('Equipment', 'rating')).flatMap((name) => {
		const kind = property(name, 'kind');
		const kinds = Array.isArray(kind.enum) ? kind.enum : [kind.const];
		return kinds.map((k): [unknown, string] => [k, name]);
	})
);

/** The schema an equipment rating is validated against, by its kind; null when none matches. */
export function ratingSchemaName(kind: unknown): string | null {
	return RATING_SCHEMAS.get(kind) ?? null;
}

/** The rating kinds the `Equipment.rating` union allows, in its members' order. */
export function ratingKinds(): unknown[] {
	return [...RATING_SCHEMAS.keys()];
}

/**
 * The capacity schemas of the `ReliefValve.capacity` union, by their `kind` const (an API 526
 * letter, an API 520 effective area, a certified capacity), read from the members, never copied
 * (proposal pressure-relief-valve.md decision 7, W1).
 */
const CAPACITY_SCHEMAS: ReadonlyMap<unknown, string> = new Map(
	unionMembers(property('ReliefValve', 'capacity')).map((name) => [
		property(name, 'kind').const,
		name
	])
);

/** The schema a relief valve's capacity is validated against, by its kind; null when none. */
export function capacitySchemaName(kind: unknown): string | null {
	return CAPACITY_SCHEMAS.get(kind) ?? null;
}

/** The capacity kinds the `ReliefValve.capacity` union allows, in its members' order. */
export function capacityKinds(): unknown[] {
	return [...CAPACITY_SCHEMAS.keys()];
}

/**
 * The relief valve's cited data (`x-relief-data` on `ReliefValve`, from the API's
 * data/api526_orifices.json): API 526's effective area of each orifice letter (m²), API 520's
 * effective coefficient of discharge, and ASME's liquid certification overpressure (a fraction
 * of the set, with its floor in Pa) and the lowest set it covers (Pa), ASME VIII's 15 psi scope
 * (proposal pressure-relief-valve.md decisions 6, 27). Read, never copied (D10).
 */
export interface ReliefData {
	/** API 526's letters, in the schema's order, with their effective areas, m². */
	api526Areas: Readonly<Record<string, number>>;
	effectiveDischargeCoefficient: number;
	asmeOverpressureFraction: number;
	asmeOverpressureFloor: number;
	asmeMinimumSetPressure: number;
}

export const RELIEF_DATA: ReliefData = (() => {
	const published = schema('ReliefValve')['x-relief-data'];
	if (!isRecord(published) || !isRecord(published.api526Areas)) {
		throw new Error('openapi.json: ReliefValve has no x-relief-data');
	}
	const letters = stringList(property('Api526Orifice', 'letter').enum, 'Api526Orifice.letter');
	const api526Areas: Record<string, number> = {};
	for (const letter of letters) {
		const area = published.api526Areas[letter];
		if (typeof area !== 'number') {
			throw new Error(`openapi.json: x-relief-data.api526Areas has no letter ${letter}`);
		}
		api526Areas[letter] = area;
	}
	if (Object.keys(published.api526Areas).length !== letters.length) {
		throw new Error('openapi.json: x-relief-data.api526Areas is not the letters of Api526Orifice');
	}
	const number = (key: string) => {
		const value = (published as JsonObject)[key];
		if (typeof value !== 'number') throw new Error(`openapi.json: x-relief-data.${key}`);
		return value;
	};
	return {
		api526Areas,
		effectiveDischargeCoefficient: number('effectiveDischargeCoefficient'),
		asmeOverpressureFraction: number('asmeOverpressureFraction'),
		asmeOverpressureFloor: number('asmeOverpressureFloor'),
		asmeMinimumSetPressure: number('asmeMinimumSetPressure')
	};
})();

/** API 526's orifice letters, D to T, in the schema's order. */
export function api526Letters(): string[] {
	return Object.keys(RELIEF_DATA.api526Areas);
}

/** The override schemas of the `Scenario.overrides` union, by their `kind`. */
const OVERRIDE_SCHEMAS: ReadonlyMap<unknown, string> = new Map(
	unionMembers(
		isRecord(property('Scenario', 'overrides').items)
			? (property('Scenario', 'overrides').items as JsonObject)
			: {}
	).map((name) => [property(name, 'kind').const, name])
);

/** The schema a scenario change (override) is validated against, by its kind; null when none. */
export function overrideSchemaName(kind: unknown): string | null {
	return OVERRIDE_SCHEMAS.get(kind) ?? null;
}

function componentSchema(component: ComponentTagged): JsonObject | null {
	const name = componentSchemaName(component);
	return name ? schema(name) : null;
}

/** The exact port ids a component's type requires (`x-port-ids`), or null when they are free. */
export function requiredPortIds(component: ComponentTagged): readonly string[] | null {
	const ids = componentSchema(component)?.['x-port-ids'];
	return ids === undefined ? null : stringList(ids, 'x-port-ids');
}

/** The exact number of ports of a type whose port ids are free (`x-port-count`), or null. */
export function requiredPortCount(component: ComponentTagged): number | null {
	const count = componentSchema(component)?.['x-port-count'];
	return typeof count === 'number' ? count : null;
}

/**
 * The role of a named port in its type's forward flow direction (`x-port-roles`: positive pump
 * flow, a valve's forward direction, a branch's dividing pattern), or null for a port the type
 * does not name. Roles orient new connections; the solver decides the actual flow direction.
 */
export function namedPortRole(
	component: ComponentTagged,
	portId: string
): 'inlet' | 'outlet' | null {
	const roles = componentSchema(component)?.['x-port-roles'];
	const role = isRecord(roles) ? roles[portId] : undefined;
	return role === 'inlet' || role === 'outlet' ? role : null;
}

/** The largest number of ports a component of this type may have (the schema's maxItems). */
export function maxPorts(component: ComponentTagged): number {
	const name = componentSchemaName(component);
	const max = name ? property(name, 'ports').maxItems : undefined;
	if (typeof max !== 'number') throw new Error('openapi.json: ports has no maxItems');
	return max;
}

/**
 * Bounds of a control valve's setpoint for its valve type, SI: `x-setpoint-bounds` where the
 * type has its own (an FCV's setpoint is a flow, m³/s), else the setpoint field's bounds.
 */
export function setpointBounds(valveType: string): Bounds {
	const own = schema('ControlValve')['x-setpoint-bounds'];
	const bounds = isRecord(own) ? own[valveType] : undefined;
	const source = isRecord(bounds) ? bounds : property('ControlValve', 'setpoint');
	const result: Bounds = {};
	for (const key of ['minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum'] as const) {
		const value = source[key];
		if (typeof value === 'number') result[key] = value;
	}
	return result;
}

// ---------------------------------------------------------------------------------------------
// Ordered fields
// ---------------------------------------------------------------------------------------------

/**
 * Two fields of a component whose values must be ordered (`x-ordered-fields`): `lower` below
 * `upper` when `strict`, else at most `upper`. Fields are dotted camelCase paths
 * ('control.minSpeed'); the rule applies when both are present.
 */
export interface OrderedFields {
	lower: string;
	upper: string;
	strict: boolean;
}

/** The ordered field pairs a component's type publishes (`x-ordered-fields`); none when absent. */
export function orderedFields(component: ComponentTagged): readonly OrderedFields[] {
	const name = componentSchemaName(component);
	return name ? schemaOrderedFields(name) : [];
}

/** The ordered field pairs (`x-ordered-fields`) a schema publishes; none when absent. */
export function schemaOrderedFields(schemaName: string): readonly OrderedFields[] {
	const published = schema(schemaName)['x-ordered-fields'];
	if (published === undefined) return [];
	if (!Array.isArray(published)) throw new Error('openapi.json: x-ordered-fields is not a list');
	return published.map((pair: unknown, i) => {
		if (
			!isRecord(pair) ||
			typeof pair.lower !== 'string' ||
			typeof pair.upper !== 'string' ||
			typeof pair.strict !== 'boolean'
		) {
			throw new Error(`openapi.json: x-ordered-fields[${i}] is not {lower, upper, strict}`);
		}
		return { lower: pair.lower, upper: pair.upper, strict: pair.strict };
	});
}

/** The finite number at dotted path `path` of `value` ('control.minSpeed'), or null. */
export function fieldValue(value: unknown, path: string): number | null {
	let node = value;
	for (const key of path.split('.')) {
		if (!isRecord(node)) return null;
		node = node[key];
	}
	return typeof node === 'number' && Number.isFinite(node) ? node : null;
}

/** The ordered pairs (`x-ordered-fields`) whose two values `component` holds out of order. */
export function orderViolations(component: ComponentTagged): OrderedFields[] {
	return orderedFields(component).filter((pair) => {
		const lower = fieldValue(component, pair.lower);
		const upper = fieldValue(component, pair.upper);
		if (lower === null || upper === null) return false;
		return pair.strict ? !(lower < upper) : !(lower <= upper);
	});
}

/**
 * The bounds the ordered pairs (`x-ordered-fields`) put on field `path` of `component`, from the
 * values of the fields it is ordered with: below (or at most) each upper field, above (or at
 * least) each lower one. A pair whose other field is absent adds nothing.
 */
export function orderedBounds(component: ComponentTagged, path: string): Bounds {
	return pairBounds(orderedFields(component), component, path);
}

/**
 * The bounds the ordered pairs `pairs` put on field `path` of `value` (a record of a schema that
 * publishes them, such as a goal-seek variable's lower and upper bounds), as orderedBounds.
 */
export function pairBounds(pairs: readonly OrderedFields[], value: unknown, path: string): Bounds {
	let bounds: Bounds = {};
	for (const pair of pairs) {
		if (pair.lower === path) {
			const upper = fieldValue(value, pair.upper);
			if (upper !== null) {
				bounds = intersectBounds(
					bounds,
					pair.strict ? { exclusiveMaximum: upper } : { maximum: upper }
				);
			}
		}
		if (pair.upper === path) {
			const lower = fieldValue(value, pair.lower);
			if (lower !== null) {
				bounds = intersectBounds(
					bounds,
					pair.strict ? { exclusiveMinimum: lower } : { minimum: lower }
				);
			}
		}
	}
	return bounds;
}

interface Limit {
	value: number;
	exclusive: boolean;
}

/** The tighter of two limits: `higher` for lower limits, else the lower one (exclusive wins a tie). */
function tighter(a: Limit | null, b: Limit | null, higher: boolean): Limit | null {
	if (!a) return b;
	if (!b) return a;
	if (a.value === b.value) return a.exclusive ? a : b;
	return a.value > b.value === higher ? a : b;
}

function limit(value: number | undefined, exclusive: boolean): Limit | null {
	return value === undefined ? null : { value, exclusive };
}

/** Bounds that hold where both `a` and `b` hold (the tighter limit on each side). */
export function intersectBounds(a: Bounds, b: Bounds): Bounds {
	const low = [
		limit(a.minimum, false),
		limit(a.exclusiveMinimum, true),
		limit(b.minimum, false),
		limit(b.exclusiveMinimum, true)
	].reduce((x, y) => tighter(x, y, true), null);
	const high = [
		limit(a.maximum, false),
		limit(a.exclusiveMaximum, true),
		limit(b.maximum, false),
		limit(b.exclusiveMaximum, true)
	].reduce((x, y) => tighter(x, y, false), null);
	const result: Bounds = {};
	if (low) result[low.exclusive ? 'exclusiveMinimum' : 'minimum'] = low.value;
	if (high) result[high.exclusive ? 'exclusiveMaximum' : 'maximum'] = high.value;
	return result;
}

// ---------------------------------------------------------------------------------------------
// Fittings
// ---------------------------------------------------------------------------------------------

/** A fitting field that some fitting types require. */
export type FittingParameter = 'angle' | 'radiusRatio' | 'kOverride';

const FITTING = schema('Fitting');
const FITTING_FIELDS = new Set(Object.keys(isRecord(FITTING.properties) ? FITTING.properties : {}));
const FITTING_TYPES = new Set(stringList(property('Fitting', 'type').enum, 'Fitting.type'));

function fittingTypes(key: string): ReadonlySet<FittingType> {
	const types = stringList(FITTING[key], key);
	for (const type of types) {
		if (!FITTING_TYPES.has(type)) throw new Error(`openapi.json: ${key} names "${type}"`);
	}
	return new Set(types as FittingType[]);
}

/** Fields each fitting type requires beyond type, quantity and pipeIndex (`x-required-parameters`). */
export const FITTING_PARAMETERS: Readonly<Record<string, readonly FittingParameter[]>> = (() => {
	const published = FITTING['x-required-parameters'];
	if (!isRecord(published)) throw new Error('openapi.json: Fitting has no x-required-parameters');
	const parameters: Record<string, FittingParameter[]> = {};
	for (const [type, fields] of Object.entries(published)) {
		parameters[type] = stringList(fields, `x-required-parameters.${type}`).map((field) => {
			if (!FITTING_FIELDS.has(field)) throw new Error(`openapi.json: Fitting has no ${field}`);
			return field as FittingParameter;
		});
	}
	return parameters;
})();

/** Fittings that sit between two pipes, pipeIndex and pipeIndex + 1 (`x-reducer-types`). */
export const REDUCER_TYPES: ReadonlySet<FittingType> = fittingTypes('x-reducer-types');
/** Fittings for the loss where flow leaves a body of liquid into a pipe (`x-entrance-types`). */
export const ENTRANCE_TYPES: ReadonlySet<FittingType> = fittingTypes('x-entrance-types');
/** Fittings for the loss where flow leaves a pipe into a body of liquid (`x-exit-types`). */
export const EXIT_TYPES: ReadonlySet<FittingType> = fittingTypes('x-exit-types');

/**
 * The fields of `fitting` its type requires that it does not have. A reference to a project
 * library entry (`x-reference-fields`: a resistanceId) meets the need for the fields it stands in
 * for (a custom fitting's kOverride).
 */
export function missingFittingParameters(fitting: Fitting): FittingParameter[] {
	const given = referencedFields(fitting, FITTING_REFERENCES);
	return (FITTING_PARAMETERS[fitting.type] ?? []).filter(
		(f) => fitting[f] == null && !given.has(f)
	);
}

// ---------------------------------------------------------------------------------------------
// Project library references and entries (CLAUDE.md D22)
// ---------------------------------------------------------------------------------------------

/**
 * A field that refers to an entry of the project library (`x-reference-fields`): with it given,
 * none of `replaces` may be given, and it meets any rule that requires one of them
 * (`x-required-parameters`); without it, `requiredWithout` are required.
 */
export interface ReferenceField {
	replaces: readonly string[];
	requiredWithout: readonly string[];
}

/** The reference fields a schema publishes (`x-reference-fields`), by field; none when absent. */
export function referenceFields(schemaName: string): Readonly<Record<string, ReferenceField>> {
	const published = schema(schemaName)['x-reference-fields'];
	if (published === undefined) return {};
	if (!isRecord(published)) throw new Error(`openapi.json: ${schemaName} x-reference-fields`);
	const properties = schema(schemaName).properties;
	const known = (field: string) => isRecord(properties) && field in properties;
	const fields: Record<string, ReferenceField> = {};
	for (const [name, entry] of Object.entries(published)) {
		const where = `${schemaName} x-reference-fields.${name}`;
		if (!isRecord(entry) || !known(name)) throw new Error(`openapi.json: ${where}`);
		const replaces = stringList(entry.replaces, `${where}.replaces`);
		const requiredWithout = stringList(entry.requiredWithout, `${where}.requiredWithout`);
		for (const field of [...replaces, ...requiredWithout]) {
			if (!known(field)) throw new Error(`openapi.json: ${where} names "${field}"`);
		}
		fields[name] = { replaces, requiredWithout };
	}
	return fields;
}

/** A pipe's reference to a pipe spec of the project library (specId, `x-reference-fields`). */
export const PIPE_REFERENCES = referenceFields('PipeDefinition');
/** A fitting's reference to a resistance entry of the project library (resistanceId). */
export const FITTING_REFERENCES = referenceFields('Fitting');

/** The fields the references `value` holds stand in for (a resistanceId: kOverride). */
export function referencedFields(
	value: object,
	references: Readonly<Record<string, ReferenceField>>
): Set<string> {
	const record = value as JsonObject;
	const fields = new Set<string>();
	for (const [name, ref] of Object.entries(references)) {
		if (record[name] != null) for (const f of ref.replaces) fields.add(f);
	}
	return fields;
}

/**
 * What `value` breaks of its references' rules (`x-reference-fields`), by reference field: the
 * fields given beside a reference (`given`), and those missing without it (`missing`); none when
 * it keeps them. Null counts as absent, as the API's.
 */
export function referenceViolations(
	value: object,
	references: Readonly<Record<string, ReferenceField>>
): { reference: string; given: string[]; missing: string[] }[] {
	const record = value as JsonObject;
	const found: { reference: string; given: string[]; missing: string[] }[] = [];
	for (const [name, ref] of Object.entries(references)) {
		const given = record[name] != null ? ref.replaces.filter((f) => record[f] != null) : [];
		const missing =
			record[name] == null ? ref.requiredWithout.filter((f) => record[f] == null) : [];
		if (given.length || missing.length) found.push({ reference: name, given, missing });
	}
	return found;
}

/**
 * The fields one field's value requires (given, not null) and forbids (absent or null), published
 * as `x-fields-by-value`: a value not listed adds no rule.
 */
export interface FieldsByValue {
	field: string;
	required: Readonly<Record<string, readonly string[]>>;
	forbidden: Readonly<Record<string, readonly string[]>>;
}

function fieldLists(value: unknown, where: string): Record<string, string[]> {
	if (!isRecord(value)) throw new Error(`openapi.json: ${where}`);
	const lists: Record<string, string[]> = {};
	for (const [key, fields] of Object.entries(value))
		lists[key] = stringList(fields, `${where}.${key}`);
	return lists;
}

/** The rule a schema publishes as `x-fields-by-value`, or null when it publishes none. */
export function fieldsByValue(schemaName: string): FieldsByValue | null {
	const published = schema(schemaName)['x-fields-by-value'];
	if (published === undefined) return null;
	const where = `${schemaName} x-fields-by-value`;
	if (!isRecord(published) || typeof published.field !== 'string') {
		throw new Error(`openapi.json: ${where}`);
	}
	return {
		field: published.field,
		required: fieldLists(published.required, `${where}.required`),
		forbidden: fieldLists(published.forbidden, `${where}.forbidden`)
	};
}

/**
 * What `value` breaks of the `x-fields-by-value` rule of schema `schemaName`: the fields its
 * deciding field's value requires that it lacks (`missing`), and those it forbids that it has
 * (`extra`); both empty when it keeps the rule, or the schema has none.
 */
export function byValueViolations(
	value: object,
	schemaName: string
): { field: string; value: string; missing: string[]; extra: string[] } {
	const rule = fieldsByValue(schemaName);
	const record = value as JsonObject;
	const key = rule ? record[rule.field] : undefined;
	if (!rule || typeof key !== 'string')
		return { field: rule?.field ?? '', value: '', missing: [], extra: [] };
	return {
		field: rule.field,
		value: key,
		missing: (rule.required[key] ?? []).filter((f) => record[f] == null),
		extra: (rule.forbidden[key] ?? []).filter((f) => record[f] != null)
	};
}

/** The ordered pairs (`x-ordered-fields`) of schema `schemaName` whose values `value` breaks. */
export function schemaOrderViolations(value: unknown, schemaName: string): OrderedFields[] {
	return schemaOrderedFields(schemaName).filter((pair) => {
		const lower = fieldValue(value, pair.lower);
		const upper = fieldValue(value, pair.upper);
		if (lower === null || upper === null) return false;
		return pair.strict ? !(lower < upper) : !(lower <= upper);
	});
}

/**
 * The schemas of a valve's resistance union (a coefficient as entered, or a reference to a
 * resistance entry), by each `kind` a member allows (its const or enum), read from the members of
 * `IsolationValve.resistance` (the three valve schemas share it).
 */
const RESISTANCE_SCHEMAS: ReadonlyMap<unknown, string> = (() => {
	const resistance = property('IsolationValve', 'resistance');
	const branches = Array.isArray(resistance.anyOf) ? resistance.anyOf : [resistance];
	const union = branches.find((b): b is JsonObject => isRecord(b) && Array.isArray(b.oneOf));
	if (!union) throw new Error('openapi.json: IsolationValve.resistance is not a union');
	return new Map(
		unionMembers(union).flatMap((name) => {
			const kind = property(name, 'kind');
			const kinds = Array.isArray(kind.enum) ? kind.enum : [kind.const];
			return kinds.map((k): [unknown, string] => [k, name]);
		})
	);
})();

/** The schema a valve's resistance is validated against, by its kind; null when none matches. */
export function resistanceSchemaName(kind: unknown): string | null {
	return RESISTANCE_SCHEMAS.get(kind) ?? null;
}

/** The kind of a valve resistance that refers to a resistance entry ('library'), from the schema. */
export const LIBRARY_RESISTANCE_KIND: string = (() => {
	const kind = property('ResistanceRef', 'kind').const;
	if (typeof kind !== 'string') throw new Error('openapi.json: ResistanceRef.kind has no const');
	return kind;
})();

// ---------------------------------------------------------------------------------------------
// Scenario overrides
// ---------------------------------------------------------------------------------------------

/**
 * One value a scenario may change on a target type (`x-override-fields`): the schema that holds
 * it (its bounds are that schema's property) and its camelCase path from the target, or, for a
 * group whose keys are replaced together (a pipe's spec), those keys of the target. `holders`,
 * where the entry publishes them, are every schema whose objects hold it (a relief valve's
 * `capacity.area`, held by an effective and by a certified capacity); absent, `schema` alone
 * (holdersOf).
 */
export interface OverrideField {
	schema: string;
	path: readonly string[];
	keys: readonly string[];
	holders?: readonly string[];
}

/** The schemas whose objects hold an allow-list value: its published holders, else its schema. */
export function holdersOf(entry: OverrideField): readonly string[] {
	return entry.holders ?? [entry.schema];
}

/**
 * The scenario allow-list (`x-override-fields` on `Scenario`): by target schema (each component
 * schema, `PipeDefinition`, `Project`), the fields a scenario may change. A component schema with
 * no entry takes none.
 */
export const OVERRIDE_FIELDS: Readonly<Record<string, Readonly<Record<string, OverrideField>>>> =
	(() => {
		const published = schema('Scenario')['x-override-fields'];
		if (!isRecord(published)) throw new Error('openapi.json: Scenario has no x-override-fields');
		const fields: Record<string, Record<string, OverrideField>> = {};
		for (const [target, entries] of Object.entries(published)) {
			if (!isRecord(entries)) throw new Error(`openapi.json: x-override-fields.${target}`);
			fields[target] = {};
			for (const [name, entry] of Object.entries(entries)) {
				if (!isRecord(entry) || typeof entry.schema !== 'string') {
					throw new Error(`openapi.json: x-override-fields.${target}.${name}`);
				}
				schema(entry.schema); // the holder exists
				const holders =
					entry.holders === undefined
						? null
						: stringList(entry.holders, `${target}.${name}.holders`);
				for (const holder of holders ?? []) schema(holder);
				fields[target][name] = {
					schema: entry.schema,
					path: entry.path === undefined ? [] : stringList(entry.path, `${target}.${name}.path`),
					keys: entry.keys === undefined ? [] : stringList(entry.keys, `${target}.${name}.keys`),
					...(holders ? { holders } : {})
				};
			}
		}
		return fields;
	})();

/** The fields a scenario may change on a component (by its schema); none for an unknown type. */
export function componentOverrideFields(
	component: ComponentTagged
): Readonly<Record<string, OverrideField>> {
	const name = componentSchemaName(component);
	return (name && OVERRIDE_FIELDS[name]) || {};
}

/** The fields a scenario may change on one pipe (`PipeDefinition`). */
export function pipeOverrideFields(): Readonly<Record<string, OverrideField>> {
	return OVERRIDE_FIELDS.PipeDefinition ?? {};
}

/** The fields a scenario may change on the project itself (the fluid). */
export function projectOverrideFields(): Readonly<Record<string, OverrideField>> {
	return OVERRIDE_FIELDS.Project ?? {};
}

// ---------------------------------------------------------------------------------------------
// Goal seek
// ---------------------------------------------------------------------------------------------

/**
 * One value goal seek may vary on a target type (`x-goal-variables`): the schema whose property
 * bounds the number, the camelCase path from the target to the number (a resistance's is
 * ['resistance', 'value']: it varies one flow coefficient), its search scale, and for a
 * resistance the coefficients it may be varied as.
 */
export interface GoalVariableField {
	schema: string;
	path: readonly string[];
	scale: 'linear' | 'log';
	coefficients: readonly string[];
}

const GOAL_SEEK_REQUEST = schema('GoalSeekRequest');

/**
 * The values goal seek may vary (`x-goal-variables` on `GoalSeekRequest`), by target schema (each
 * component schema, `PipeDefinition`, `Project`): a subset of the scenario allow-list, its numeric
 * values. A schema with no entry has none.
 */
export const GOAL_VARIABLE_FIELDS: Readonly<
	Record<string, Readonly<Record<string, GoalVariableField>>>
> = (() => {
	const published = GOAL_SEEK_REQUEST['x-goal-variables'];
	if (!isRecord(published))
		throw new Error('openapi.json: GoalSeekRequest has no x-goal-variables');
	const fields: Record<string, Record<string, GoalVariableField>> = {};
	for (const [target, entries] of Object.entries(published)) {
		if (!isRecord(entries)) throw new Error(`openapi.json: x-goal-variables.${target}`);
		fields[target] = {};
		for (const [name, entry] of Object.entries(entries)) {
			if (
				!isRecord(entry) ||
				typeof entry.schema !== 'string' ||
				(entry.scale !== 'linear' && entry.scale !== 'log')
			) {
				throw new Error(`openapi.json: x-goal-variables.${target}.${name}`);
			}
			schema(entry.schema); // the bounding schema exists
			fields[target][name] = {
				schema: entry.schema,
				path: stringList(entry.path, `x-goal-variables.${target}.${name}.path`),
				scale: entry.scale,
				coefficients:
					entry.coefficients === undefined
						? []
						: stringList(entry.coefficients, `x-goal-variables.${target}.${name}.coefficients`)
			};
		}
	}
	return fields;
})();

/** The values goal seek may vary on a component (by its schema); none for an unknown type. */
export function componentGoalFields(
	component: ComponentTagged
): Readonly<Record<string, GoalVariableField>> {
	const name = componentSchemaName(component);
	return (name && GOAL_VARIABLE_FIELDS[name]) || {};
}

/** The values goal seek may vary on one pipe (`PipeDefinition`). */
export function pipeGoalFields(): Readonly<Record<string, GoalVariableField>> {
	return GOAL_VARIABLE_FIELDS.PipeDefinition ?? {};
}

/** The values goal seek may vary on the project itself (a built-in fluid's temperature). */
export function projectGoalFields(): Readonly<Record<string, GoalVariableField>> {
	return GOAL_VARIABLE_FIELDS.Project ?? {};
}

/**
 * A result a goal may name (`x-goal-quantities`): its SI unit as the API words it, the schemas of
 * the elements it may name (`PipeConnection` for a connection), whether it names a port, its
 * default tolerance (max(relativeTolerance × |target|, the floor); a head floor applies to a
 * pressure through ρg of the case fluid), the smallest tolerance it accepts (max(relative ×
 * |target|, absolute), in its unit: never the fluid's) and what the case must have for it.
 */
export interface GoalQuantityRule {
	unit: string;
	targets: readonly string[];
	port: boolean;
	relativeTolerance: number;
	floor: Readonly<Partial<Record<'head' | 'flow' | 'velocity', number>>>;
	minimum: { relative: number; absolute: number };
	needs: readonly string[];
}

/** The results a goal may name (`x-goal-quantities` on `GoalSeekRequest`), by API quantity. */
export const GOAL_QUANTITY_RULES: Readonly<Record<string, GoalQuantityRule>> = (() => {
	const published = GOAL_SEEK_REQUEST['x-goal-quantities'];
	if (!isRecord(published)) {
		throw new Error('openapi.json: GoalSeekRequest has no x-goal-quantities');
	}
	const rules: Record<string, GoalQuantityRule> = {};
	for (const [quantity, rule] of Object.entries(published)) {
		const where = `x-goal-quantities.${quantity}`;
		if (
			!isRecord(rule) ||
			typeof rule.unit !== 'string' ||
			typeof rule.port !== 'boolean' ||
			typeof rule.relativeTolerance !== 'number' ||
			!isRecord(rule.floor) ||
			!isRecord(rule.minimum) ||
			typeof rule.minimum.relative !== 'number' ||
			typeof rule.minimum.absolute !== 'number'
		) {
			throw new Error(`openapi.json: ${where}`);
		}
		const floor: Partial<Record<'head' | 'flow' | 'velocity', number>> = {};
		for (const [kind, value] of Object.entries(rule.floor)) {
			if ((kind !== 'head' && kind !== 'flow' && kind !== 'velocity') || typeof value !== 'number')
				throw new Error(`openapi.json: ${where}.floor`);
			floor[kind] = value;
		}
		rules[quantity] = {
			unit: rule.unit,
			targets: stringList(rule.targets, `${where}.targets`),
			port: rule.port,
			relativeTolerance: rule.relativeTolerance,
			floor,
			minimum: { relative: rule.minimum.relative, absolute: rule.minimum.absolute },
			needs: rule.needs === undefined ? [] : stringList(rule.needs, `${where}.needs`)
		};
	}
	return rules;
})();

/** The goal quantities (`x-goal-quantities`), in the published order. */
export function goalQuantities(): Readonly<Record<string, GoalQuantityRule>> {
	return GOAL_QUANTITY_RULES;
}

/**
 * The goal-seek request's list rules (`x-goal-seek-rules`): lists that must have the same length
 * (variables and goals, PRD §3.9), and the keys by which the items of a list must differ (a key
 * an item lacks counts as null). The item limits are the lists' maxItems.
 */
export interface GoalSeekLimits {
	variables: number;
	goals: number;
	sameLength: readonly (readonly [string, string])[];
	uniqueBy: Readonly<Record<string, readonly string[]>>;
}

export const GOAL_SEEK_LIMITS: GoalSeekLimits = (() => {
	const published = GOAL_SEEK_REQUEST['x-goal-seek-rules'];
	if (!isRecord(published) || !Array.isArray(published.sameLength) || !isRecord(published.uniqueBy))
		throw new Error('openapi.json: GoalSeekRequest has no x-goal-seek-rules');
	const sameLength = published.sameLength.map((pair: unknown, i) => {
		const names = stringList(pair, `x-goal-seek-rules.sameLength[${i}]`);
		if (names.length !== 2) throw new Error(`openapi.json: x-goal-seek-rules.sameLength[${i}]`);
		return [names[0], names[1]] as [string, string];
	});
	const uniqueBy: Record<string, string[]> = {};
	for (const [list, keys] of Object.entries(published.uniqueBy)) {
		uniqueBy[list] = stringList(keys, `x-goal-seek-rules.uniqueBy.${list}`);
	}
	const maxItems = (name: string) => {
		const max = property('GoalSeekRequest', name).maxItems;
		if (typeof max !== 'number') throw new Error(`openapi.json: GoalSeekRequest.${name} maxItems`);
		return max;
	};
	return { variables: maxItems('variables'), goals: maxItems('goals'), sameLength, uniqueBy };
})();

/** The goal-seek request's limits and list rules (see GoalSeekLimits). */
export function goalSeekLimits(): GoalSeekLimits {
	return GOAL_SEEK_LIMITS;
}

/** The goal-seek variable schemas of the `GoalSeekRequest.variables` union, by their `kind`. */
const GOAL_VARIABLE_SCHEMAS: ReadonlyMap<unknown, string> = new Map(
	unionMembers(
		isRecord(property('GoalSeekRequest', 'variables').items)
			? (property('GoalSeekRequest', 'variables').items as JsonObject)
			: {}
	).map((name) => [property(name, 'kind').const, name])
);

/** The schema a goal-seek variable is validated against, by its kind; null when none. */
export function goalVariableSchemaName(kind: unknown): string | null {
	return GOAL_VARIABLE_SCHEMAS.get(kind) ?? null;
}

// ---------------------------------------------------------------------------------------------
// Design checks (CLAUDE.md D19)
// ---------------------------------------------------------------------------------------------

/** A cited preset of a design check's limits (`x-design-check-presets`). */
export interface DesignCheckPreset {
	id: 'api610_por' | 'hi961_2012_general';
	check: 'npshMargin' | 'operatingRegion';
	values: Record<string, number>;
	citation: string;
}

const DESIGN_CHECK_PRESETS: readonly DesignCheckPreset[] = (() => {
	const published = schema('DesignChecks')['x-design-check-presets'];
	if (!Array.isArray(published)) throw new Error('openapi.json: DesignChecks has no presets');
	return published.map((p: unknown, i) => {
		if (
			!isRecord(p) ||
			typeof p.id !== 'string' ||
			typeof p.check !== 'string' ||
			typeof p.citation !== 'string' ||
			!isRecord(p.values) ||
			!Object.values(p.values).every((v) => typeof v === 'number')
		) {
			throw new Error(`openapi.json: x-design-check-presets[${i}]`);
		}
		return p as unknown as DesignCheckPreset;
	});
})();

/** The design checks' cited presets, as the API publishes them. */
export function designCheckPresets(check?: DesignCheckPreset['check']): DesignCheckPreset[] {
	return DESIGN_CHECK_PRESETS.filter((p) => !check || p.check === check);
}

// ---------------------------------------------------------------------------------------------
// Fields of a schema (the Build form registry, utils/field-registry.ts)
// ---------------------------------------------------------------------------------------------

/** One field of a schema: its dotted path from the schema and what the schema says of it. */
export interface SchemaField {
	/** 'speed', 'control.setpoint', 'capacity.letter' (a union member's field). */
	path: string;
	/** The schemas holding it (several for a field of more than one union member). */
	holders: readonly string[];
	/** Its default, when the schema states one. */
	default?: unknown;
	/** It is an object (a pump's control, a relief valve's capacity), not a value. */
	object: boolean;
}

/** The object schemas a property's value can be: $refs, and the members of anyOf/oneOf. */
function objectSchemasOf(node: JsonObject): string[] {
	if (typeof node.$ref === 'string') {
		const name = node.$ref.split('/').pop() ?? '';
		return isRecord(schema(name).properties) ? [name] : [];
	}
	const members = [
		...(Array.isArray(node.anyOf) ? node.anyOf : []),
		...(Array.isArray(node.oneOf) ? node.oneOf : [])
	];
	return members.filter(isRecord).flatMap(objectSchemasOf);
}

/** A discriminator: a property whose value is fixed (`const`), such as `kind` or `mode`. */
function isConst(node: JsonObject): boolean {
	return 'const' in node;
}

/**
 * Every field of schema `name` a form can set, read from openapi.json: each property that is not
 * a discriminator (`const`), and, inside an object property (a $ref, or a union of them), each of
 * its members' fields, under its dotted path. Lists (ports, curve points) are one field each. A
 * field held by several union members (a capacity's `area`) is listed once, with every holder.
 */
export function schemaFields(name: string): SchemaField[] {
	const found = new Map<string, SchemaField>();
	const walk = (schemaName: string, prefix: string) => {
		const properties = schema(schemaName).properties;
		if (!isRecord(properties)) return;
		for (const [key, node] of Object.entries(properties)) {
			if (!isRecord(node) || isConst(node)) continue;
			const path = prefix + key;
			const objects = objectSchemasOf(node);
			const existing = found.get(path);
			if (existing) {
				existing.holders = [...existing.holders, schemaName];
			} else {
				found.set(path, {
					path,
					holders: [schemaName],
					...('default' in node ? { default: node.default } : {}),
					object: objects.length > 0
				});
			}
			for (const member of objects) walk(member, `${path}.`);
		}
	};
	walk(name, '');
	return [...found.values()];
}

/** The values a choice field of schema `name` allows (its `enum`, also inside anyOf), in order. */
export function schemaChoices(name: string, path: string): string[] {
	const node = property(name, path);
	const alternatives = Array.isArray(node.anyOf) ? node.anyOf.filter(isRecord) : [node];
	const values = alternatives.flatMap((alt) => (Array.isArray(alt.enum) ? alt.enum : []));
	return values.map(String);
}
