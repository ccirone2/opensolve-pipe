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
import { enteredFor } from '../testing/helpers';

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

	it("reads an equipment rating's bounds from its member of the union", () => {
		// The rating's fields have no default; their bounds are the schema's (decision 3).
		expect(schemaBounds('RatedPoint', 'pressureLoss')).toEqual({
			exclusiveMinimum: 0,
			maximum: 1e8
		});
		expect(schemaBounds('RatedPoint', 'flow')).toEqual({ exclusiveMinimum: 0, maximum: 100 });
		expect(schemaBounds('RatedPoint', 'density')).toEqual({ exclusiveMinimum: 0, maximum: 3e4 });
		expect(schemaBounds('RatedFlowCoefficient', 'value')).toEqual(
			schemaBounds('FlowCoefficient', 'value')
		);
	});

	it("reads an orifice plate's bounds: the bore and the entered C (orifice-plate.md §2.1)", () => {
		// (0, 10] m, the pipe inner diameter's bound; C in (0, 1], or absent (ISO 5167-2's).
		expect(schemaBounds('Orifice', 'boreDiameter')).toEqual({ exclusiveMinimum: 0, maximum: 10 });
		expect(schemaBounds('Orifice', 'boreDiameter')).toEqual(
			schemaBounds('PipeDefinition', 'innerDiameter')
		);
		expect(schemaBounds('Orifice', 'dischargeCoefficient')).toEqual({
			exclusiveMinimum: 0,
			maximum: 1
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
		// An assigned-flow node's flow, an equipment item's rating, an orifice plate's bore and a
		// relief valve's set pressure and capacity have no default: made-up test inputs (enteredFor).
		const schemas = COMPONENT_KINDS.map((k) =>
			componentSchema(createComponent(k, project, enteredFor(k)))
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
				'ControlValve',
				'Equipment',
				'Orifice',
				'ReliefValve'
			])
		);
		for (const schema of schemas) expect(openapi.components.schemas).toHaveProperty(schema);
	});
});
