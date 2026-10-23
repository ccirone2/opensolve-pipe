/**
 * Numeric bounds of model fields, read from the generated OpenAPI schema (the Pydantic models
 * are the source of truth), so inputs reject what the API would reject before it is stored.
 */
import openapi from '../api/openapi.json';
import { componentSchemaName, type ComponentTagged } from './model-rules';

export interface Bounds {
	minimum?: number;
	maximum?: number;
	exclusiveMinimum?: number;
	exclusiveMaximum?: number;
}

type JsonObject = Record<string, unknown>;

function isRecord(value: unknown): value is JsonObject {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function pickBounds(schema: JsonObject): Bounds {
	const bounds: Bounds = {};
	for (const key of ['minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum'] as const) {
		const value = schema[key];
		if (typeof value === 'number') bounds[key] = value;
	}
	return bounds;
}

const SCHEMAS = openapi.components.schemas as unknown as Record<string, unknown>;

/**
 * Bounds of `schemaName.property` (SI, as stored). Nullable fields (anyOf [number, null]) use
 * the number branch. Unknown names give no bounds.
 */
export function schemaBounds(schemaName: string, property: string): Bounds {
	const schema = SCHEMAS[schemaName];
	if (!isRecord(schema) || !isRecord(schema.properties)) return {};
	const field = schema.properties[property];
	if (!isRecord(field)) return {};
	const alternatives = Array.isArray(field.anyOf) ? field.anyOf : [field];
	const numeric = alternatives.find(
		(alt): alt is JsonObject => isRecord(alt) && (alt.type === 'number' || alt.type === 'integer')
	);
	return numeric ? pickBounds(numeric) : {};
}

/**
 * A sentence saying why `value` is outside `bounds`, with the limit shown by `format` (which
 * converts an SI value to display text), or null when it is inside.
 */
export function boundsProblem(
	value: number,
	bounds: Bounds,
	format: (si: number) => string
): string | null {
	if (bounds.minimum !== undefined && value < bounds.minimum) {
		return `Must be at least ${format(bounds.minimum)}.`;
	}
	if (bounds.exclusiveMinimum !== undefined && value <= bounds.exclusiveMinimum) {
		return `Must be greater than ${format(bounds.exclusiveMinimum)}.`;
	}
	if (bounds.maximum !== undefined && value > bounds.maximum) {
		return `Must be at most ${format(bounds.maximum)}.`;
	}
	if (bounds.exclusiveMaximum !== undefined && value >= bounds.exclusiveMaximum) {
		return `Must be less than ${format(bounds.exclusiveMaximum)}.`;
	}
	return null;
}

/** The fitting type ids the API accepts, in schema order. */
export function fittingTypes(): string[] {
	const fitting = SCHEMAS.Fitting;
	if (!isRecord(fitting) || !isRecord(fitting.properties)) return [];
	const type = fitting.properties.type;
	return isRecord(type) && Array.isArray(type.enum) ? type.enum.map(String) : [];
}

/** Length limits of a string field (e.g. names), from the schema. */
export function stringLimits(
	schemaName: string,
	property: string
): { minLength?: number; maxLength?: number } {
	const schema = SCHEMAS[schemaName];
	if (!isRecord(schema) || !isRecord(schema.properties)) return {};
	const field = schema.properties[property];
	if (!isRecord(field)) return {};
	const alternatives = Array.isArray(field.anyOf) ? field.anyOf : [field];
	const text = alternatives.find(
		(alt): alt is JsonObject => isRecord(alt) && alt.type === 'string'
	);
	if (!text) return {};
	const limits: { minLength?: number; maxLength?: number } = {};
	if (typeof text.minLength === 'number') limits.minLength = text.minLength;
	if (typeof text.maxLength === 'number') limits.maxLength = text.maxLength;
	return limits;
}

/**
 * Name of the schema a component is validated against, e.g. 'Reservoir', 'CheckValve' (the
 * Project.components union, model-rules.ts).
 */
export function componentSchema(component: ComponentTagged): string {
	const name = componentSchemaName(component);
	if (!name) throw new Error(`No schema for component type "${String(component.type)}"`);
	return name;
}
