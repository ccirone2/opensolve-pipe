/**
 * The project library (CLAUDE.md D21, docs/proposals/project-library.md): pipe specs and loss
 * coefficients (a K at the bore it is stated at, a Cv or a Kv) the user defines once, each with
 * its source, and refers to by id: a pipe segment by `specId`, a valve by its resistance
 * `{kind: 'library', id}`, an inline fitting by `resistanceId`. They are references, not
 * templates: an edit to an entry reaches every element that refers to it (the owner's answer Q1).
 *
 * Every edit here is pure (a new project, the input never modified) and refuses with EditError,
 * as utils/edit.ts does: a new entry never takes an id in use (usedIds: one namespace with the
 * elements and pump curves), an entry is never removed while an element or a scenario's change
 * refers to it (as removePumpCurve), and an entry that breaks the API's published rules
 * (`x-fields-by-value`, `x-ordered-fields`, model-rules.ts) is never written. Both lists are left
 * out of the project when empty, so a project without a library encodes byte for byte as before.
 *
 * The browser resolves references for display only, as the server resolves them
 * (services/solver/project_library.py): a pipe of a spec is the pipe {materialId, innerDiameter,
 * roughness, length} the spec stands for; a K entry on an element of bore D is K₀ (D/d₀)⁴. A Cv or
 * Kv is converted by the server only (fluids' Cv_to_K and Kv_to_K, ISA-75.01.01), and a library
 * material's roughness at a spec's bore (Farshad & Rieke at that bore) is computed by the server
 * only: neither is copied here (D10: read, never copy), so the browser says the server resolves
 * them.
 */
import type {
	Component,
	FlowCoefficient,
	Override,
	PipeDefinition,
	PipeSize,
	PipeSpec,
	PipingSegment,
	Project,
	ResistanceRef,
	ResistanceSpec,
	UnitPreferences,
	ValveResistance
} from '../api/types';
import { EditError, updateComponent } from './edit';
import { newId, PIPE_SPEC_PREFIX, RESISTANCE_PREFIX, usedIds } from './factory';
import { componentById, connectionById } from './graph';
import { markCopy } from './identity';
import { fittingFallbackName, humanize, npsLabel, sameSize } from './labels';
import {
	byValueViolations,
	LIBRARY_RESISTANCE_KIND,
	schemaOrderViolations,
	type OrderedFields
} from './model-rules';
import { CUSTOM_MATERIAL_ID, resolvedPipe, type ResolvedPipe } from './piping';
import { formatValue } from './units';

// ---------------------------------------------------------------------------------------------
// The lists
// ---------------------------------------------------------------------------------------------

/** The project's pipe specs (none when it has no pipeLibrary). */
export function pipeSpecs(project: Project): readonly PipeSpec[] {
	return project.pipeLibrary ?? [];
}

/** The project's resistance entries (none when it has no resistanceLibrary). */
export function resistanceEntries(project: Project): readonly ResistanceSpec[] {
	return project.resistanceLibrary ?? [];
}

/** The pipe spec `id` of the project, if it has one. */
export function pipeSpecOf(project: Project, id: string | null | undefined): PipeSpec | undefined {
	return id == null ? undefined : pipeSpecs(project).find((s) => s.id === id);
}

/** The resistance entry `id` of the project, if it has one. */
export function resistanceEntryOf(
	project: Project,
	id: string | null | undefined
): ResistanceSpec | undefined {
	return id == null ? undefined : resistanceEntries(project).find((e) => e.id === id);
}

/** Whether the project has a library entry of either kind. */
export function hasLibrary(project: Project): boolean {
	return pipeSpecs(project).length > 0 || resistanceEntries(project).length > 0;
}

/** The project with its pipe specs replaced; an empty list removes the key (links as before). */
export function withPipeLibrary(project: Project, specs: readonly PipeSpec[]): Project {
	const next: Project = { ...project };
	if (specs.length) next.pipeLibrary = [...specs];
	else delete next.pipeLibrary;
	return next;
}

/** The project with its resistance entries replaced; an empty list removes the key. */
export function withResistanceLibrary(
	project: Project,
	entries: readonly ResistanceSpec[]
): Project {
	const next: Project = { ...project };
	if (entries.length) next.resistanceLibrary = [...entries];
	else delete next.resistanceLibrary;
	return next;
}

/** A new pipe spec id (PS1, PS2, ...), never one in use or referred to (factory.newId). */
export function newPipeSpecId(project: Project, reserved: Iterable<string> = []): string {
	return newId(project, PIPE_SPEC_PREFIX, reserved);
}

/** A new resistance entry id (RS1, RS2, ...), never one in use or referred to. */
export function newResistanceId(project: Project, reserved: Iterable<string> = []): string {
	return newId(project, RESISTANCE_PREFIX, reserved);
}

// ---------------------------------------------------------------------------------------------
// Valve resistances
// ---------------------------------------------------------------------------------------------

/** Whether a valve's resistance refers to a resistance entry ({kind: 'library', id}). */
export function isResistanceRef(value: unknown): value is ResistanceRef {
	return (
		typeof value === 'object' &&
		value !== null &&
		(value as { kind?: unknown }).kind === LIBRARY_RESISTANCE_KIND &&
		typeof (value as { id?: unknown }).id === 'string'
	);
}

/** A valve's resistance as entered on it (a K, Cv or Kv), or null: none, or a library entry. */
export function inlineCoefficient(
	resistance: ValveResistance | null | undefined
): FlowCoefficient | null {
	return resistance && !isResistanceRef(resistance) ? resistance : null;
}

/** The resistance entry a valve refers to, when it refers to one the project has. */
export function valveEntry(project: Project, component: Component): ResistanceSpec | undefined {
	if (component.type !== 'valve' || !isResistanceRef(component.resistance)) return undefined;
	return resistanceEntryOf(project, component.resistance.id);
}

/**
 * A K entry's K on an element of bore `bore` (m): K₀ (D/d₀)⁴, the same head loss at a given flow
 * (proposal §3.3; exactly K₀ when D = d₀); null for a Cv or Kv, which the server converts on the
 * element's bore (fluids' Cv_to_K, Kv_to_K: not copied here), or without a bore.
 */
export function entryKAtBore(
	entry: Pick<ResistanceSpec, 'kind' | 'value' | 'referenceDiameter'>,
	bore: number | null | undefined
): number | null {
	if (entry.kind !== 'K' || entry.referenceDiameter == null || bore == null || !(bore > 0)) {
		return null;
	}
	const k = entry.value * (bore / entry.referenceDiameter) ** 4;
	return Number.isFinite(k) ? k : null;
}

// ---------------------------------------------------------------------------------------------
// Pipes
// ---------------------------------------------------------------------------------------------

/**
 * The pipe a spec stands for: its material, inner diameter and roughness (when given) with the
 * segment's own length, the pipe the server solves (services/solver/project_library.spec_pipe).
 */
export function specPipe(pipe: Pick<PipeDefinition, 'length'>, spec: PipeSpec): PipeDefinition {
	const own: PipeDefinition = {
		materialId: spec.materialId,
		innerDiameter: spec.innerDiameter,
		length: pipe.length
	};
	if (spec.roughness != null) own.roughness = spec.roughness;
	return own;
}

/** A pipe as it is solved: a pipe of a spec the project has is the pipe it stands for. */
export function pipeAsSolved(project: Project, pipe: PipeDefinition): PipeDefinition {
	const spec = pipe.specId == null ? undefined : pipeSpecOf(project, pipe.specId);
	return spec ? specPipe(pipe, spec) : pipe;
}

/** What the pipe library answers for a size (a LibraryStore, or a fake in tests). */
export interface PipeSizeLookup {
	size(
		materialId: string,
		scheduleId: string | null | undefined,
		nominalSize: number | null | undefined
	): PipeSize | undefined;
}

/** A pipe's bore and roughness as far as the browser knows them, and where they come from. */
export interface PipeResolution extends ResolvedPipe {
	/** The material it is solved with: its own, or its spec's (absent: neither is known). */
	materialId?: string;
	/** The spec it refers to, when the project has it. */
	spec?: PipeSpec;
	/** The id of a spec it refers to that the project does not have (UNKNOWN_PIPE_SPEC). */
	missingSpec?: string;
	/**
	 * Its roughness is the library material's (Farshad & Rieke 2006) at its own bore, which only
	 * the server computes: a spec on a library material without a roughness, or a library pipe
	 * with an inner-diameter override and no roughness. `roughness` is then absent.
	 */
	serverRoughness?: true;
}

/**
 * The inner diameter and roughness the server resolves `pipe` of `project` to, as far as the
 * browser knows them (piping.resolvedPipe for a pipe of its own; a spec's own values for a pipe
 * of a spec). `sizes` is the pipe library; without it, a library size is unknown.
 */
export function resolvePipe(
	project: Project,
	pipe: PipeDefinition,
	sizes?: PipeSizeLookup
): PipeResolution {
	if (pipe.specId != null) {
		const spec = pipeSpecOf(project, pipe.specId);
		if (!spec) return { missingSpec: pipe.specId };
		const resolution: PipeResolution = {
			...resolvedPipe(specPipe(pipe, spec), undefined),
			materialId: spec.materialId,
			spec
		};
		if (spec.roughness == null && spec.materialId !== CUSTOM_MATERIAL_ID) {
			resolution.serverRoughness = true;
		}
		return resolution;
	}
	const materialId = pipe.materialId ?? undefined;
	const custom = materialId === CUSTOM_MATERIAL_ID;
	const size =
		materialId && !custom ? sizes?.size(materialId, pipe.schedule, pipe.nominalSize) : undefined;
	const resolution: PipeResolution = { ...resolvedPipe(pipe, size) };
	if (materialId !== undefined) resolution.materialId = materialId;
	if (!custom && pipe.innerDiameter != null && pipe.roughness == null) {
		resolution.serverRoughness = true;
	}
	return resolution;
}

/** A pipe that refers to spec `specId`: only its length beside it (x-reference-fields). */
export function withSpec(pipe: Pick<PipeDefinition, 'length'>, specId: string): PipeDefinition {
	return { specId, length: pipe.length };
}

/**
 * Whether two pipes are the same size and material (every field a spec stands in for: material,
 * schedule, nominal size and the bore and roughness overrides, or the same spec), whatever their
 * lengths. Nominal sizes are compared as the library compares them (labels.sameSize).
 */
export function samePipeKind(a: PipeDefinition, b: PipeDefinition): boolean {
	if (a.specId != null || b.specId != null) return a.specId === b.specId;
	const size = (x: number | null | undefined, y: number | null | undefined) =>
		x == null || y == null ? x == null && y == null : sameSize(x, y);
	return (
		(a.materialId ?? null) === (b.materialId ?? null) &&
		(a.schedule ?? null) === (b.schedule ?? null) &&
		size(a.nominalSize, b.nominalSize) &&
		(a.innerDiameter ?? null) === (b.innerDiameter ?? null) &&
		(a.roughness ?? null) === (b.roughness ?? null)
	);
}

// ---------------------------------------------------------------------------------------------
// Words
// ---------------------------------------------------------------------------------------------

/** An entry as texts name it: “NPS 60 STD carbon steel”. */
export function entryName(entry: Pick<PipeSpec | ResistanceSpec, 'name'>): string {
	return `“${entry.name}”`;
}

/**
 * A resistance entry's coefficient as entered, in display units: "Cv 60000", "Kv 90", "K 0.3 at
 * 736.6 mm" (a K with the bore it is stated at). 6 significant digits, as a goal seek's texts.
 */
export function entryValueText(
	entry: Pick<ResistanceSpec, 'kind' | 'value' | 'referenceDiameter'>,
	units: UnitPreferences,
	sig = 6
): string {
	const value = formatValue(entry.value, 'dimensionless', units, sig);
	const bore =
		entry.kind === 'K' && entry.referenceDiameter != null
			? ` at ${formatValue(entry.referenceDiameter, 'diameter', units, sig)}`
			: '';
	return `${entry.kind} ${value}${bore}`;
}

/** Names the browser may know besides the project (as scenarios.ValueTextOptions). */
export interface LibraryTextOptions {
	/** The material's name from the pipe library ('Carbon steel'); default: the id, humanized. */
	materialName?: (id: string) => string | undefined;
	/** Nominal sizes with their NPS designation, for "NPS 2-1/2". */
	nominalSizes?: readonly { nominalSize: number; nps: string }[];
}

/**
 * A pipe spec's values in display units: "Carbon steel, NPS 60, inner diameter 1505 mm, roughness
 * by the material at this bore", "Custom pipe, inner diameter 80 mm, roughness 0.0015 mm".
 */
export function specValuesText(
	spec: PipeSpec,
	units: UnitPreferences,
	options: LibraryTextOptions = {}
): string {
	const custom = spec.materialId === CUSTOM_MATERIAL_ID;
	const parts = [
		custom ? 'Custom pipe' : (options.materialName?.(spec.materialId) ?? humanize(spec.materialId))
	];
	if (spec.nominalSize != null) parts.push(npsLabel(spec.nominalSize, options.nominalSizes));
	parts.push(`inner diameter ${formatValue(spec.innerDiameter, 'diameter', units)}`);
	parts.push(
		spec.roughness != null
			? `roughness ${formatValue(spec.roughness, 'diameter', units)}`
			: "roughness the material's at this bore (Farshad & Rieke), as the server computes it"
	);
	return parts.join(', ');
}

/**
 * A valve's resistance in words, in display units: "Default", "Cv 120", or the entry it refers
 * to, “30 in butterfly valve” (project library, Cv 60000), by its id where the project does not
 * have it.
 */
export function resistanceText(
	project: Project,
	resistance: unknown,
	units: UnitPreferences
): string {
	if (resistance === null || resistance === undefined) return 'Default';
	if (isResistanceRef(resistance)) return entryRefText(project, resistance.id, units);
	if (typeof resistance === 'object') {
		const coefficient = resistance as { kind?: unknown; value?: unknown };
		return `${String(coefficient.kind)} ${formatValue(Number(coefficient.value), 'dimensionless', units)}`;
	}
	return String(resistance);
}

/**
 * A resistance entry a value refers to: “Name” (project library, Cv 60000); "project library
 * entry RS1 (not in the library)" when the project does not have it.
 */
export function entryRefText(project: Project, id: string, units: UnitPreferences): string {
	const entry = resistanceEntryOf(project, id);
	return entry
		? `${entryName(entry)} (project library, ${entryValueText(entry, units, 4)})`
		: `project library entry ${id} (not in the library)`;
}

/**
 * A pipe spec a value refers to: “Name” (project library pipe spec); "project library pipe spec
 * PS1 (not in the library)" when the project does not have it.
 */
export function specRefText(project: Project, id: string): string {
	const spec = pipeSpecOf(project, id);
	return spec
		? `${entryName(spec)} (project library pipe spec)`
		: `project library pipe spec ${id} (not in the library)`;
}

/** An entry the server's text names (a trace note, a data source, the methods summary). */
export interface LibraryMention {
	list: 'pipe' | 'resistance';
	id: string;
	/** Where the mention is in the text: `text.slice(index, index + length)`. */
	index: number;
	length: number;
}

/**
 * How the server names an entry (services/solver/project_library.py spec_label and
 * resistance_label): 'project library pipe spec "NPS 60 STD" (PS1)', 'project library resistance
 * "30 in butterfly valve" (RS1)'. The name is the entry's when solved (it may have been renamed
 * since); the id is what is matched.
 */
const MENTION = /project library (pipe spec|resistance) "(?:[^"]|"(?! \())*" \(([A-Za-z0-9_-]+)\)/g;

/**
 * The entries of `project`'s library that the server's `text` names, in order, for the trace view
 * to link to the entry (proposal project-library.md §6.4). A mention of an entry the project no
 * longer has is left out.
 */
export function libraryMentions(text: string, project: Project): LibraryMention[] {
	const mentions: LibraryMention[] = [];
	for (const match of text.matchAll(MENTION)) {
		const list = match[1] === 'pipe spec' ? 'pipe' : 'resistance';
		const id = match[2] ?? '';
		const known = list === 'pipe' ? pipeSpecOf(project, id) : resistanceEntryOf(project, id);
		if (known) mentions.push({ list, id, index: match.index, length: match[0].length });
	}
	return mentions;
}

// ---------------------------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------------------------

/** What refers to an entry: a pipe, a valve, a fitting, or a scenario's change. */
export type LibraryUser =
	| { kind: 'pipe'; connectionId: string; pipeIndex: number }
	| { kind: 'valve'; componentId: string }
	| { kind: 'fitting'; connectionId: string; fittingIndex: number }
	| { kind: 'scenario'; scenarioId: string; changeIndex: number; override: Override };

/** Whether a scenario's change refers to pipe spec `specId` (a spec change {specId}). */
function changeUsesSpec(o: Override, specId: string): boolean {
	if (o.kind !== 'pipe' || o.field !== 'spec') return false;
	const value = o.value as { specId?: unknown } | null;
	return !!value && typeof value === 'object' && value.specId === specId;
}

/** Whether a scenario's change refers to resistance entry `entryId` (a valve's resistance). */
function changeUsesEntry(o: Override, entryId: string): boolean {
	return (
		o.kind === 'component' &&
		o.field === 'resistance' &&
		isResistanceRef(o.value) &&
		o.value.id === entryId
	);
}

function scenarioUsers(project: Project, uses: (o: Override) => boolean): LibraryUser[] {
	const users: LibraryUser[] = [];
	for (const scenario of project.scenarios ?? []) {
		(scenario.overrides ?? []).forEach((override, changeIndex) => {
			if (uses(override)) {
				users.push({ kind: 'scenario', scenarioId: scenario.id, changeIndex, override });
			}
		});
	}
	return users;
}

/**
 * Everything that refers to pipe spec `specId`: base pipes in project order, then scenarios'
 * changes in scenario and change order.
 */
export function pipeSpecUsers(project: Project, specId: string): LibraryUser[] {
	const users: LibraryUser[] = [];
	for (const connection of project.connections) {
		connection.piping.pipes.forEach((pipe, pipeIndex) => {
			if (pipe.specId === specId) {
				users.push({ kind: 'pipe', connectionId: connection.id, pipeIndex });
			}
		});
	}
	return [...users, ...scenarioUsers(project, (o) => changeUsesSpec(o, specId))];
}

/**
 * Everything that refers to resistance entry `entryId`: valves in project order, fittings in
 * connection order, then scenarios' changes.
 */
export function resistanceUsers(project: Project, entryId: string): LibraryUser[] {
	const users: LibraryUser[] = [];
	for (const component of project.components) {
		if (
			component.type === 'valve' &&
			isResistanceRef(component.resistance) &&
			component.resistance.id === entryId
		) {
			users.push({ kind: 'valve', componentId: component.id });
		}
	}
	for (const connection of project.connections) {
		connection.piping.fittings.forEach((fitting, fittingIndex) => {
			if (fitting.resistanceId === entryId) {
				users.push({ kind: 'fitting', connectionId: connection.id, fittingIndex });
			}
		});
	}
	return [...users, ...scenarioUsers(project, (o) => changeUsesEntry(o, entryId))];
}

/** "Tank → Pump": a connection's ends by name (ids where the project has no such component). */
function pipingName(project: Project, connectionId: string): string {
	const connection = connectionById(project, connectionId);
	if (!connection) return connectionId;
	const name = (id: string) => componentById(project, id)?.name ?? id;
	return `${name(connection.fromComponentId)} → ${name(connection.toComponentId)}`;
}

/**
 * A user in words: "Pipe 2 of Tank → Pump", "Gate valve V1", "Fitting 3 (90° elbow, long radius)
 * of Tank → Pump", "Scenario Winter, change 2".
 */
export function userLabel(
	project: Project,
	user: LibraryUser,
	fittingName: (type: string) => string = fittingFallbackName
): string {
	switch (user.kind) {
		case 'pipe':
			return `Pipe ${user.pipeIndex + 1} of ${pipingName(project, user.connectionId)}`;
		case 'valve':
			return componentById(project, user.componentId)?.name ?? user.componentId;
		case 'fitting': {
			const type = connectionById(project, user.connectionId)?.piping.fittings[user.fittingIndex]
				?.type;
			const what = type ? ` (${fittingName(type)})` : '';
			return `Fitting ${user.fittingIndex + 1}${what} of ${pipingName(project, user.connectionId)}`;
		}
		case 'scenario': {
			const scenario = project.scenarios?.find((s) => s.id === user.scenarioId);
			return `Scenario ${scenario?.name ?? user.scenarioId}, change ${user.changeIndex + 1}`;
		}
	}
}

// ---------------------------------------------------------------------------------------------
// Rules
// ---------------------------------------------------------------------------------------------

/** "inner diameter", "reference diameter": a field of an entry in a sentence. */
const FIELD_WORDS: Readonly<Record<string, string>> = {
	innerDiameter: 'inner diameter',
	outerDiameter: 'outer diameter',
	nominalSize: 'nominal size',
	referenceDiameter: 'reference diameter',
	materialId: 'material',
	roughness: 'roughness'
};

function fieldWords(field: string): string {
	return FIELD_WORDS[field] ?? humanize(field).toLowerCase();
}

function words(fields: readonly string[]): string {
	const list = fields.map(fieldWords);
	return list.length < 2
		? (list[0] ?? '')
		: `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`;
}

function orderWords(pairs: readonly OrderedFields[]): string[] {
	return pairs.map(
		(p) =>
			`its ${fieldWords(p.lower)} must be ${p.strict ? 'below' : 'at most'} its ${fieldWords(p.upper)}`
	);
}

/**
 * The API's model rules a pipe spec breaks (`x-fields-by-value`: a custom spec states its
 * roughness; `x-ordered-fields`: its inner diameter below its outer), in words, naming fields only;
 * none when it keeps them. Bounds and required fields are the schema's (validate.ts).
 */
export function pipeSpecRuleProblems(spec: PipeSpec): string[] {
	const problems: string[] = [];
	const rule = byValueViolations(spec, 'PipeSpec');
	if (rule.missing.length) {
		const what = rule.value === CUSTOM_MATERIAL_ID ? 'a custom pipe spec' : 'this pipe spec';
		problems.push(`${what} needs its ${words(rule.missing)}`);
	}
	if (rule.extra.length) problems.push(`this pipe spec takes no ${words(rule.extra)}`);
	problems.push(...orderWords(schemaOrderViolations(spec, 'PipeSpec')));
	return problems;
}

/**
 * The API's model rules a resistance entry breaks (`x-fields-by-value`: a K states the bore it is
 * stated at; a Cv or Kv takes none), in words; none when it keeps them.
 */
export function resistanceSpecRuleProblems(entry: ResistanceSpec): string[] {
	const problems: string[] = [];
	const rule = byValueViolations(entry, 'ResistanceSpec');
	if (rule.missing.length) {
		problems.push(
			`a ${rule.value} entry needs its ${words(rule.missing)} (a K is stated at a bore)`
		);
	}
	if (rule.extra.length) {
		problems.push(`a ${rule.value} entry takes no ${words(rule.extra)} (it needs no bore)`);
	}
	problems.push(...orderWords(schemaOrderViolations(entry, 'ResistanceSpec')));
	return problems;
}

/** A resistance entry as a form holds it: its value may not be entered yet. */
export type ResistanceDraft = Omit<ResistanceSpec, 'value'> & { value?: number };

/**
 * A resistance entry as the form keeps it when its kind changes: the kind set, the value kept
 * only within the same kind (a Cv is not a K), and the reference diameter kept for a K only (a Cv
 * or Kv takes none). Its id, name and source stay.
 */
export function withResistanceKind(
	entry: ResistanceDraft,
	kind: ResistanceSpec['kind']
): ResistanceDraft {
	if (kind === entry.kind) return { ...entry };
	return { id: entry.id, name: entry.name, source: entry.source, kind };
}

// ---------------------------------------------------------------------------------------------
// Edits
// ---------------------------------------------------------------------------------------------

function sentence(problems: readonly string[]): string {
	const text = problems.join('; ');
	return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
}

/**
 * Add a pipe spec to the project library, or replace the one with its id (every pipe that refers
 * to it then takes its new values). A new spec's id must not be in use (usedIds: elements, pump
 * curves and both lists); one that breaks the published rules is refused (pipeSpecRuleProblems).
 */
export function setPipeSpec(project: Project, spec: PipeSpec): Project {
	const specs = pipeSpecs(project);
	const index = specs.findIndex((s) => s.id === spec.id);
	if (index === -1 && usedIds(project).has(spec.id)) {
		throw new EditError(`The id "${spec.id}" is already used in this project.`);
	}
	const problems = pipeSpecRuleProblems(spec);
	if (problems.length) throw new EditError(sentence(problems));
	const next = index === -1 ? [...specs, spec] : specs.map((s, i) => (i === index ? spec : s));
	return withPipeLibrary(project, next);
}

/**
 * Add a resistance entry to the project library, or replace the one with its id (every valve and
 * fitting that refers to it then takes its new coefficient, a change of kind included). The same
 * id and rule refusals as setPipeSpec.
 */
export function setResistanceSpec(project: Project, entry: ResistanceSpec): Project {
	const entries = resistanceEntries(project);
	const index = entries.findIndex((e) => e.id === entry.id);
	if (index === -1 && usedIds(project).has(entry.id)) {
		throw new EditError(`The id "${entry.id}" is already used in this project.`);
	}
	const problems = resistanceSpecRuleProblems(entry);
	if (problems.length) throw new EditError(sentence(problems));
	const next =
		index === -1 ? [...entries, entry] : entries.map((e, i) => (i === index ? entry : e));
	return withResistanceLibrary(project, next);
}

/** Why an entry cannot be removed: its first user ("Pipe 2 of Tank → Pump uses this spec."). */
function inUse(project: Project, users: readonly LibraryUser[], what: string): never {
	const first = users[0] as LibraryUser;
	const more = users.length > 1 ? ` (and ${users.length - 1} more)` : '';
	throw new EditError(`${userLabel(project, first)}${more} uses this ${what}.`);
}

/**
 * Remove a pipe spec that nothing refers to: no pipe and no scenario's change (refused, naming the
 * first user, as removePumpCurve). Removing the last spec removes the list.
 */
export function removePipeSpec(project: Project, specId: string): Project {
	if (!pipeSpecOf(project, specId)) throw new EditError(`There is no pipe spec "${specId}".`);
	const users = pipeSpecUsers(project, specId);
	if (users.length) inUse(project, users, 'spec');
	return withPipeLibrary(
		project,
		pipeSpecs(project).filter((s) => s.id !== specId)
	);
}

/** Remove a resistance entry that nothing refers to (valves, fittings, scenarios' changes). */
export function removeResistanceSpec(project: Project, entryId: string): Project {
	if (!resistanceEntryOf(project, entryId)) {
		throw new EditError(`There is no resistance entry "${entryId}".`);
	}
	const users = resistanceUsers(project, entryId);
	if (users.length) inUse(project, users, 'entry');
	return withResistanceLibrary(
		project,
		resistanceEntries(project).filter((e) => e.id !== entryId)
	);
}

/**
 * Which pipes "Use this spec for…" reaches (proposal §6.2), from the pipe `pipeIndex` of
 * connection `connectionId`: that pipe; every pipe of the project of the same size and material
 * (samePipeKind: its material, schedule, nominal size and overrides, or the same spec); or every
 * pipe of that connection.
 */
export interface PipeSpecScope {
	kind: 'pipe' | 'same' | 'connection';
	connectionId: string;
	pipeIndex: number;
}

/** The pipes a scope reaches, in project order (EditError when its pipe does not exist). */
export function pipeSpecScope(
	project: Project,
	scope: PipeSpecScope
): { connectionId: string; pipeIndex: number }[] {
	const connection = connectionById(project, scope.connectionId);
	const seed = connection?.piping.pipes[scope.pipeIndex];
	if (!connection || !seed) {
		throw new EditError(
			`There is no pipe ${scope.pipeIndex + 1} in connection "${scope.connectionId}".`
		);
	}
	if (scope.kind === 'pipe') return [{ connectionId: connection.id, pipeIndex: scope.pipeIndex }];
	if (scope.kind === 'connection') {
		return connection.piping.pipes.map((_, pipeIndex) => ({
			connectionId: connection.id,
			pipeIndex
		}));
	}
	return project.connections.flatMap((c) =>
		c.piping.pipes.flatMap((pipe, pipeIndex) =>
			samePipeKind(pipe, seed) ? [{ connectionId: c.id, pipeIndex }] : []
		)
	);
}

/**
 * The project with pipe spec `specId` used for every pipe `scope` reaches, each keeping its length
 * (the store's update makes it one undo step), and how many pipes changed (a pipe that refers to
 * the spec already is left as it is). Each pipe stays the same pipe (identity.ts), so scenario
 * changes and the last solve's results stay on it. Refused for a spec the project does not have.
 */
export function applyPipeSpec(
	project: Project,
	specId: string,
	scope: PipeSpecScope
): { project: Project; count: number } {
	if (!pipeSpecOf(project, specId)) throw new EditError(`There is no pipe spec "${specId}".`);
	const reached = new Set(
		pipeSpecScope(project, scope).map((p) => `${p.connectionId}\u0000${p.pipeIndex}`)
	);
	let count = 0;
	const connections = project.connections.map((connection) => {
		let changed = false;
		const pipes = connection.piping.pipes.map((pipe, i) => {
			if (!reached.has(`${connection.id}\u0000${i}`) || pipe.specId === specId) return pipe;
			const next = withSpec(pipe, specId);
			markCopy(next, pipe);
			changed = true;
			count++;
			return next;
		});
		return changed ? { ...connection, piping: { ...connection.piping, pipes } } : connection;
	});
	return { project: count ? { ...project, connections } : project, count };
}

/**
 * The project with a valve's resistance set: a coefficient as entered, a reference to a
 * resistance entry ({kind: 'library', id}, which the project must have), or none (null: the
 * solver's default). Refused for a component that is not a valve.
 */
export function setValveResistance(
	project: Project,
	componentId: string,
	resistance: ValveResistance | null
): Project {
	const component = componentById(project, componentId);
	if (component?.type !== 'valve') {
		throw new EditError(`"${componentId}" is not a valve: it has no resistance.`);
	}
	if (isResistanceRef(resistance) && !resistanceEntryOf(project, resistance.id)) {
		throw new EditError(`There is no resistance entry "${resistance.id}".`);
	}
	return updateComponent(project, componentId, (c) => {
		const valve = { ...c } as Extract<Component, { type: 'valve' }>;
		if (resistance === null) delete valve.resistance;
		else valve.resistance = structuredClone(resistance);
		return valve;
	});
}

/**
 * The piping with fitting `index` taking its K from resistance entry `entryId` (its kOverride
 * removed: never both), or, with null, from neither (its correlation, or none for a custom
 * fitting until a K is entered). Pure, as utils/piping.ts.
 */
export function setFittingResistance(
	piping: PipingSegment,
	index: number,
	entryId: string | null
): PipingSegment {
	const fitting = piping.fittings[index];
	if (!fitting) return piping;
	const next = { ...fitting };
	delete next.kOverride;
	if (entryId === null) delete next.resistanceId;
	else next.resistanceId = entryId;
	return { ...piping, fittings: piping.fittings.map((f, i) => (i === index ? next : f)) };
}
