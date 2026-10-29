/**
 * What every part of an export reads (proposal export.md §2.1–§2.4): the exported cases with their
 * values decided once (`hasValues`, `stale`), the projects their names and structure come from,
 * the file's units, and the words every sheet and row uses for a case and its state.
 *
 * Names and structure (decision 8): a case whose results are current is named from the current
 * project (its fingerprint guarantees the same ids and kinds); an out-of-date case from the project
 * as sent for its solve (a deleted element's id may since have been re-used). Structure always
 * comes from the case as solved: connection endpoints (so the flow sign), ports, kinds, pipe specs,
 * fitting positions and valve types.
 */
import type {
	Component,
	PipeConnection,
	Project,
	PumpResult,
	SolvedState,
	SolveResponse,
	SystemCurveResponse
} from '../../api/types';
import type { SystemCurveState } from '../../state/project.svelte';
import { CASE_STATUS_LABELS, fittingFallbackName, portLabel } from '../labels';
import { scenariosOf } from '../scenarios';
import { localIso } from './filename';
import type { ExportCase, ExportInput, SheetSpec } from './model';
import { ExportUnitSystem } from './units';

/** One exported case, with what the file holds of it. */
export interface CaseView {
	input: ExportCase;
	response: SolveResponse | null;
	solved: SolvedState | null;
	/** Its response converged: its values are a solution (Compare's rule). */
	hasValues: boolean;
	/** Its response is out of date. */
	stale: boolean;
	/** The project its names come from: current, or as sent (out of date). */
	names: Project;
	/** The case as solved: endpoints, ports, kinds, pipes, fittings, valve types. */
	structure: Project;
	/** "Base case", or "Winter (S2)". */
	label: string;
}

export interface ExportContext {
	input: ExportInput;
	units: ExportUnitSystem;
	hasScenarios: boolean;
	/** A one-case file (the case shown, or a project without scenarios). */
	single: boolean;
	cases: readonly CaseView[];
	/** The cases with a response (flags, scenario changes, methods). */
	responded: readonly CaseView[];
	/** The cases with values (every element table). */
	valued: readonly CaseView[];
	fittingName: (type: string) => string;
	materialName: (id: string) => string | undefined;
}

/** A project's components and connections by id (projects are never mutated: the store freezes them). */
const indexes = new WeakMap<
	Project,
	{ components: Map<string, Component>; connections: Map<string, PipeConnection> }
>();

function indexOf(project: Project) {
	let index = indexes.get(project);
	if (!index) {
		index = {
			components: new Map(project.components.map((c) => [c.id, c])),
			connections: new Map(project.connections.map((c) => [c.id, c]))
		};
		indexes.set(project, index);
	}
	return index;
}

/** componentById, by an index (a large export looks up thousands of rows). */
export function componentById(project: Project, id: string): Component | undefined {
	return indexOf(project).components.get(id);
}

/** connectionById, by an index. */
export function connectionById(project: Project, id: string): PipeConnection | undefined {
	return indexOf(project).connections.get(id);
}

/** "Base case", or "Winter (S2)". */
export function caseLabel(c: Pick<ExportCase, 'id' | 'name'>): string {
	return c.id === null ? 'Base case' : `${c.name} (${c.id})`;
}

export function exportContext(input: ExportInput): ExportContext {
	const hasScenarios = scenariosOf(input.project).length > 0;
	const cases = input.cases.map((c): CaseView => {
		const response = c.response;
		const hasValues = !!response && response.success && response.solvedState.converged;
		const stale = !!response && c.stale;
		const names = stale ? (c.sent ?? input.project) : input.project;
		return {
			input: c,
			response,
			solved: response?.solvedState ?? null,
			hasValues,
			stale,
			names,
			structure: c.inputs ?? c.sent ?? names,
			label: caseLabel(c)
		};
	});
	return {
		input,
		units: new ExportUnitSystem(input.options.units, input.prefs),
		hasScenarios,
		single: input.options.cases === 'shown' || !hasScenarios,
		cases,
		responded: cases.filter((c) => c.response),
		valued: cases.filter((c) => c.hasValues),
		fittingName: (type) => input.library.fittings[type] ?? fittingFallbackName(type),
		materialName: (id) => input.library.materials[id]
	};
}

/** A row's state (decision 28): Current, Out of date, Did not converge (, out of date). */
export function resultsWord(c: CaseView): string {
	if (c.hasValues) return c.stale ? 'Out of date' : 'Current';
	return c.stale ? 'Did not converge, out of date' : 'Did not converge';
}

/** A component's name in a case (its names project), else its id. */
export function componentName(c: CaseView, id: string): string {
	return componentById(c.names, id)?.name ?? id;
}

/** "From → To" of a connection, endpoints as solved, named as the case is; else its id. */
export function connectionLabel(c: CaseView, id: string): string {
	const connection = connectionById(c.structure, id) ?? connectionById(c.names, id);
	if (!connection) return id;
	return `${componentName(c, connection.fromComponentId)} → ${componentName(c, connection.toComponentId)}`;
}

/** An element's name in a case: a component, a port ("Discharge of Transfer pump"), a connection. */
export function elementLabel(c: CaseView, id: string): string {
	if (componentById(c.names, id) || componentById(c.structure, id)) return componentName(c, id);
	if (connectionById(c.structure, id) || connectionById(c.names, id)) return connectionLabel(c, id);
	const [componentId = '', portId] = id.split(':');
	if (
		portId !== undefined &&
		(componentById(c.names, componentId) || componentById(c.structure, componentId))
	) {
		return `${portLabel(portId)} of ${componentName(c, componentId)}`;
	}
	return id;
}

/** The sheet caption's case part (XLSX A1, §3.2). */
function casePart(ctx: ExportContext, c: CaseView | undefined): string {
	const parts: string[] = [];
	if (!c) return '';
	if (ctx.hasScenarios) parts.push(c.label);
	if (c.solved) {
		parts.push(`solved ${c.solved.timestamp}`, `calculation methods ${c.solved.methodVersion}`);
	} else {
		parts.push(`no results in this file: ${CASE_STATUS_LABELS[c.input.status]}`);
	}
	return parts.join(' — ');
}

const MESSAGE_SHEETS = new Set(['flags', 'methods']);
const SI_REPORTED: Readonly<Record<string, string>> = {
	trace: ' — SI, as reported',
	methods: ' — SI, as reported',
	flags: ' — the server’s messages and the details in SI, as reported'
};

/**
 * The Goal seek sheet's caption tail: the case it ran on (with scenarios), its run time and its
 * methods version, and its own staleness. A goal seek is its own set of solves, so it never names
 * the exported case's solve or that solve's staleness (review V3).
 */
function goalSeekPart(ctx: ExportContext): string | null {
	const gs = ctx.input.goalSeek;
	if (gs?.status !== 'done' || !gs.response) return null;
	const c = ctx.cases.find((x) => x.input.id === gs.run.caseId);
	const parts = [
		...(ctx.hasScenarios && c ? [c.label] : []),
		`goal seek run ${localIso(gs.run.startedAt, ctx.input.utcOffsetMinutes)}`,
		`calculation methods ${gs.response.result.methodVersion}`
	];
	let text = parts.join(' — ');
	if (gs.stale) text += ' — OUT OF DATE: the project changed after this goal seek';
	return text;
}

/**
 * Where an All cases sheet says each case's solve is: its rows' Case, Solved at and Results
 * columns, or, for the sheets without them, About's case blocks and Compare's first two rows.
 */
const ALL_CASES_SOLVE: Readonly<Record<string, string>> = {
	about: "each case's solve and state: its Case block in this sheet",
	'compare-cases': "each case's solve and state: the Status and Solved at rows"
};

/** Row 1 of a sheet (§3.2): sheet, project, case and solve, and the states that matter. */
export function caption(ctx: ExportContext, sheet: Pick<SheetSpec, 'id' | 'title'>): string {
	const parts = [sheet.title, ctx.input.project.metadata.name];
	let text: string;
	const goalSeek = sheet.id === 'goal-seek' ? goalSeekPart(ctx) : null;
	if (goalSeek) {
		text = [...parts, goalSeek].join(' — ');
	} else if (ctx.single) {
		const c = ctx.cases[0];
		const tail = casePart(ctx, c);
		text = [...parts, ...(tail ? [tail] : [])].join(' — ');
		if (c?.stale) text += ' — OUT OF DATE: the project changed after this solve';
		if (c?.response && !c.hasValues && MESSAGE_SHEETS.has(sheet.id)) {
			text += ' — DID NOT CONVERGE: not a solution';
		}
	} else {
		// All cases: only with scenarios (a project without them is always a one-case file).
		const where =
			ALL_CASES_SOLVE[sheet.id] ?? "each row's case and solve: Case, Solved at, Results";
		text = [...parts, `all cases (${where})`].join(' — ');
		if (ctx.cases.some((c) => c.stale)) text += ' — includes out-of-date results';
		if (MESSAGE_SHEETS.has(sheet.id) && ctx.responded.some((c) => !c.hasValues)) {
			text += ' — includes a solve that did not converge';
		}
	}
	if (ctx.units.units === 'si') text += ' — SI base units';
	return text + (SI_REPORTED[sheet.id] ?? '');
}

/** Why a case's values are not in the file (null: they are). */
export function noValuesReason(c: CaseView): string | null {
	if (c.hasValues) return null;
	if (c.response) {
		return `the solve did not converge${c.stale ? ' (and the project changed after it)' : ''}: its values are not a solution of the network. Its convergence report, flags and methods are in the file`;
	}
	const status = c.input.status;
	if (status === 'failed') {
		return `the latest solve failed${c.input.error ? ` (${c.input.error})` : ''}; results kept from an earlier version of the project are not used`;
	}
	if (status === 'not_reached')
		return 'not solved: the Solve all run stopped after a network error';
	if (status === 'cancelled') return 'the solve was cancelled';
	if (status === 'not_solved') return 'not solved';
	return CASE_STATUS_LABELS[status].toLowerCase();
}

/** The dialog's warnings for the cases exported (§5.3), from `hasValues` and `stale`. */
export function warnings(ctx: ExportContext) {
	const list: { kind: 'not_converged' | 'stale' | 'failed_shown'; text: string }[] = [];
	const failed = ctx.responded.filter((c) => !c.hasValues);
	const stale = ctx.valued.filter((c) => c.stale);
	if (ctx.single) {
		const c = failed[0];
		if (c) {
			list.push({
				kind: 'not_converged',
				text: `This ${c.stale ? 'out-of-date ' : ''}solve did not converge: its values are not a solution of the network. The file holds its convergence report, flags and methods, but no values.`
			});
		}
	} else if (failed.length) {
		const n = failed.length;
		list.push({
			kind: 'not_converged',
			text: `${n} case${n === 1 ? '' : 's'} did not converge${failed.some((c) => c.stale) ? ' (out of date included)' : ''}: the file lists ${n === 1 ? 'it' : 'them'} without values.`
		});
	}
	if (stale.length) {
		// The link only when the file holds one (review V5).
		const holds = ctx.input.options.link
			? 'the results, names and link of the project as it was solved'
			: 'the results and names of the project as it was solved (the project link was left out)';
		const tail = `The file holds ${holds}, and says so in every row. Solve again for current results.`;
		list.push({
			kind: 'stale',
			text: ctx.single
				? `The project changed after this solve. ${tail}`
				: `${stale.map((c) => c.label).join(', ')}: the project changed after ${stale.length === 1 ? 'this solve' : 'these solves'}. ${tail}`
		});
	}
	const shown = ctx.cases.find((c) => c.input.id === ctx.input.shownCase);
	if (shown && shown.input.status === 'failed' && shown.input.keptResponse) {
		list.push({
			kind: 'failed_shown',
			text: 'The latest solve failed. The results shown below the error are from an earlier version of the project and are not in the file.'
		});
	}
	return list;
}

/**
 * Component ids of `keys` in project order, then the ids no longer in the project, in key order:
 * the screen tables' order (results.ts).
 */
export function orderedIds(project: Project, keys: readonly string[]): string[] {
	const wanted = new Set(keys);
	const known = project.components.map((c) => c.id).filter((id) => wanted.has(id));
	const seen = new Set(known);
	return [...known, ...keys.filter((k) => !seen.has(k))];
}

/** Connection ids of `keys` in project order, then the others, in key order. */
export function orderedConnections(project: Project, keys: readonly string[]): string[] {
	const wanted = new Set(keys);
	const known = project.connections.map((c) => c.id).filter((id) => wanted.has(id));
	const seen = new Set(known);
	return [...known, ...keys.filter((k) => !seen.has(k))];
}

/** The system-curve key's pump and range (the store's curveKey: pump id, or id NUL min NUL max). */
export function parseCurveKey(key: string): { pumpId: string; range: [number, number] | null } {
	const [pumpId = '', min, max] = key.split('\u0000');
	return { pumpId, range: min === undefined ? null : [Number(min), Number(max)] };
}

/** A ready system curve of a case: its pump, its range key (null: the default range). */
export interface ReadyCurve {
	pumpId: string;
	range: [number, number] | null;
	result: PumpResult;
	curve: SystemCurveResponse;
}

/**
 * The computed (ready) system curves of a case, by pump in table order: the default range first,
 * then the overlay ranges (drawn with another case's chart) by flow. The System curves sheet
 * writes exactly these, and About and the dialog say what is left out from them, so the file's
 * record of its curves is its contents (review V1).
 */
export function readyCurves(c: CaseView): ReadyCurve[] {
	const solved = c.solved;
	if (!solved) return [];
	const entries = Object.entries(c.input.systemCurves)
		.map(([key, state]) => ({ ...parseCurveKey(key), state }))
		.filter(
			(
				e
			): e is {
				pumpId: string;
				range: [number, number] | null;
				state: Extract<SystemCurveState, { status: 'ready' }>;
			} => e.state.status === 'ready' && !!solved.pumpResults[e.pumpId]
		);
	const out: ReadyCurve[] = [];
	for (const pumpId of orderedIds(c.structure, Object.keys(solved.pumpResults))) {
		const own = entries
			.filter((e) => e.pumpId === pumpId)
			.sort((a, b) =>
				!a.range ? -1 : !b.range ? 1 : a.range[0] - b.range[0] || a.range[1] - b.range[1]
			);
		for (const e of own) {
			out.push({
				pumpId,
				range: e.range,
				result: solved.pumpResults[pumpId]!,
				curve: e.state.curve
			});
		}
	}
	return out;
}

/** Why a pump's default-range curve is not in the file (its state in the case's slot). */
function curveReason(state: SystemCurveState | undefined): string {
	return !state
		? 'not computed: open the pump’s chart to compute it'
		: state.status === 'loading'
			? 'being computed when exported'
			: state.status === 'error'
				? `failed: ${state.message}`
				: 'cancelled';
}

/** The system curves of a case that are not in the file (no ready curve at all), by pump. */
export function curvesLeftOut(c: CaseView): { pumpId: string; reason: string }[] {
	if (!c.solved) return [];
	const included = new Set(readyCurves(c).map((r) => r.pumpId));
	return orderedIds(c.structure, Object.keys(c.solved.pumpResults))
		.filter((pumpId) => !included.has(pumpId))
		.map((pumpId) => ({ pumpId, reason: curveReason(c.input.systemCurves[pumpId]) }));
}

/**
 * The pumps whose curves are in the file over overlay ranges only (another case's chart drew them
 * for comparison), with why their default range is not.
 */
export function curvesOverlayOnly(c: CaseView): { pumpId: string; reason: string }[] {
	const ready = readyCurves(c);
	const pumps = [...new Set(ready.map((r) => r.pumpId))];
	return pumps
		.filter((pumpId) => !ready.some((r) => r.pumpId === pumpId && !r.range))
		.map((pumpId) => ({ pumpId, reason: curveReason(c.input.systemCurves[pumpId]) }));
}

/**
 * What a pump group's curves are listed as when left out of an export: its group curve and its
 * group system curve (CLAUDE.md D21, slices 4a and 4b; slice 4c exports them).
 */
export const GROUP_CURVES_ITEM = 'Group curves and group system curves';

/** Why group curves are not in an export (CLAUDE.md D21, proposal pump-groups.md §6.6). */
export const GROUP_CURVES_LEFT_OUT =
	'not exported in this version: the Pumps together card under the pump chart draws them on request, and its Download image saves its chart';

/**
 * A case of the file has two or more pumps with results: the Pumps together card can show
 * them, so About and the dialog say its group curves are left out.
 */
export function groupCurvesLeftOut(ctx: ExportContext): boolean {
	return ctx.valued.some((c) => Object.keys(c.solved?.pumpResults ?? {}).length >= 2);
}

/** What the dialog lists as left out (§5.3 item 6). */
export function omitted(ctx: ExportContext): { what: string; reason: string }[] {
	const list: { what: string; reason: string }[] = [];
	const named = (c: CaseView, what: string) => (ctx.hasScenarios ? `${what} (${c.label})` : what);
	for (const c of ctx.cases) {
		const reason = noValuesReason(c);
		if (reason) list.push({ what: named(c, 'Values'), reason });
	}
	for (const c of ctx.valued) {
		for (const { pumpId, reason } of curvesLeftOut(c)) {
			list.push({ what: named(c, `System curve of ${componentName(c, pumpId)}`), reason });
		}
	}
	if (groupCurvesLeftOut(ctx))
		list.push({ what: GROUP_CURVES_ITEM, reason: GROUP_CURVES_LEFT_OUT });
	if (!ctx.single) {
		list.push({
			what: 'Trace',
			reason: 'in single-case exports only: export one case to include it'
		});
	}
	const gs = ctx.input.goalSeek;
	if (gs?.status === 'done' && gs.response && ctx.cases.some((c) => c.input.id === gs.run.caseId)) {
		list.push({
			what: 'Goal seek',
			reason: 'the report only. To export full results at the values found, apply them and solve.'
		});
	}
	if (!ctx.input.options.link)
		list.push({ what: 'Project link', reason: 'left out when exported' });
	return list;
}
