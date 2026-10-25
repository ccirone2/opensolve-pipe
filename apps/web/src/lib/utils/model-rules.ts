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
 * - on a component schema, `x-ordered-fields` (pairs of fields whose values must be ordered, such
 *   as a speed-controlled pump's minimum speed below its speed, the maximum);
 * - on `Scenario`, `x-override-fields` (the values a scenario may change, by target schema: the
 *   allow-list of the scenario manager, PRD §3.8);
 * - on `GoalSeekRequest`, `x-goal-variables` (the numeric allow-list values goal seek may vary, by
 *   target schema, with the schema that bounds each number and its search scale),
 *   `x-goal-quantities` (the results a goal may name, with their default-tolerance rules) and
 *   `x-goal-seek-rules` (the request's list rules), and `x-ordered-fields` on each goal-seek
 *   variable schema (its lower bound below its upper), PRD §3.9.
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

/** The fields of `fitting` its type requires that it does not have. */
export function missingFittingParameters(fitting: Fitting): FittingParameter[] {
	return (FITTING_PARAMETERS[fitting.type] ?? []).filter((f) => fitting[f] == null);
}

// ---------------------------------------------------------------------------------------------
// Scenario overrides
// ---------------------------------------------------------------------------------------------

/**
 * One value a scenario may change on a target type (`x-override-fields`): the schema that holds
 * it (its bounds are that schema's property) and its camelCase path from the target, or, for a
 * group whose keys are replaced together (a pipe's spec), those keys of the target.
 */
export interface OverrideField {
	schema: string;
	path: readonly string[];
	keys: readonly string[];
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
				fields[target][name] = {
					schema: entry.schema,
					path: entry.path === undefined ? [] : stringList(entry.path, `${target}.${name}.path`),
					keys: entry.keys === undefined ? [] : stringList(entry.keys, `${target}.${name}.keys`)
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
