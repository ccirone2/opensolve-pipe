/**
 * The app's model rules are the API schema's (openapi.json, generated from the Pydantic models):
 * these tests fail if a rule the app applies and the one the schema publishes disagree. The API
 * side (tests/unit/test_schema_rules.py) checks that each published extension is what the
 * models' validators enforce, and that openapi.json is the API's current schema.
 */
import { describe, expect, it } from 'vitest';
import openapi from '../api/openapi.json';
import type { Component, Fitting, FittingType } from '../api/types';
import { projectWith } from '../testing/helpers';
import { DEFAULT_ENTRANCE, DEFAULT_EXIT, hasReservoirLoss } from './edit';
import { COMPONENT_KINDS, componentKind, createComponent, createEmptyProject } from './factory';
import { portRole } from './graph';
import {
	COMPONENT_SCHEMAS,
	componentSchemaName,
	ENTRANCE_TYPES,
	EXIT_TYPES,
	FITTING_PARAMETERS,
	fluidSchemaName,
	maxPorts,
	missingFittingParameters,
	namedPortRole,
	REDUCER_TYPES,
	requiredPortCount,
	requiredPortIds,
	schemaExtensions,
	setpointBounds
} from './model-rules';
import { isReducer, maxPipeIndex } from './piping';
import { componentSchema, schemaBounds } from './schema-bounds';
import { modelRuleIssues, modelRuleProblems, schemaProblems } from './validate';

type JsonObject = Record<string, unknown>;
const SCHEMAS = openapi.components.schemas as unknown as Record<string, JsonObject>;
const extension = (schema: string, key: string) => SCHEMAS[schema]![key];

/** One component of every kind the app creates, with its schema. */
const COMPONENTS = COMPONENT_KINDS.map((kind) => createComponent(kind, createEmptyProject()));

describe('component schemas', () => {
	it('are the members of the Project.components union, and every kind maps to one', () => {
		const union = openapi.components.schemas.Project.properties.components.items.oneOf.map((m) =>
			m.$ref.split('/').pop()
		);
		expect(COMPONENT_SCHEMAS).toEqual(union);
		const used = new Set(COMPONENTS.map((c) => componentSchemaName(c)));
		expect([...used].sort()).toEqual([...COMPONENT_SCHEMAS].sort());
		for (const component of COMPONENTS) {
			const name = componentSchema(component);
			const properties = SCHEMAS[name]!.properties as Record<string, JsonObject>;
			expect(properties.type!.const).toBe(component.type);
			const valveTypes = properties.valveType?.enum as string[] | undefined;
			if (component.type === 'valve') expect(valveTypes).toContain(component.valveType);
			if (component.type === 'branch')
				expect(properties.branchType!.const).toBe(component.branchType);
		}
		expect(componentSchemaName({ type: 'valve', valveType: 'relief' })).toBeNull();
		expect(componentSchemaName({ type: 'tank' })).toBeNull();
		expect(fluidSchemaName('builtin')).toBe('BuiltinFluid');
		expect(fluidSchemaName('custom')).toBe('CustomFluid');
		expect(fluidSchemaName('plasma')).toBeNull();
	});

	it('give the port ids, count and roles the app uses', () => {
		for (const component of COMPONENTS) {
			const name = componentSchema(component);
			const ids = extension(name, 'x-port-ids') as string[] | undefined;
			const roles = (extension(name, 'x-port-roles') ?? {}) as Record<string, string>;
			expect(requiredPortIds(component)).toEqual(ids ?? null);
			expect(requiredPortCount(component)).toEqual(extension(name, 'x-port-count') ?? null);
			// New components have exactly the schema's ports.
			if (ids) expect(component.ports.map((p) => p.id).sort(), name).toEqual([...ids].sort());
			const count = extension(name, 'x-port-count');
			if (typeof count === 'number') expect(component.ports).toHaveLength(count);
			for (const port of component.ports) {
				const role = roles[port.id];
				expect(namedPortRole(component, port.id)).toBe(role ?? null);
				// The navigator orients connections by the schema's roles (graph.ts).
				expect(portRole(component, port.id), `${name} ${port.id}`).toBe(
					role === 'inlet' ? 'in' : role === 'outlet' ? 'out' : 'any'
				);
			}
			const ports = openapi.components.schemas.Reservoir.properties.ports;
			expect(maxPorts(component)).toBe(
				(SCHEMAS[name]!.properties as Record<string, JsonObject>).ports!.maxItems
			);
			expect(maxPorts(component)).toBeLessThanOrEqual(ports.maxItems);
		}
	});

	it('are what the model-rule check enforces', () => {
		for (const component of COMPONENTS) {
			const ids = requiredPortIds(component);
			const count = requiredPortCount(component);
			if (!ids && count === null) continue;
			const wrong = structuredClone(component) as Component;
			if (ids) wrong.ports[wrong.ports.length - 1]!.id = 'other';
			else wrong.ports.push({ ...wrong.ports[0]!, id: 'port_extra' });
			const problems = modelRuleProblems(projectWith([wrong])).filter(
				(p) => !p.includes('pump curve')
			);
			expect(problems, componentKind(component)).toHaveLength(1);
			expect(problems[0]).toMatch(ids ? /must have ports/ : /exactly one port/);
		}
	});

	it('bound control-valve setpoints by valve type', () => {
		const own = extension('ControlValve', 'x-setpoint-bounds') as Record<string, JsonObject>;
		expect(Object.keys(own)).toEqual(['fcv']);
		expect(setpointBounds('fcv')).toEqual(own.fcv);
		for (const type of ['prv', 'psv']) {
			expect(setpointBounds(type)).toEqual(schemaBounds('ControlValve', 'setpoint'));
		}
		const fcv = createComponent('fcv', createEmptyProject());
		const { minimum, maximum } = setpointBounds('fcv') as { minimum: number; maximum: number };
		for (const [setpoint, problems] of [
			[minimum, 0],
			[maximum, 0],
			[maximum * (1 + 1e-12), 1],
			[-1e-12, 1]
		] as const) {
			const project = projectWith([{ ...fcv, setpoint }]);
			expect(modelRuleProblems(project), String(setpoint)).toHaveLength(problems);
		}
	});
});

describe('fitting rules', () => {
	const fitting = openapi.components.schemas.Fitting;

	it('are the schema extensions of Fitting', () => {
		expect(FITTING_PARAMETERS).toEqual(fitting['x-required-parameters']);
		expect([...REDUCER_TYPES]).toEqual(fitting['x-reducer-types']);
		expect([...ENTRANCE_TYPES]).toEqual(fitting['x-entrance-types']);
		expect([...EXIT_TYPES]).toEqual(fitting['x-exit-types']);
		expect(ENTRANCE_TYPES.has(DEFAULT_ENTRANCE)).toBe(true);
		expect(EXIT_TYPES.has(DEFAULT_EXIT)).toBe(true);
	});

	it('are what the piping checks and edits apply', () => {
		for (const type of fitting.properties.type.enum as FittingType[]) {
			const bare: Fitting = { type, quantity: 1, pipeIndex: 0 };
			const required = FITTING_PARAMETERS[type] ?? [];
			expect(missingFittingParameters(bare)).toEqual(required);
			expect(isReducer(bare)).toBe(REDUCER_TYPES.has(type));
			expect(maxPipeIndex(bare, 3)).toBe(REDUCER_TYPES.has(type) ? 1 : 2);
			const piping = { pipes: [], fittings: [bare] };
			expect(hasReservoirLoss(piping)).toBe(ENTRANCE_TYPES.has(type) || EXIT_TYPES.has(type));
		}
	});
});

describe('the validator', () => {
	it('knows every extension keyword of the schema', () => {
		const keys = new Set<string>();
		for (const schema of Object.values(SCHEMAS)) {
			for (const key of Object.keys(schema)) if (key.startsWith('x-')) keys.add(key);
		}
		expect(schemaExtensions()).toEqual([...keys].sort());
		expect(schemaProblems(createEmptyProject())).toEqual([]);
	});

	it("mirrors the API's DUPLICATE_ID rule: a component and a connection sharing an id", () => {
		const project = projectWith([
			createComponent('reservoir', createEmptyProject(), { id: 'R1' }),
			createComponent('reservoir', createEmptyProject(), { id: 'R2' })
		]);
		project.connections.push({
			id: 'R2',
			fromComponentId: 'R1',
			fromPortId: 'port_1',
			toComponentId: 'R2',
			toPortId: 'port_1',
			piping: {
				pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 10 }],
				fittings: []
			}
		});
		const [issue] = modelRuleIssues(project);
		expect(issue).toMatchObject({
			code: 'DUPLICATE_ID',
			text: 'Id "R2" is used by both a component and a connection.',
			componentId: 'R2',
			connectionId: 'R2'
		});
		expect(modelRuleIssues(project)).toHaveLength(1);
	});
});
