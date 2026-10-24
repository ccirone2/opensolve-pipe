import { describe, expect, it } from 'vitest';
import openapi from '../api/openapi.json';
import {
	boundsProblem,
	componentSchema,
	fittingTypes,
	schemaBounds,
	stringLimits
} from './schema-bounds';
import { COMPONENT_KINDS, createComponent, createEmptyProject } from './factory';

describe('schemaBounds', () => {
	it('reads bounds from the generated schema', () => {
		expect(schemaBounds('Reservoir', 'liquidLevel')).toEqual({ minimum: 0, maximum: 1000 });
		expect(schemaBounds('PipeDefinition', 'length')).toEqual({
			exclusiveMinimum: 0,
			maximum: 1_000_000
		});
	});

	it('uses the number branch of nullable fields', () => {
		expect(schemaBounds('PipeDefinition', 'roughness')).toEqual({ minimum: 0, maximum: 0.1 });
		expect(schemaBounds('ProjectSettings', 'atmosphericPressure')).toEqual({
			minimum: 10000,
			maximum: 120000
		});
	});

	it('gives no bounds for unknown names', () => {
		expect(schemaBounds('Nope', 'x')).toEqual({});
		expect(schemaBounds('Reservoir', 'name')).toEqual({});
	});
});

describe('boundsProblem', () => {
	const fmt = (v: number) => `${v} u`;
	it('reports the violated limit', () => {
		expect(boundsProblem(-1, { minimum: 0 }, fmt)).toBe('Must be at least 0 u.');
		expect(boundsProblem(0, { exclusiveMinimum: 0 }, fmt)).toBe('Must be greater than 0 u.');
		expect(boundsProblem(11, { maximum: 10 }, fmt)).toBe('Must be at most 10 u.');
		expect(boundsProblem(10, { exclusiveMaximum: 10 }, fmt)).toBe('Must be less than 10 u.');
		expect(boundsProblem(5, { minimum: 0, maximum: 10 }, fmt)).toBeNull();
	});
});

describe('schema lookups', () => {
	it('lists the fitting types in the schema', () => {
		expect(fittingTypes()).toEqual(openapi.components.schemas.Fitting.properties.type.enum);
	});

	it('reads string limits', () => {
		expect(stringLimits('ProjectMetadata', 'name')).toEqual({ minLength: 1, maxLength: 200 });
		expect(stringLimits('PumpCurve', 'manufacturer')).toEqual({ maxLength: 100 });
	});

	it('names the schema of every kind of component', () => {
		const project = createEmptyProject();
		// An assigned-flow node's flow has no default; 0.004 m³/s is a made-up test input.
		const schemas = COMPONENT_KINDS.map((k) =>
			componentSchema(createComponent(k, project, { flow: 0.004 }))
		);
		expect(new Set(schemas)).toEqual(
			new Set([
				'Reservoir',
				'IdealReferenceNode',
				'Plug',
				'AssignedFlow',
				'TeeBranch',
				'WyeBranch',
				'Pump',
				'IsolationValve',
				'CheckValve',
				'ControlValve'
			])
		);
		for (const schema of schemas) expect(openapi.components.schemas).toHaveProperty(schema);
	});
});
