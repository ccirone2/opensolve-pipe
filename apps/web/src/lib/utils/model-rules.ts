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
 * - on `ControlValve`, `x-setpoint-bounds` (an FCV's setpoint is a flow).
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
