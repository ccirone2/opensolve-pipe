import { describe, expect, it } from 'vitest';
import {
	fieldEntry,
	FIELD_REGISTRY,
	isSet,
	unitOf,
	sectionsOf,
	staleEntries,
	unregisteredFields,
	valueAt
} from './field-registry';
import {
	COMPONENT_SCHEMAS,
	GOAL_VARIABLE_FIELDS,
	OVERRIDE_FIELDS,
	schemaFields
} from './model-rules';

/**
 * The schemas a Build form edits: every component type (the Project.components union, read from
 * the schema), and the pipe, port and pump curve schemas its Piping and curve forms edit.
 */
const BUILD_SCHEMAS = [...COMPONENT_SCHEMAS, 'Port', 'PipeDefinition', 'Fitting', 'PumpCurve'];

describe('the Build form registry (proposal build-density.md §5)', () => {
	it('covers every component schema the API has', () => {
		expect(COMPONENT_SCHEMAS.length).toBeGreaterThan(10);
		for (const name of BUILD_SCHEMAS) expect(FIELD_REGISTRY[name], name).toBeDefined();
	});

	it.each(BUILD_SCHEMAS)('gives every field of %s a section and a tier', (name) => {
		// A field added to the model reaches Build only with its entry: a section and a tier.
		expect(unregisteredFields(name)).toEqual([]);
	});

	it.each(BUILD_SCHEMAS)('names only fields %s has', (name) => {
		expect(staleEntries(name)).toEqual([]);
	});

	it('names no schema the API lacks', () => {
		for (const name of Object.keys(FIELD_REGISTRY)) expect(BUILD_SCHEMAS).toContain(name);
	});

	it('reads fields from the schema, inside unions and nested objects', () => {
		const pump = schemaFields('Pump').map((f) => f.path);
		expect(pump).toEqual(expect.arrayContaining(['speed', 'control', 'control.setpoint']));
		expect(pump).not.toContain('control.mode'); // a discriminator (const)
		expect(pump).not.toContain('type');
		const relief = schemaFields('ReliefValve');
		const area = relief.find((f) => f.path === 'capacity.area');
		expect(area?.holders).toEqual(['EffectiveOrifice', 'CertifiedOrifice']);
		expect(schemaFields('Pump').find((f) => f.path === 'speed')?.default).toBe(1);
	});

	it('fails a schema field with no entry', () => {
		const saved = FIELD_REGISTRY.Reservoir!;
		const rest = { ...saved };
		delete rest.liquidLevel;
		(FIELD_REGISTRY as Record<string, unknown>).Reservoir = rest;
		try {
			expect(unregisteredFields('Reservoir')).toEqual(['liquidLevel']);
		} finally {
			(FIELD_REGISTRY as Record<string, unknown>).Reservoir = saved;
		}
	});

	it('orders sections by facet and keeps the registry order inside one', () => {
		expect(sectionsOf('Pump', 'core').map((s) => [s.facet, s.paths])).toEqual([
			['operation', ['status', 'control', 'control.setpoint', 'control.minSpeed', 'speed']],
			['rating', ['curveId']],
			['placement', ['elevation']]
		]);
		expect(sectionsOf('Pump', 'more').map((s) => s.paths)).toEqual([['ports']]);
		expect(sectionsOf('Reservoir', 'more').map((s) => s.paths)).toEqual([
			['surfacePressure'],
			['ports']
		]);
	});

	it('states gauge or not for every pressure it draws (D4)', () => {
		// A pressure field drawn without saying so would be labelled "kPa", gauge or not.
		for (const [schema, entries] of Object.entries(FIELD_REGISTRY)) {
			for (const [path, entry] of Object.entries(entries)) {
				if (entry.input?.kind === 'number' && entry.input.category === 'pressure') {
					expect(typeof entry.input.gauge, `${schema}.${path}`).toBe('boolean');
				}
			}
		}
	});

	it('names every value a scenario may change, and gives each number goal seek varies a unit', () => {
		// Scenario notes, goal seek and the export read labels and units here (one table): a field
		// added to an allow-list (x-override-fields, x-goal-variables) needs its entry, or a
		// scenario change would read "Minimum flow" humanized and a flow would show with no unit.
		let checked = 0;
		for (const schema of [...COMPONENT_SCHEMAS, 'PipeDefinition']) {
			checked += Object.keys(GOAL_VARIABLE_FIELDS[schema] ?? {}).length;
			for (const path of Object.keys(OVERRIDE_FIELDS[schema] ?? {})) {
				if (schema === 'PipeDefinition' && path === 'spec') continue; // a group: its keys
				expect(fieldEntry(schema, path), `${schema}.${path}`).toBeDefined();
			}
			for (const path of Object.keys(GOAL_VARIABLE_FIELDS[schema] ?? {})) {
				const entry = fieldEntry(schema, path);
				expect(entry, `${schema}.${path}`).toBeDefined();
				// A resistance is written with its coefficient ("Cv 120"), its own rule.
				if (path !== 'resistance') expect(unitOf(entry!), `${schema}.${path}`).not.toBeNull();
			}
		}
		expect(checked).toBeGreaterThan(15);
	});

	it('counts a value as set when it is not the schema default', () => {
		expect(isSet('Pump', 'speed', 1)).toBe(false);
		expect(isSet('Pump', 'speed', 0.9)).toBe(true);
		expect(isSet('CheckValve', 'resistance', undefined)).toBe(false);
		expect(isSet('CheckValve', 'resistance', { kind: 'K', value: 2 })).toBe(true);
		expect(isSet('WyeBranch', 'lossModel', 'crane')).toBe(false);
		expect(isSet('WyeBranch', 'lossModel', 'ideal')).toBe(true);
		// Ports always have a size; an elevation of their own is what counts.
		expect(isSet('Pump', 'ports', [{ id: 'suction', nominalSize: 0.1 }])).toBe(false);
		expect(isSet('Pump', 'ports', [{ id: 'suction', nominalSize: 0.1, elevation: 2 }])).toBe(true);
		expect(valueAt({ control: { setpoint: 3 } }, 'control.setpoint')).toBe(3);
		expect(valueAt({ control: null }, 'control.setpoint')).toBeUndefined();
	});
});
