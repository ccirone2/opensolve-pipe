/**
 * Project validation.
 *
 * - schemaProblems: the generated `Project` JSON schema (src/lib/api/openapi.json, produced
 *   from the Pydantic models, which are the source of truth), checked with Ajv.
 * - referenceProblems: integrity of the port graph (D2): unique ids, every connection end names
 *   an existing component and port, at most one connection per port.
 * - modelRuleProblems: rules the API models enforce in validators, which JSON Schema cannot
 *   express (port ids per component type, pipe size source, fitting parameters, increasing
 *   curve flows, ...), plus pump-curve references. A project that breaks only these still
 *   opens; the solver reports them too.
 *
 * Every problem is a human-readable sentence that names where it is.
 */
import Ajv2020, { type ErrorObject, type ValidateFunction } from 'ajv/dist/2020.js';
import openapi from '../api/openapi.json';
import type { Component, PipeConnection, Project, UnitPreferences } from '../api/types';
import { componentName, fittingFallbackName, portLabel } from './labels';
import { formatValue, SI_UNITS } from './units';

const SCHEMA_ID = 'urn:opensolve-pipe:openapi';
const IDENTIFIER_PATTERN = '^[A-Za-z0-9_-]+$';

type JsonObject = Record<string, unknown>;

function isRecord(value: unknown): value is JsonObject {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

let ajv: Ajv2020 | undefined;

function getAjv(): Ajv2020 {
	if (!ajv) {
		ajv = new Ajv2020({ allErrors: true, strict: true });
		// OpenAPI annotation; the oneOf it annotates is what is validated.
		ajv.addKeyword('discriminator');
		// The OpenAPI document section that holds the schemas; refs point into it.
		ajv.addKeyword('components');
		ajv.addSchema({ $id: SCHEMA_ID, components: { schemas: openapi.components.schemas } });
	}
	return ajv;
}

const validators = new Map<string, ValidateFunction>();

/** Compiled validator for one named schema in openapi.json (compiled once, on first use). */
function validatorFor(name: string): ValidateFunction {
	let validate = validators.get(name);
	if (!validate) {
		validate = getAjv().getSchema(`${SCHEMA_ID}#/components/schemas/${name}`);
		if (!validate) throw new Error(`Schema ${name} is missing from openapi.json`);
		validators.set(name, validate);
	}
	return validate;
}

// ---------------------------------------------------------------------------------------------
// Schema problems
// ---------------------------------------------------------------------------------------------

/** Valve family by valveType, as in the API's component discriminator (models/components.py). */
const VALVE_SCHEMAS: Record<string, string> = {
	gate: 'IsolationValve',
	ball: 'IsolationValve',
	butterfly: 'IsolationValve',
	globe: 'IsolationValve',
	check: 'CheckValve',
	stop_check: 'CheckValve',
	prv: 'ControlValve',
	psv: 'ControlValve',
	fcv: 'ControlValve'
};

/**
 * The schema a oneOf member is meant to match, from its tag (component type refined by
 * branchType or valveType; fluid kind). Mirrors the API's discriminators, so problems are
 * reported against the intended schema instead of every alternative.
 */
function taggedSchema(value: unknown): string | null {
	if (!isRecord(value)) return null;
	if ('kind' in value && !('type' in value)) {
		return value.kind === 'builtin'
			? 'BuiltinFluid'
			: value.kind === 'custom'
				? 'CustomFluid'
				: null;
	}
	switch (value.type) {
		case 'reservoir':
			return 'Reservoir';
		case 'reference_node':
			return 'IdealReferenceNode';
		case 'plug':
			return 'Plug';
		case 'pump':
			return 'Pump';
		case 'branch':
			return value.branchType === 'tee'
				? 'TeeBranch'
				: value.branchType === 'wye'
					? 'WyeBranch'
					: null;
		case 'valve':
			return typeof value.valveType === 'string' ? (VALVE_SCHEMAS[value.valveType] ?? null) : null;
		default:
			return null;
	}
}

function valueAt(root: unknown, pointer: string): unknown {
	let node = root;
	for (const segment of pointerSegments(pointer)) {
		if (Array.isArray(node)) node = node[Number(segment)];
		else if (isRecord(node)) node = node[segment];
		else return undefined;
	}
	return node;
}

function pointerSegments(pointer: string): string[] {
	if (pointer === '') return [];
	return pointer
		.slice(1)
		.split('/')
		.map((s) => s.replace(/~1/g, '/').replace(/~0/g, '~'));
}

/** '/components/0/ports/1/id' → 'components[0] "R1" › ports[1] "suction" › id'. */
function describePath(root: unknown, pointer: string): string {
	const parts: string[] = [];
	let node = root;
	for (const segment of pointerSegments(pointer)) {
		if (Array.isArray(node)) {
			node = node[Number(segment)];
			const id = isRecord(node) && typeof node.id === 'string' ? ` "${node.id}"` : '';
			const last = parts.pop() ?? '';
			parts.push(`${last}[${segment}]${id}`);
		} else {
			node = isRecord(node) ? node[segment] : undefined;
			parts.push(segment);
		}
	}
	return parts.length ? parts.join(' › ') : 'project';
}

function describeError(error: ErrorObject): string {
	const params = error.params as Record<string, unknown>;
	switch (error.keyword) {
		case 'required':
			return `is missing the required field "${String(params.missingProperty)}"`;
		case 'additionalProperties':
			return `has an unknown field "${String(params.additionalProperty)}"`;
		case 'const':
			return `must be ${JSON.stringify(params.allowedValue)}`;
		case 'enum':
			return `must be one of ${(params.allowedValues as unknown[]).map((v) => JSON.stringify(v)).join(', ')}`;
		case 'pattern':
			return params.pattern === IDENTIFIER_PATTERN
				? "must use only letters, digits, '_' or '-'"
				: (error.message ?? 'has the wrong format');
		case 'type':
			return `must be ${params.type === 'integer' ? 'a whole number' : `of type ${String(params.type)}`}`;
		default:
			return error.message ?? `fails the "${error.keyword}" check`;
	}
}

/** Collect readable problems for `value` validated with `validate`; `base` prefixes paths. */
function collect(
	validate: ValidateFunction,
	value: unknown,
	root: unknown,
	base: string
): string[] {
	if (validate(value)) return [];
	const errors = validate.errors ?? [];
	const oneOfPaths = errors.filter((e) => e.keyword === 'oneOf').map((e) => e.instancePath);
	const insideOneOf = (path: string) =>
		oneOfPaths.some((p) => path === p || path.startsWith(`${p}/`));
	const problems: string[] = [];

	for (const path of new Set(oneOfPaths)) {
		const member = valueAt(value, path);
		const name = taggedSchema(member);
		const where = describePath(root, base + path);
		if (name) problems.push(...collect(validatorFor(name), member, root, base + path));
		else if (isRecord(member) && 'type' in member)
			problems.push(`${where}: unknown component type (or branchType / valveType)`);
		else if (isRecord(member) && 'kind' in member)
			problems.push(`${where}: unknown fluid kind ${JSON.stringify(member.kind)}`);
		else problems.push(`${where}: must be an object of one of the allowed kinds`);
	}

	const nullBranch = (e: ErrorObject) =>
		e.keyword === 'type' && (e.params as { type?: unknown }).type === 'null';
	const rest = errors.filter(
		(e) => !insideOneOf(e.instancePath) && e.keyword !== 'anyOf' && !nullBranch(e)
	);
	// A nullable field (anyOf [X, null]) whose only failure is "not null" still needs a message.
	const shown = rest.length || problems.length ? rest : errors.filter((e) => e.keyword !== 'anyOf');
	for (const error of shown) {
		problems.push(`${describePath(root, base + error.instancePath)}: ${describeError(error)}`);
	}
	return [...new Set(problems)];
}

/** Problems found by checking `value` against the API's `Project` JSON schema. */
export function schemaProblems(value: unknown): string[] {
	return collect(validatorFor('Project'), value, value, '');
}

// ---------------------------------------------------------------------------------------------
// Schema defaults
// ---------------------------------------------------------------------------------------------

function resolveRef(schema: JsonObject): JsonObject {
	let current = schema;
	for (let guard = 0; typeof current.$ref === 'string' && guard < 32; guard++) {
		const name = current.$ref.replace('#/components/schemas/', '');
		const target = (openapi.components.schemas as Record<string, unknown>)[name];
		if (!isRecord(target)) break;
		current = target;
	}
	return current;
}

function schemaName(schema: unknown): string | null {
	return isRecord(schema) && typeof schema.$ref === 'string'
		? schema.$ref.replace('#/components/schemas/', '')
		: null;
}

function fillDefaults(schemaIn: unknown, data: unknown): void {
	if (!isRecord(schemaIn) || data === null || typeof data !== 'object') return;
	const schema = resolveRef(schemaIn);
	const alternatives = (schema.oneOf ?? schema.anyOf) as unknown[] | undefined;
	if (Array.isArray(alternatives)) {
		const match = alternatives.find((alt) => {
			const name = schemaName(alt);
			return name ? validatorFor(name)(data) : isRecord(alt) && alt.type !== 'null';
		});
		fillDefaults(match, data);
		return;
	}
	if (Array.isArray(data)) {
		for (const item of data) fillDefaults(schema.items, item);
		return;
	}
	const record = data as JsonObject;
	const properties = isRecord(schema.properties) ? schema.properties : {};
	for (const [key, sub] of Object.entries(properties)) {
		if (!isRecord(sub)) continue;
		if (!(key in record) && 'default' in sub) record[key] = structuredClone(sub.default);
		if (key in record) fillDefaults(sub, record[key]);
	}
	if (isRecord(schema.additionalProperties)) {
		for (const [key, item] of Object.entries(record)) {
			if (!(key in properties)) fillDefaults(schema.additionalProperties, item);
		}
	}
}

// ---------------------------------------------------------------------------------------------
// Port-graph references
// ---------------------------------------------------------------------------------------------

function duplicates(values: Iterable<string>): string[] {
	const seen = new Set<string>();
	const dups = new Set<string>();
	for (const v of values) (seen.has(v) ? dups : seen).add(v);
	return [...dups];
}

/**
 * Integrity of the port graph. A project with any of these problems cannot be shown or edited
 * as a graph, so links with them do not open.
 */
export function referenceProblems(project: Project): string[] {
	const problems: string[] = [];
	for (const id of duplicates(project.components.map((c) => c.id))) {
		problems.push(`Component id "${id}" is used more than once.`);
	}
	for (const id of duplicates(project.connections.map((c) => c.id))) {
		problems.push(`Connection id "${id}" is used more than once.`);
	}
	const ports = new Map<string, Set<string>>();
	for (const component of project.components) {
		for (const id of duplicates(component.ports.map((p) => p.id))) {
			problems.push(`Component "${component.id}" has more than one port "${id}".`);
		}
		ports.set(component.id, new Set(component.ports.map((p) => p.id)));
	}
	const usedBy = new Map<string, string>();
	for (const connection of project.connections) {
		const ends = [
			['from', connection.fromComponentId, connection.fromPortId],
			['to', connection.toComponentId, connection.toPortId]
		] as const;
		for (const [end, componentId, portId] of ends) {
			const componentPorts = ports.get(componentId);
			if (!componentPorts) {
				problems.push(
					`Connection "${connection.id}" (${end} end) refers to component "${componentId}", which does not exist.`
				);
				continue;
			}
			if (!componentPorts.has(portId)) {
				problems.push(
					`Connection "${connection.id}" (${end} end) refers to port "${portId}" of component "${componentId}", which does not exist.`
				);
				continue;
			}
			const key = `${componentId}:${portId}`;
			const other = usedBy.get(key);
			if (other === connection.id) {
				problems.push(`Connection "${connection.id}" connects port "${key}" to itself.`);
			} else if (other !== undefined) {
				problems.push(
					`Port "${key}" has more than one connection ("${other}" and "${connection.id}"); a port takes one.`
				);
			} else {
				usedBy.set(key, connection.id);
			}
		}
	}
	return problems;
}

// ---------------------------------------------------------------------------------------------
// Model rules (mirrors apps/api/src/opensolve_pipe/models validators)
// ---------------------------------------------------------------------------------------------

/** Required port ids per component, as models/components.py `_require_ports`. */
export function requiredPortIds(component: Component): readonly string[] | null {
	switch (component.type) {
		case 'plug':
			return ['port_1'];
		case 'branch':
			return component.branchType === 'tee'
				? ['run_inlet', 'run_outlet', 'branch']
				: ['inlet', 'outlet_1', 'outlet_2'];
		case 'pump':
			return ['suction', 'discharge'];
		case 'valve':
			return ['inlet', 'outlet'];
		default:
			return null;
	}
}

/** Fitting fields each type needs (models/piping.py REQUIRED_PARAMETERS). */
export const FITTING_PARAMETERS: Record<
	string,
	readonly ('angle' | 'radiusRatio' | 'kOverride')[]
> = {
	bend: ['angle', 'radiusRatio'],
	entrance_rounded: ['radiusRatio'],
	reducer_conical: ['angle'],
	custom: ['kOverride']
};
const REDUCERS = new Set(['reducer_sudden', 'reducer_conical']);

/**
 * One model-rule problem: `text` names elements by id (validation messages, as the API does);
 * `message` names them as people see them (component names, pipe numbers, display units), for
 * the results pane. `componentId` and `portId` locate it in Build (for a connection, its 'from'
 * end, where its piping opens).
 */
export interface ModelRuleIssue {
	text: string;
	message: string;
	componentId?: string;
	portId?: string;
	connectionId?: string;
}

function pipingIssues(project: Project, connection: PipeConnection): ModelRuleIssue[] {
	const issues: ModelRuleIssue[] = [];
	const where = `Connection "${connection.id}"`;
	const named = `Piping ${componentName(project, connection.fromComponentId)} → ${componentName(project, connection.toComponentId)}`;
	const at = {
		componentId: connection.fromComponentId,
		portId: connection.fromPortId,
		connectionId: connection.id
	};
	const add = (text: string, message: string) => issues.push({ text, message, ...at });
	const { pipes, fittings } = connection.piping;
	pipes.forEach((pipe, i) => {
		if (pipe.materialId === 'custom') {
			if (pipe.innerDiameter == null || pipe.roughness == null) {
				add(
					`${where}, pipe ${i + 1}: a custom pipe needs an inner diameter and a roughness.`,
					`${named}, pipe ${i + 1}: a custom pipe needs an inner diameter and a roughness.`
				);
			}
		} else if (pipe.innerDiameter == null && (pipe.schedule == null || pipe.nominalSize == null)) {
			const rule = 'a library pipe needs a schedule and a nominal size (or an inner diameter).';
			add(`${where}, pipe ${i + 1}: ${rule}`, `${named}, pipe ${i + 1}: ${rule}`);
		}
	});
	const fields = { angle: 'an angle', radiusRatio: 'a radius ratio', kOverride: 'a K value' };
	fittings.forEach((fitting, i) => {
		const missing = (FITTING_PARAMETERS[fitting.type] ?? []).filter((f) => fitting[f] == null);
		if (missing.length) {
			add(
				`${where}, fitting ${i + 1} (${fitting.type}) needs ${missing.join(', ')}.`,
				`${named}, fitting ${i + 1} (${fittingFallbackName(fitting.type).toLowerCase()}) needs ${missing.map((f) => fields[f]).join(' and ')}.`
			);
		}
		const last = REDUCERS.has(fitting.type) ? pipes.length - 2 : pipes.length - 1;
		if (fitting.pipeIndex > last) {
			const segments = `${pipes.length} pipe segment${pipes.length === 1 ? '' : 's'}`;
			const tail = REDUCERS.has(fitting.type) ? ' and a reducer needs a following segment.' : '.';
			add(
				`${where}, fitting ${i + 1} (${fitting.type}) is on pipe ${fitting.pipeIndex + 1}, ` +
					`but the connection has ${pipes.length} pipe segment(s)${tail}`,
				`${named}, fitting ${i + 1} is on pipe ${fitting.pipeIndex + 1}, but the piping has ${segments}${tail}`
			);
		}
	});
	return issues;
}

function increasing(flows: number[]): boolean {
	return flows.every((q, i) => i === 0 || q > (flows[i - 1] as number));
}

/** FCV setpoint bounds, m³/s (models/components.py). */
const FCV_SETPOINT_MAX = 100;

/**
 * Rules the API models check in validators, and pump-curve references, as issues located in the
 * project (see ModelRuleIssue). `units` formats values in `message` (default SI).
 */
export function modelRuleIssues(
	project: Project,
	units: UnitPreferences = SI_UNITS
): ModelRuleIssue[] {
	const issues: ModelRuleIssue[] = [];
	const curveIds = new Set(project.pumpLibrary.map((c) => c.id));
	const connectionIds = new Set(project.connections.map((c) => c.id));
	const curveName = (id: string) => {
		const curve = project.pumpLibrary.find((c) => c.id === id);
		return curve ? `“${curve.name}”` : `“${id}”`;
	};

	for (const component of project.components) {
		const where = `Component "${component.id}"`;
		const at = { componentId: component.id };
		const required = requiredPortIds(component);
		const ids = component.ports.map((p) => p.id).sort();
		if (required && JSON.stringify(ids) !== JSON.stringify([...required].sort())) {
			issues.push({
				text: `${where} must have ports ${required.join(', ')} (it has ${ids.join(', ')}).`,
				message: `${component.name} must have the ports ${required.map(portLabel).join(', ')} (it has ${ids.map(portLabel).join(', ')}).`,
				...at
			});
		}
		if (component.type === 'reference_node' && component.ports.length !== 1) {
			issues.push({
				text: `${where}: a reference node has exactly one port.`,
				message: `${component.name}: a reference node has exactly one port.`,
				...at
			});
		}
		if (component.type === 'valve' && component.valveType === 'fcv') {
			if (!(component.setpoint >= 0 && component.setpoint <= FCV_SETPOINT_MAX)) {
				issues.push({
					text: `${where}: an FCV setpoint is a flow between 0 and ${FCV_SETPOINT_MAX} m³/s.`,
					message: `The flow setpoint of ${component.name} must be between ${formatValue(0, 'flow', units)} and ${formatValue(FCV_SETPOINT_MAX, 'flow', units)}.`,
					...at
				});
			}
		}
		if (component.type === 'pump' && !curveIds.has(component.curveId)) {
			issues.push({
				text: `${where} uses pump curve "${component.curveId}", which is not in the pump library.`,
				message: `${component.name} needs a pump curve: enter at least 3 points of its head against flow, or pick a curve from the project's pump library.`,
				...at
			});
		}
		if (connectionIds.has(component.id)) {
			const text = `Id "${component.id}" is used by both a component and a connection.`;
			issues.push({ text, message: text, ...at });
		}
	}
	for (const connection of project.connections) issues.push(...pipingIssues(project, connection));
	for (const id of duplicates(project.pumpLibrary.map((c) => c.id))) {
		const text = `Pump curve id "${id}" is used more than once.`;
		issues.push({ text, message: text });
	}
	for (const curve of project.pumpLibrary) {
		const where = `Pump curve "${curve.id}"`;
		const named = `Pump curve ${curveName(curve.id)}`;
		const user = project.components.find((c) => c.type === 'pump' && c.curveId === curve.id);
		const at = user ? { componentId: user.id } : {};
		const add = (rule: string) =>
			issues.push({ text: `${where}: ${rule}`, message: `${named}: ${rule}`, ...at });
		if (!increasing(curve.points.map((p) => p.flow))) {
			add('flows must be strictly increasing.');
		}
		if (curve.efficiencyCurve && !increasing(curve.efficiencyCurve.map((p) => p.flow))) {
			add('efficiency curve flows must be strictly increasing.');
		}
		if (curve.npshrCurve && !increasing(curve.npshrCurve.map((p) => p.flow))) {
			add('NPSHr curve flows must be strictly increasing.');
		}
	}
	return issues;
}

/** Rules the API models check in validators, and pump-curve references (ids, see modelRuleIssues). */
export function modelRuleProblems(project: Project): string[] {
	return modelRuleIssues(project).map((issue) => issue.text);
}

// ---------------------------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------------------------

/** Every problem: schema first; graph and model rules only when the schema holds. */
export function projectProblems(value: unknown): string[] {
	const schema = schemaProblems(value);
	if (schema.length) return schema;
	const project = value as Project;
	return [...referenceProblems(project), ...modelRuleProblems(project)];
}

export class ProjectValidationError extends Error {
	readonly problems: readonly string[];

	constructor(problems: readonly string[]) {
		super(`Invalid project: ${problems.slice(0, 3).join(' ')}${problems.length > 3 ? ' …' : ''}`);
		this.name = 'ProjectValidationError';
		this.problems = problems;
	}
}

/**
 * Check a decoded project and return it typed. Throws ProjectValidationError when it fails the
 * schema or the port-graph checks. Fields the schema gives defaults for are filled in when
 * absent (as the API does), so the result satisfies the generated `Project` type. The value is
 * modified in place.
 */
export function parseProject(value: unknown): Project {
	const schema = schemaProblems(value);
	if (schema.length) throw new ProjectValidationError(schema);
	fillDefaults({ $ref: '#/components/schemas/Project' }, value);
	const project = value as Project;
	const references = referenceProblems(project);
	if (references.length) throw new ProjectValidationError(references);
	return project;
}
