/**
 * The tables of an export (proposal export.md §2.2, §2.6), as rows built on the fly.
 *
 * Contract: one value per cell; every number is the API's double converted by `fromSI` to the
 * file's units, never rounded (Compare's differences are the only values computed: `value − base`
 * and its relative form, as the screen computes them); a null is an empty cell; booleans are
 * booleans; every row carries the API's ids and the names of its case (context.ts); words are the
 * app's labels; rows follow the screen tables' order (components, then their ports, in project
 * order; connections in project order; then ids no longer in the project). Every table starts with
 * `Case id` and `Case` in a project with scenarios, then `Solved at` and `Results` (decision 28),
 * so a row read alone still names its solve and its state.
 */
import type {
	BoundaryResult,
	EquipmentRating,
	Flag,
	OverrideResult,
	Project
} from '../../api/types';
import {
	compareCells,
	compareValue,
	ENDS_NOTE,
	PIPES_NOTE,
	QUANTITIES,
	REVERSED_NOTE,
	rowLabel,
	type CompareColumn
} from '../compare';
import { canonicalJson } from '../json';
import {
	CASE_STATUS_LABELS,
	humanize,
	kindLabel,
	LOSS_MODEL_LABELS,
	npsLabel,
	portLabel,
	PUMP_CONTROL_MODE_NAMES,
	PUMP_CONTROL_STATE_LABELS
} from '../labels';
import { flagText } from '../flag-text';
import {
	CHECK_CATEGORIES,
	CHECK_TITLES,
	checkText,
	groupChecks,
	OUTCOME_TITLES,
	sourceLabel
} from '../design-checks';
import { DIRECTION_NAMES, flowDirection } from '../assigned-flow';
import { pumpChartData } from '../pump-chart';
import { TAP_LABELS } from '../orifice';
import { entryFor, unitOf } from '../field-registry';
import { componentSchemaName, RELIEF_DATA } from '../model-rules';
import {
	asmeRuleWords,
	capacityGivenBy,
	letterArea,
	OVERPRESSURE_SOURCE_LABELS,
	reliefStateLabel
} from '../relief';
import {
	boundaryTable,
	branchPatternLabel,
	orificeCoefficientSource,
	branchVelocityBasis,
	fittingFlags,
	flagsForElement,
	groupFlags,
	pumpStatusLabel,
	regimeLabel,
	RELIEF_NO_RESULT,
	segmentFlags,
	SEVERITY_LABELS,
	valveStateLabel,
	valveTypeLabel
} from '../results';
import {
	changeFieldLabel,
	changeTargetLabel,
	changeValueText,
	ISO_COEFFICIENT_TEXT
} from '../scenarios';
import { CUSTOM_MATERIAL_ID } from '../piping';
import {
	isResistanceRef,
	pipeSpecOf,
	pipeSpecs,
	pipeSpecUsers,
	resistanceEntries,
	resistanceEntryOf,
	resistanceUsers,
	type LibraryUser
} from '../project-library';
import type { LabelOptions, UnitCategory } from '../units';
import {
	componentById,
	componentName,
	connectionById,
	connectionLabel,
	elementLabel,
	orderedConnections,
	orderedIds,
	readyCurves,
	resultsWord,
	type CaseView,
	type ExportContext
} from './context';
import type { CellValue, ExportColumn, SheetSpec } from './model';

export const text = (label: string): ExportColumn => ({ label, kind: 'text' });
export const bool = (label: string): ExportColumn => ({ label, kind: 'boolean' });
export const json = (label: string): ExportColumn => ({ label, kind: 'json' });
export function number(label: string, unit = ''): ExportColumn {
	return unit ? { label, unit, kind: 'number' } : { label, kind: 'number' };
}

/** A number column in the file's unit of `category`. */
function quantity(
	ctx: ExportContext,
	label: string,
	category: UnitCategory,
	options: LabelOptions = {}
): ExportColumn {
	return number(label, ctx.units.label(category, options));
}

/** The leading columns of every table: Case id, Case (with scenarios), Solved at, Results. */
export function caseColumns(ctx: ExportContext): ExportColumn[] {
	return [
		...(ctx.hasScenarios ? [text('Case id'), text('Case')] : []),
		text('Solved at'),
		text('Results')
	];
}

/** A case's leading cells. */
export function casePrefix(ctx: ExportContext, c: CaseView): CellValue[] {
	return [
		...(ctx.hasScenarios ? [c.input.id, c.input.name] : []),
		c.solved?.timestamp ?? null,
		resultsWord(c)
	];
}

/** Flag codes joined by "; " (empty for none). */
function codes(flags: readonly Flag[]): string | null {
	return flags.length ? flags.map((f) => f.code).join('; ') : null;
}

/** A 0-based index in a flag's details, as the 1-based number the app shows. */
function detailNumber(flag: Flag, key: string): number | null {
	const value = flag.details[key];
	return typeof value === 'number' && Number.isInteger(value) ? value + 1 : null;
}

/** A table: its rows, case by case, and their count. */
function table(
	ctx: ExportContext,
	id: string,
	title: string,
	columns: ExportColumn[],
	cases: readonly CaseView[],
	count: (c: CaseView) => number,
	rows: (c: CaseView) => Iterable<CellValue[]>
): SheetSpec {
	return {
		id,
		title,
		file: `${id}.csv`,
		kind: 'table',
		columns: [...caseColumns(ctx), ...columns],
		rowCount: cases.reduce((n, c) => n + count(c), 0),
		*rows() {
			for (const c of cases) {
				const prefix = casePrefix(ctx, c);
				for (const row of rows(c)) yield [...prefix, ...row];
			}
		}
	};
}

const ELEMENT_KINDS = { component: 'Component', connection: 'Connection', network: 'Network' };

/** Flags: one row per flag of every case with a response, invalid first (§2.6). */
export function flagsTable(ctx: ExportContext): SheetSpec {
	const prefs = ctx.units.prefs;
	return table(
		ctx,
		'flags',
		'Flags',
		[
			text('Severity'),
			text('Code'),
			text('Element kind'),
			text('Element id'),
			text('Element'),
			text('Port id'),
			text('Port'),
			number('Pipe #'),
			number('Fitting #'),
			text('Message'),
			text('Message (as reported, SI)'),
			json('Details (SI, JSON)')
		],
		ctx.responded,
		(c) => c.solved?.flags.length ?? 0,
		function* (c) {
			const solved = c.solved;
			if (!solved) return;
			const valveTypes = Object.fromEntries(
				Object.entries(solved.valveResults).map(([id, v]) => [id, v.valveType])
			);
			const context = { project: c.names, prefs, fittingName: ctx.fittingName, valveTypes };
			for (const group of groupFlags(solved.flags)) {
				for (const flag of group.flags) {
					const kind = flag.componentId
						? 'component'
						: flag.connectionId
							? 'connection'
							: 'network';
					const id = flag.componentId ?? flag.connectionId ?? null;
					yield [
						SEVERITY_LABELS[flag.severity] ?? humanize(flag.severity),
						flag.code,
						ELEMENT_KINDS[kind],
						id,
						kind === 'component'
							? componentName(c, id as string)
							: kind === 'connection'
								? connectionLabel(c, id as string)
								: null,
						flag.portId,
						flag.portId ? portLabel(flag.portId) : null,
						detailNumber(flag, 'segmentIndex'),
						detailNumber(flag, 'fittingIndex'),
						flagText(flag, context),
						flag.message,
						canonicalJson(flag.details)
					];
				}
			}
		}
	);
}

/**
 * Design checks (CLAUDE.md D19): one row per check result of every case with values, in the
 * screen's order (not met, met, not evaluated). A check's value and limits are in its own
 * quantity, so the row says which (Unit); the words are the screen's, in the file's units but
 * with fractions in % and powers in kW (hp with gpm), as the app's sentences give them, and
 * the server's message (SI) and source are kept as reported. Design practice, not flags.
 */
export function designChecksTable(ctx: ExportContext): SheetSpec {
	const u = ctx.units;
	return table(
		ctx,
		'design-checks',
		'Design checks',
		[
			text('Outcome'),
			text('Check'),
			text('Element kind'),
			text('Element id'),
			text('Element'),
			number('Pipe #'),
			text('Pipes outside #'),
			number('Value'),
			number('Lower limit'),
			number('Upper limit'),
			text('Unit'),
			text('Limits from'),
			text('Result'),
			text('Message (as reported, SI)'),
			text('Limits from (as reported)')
		],
		ctx.valued,
		(c) => c.solved?.designChecks?.length ?? 0,
		function* (c) {
			const results = c.solved?.designChecks ?? [];
			for (const group of groupChecks(results)) {
				for (const r of group.results) {
					const category = CHECK_CATEGORIES[r.check];
					const kind = r.componentId ? 'component' : 'connection';
					const id = r.componentId ?? r.connectionId ?? null;
					const pipes = r.check === 'pipe_velocity';
					yield [
						OUTCOME_TITLES[r.outcome],
						CHECK_TITLES[r.check],
						ELEMENT_KINDS[kind],
						id,
						id === null
							? null
							: kind === 'component'
								? componentName(c, id)
								: connectionLabel(c, id),
						pipes && r.pipeIndex !== null && r.pipeIndex !== undefined ? r.pipeIndex + 1 : null,
						pipes && r.pipesOutside?.length ? r.pipesOutside.map((i) => i + 1).join('; ') : null,
						u.value(r.value, category),
						u.value(r.limits.min, category),
						u.value(r.limits.max, category),
						u.label(category) || null,
						sourceLabel(r.source),
						checkText(r, u.prefs),
						r.message,
						r.source
					];
				}
			}
		}
	);
}

/** The node-result keys of a case in the screen's order: components and their ports, then the rest. */
function nodeKeys(c: CaseView): string[] {
	const results = c.solved?.nodeResults ?? {};
	const keys: string[] = [];
	const seen = new Set<string>();
	for (const component of c.structure.components) {
		for (const port of component.ports) {
			const key = `${component.id}:${port.id}`;
			if (results[key]) {
				keys.push(key);
				seen.add(key);
			}
		}
	}
	for (const key of Object.keys(results)) if (!seen.has(key)) keys.push(key);
	return keys;
}

function linkIds(c: CaseView): string[] {
	return orderedConnections(c.structure, Object.keys(c.solved?.linkResults ?? {}));
}

/** The largest |velocity| of a connection's pipes (Compare's and goal seek's linkVelocity). */
function largestVelocity(c: CaseView, id: string): number | null {
	const value = QUANTITIES.linkVelocity.value(c.solved!, {
		quantity: 'linkVelocity',
		elementId: id
	});
	return typeof value === 'number' ? value : null;
}

function kindOf(c: CaseView, id: string): string | null {
	const component = componentById(c.structure, id) ?? componentById(c.names, id);
	return component ? kindLabel(component) : null;
}

/** A per-port map's keys in the component's port order (as solved), then the others. */
function portOrder(
	c: CaseView,
	id: string,
	...maps: Readonly<Record<string, unknown>>[]
): string[] {
	const component = componentById(c.structure, id);
	const keys = new Set(maps.flatMap((m) => Object.keys(m)));
	const order = (component?.ports.map((p) => p.id) ?? []).filter((p) => keys.has(p));
	const seen = new Set(order);
	return [...order, ...[...keys].filter((k) => !seen.has(k))];
}

const isAssigned = (b: BoundaryResult | undefined) => b?.type === 'assigned_flow';

/** An equipment rating's kind in words (the form's Rated by choice). */
const RATED_BY: Readonly<Record<EquipmentRating['kind'], string>> = {
	point: 'Pressure drop at a flow',
	Cv: 'Cv',
	Kv: 'Kv'
};

/** The element tables (§2.6), in sheet order; each is written only when it has rows. */
export function elementTables(ctx: ExportContext): SheetSpec[] {
	const u = ctx.units;
	const q = (label: string, category: UnitCategory, options: LabelOptions = {}) =>
		quantity(ctx, label, category, options);
	const cases = ctx.valued;
	const solvedOf = (c: CaseView) => c.solved!;

	const nodes = table(
		ctx,
		'nodes',
		'Nodes',
		[
			text('Component id'),
			text('Component'),
			text('Type'),
			text('Port id'),
			text('Port'),
			q('Elevation', 'length'),
			q('Pressure', 'pressure', { gauge: true }),
			q('Dynamic pressure', 'pressure'),
			q('Total pressure', 'pressure', { gauge: true }),
			q('Absolute pressure', 'pressure', { absolute: true }),
			q('Velocity', 'velocity'),
			q('HGL', 'head'),
			q('EGL', 'head'),
			text('Flags')
		],
		cases,
		(c) => Object.keys(solvedOf(c).nodeResults).length,
		function* (c) {
			const solved = solvedOf(c);
			for (const key of nodeKeys(c)) {
				const node = solved.nodeResults[key]!;
				yield [
					node.componentId,
					componentName(c, node.componentId),
					kindOf(c, node.componentId),
					node.portId,
					portLabel(node.portId),
					u.value(node.elevation, 'length'),
					u.value(node.pressure, 'pressure'),
					u.value(node.dynamicPressure, 'pressure'),
					u.value(node.totalPressure, 'pressure'),
					u.value(node.absolutePressure, 'pressure'),
					u.value(node.velocity, 'velocity'),
					u.value(node.hgl, 'head'),
					u.value(node.egl, 'head'),
					codes(
						solved.flags.filter(
							(f) => f.componentId === node.componentId && f.portId === node.portId
						)
					)
				];
			}
		}
	);

	const links = table(
		ctx,
		'links',
		'Links',
		[
			text('Connection id'),
			text('Connection'),
			text('From id'),
			text('From port'),
			text('To id'),
			text('To port'),
			q('Flow (+ from → to)', 'flow'),
			q('Largest velocity', 'velocity'),
			q('Head loss (EGL from − to)', 'head'),
			q('Friction loss (+ with the flow)', 'head'),
			q('Fittings loss (+ with the flow)', 'head'),
			number('Pipes'),
			number('Fittings'),
			text('Flags')
		],
		cases,
		(c) => Object.keys(solvedOf(c).linkResults).length,
		function* (c) {
			const solved = solvedOf(c);
			for (const id of linkIds(c)) {
				const link = solved.linkResults[id]!;
				const connection = connectionById(c.structure, id) ?? connectionById(c.names, id);
				yield [
					id,
					connectionLabel(c, id),
					connection?.fromComponentId ?? null,
					connection?.fromPortId ?? null,
					connection?.toComponentId ?? null,
					connection?.toPortId ?? null,
					u.value(link.flow, 'flow'),
					u.value(largestVelocity(c, id), 'velocity'),
					u.value(link.headLoss, 'head'),
					u.value(link.frictionHeadLoss, 'head'),
					u.value(link.fittingsHeadLoss, 'head'),
					link.segments.length,
					link.fittings.length,
					codes(flagsForElement(solved.flags, { kind: 'connection', id }))
				];
			}
		}
	);

	// The project library (CLAUDE.md D22): the entry each pipe, fitting and valve refers to, by id
	// and name in the case as solved, as columns only in a file with a library (else as before).
	const library = ctx.library;
	const entryColumns = (what: string) =>
		library ? [text(`${what} id`), text(what)] : ([] as ExportColumn[]);
	const entryCells = (id: string | null | undefined, name: string | undefined): CellValue[] =>
		library ? [id ?? null, id == null ? null : (name ?? null)] : [];

	const pipes = table(
		ctx,
		'pipes',
		'Pipes',
		[
			text('Connection id'),
			text('Connection'),
			number('Pipe #'),
			...entryColumns('Pipe spec'),
			text('Material'),
			text('Schedule'),
			text('Nominal size'),
			q('Inner diameter', 'diameter'),
			q('Length', 'length'),
			q('Roughness', 'diameter'),
			q('Velocity (signed as the flow)', 'velocity'),
			number('Re'),
			number('f (Darcy)'),
			text('Regime'),
			q('Friction loss (+ with the flow)', 'head'),
			text('Flags')
		],
		cases,
		(c) => Object.values(solvedOf(c).linkResults).reduce((n, l) => n + l.segments.length, 0),
		function* (c) {
			const solved = solvedOf(c);
			for (const id of linkIds(c)) {
				const link = solved.linkResults[id]!;
				const name = connectionLabel(c, id);
				const piping = connectionById(c.structure, id)?.piping;
				for (const s of link.segments) {
					const pipe = piping?.pipes[s.index];
					// A pipe of a project library spec: the spec's material and nominal size.
					const spec = pipeSpecOf(c.structure, pipe?.specId);
					const materialId = spec?.materialId ?? pipe?.materialId ?? null;
					const nominalSize = spec ? spec.nominalSize : pipe?.nominalSize;
					yield [
						id,
						name,
						s.index + 1,
						...entryCells(pipe?.specId, spec?.name),
						materialId === null
							? null
							: materialId === CUSTOM_MATERIAL_ID
								? 'Custom pipe'
								: (ctx.materialName(materialId) ?? materialId),
						pipe?.schedule ?? null,
						nominalSize != null ? npsLabel(nominalSize, ctx.input.library.nominalSizes) : null,
						u.value(s.innerDiameter, 'diameter'),
						u.value(s.length, 'length'),
						u.value(s.roughness, 'diameter'),
						u.value(s.velocity, 'velocity'),
						s.reynoldsNumber,
						s.frictionFactor,
						regimeLabel(s.flowRegime),
						u.value(s.headLoss, 'head'),
						codes(segmentFlags(solved.flags, id, s.index))
					];
				}
			}
		}
	);

	const fittings = table(
		ctx,
		'fittings',
		'Fittings',
		[
			text('Connection id'),
			text('Connection'),
			number('Fitting #'),
			text('Type id'),
			text('Fitting'),
			number('Pipe #'),
			number('Quantity'),
			number('K (each)'),
			q('K referred to diameter', 'diameter'),
			q('Head loss, all (+ with the flow)', 'head'),
			...entryColumns('Resistance entry'),
			text('K source'),
			text('Flags')
		],
		cases,
		(c) => Object.values(solvedOf(c).linkResults).reduce((n, l) => n + l.fittings.length, 0),
		function* (c) {
			const solved = solvedOf(c);
			for (const id of linkIds(c)) {
				const link = solved.linkResults[id]!;
				const name = connectionLabel(c, id);
				const listed = connectionById(c.structure, id)?.piping.fittings;
				for (const f of link.fittings) {
					const fitting = listed?.[f.index];
					yield [
						id,
						name,
						f.index + 1,
						f.type,
						ctx.fittingName(f.type),
						fitting ? fitting.pipeIndex + 1 : null,
						f.quantity,
						f.k,
						u.value(f.referenceDiameter, 'diameter'),
						u.value(f.headLoss, 'head'),
						...entryCells(
							fitting?.resistanceId,
							resistanceEntryOf(c.structure, fitting?.resistanceId)?.name
						),
						f.source,
						codes(fittingFlags(solved.flags, id, f.index))
					];
				}
			}
		}
	);

	const pumpIds = (c: CaseView) => orderedIds(c.structure, Object.keys(solvedOf(c).pumpResults));
	const pumps = table(
		ctx,
		'pumps',
		'Pumps',
		[
			text('Pump id'),
			text('Pump'),
			text('Status'),
			q('Speed', 'fraction'),
			text('Control'),
			q('Flow setpoint', 'flow'),
			text('Control state'),
			bool('Setpoint achieved'),
			q('Flow', 'flow'),
			q('Head', 'head'),
			bool('In curve range'),
			q('Efficiency', 'fraction'),
			q('Hydraulic power', 'power'),
			q('Shaft power', 'power'),
			q('NPSHa', 'head'),
			q('NPSHr', 'head'),
			q('NPSH margin', 'head'),
			q('Suction absolute pressure', 'pressure', { absolute: true }),
			text('Flags')
		],
		cases,
		(c) => Object.keys(solvedOf(c).pumpResults).length,
		function* (c) {
			const solved = solvedOf(c);
			for (const id of pumpIds(c)) {
				const pump = solved.pumpResults[id]!;
				const flags = flagsForElement(solved.flags, { kind: 'component', id });
				const control = pump.control;
				yield [
					id,
					componentName(c, id),
					pumpStatusLabel(pump, flags),
					pump.status === 'off' ? null : u.value(pump.speed, 'fraction'),
					control
						? (PUMP_CONTROL_MODE_NAMES[control.mode] ?? humanize(control.mode))
						: 'Fixed speed',
					control ? u.value(control.setpoint, 'flow') : null,
					control ? (PUMP_CONTROL_STATE_LABELS[control.state] ?? humanize(control.state)) : null,
					control?.setpointAchieved ?? null,
					u.value(pump.operatingFlow, 'flow'),
					u.value(pump.operatingHead, 'head'),
					pump.inCurveRange,
					u.value(pump.efficiency, 'fraction'),
					u.value(pump.hydraulicPower, 'power'),
					u.value(pump.shaftPower, 'power'),
					u.value(pump.npshAvailable, 'head'),
					u.value(pump.npshRequired, 'head'),
					u.value(pump.npshMargin, 'head'),
					u.value(pump.suctionAbsolutePressure, 'pressure'),
					codes(flags)
				];
			}
		}
	);

	const pumpCurves = table(
		ctx,
		'pump-curves',
		'Pump curves',
		[text('Pump id'), text('Pump'), number('Point #'), q('Flow', 'flow'), q('Head', 'head')],
		cases,
		(c) => Object.values(solvedOf(c).pumpResults).reduce((n, p) => n + p.curve.length, 0),
		function* (c) {
			const solved = solvedOf(c);
			for (const id of pumpIds(c)) {
				const pump = solved.pumpResults[id]!;
				const name = componentName(c, id);
				for (const [i, p] of pump.curve.entries()) {
					yield [id, name, i + 1, u.value(p.flow, 'flow'), u.value(p.head, 'head')];
				}
			}
		}
	);

	const systemCurves = table(
		ctx,
		'system-curves',
		'System curves',
		[
			text('Pump id'),
			text('Pump'),
			q('Flow from', 'flow'),
			q('Flow to', 'flow'),
			number('Point #'),
			q('Flow', 'flow'),
			q('Head', 'head'),
			bool('Converged'),
			text('Reason code'),
			text('Reason')
		],
		cases,
		(c) => readyCurves(c).reduce((n, r) => n + r.curve.points.length, 0),
		function* (c) {
			for (const { pumpId, result, curve } of readyCurves(c)) {
				const name = componentName(c, pumpId);
				// The chart's own rows (one per point, in flow order), so each reason is the text the
				// chart's data table shows for that point: never a copy of its words.
				const notes = pumpChartData(result, u.prefs, null, curve, {
					project: c.names,
					solved: c.structure
				}).systemRows;
				const points = [...curve.points].sort((a, b) => a.flow - b.flow);
				for (const [i, p] of points.entries()) {
					yield [
						pumpId,
						name,
						u.value(curve.flowRange.min, 'flow'),
						u.value(curve.flowRange.max, 'flow'),
						i + 1,
						u.value(p.flow, 'flow'),
						u.value(p.head, 'head'),
						p.converged,
						p.reason,
						notes[i]?.note || null
					];
				}
			}
		}
	);

	const valves = table(
		ctx,
		'valves',
		'Valves',
		[
			text('Valve id'),
			text('Valve'),
			text('Type'),
			text('State'),
			q('Flow (+ inlet → outlet)', 'flow'),
			q('Head loss', 'head'),
			q('Pressure drop, static', 'pressure'),
			number('K (open)'),
			q('K referred to diameter', 'diameter'),
			number('K effective'),
			number('Cv effective'),
			...entryColumns('Resistance entry'),
			q('Pressure setpoint', 'pressure', { gauge: true }),
			q('Flow setpoint', 'flow'),
			bool('Setpoint achieved'),
			text('Flags')
		],
		cases,
		(c) => Object.keys(solvedOf(c).valveResults).length,
		function* (c) {
			const solved = solvedOf(c);
			for (const id of orderedIds(c.structure, Object.keys(solved.valveResults))) {
				const valve = solved.valveResults[id]!;
				const pressureSet = valve.valveType === 'prv' || valve.valveType === 'psv';
				const own = componentById(c.structure, id);
				const ref =
					own?.type === 'valve' && isResistanceRef(own.resistance) ? own.resistance.id : null;
				yield [
					id,
					componentName(c, id),
					valveTypeLabel(valve.valveType),
					valveStateLabel(valve.state),
					u.value(valve.flow, 'flow'),
					u.value(valve.headLoss, 'head'),
					u.value(valve.pressureDrop, 'pressure'),
					valve.kOpen,
					u.value(valve.referenceDiameter, 'diameter'),
					valve.kEffective,
					valve.cvEffective,
					...entryCells(ref, resistanceEntryOf(c.structure, ref)?.name),
					pressureSet ? u.value(valve.setpoint, 'pressure') : null,
					valve.valveType === 'fcv' ? u.value(valve.setpoint, 'flow') : null,
					valve.setpointAchieved,
					codes(flagsForElement(solved.flags, { kind: 'component', id }))
				];
			}
		}
	);

	// Relief valves (proposal pressure-relief-valve.md §5): the results, then the set, overpressure
	// and capacity the solve used (ReliefValveResult's, a scenario's or a goal-seek trial's): the
	// sheet's named departure from the screen's table, as equipment's rating. A valve with no
	// result (a side closed off or floating: RELIEF_VALVE_CLOSED) is listed by its flag, as on the
	// screen, with its values empty. Inlet and back pressures are null where the level is
	// undetermined.
	const reliefIds = (c: CaseView) => {
		const solved = solvedOf(c);
		const results = solved.reliefValveResults ?? {};
		const closed = solved.flags
			.filter((flag) => flag.code === 'RELIEF_VALVE_CLOSED' && flag.componentId)
			.map((flag) => flag.componentId as string)
			.filter((id) => !(id in results));
		return orderedIds(c.structure, [...Object.keys(results), ...new Set(closed)]);
	};
	const reliefValves = table(
		ctx,
		'relief-valves',
		'Relief valves',
		[
			text('Relief valve id'),
			text('Relief valve'),
			text('State'),
			q('Flow (+ inlet → outlet)', 'flow'),
			q('Lift', 'fraction'),
			q('Capacity (full lift)', 'flow'),
			q('Flow ÷ capacity', 'fraction'),
			q('Inlet pressure', 'pressure', { gauge: true }),
			q('Back pressure', 'pressure', { gauge: true }),
			q('Δp ÷ set', 'fraction'),
			q('Pressure difference, total', 'pressure'),
			q('Pressure drop, static', 'pressure'),
			q('Head loss', 'head'),
			q('Set pressure', 'pressure'),
			q('Overpressure at full lift', 'fraction'),
			text('Overpressure from'),
			text('Capacity given by'),
			q('Area', 'area'),
			number('Kd'),
			text('Covering letter'),
			number('Reynolds number (orifice)'),
			text('Flags')
		],
		cases,
		(c) => reliefIds(c).length,
		function* (c) {
			const solved = solvedOf(c);
			for (const id of reliefIds(c)) {
				const valve = solved.reliefValveResults?.[id];
				const flags = codes(flagsForElement(solved.flags, { kind: 'component', id }));
				if (!valve) {
					yield [id, componentName(c, id), RELIEF_NO_RESULT, ...Array(18).fill(null), flags];
					continue;
				}
				const capacity = valve.capacity;
				yield [
					id,
					componentName(c, id),
					reliefStateLabel(valve.state, id, c.input.inputs),
					u.value(valve.flow, 'flow'),
					u.value(valve.lift, 'fraction'),
					u.value(valve.fullLiftFlow, 'flow'),
					u.value(valve.flowRatio, 'fraction'),
					u.value(valve.inletPressure, 'pressure'),
					u.value(valve.backPressure, 'pressure'),
					u.value(valve.setRatio, 'fraction'),
					u.value(valve.totalPressureDifference, 'pressure'),
					u.value(valve.pressureDrop, 'pressure'),
					u.value(valve.headLoss, 'head'),
					u.value(valve.setPressure, 'pressure'),
					u.value(valve.overpressure, 'fraction'),
					OVERPRESSURE_SOURCE_LABELS[valve.overpressureSource],
					capacityGivenBy(capacity),
					u.value(capacity.area, 'area'),
					capacity.dischargeCoefficient,
					capacity.kind === 'effective' ? capacity.coveringLetter : null,
					valve.reynoldsNumber,
					flags
				];
			}
		}
	);

	// Equipment (proposal equipment-pressure-drop.md §5.4): the results, then the rating the solve
	// used (EquipmentResult.rating: a scenario's or a goal-seek trial's), its one named departure
	// from the screen's table, since a file has no form to read the rating from. "(loss)" says
	// which result the rated drop scales to.
	const equipmentIds = (c: CaseView) =>
		orderedIds(c.structure, Object.keys(solvedOf(c).equipmentResults ?? {}));
	const equipment = table(
		ctx,
		'equipment',
		'Equipment',
		[
			text('Equipment id'),
			text('Equipment'),
			q('Flow (+ inlet → outlet)', 'flow'),
			q('Flow ÷ rated flow', 'fraction'),
			q('Pressure loss', 'pressure'),
			q('Head loss', 'head'),
			q('Pressure drop, static', 'pressure'),
			text('Rated by'),
			q('Rated pressure drop (loss)', 'pressure'),
			q('Rated flow', 'flow'),
			q('Rated fluid density', 'density'),
			number('Flow coefficient'),
			text('Flags')
		],
		cases,
		(c) => equipmentIds(c).length,
		function* (c) {
			const solved = solvedOf(c);
			for (const id of equipmentIds(c)) {
				const item = solved.equipmentResults[id]!;
				const rating = item.rating;
				const point = rating.kind === 'point' ? rating : null;
				yield [
					id,
					componentName(c, id),
					u.value(item.flow, 'flow'),
					u.value(item.flowRatio, 'fraction'),
					u.value(item.pressureLoss, 'pressure'),
					u.value(item.headLoss, 'head'),
					u.value(item.pressureDrop, 'pressure'),
					RATED_BY[rating.kind],
					u.value(point?.pressureLoss, 'pressure'),
					u.value(point?.flow, 'flow'),
					u.value(point?.density, 'density'),
					rating.kind === 'point' ? null : rating.value,
					codes(flagsForElement(solved.flags, { kind: 'component', id }))
				];
			}
		}
	);

	// Orifice plates (proposal orifice-plate.md §5.4): the results, the coefficients the solve used
	// and where C came from, then the bore and pipe bore it used (the echoed inputs, a scenario's or
	// a goal-seek trial's): the sheet's named departure from the screen's table, as equipment's
	// rating. The reading is null without taps; the vena contracta pressure at zero flow and where
	// the pressure level is undetermined.
	const orificeIds = (c: CaseView) =>
		orderedIds(c.structure, Object.keys(solvedOf(c).orificeResults ?? {}));
	const orifices = table(
		ctx,
		'orifices',
		'Orifice plates',
		[
			text('Orifice id'),
			text('Orifice'),
			q('Flow (+ inlet → outlet)', 'flow'),
			q('Permanent pressure loss', 'pressure'),
			q('Differential pressure (taps)', 'pressure'),
			q('Pressure drop, static', 'pressure'),
			q('Head loss', 'head'),
			q('Vena contracta pressure', 'pressure', { gauge: true }),
			number('β'),
			number('Reynolds number (inlet pipe)'),
			number('Discharge coefficient (loss)'),
			text('C from'),
			number('C evaluated at Re'),
			number('Tap ratio r'),
			text('Taps'),
			number('Meter C'),
			number('Loss coefficient K'),
			q('Bore', 'diameter'),
			q('Pipe bore D', 'diameter'),
			text('Flags')
		],
		cases,
		(c) => orificeIds(c).length,
		function* (c) {
			const solved = solvedOf(c);
			for (const id of orificeIds(c)) {
				const plate = solved.orificeResults[id]!;
				yield [
					id,
					componentName(c, id),
					u.value(plate.flow, 'flow'),
					u.value(plate.pressureLoss, 'pressure'),
					u.value(plate.differentialPressure, 'pressure'),
					u.value(plate.pressureDrop, 'pressure'),
					u.value(plate.headLoss, 'head'),
					u.value(plate.venaContractaPressure, 'pressure'),
					plate.beta,
					plate.reynoldsNumber,
					plate.dischargeCoefficient,
					orificeCoefficientSource(plate),
					plate.coefficientReynoldsNumber,
					plate.tapCoefficientRatio,
					plate.taps ? TAP_LABELS[plate.taps] : 'None',
					plate.meterDischargeCoefficient,
					plate.lossCoefficient,
					u.value(plate.boreDiameter, 'diameter'),
					u.value(plate.pipeDiameter, 'diameter'),
					codes(flagsForElement(solved.flags, { kind: 'component', id }))
				];
			}
		}
	);

	const branchIds = (c: CaseView) =>
		orderedIds(c.structure, Object.keys(solvedOf(c).branchResults));
	const branches = table(
		ctx,
		'branches',
		'Branches',
		[
			text('Branch id'),
			text('Branch'),
			text('Type'),
			text('Loss model'),
			text('Flow pattern'),
			text('Combined port id'),
			q('Combined-flow velocity', 'velocity'),
			text('K is on'),
			text('Correlation'),
			bool('In correlation range'),
			text('Flags')
		],
		cases,
		(c) => Object.keys(solvedOf(c).branchResults).length,
		function* (c) {
			const solved = solvedOf(c);
			for (const id of branchIds(c)) {
				const branch = solved.branchResults[id]!;
				yield [
					id,
					componentName(c, id),
					humanize(branch.branchType),
					LOSS_MODEL_LABELS[branch.lossModel] ?? humanize(branch.lossModel),
					branchPatternLabel(branch.pattern, componentById(c.structure, id)),
					branch.combinedPortId,
					u.value(branch.referenceVelocity, 'velocity'),
					branchVelocityBasis(branch) === 'combined'
						? 'Combined-flow velocity'
						: 'None (ideal or no flow)',
					branch.correlation,
					branch.inCorrelationRange,
					codes(flagsForElement(solved.flags, { kind: 'component', id }))
				];
			}
		}
	);

	const branchPorts = table(
		ctx,
		'branch-ports',
		'Branch ports',
		[
			text('Branch id'),
			text('Branch'),
			text('Port id'),
			text('Port'),
			q('Flow (+ into the branch)', 'flow'),
			bool('Combined port'),
			number('K of the path from the combined port'),
			q('Velocity K is on', 'velocity'),
			q('Path head loss (+ in the flow direction)', 'head')
		],
		cases,
		(c) =>
			Object.entries(solvedOf(c).branchResults).reduce(
				(n, [id, b]) => n + portOrder(c, id, b.portFlows, b.kFactors, b.pathHeadLosses).length,
				0
			),
		function* (c) {
			const solved = solvedOf(c);
			for (const id of branchIds(c)) {
				const branch = solved.branchResults[id]!;
				const name = componentName(c, id);
				const combined = branch.combinedPortId;
				const onCombined = branchVelocityBasis(branch) === 'combined';
				for (const port of portOrder(
					c,
					id,
					branch.portFlows,
					branch.kFactors,
					branch.pathHeadLosses
				)) {
					const k = port !== combined ? (branch.kFactors[port] ?? null) : null;
					yield [
						id,
						name,
						port,
						portLabel(port),
						u.value(branch.portFlows[port], 'flow'),
						port === combined,
						k,
						// K·v²/(2g) is the path's loss with v the combined-flow velocity (decision 29).
						k !== null && onCombined
							? u.value(Math.abs(branch.referenceVelocity), 'velocity')
							: null,
						u.value(branch.pathHeadLosses[port], 'head')
					];
				}
			}
		}
	);

	const boundaryIds = (c: CaseView) => {
		const results = solvedOf(c).boundaryResults;
		return orderedIds(
			c.structure,
			Object.keys(results).filter((id) => !isAssigned(results[id]))
		);
	};
	const boundaries = table(
		ctx,
		'boundaries',
		'Boundaries',
		[
			text('Boundary id'),
			text('Boundary'),
			text('Type'),
			q('EGL', 'head'),
			q('Net outflow (+ into the network)', 'flow'),
			number('Ports'),
			text('Flags')
		],
		cases,
		(c) => boundaryIds(c).length,
		function* (c) {
			const solved = solvedOf(c);
			// The screen's words for the boundary types (its Type column).
			const types = new Map(
				boundaryTable(c.names, solved, u.prefs).rows.map((r) => [r.key, r.cells.type])
			);
			for (const id of boundaryIds(c)) {
				const b = solved.boundaryResults[id]!;
				const type = types.get(id);
				yield [
					id,
					componentName(c, id),
					typeof type === 'string' ? type : humanize(b.type),
					u.value(b.egl, 'head'),
					u.value(b.outflow, 'flow'),
					Object.keys(b.portOutflows).length,
					codes(flagsForElement(solved.flags, { kind: 'component', id }))
				];
			}
		}
	);

	const multiPort = (c: CaseView) =>
		boundaryIds(c).filter(
			(id) => Object.keys(solvedOf(c).boundaryResults[id]!.portOutflows).length > 1
		);
	const boundaryPorts = table(
		ctx,
		'boundary-ports',
		'Boundary ports',
		[
			text('Boundary id'),
			text('Boundary'),
			text('Port id'),
			text('Port'),
			q('Outflow (+ into the network)', 'flow')
		],
		cases,
		(c) =>
			multiPort(c).reduce(
				(n, id) => n + Object.keys(solvedOf(c).boundaryResults[id]!.portOutflows).length,
				0
			),
		function* (c) {
			const solved = solvedOf(c);
			for (const id of multiPort(c)) {
				const b = solved.boundaryResults[id]!;
				const name = componentName(c, id);
				for (const port of portOrder(c, id, b.portOutflows)) {
					yield [id, name, port, portLabel(port), u.value(b.portOutflows[port], 'flow')];
				}
			}
		}
	);

	const assignedIds = (c: CaseView) => {
		const results = solvedOf(c).boundaryResults;
		return orderedIds(
			c.structure,
			Object.keys(results).filter((id) => isAssigned(results[id]))
		);
	};
	const assignedFlows = table(
		ctx,
		'assigned-flows',
		'Assigned flows',
		[
			text('Node id'),
			text('Node'),
			text('Port id'),
			text('Direction'),
			q('Assigned flow (+ demand, − supply)', 'flow'),
			q('Net outflow (+ into the network)', 'flow'),
			q('Elevation', 'length'),
			q('Pressure', 'pressure', { gauge: true }),
			q('Absolute pressure', 'pressure', { absolute: true }),
			q('HGL', 'head'),
			text('Flags')
		],
		cases,
		(c) => assignedIds(c).length,
		function* (c) {
			const solved = solvedOf(c);
			for (const id of assignedIds(c)) {
				const b = solved.boundaryResults[id]!;
				const port = Object.keys(b.portOutflows)[0];
				const node = port === undefined ? undefined : solved.nodeResults[`${id}:${port}`];
				const input = componentById(c.structure, id);
				const flow = input?.type === 'assigned_flow' ? input.flow : null;
				const direction = flow === null ? null : flowDirection(flow);
				yield [
					id,
					componentName(c, id),
					port ?? null,
					flow === null ? null : direction ? DIRECTION_NAMES[direction] : 'None (as a plug)',
					u.value(flow, 'flow'),
					u.value(b.outflow, 'flow'),
					u.value(node?.elevation, 'length'),
					u.value(node?.pressure, 'pressure'),
					u.value(node?.absolutePressure, 'pressure'),
					u.value(node?.hgl, 'head'),
					codes(flagsForElement(solved.flags, { kind: 'component', id }))
				];
			}
		}
	);

	return [
		nodes,
		links,
		pipes,
		fittings,
		pumps,
		pumpCurves,
		systemCurves,
		valves,
		reliefValves,
		equipment,
		orifices,
		branches,
		branchPorts,
		boundaries,
		boundaryPorts,
		assignedFlows
	];
}

// ---------------------------------------------------------------------------------------------
// Scenario changes
// ---------------------------------------------------------------------------------------------

const CHANGE_STATES: Readonly<Record<OverrideResult['state'], string>> = {
	applied: 'Applied',
	orphaned: 'Not applied: element not in the project',
	not_applicable: 'Not applicable'
};

/** The unit category of a change's numeric value, by its field (null: a text value). */
export function changeCategory(
	project: Project,
	record: OverrideResult
): { category: UnitCategory; options: LabelOptions } | null {
	const o = record.override;
	if (o.kind === 'pipe') return o.field === 'length' ? { category: 'length', options: {} } : null;
	if (o.kind === 'project') {
		return o.field === 'fluid.temperature' ? { category: 'temperature', options: {} } : null;
	}
	switch (o.field) {
		case 'status':
		case 'resistance':
		case 'rating':
		case 'rating.value':
		case 'capacity':
		case 'capacity.letter':
			// Text: a coefficient as entered with its kind ("Cv 120"), a whole rating or capacity, or
			// an API 526 letter.
			return null;
		default: {
			// A number in its registry unit (field-registry.ts), gauge pressures marked (D4).
			const component = componentById(project, o.componentId);
			const entry = entryFor(component ? componentSchemaName(component) : null, o.field);
			const unit = entry ? unitOf(entry, component) : null;
			return {
				category: unit?.category ?? 'dimensionless',
				options: unit?.gauge ? { gauge: true } : {}
			};
		}
	}
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
	!!v && typeof v === 'object' && !Array.isArray(v);

/**
 * A whole rating as text in the file's units, every number exact (as a resistance's, never
 * rounded): "Cv 120", or "50 kPa at 15 L/s, 999.1 kg/m³" (the drop a difference: no marker).
 */
function ratingCell(value: Record<string, unknown>, u: ExportContext['units']): string {
	if (value.kind !== 'point') return `${String(value.kind)} ${String(value.value)}`;
	const part = (v: unknown, category: UnitCategory) => {
		const n = typeof v === 'number' ? u.value(v, category) : null;
		const label = u.label(category);
		return n === null ? '—' : label ? `${n} ${label}` : String(n);
	};
	return `${part(value.pressureLoss, 'pressure')} at ${part(value.flow, 'flow')}, ${part(value.density, 'density')}`;
}

/**
 * A whole relief valve capacity as text in the file's units, every number exact: "API 526 J
 * (0.00083032092 m²), Kd 0.65 (preliminary)", "API 520 effective area 447.0709 mm², Kd 0.65
 * (preliminary)", "Certified area 250 mm², rated coefficient 0.7, overpressure 8 %".
 */
function capacityCell(value: Record<string, unknown>, u: ExportContext['units']): string {
	const part = (v: unknown, category: UnitCategory) => {
		const n = typeof v === 'number' ? u.value(v, category) : null;
		const label = u.label(category);
		return n === null ? '—' : label ? `${n} ${label}` : String(n);
	};
	const kd = `Kd ${RELIEF_DATA.effectiveDischargeCoefficient} (preliminary)`;
	if (value.kind === 'api526') {
		const letter = String(value.letter);
		return `API 526 ${letter} (${part(letterArea(letter), 'area')}), ${kd}`;
	}
	if (value.kind === 'effective')
		return `API 520 effective area ${part(value.area, 'area')}, ${kd}`;
	const op =
		typeof value.overpressure === 'number' ? part(value.overpressure, 'fraction') : asmeRuleWords();
	return `Certified area ${part(value.area, 'area')}, rated coefficient ${String(value.dischargeCoefficient)}, overpressure ${op}`;
}

/**
 * The project library (CLAUDE.md D22, proposal project-library.md §5.3): every pipe spec and
 * resistance entry of each case with a response, as that case was solved (its project as solved:
 * an out-of-date case's may differ from the project now), one per row, pipe specs first, in the
 * library's order: its values as entered in the file's units (a K with the bore it is stated at; a
 * Cv or Kv as entered, in every unit system), its source as typed, and the elements of the case
 * that refer to it (an entry nothing uses has none: the methods summary lists it as not used).
 * A library material's roughness left blank is the material's at the inner diameter, which the
 * server computes (Roughness from). Only in a file with a library (ctx.library).
 */
export function projectLibraryTable(ctx: ExportContext): SheetSpec | null {
	if (!ctx.library) return null;
	const u = ctx.units;
	const q = (label: string, category: UnitCategory) => quantity(ctx, label, category);
	const cases = ctx.responded;
	const elementUsers = (users: readonly LibraryUser[]) =>
		users.filter((x) => x.kind !== 'scenario');
	const where = (c: CaseView, user: LibraryUser): { id: string; label: string } => {
		switch (user.kind) {
			case 'pipe':
				return {
					id: `${user.connectionId} pipe ${user.pipeIndex + 1}`,
					label: `Pipe ${user.pipeIndex + 1} of ${connectionLabel(c, user.connectionId)}`
				};
			case 'fitting': {
				const type = connectionById(c.structure, user.connectionId)?.piping.fittings[
					user.fittingIndex
				]?.type;
				return {
					id: `${user.connectionId} fitting ${user.fittingIndex + 1}`,
					label: `Fitting ${user.fittingIndex + 1}${type ? ` (${ctx.fittingName(type)})` : ''} of ${connectionLabel(c, user.connectionId)}`
				};
			}
			case 'valve':
				return { id: user.componentId, label: componentName(c, user.componentId) };
			default:
				return { id: '', label: '' };
		}
	};
	const used = (c: CaseView, users: readonly LibraryUser[]): CellValue[] => {
		const found = elementUsers(users).map((x) => where(c, x));
		return [
			found.length,
			found.length ? found.map((f) => f.label).join('; ') : null,
			found.length ? found.map((f) => f.id).join('; ') : null
		];
	};
	return table(
		ctx,
		'project-library',
		'Project library',
		[
			text('List'),
			text('Entry id'),
			text('Entry'),
			text('Material id'),
			text('Material'),
			text('Nominal size'),
			q('Inner diameter', 'diameter'),
			q('Outer diameter', 'diameter'),
			q('Roughness', 'diameter'),
			text('Roughness from'),
			text('Coefficient kind'),
			number('Coefficient (as entered)'),
			q('Reference diameter (K)', 'diameter'),
			text('Source'),
			number('Used by (count)'),
			text('Used by'),
			text('Used by (ids)')
		],
		cases,
		(c) => pipeSpecs(c.structure).length + resistanceEntries(c.structure).length,
		function* (c) {
			for (const spec of pipeSpecs(c.structure)) {
				const custom = spec.materialId === CUSTOM_MATERIAL_ID;
				yield [
					'Pipe spec',
					spec.id,
					spec.name,
					spec.materialId,
					custom ? 'Custom pipe' : (ctx.materialName(spec.materialId) ?? spec.materialId),
					spec.nominalSize != null
						? npsLabel(spec.nominalSize, ctx.input.library.nominalSizes)
						: null,
					u.value(spec.innerDiameter, 'diameter'),
					u.value(spec.outerDiameter, 'diameter'),
					u.value(spec.roughness, 'diameter'),
					spec.roughness != null
						? 'The entry'
						: "The material's at the inner diameter (Farshad & Rieke 2006), computed by the server",
					null,
					null,
					null,
					spec.source,
					...used(c, pipeSpecUsers(c.structure, spec.id))
				];
			}
			for (const entry of resistanceEntries(c.structure)) {
				yield [
					'Resistance',
					entry.id,
					entry.name,
					null,
					null,
					null,
					null,
					null,
					null,
					null,
					entry.kind,
					entry.value,
					u.value(entry.referenceDiameter, 'diameter'),
					entry.source,
					...used(c, resistanceUsers(c.structure, entry.id))
				];
			}
		}
	);
}

/** Scenario changes (§2.6): the overrides the server applied, from its record. */
export function scenarioChangesTable(ctx: ExportContext): SheetSpec {
	const u = ctx.units;
	const cases = ctx.responded.filter((c) => c.response?.scenario);
	return table(
		ctx,
		'scenario-changes',
		'Scenario changes',
		[
			number('Change #'),
			text('Target'),
			text('Element id'),
			number('Pipe #'),
			text('Field'),
			text('Field id'),
			text('State'),
			text('Value'),
			text('Base value'),
			text('Unit'),
			json('Value (SI, JSON)'),
			json('Base value (SI, JSON)'),
			text('SI unit'),
			text('Message')
		],
		cases,
		(c) => c.response!.scenario!.overrides.length,
		function* (c) {
			// Fields and units as solved (ScenarioCard's rule): the project as sent.
			const solvedAs = c.input.sent ?? c.structure;
			const options = {
				materialName: ctx.materialName,
				nominalSizes: ctx.input.library.nominalSizes
			};
			for (const record of c.response!.scenario!.overrides) {
				const o = record.override;
				const category = changeCategory(solvedAs, record);
				// The server records the values only for a change it applied (null otherwise): an
				// ignored change has no Value or Base value, as the screen shows none (review V2).
				// The JSON columns keep the record as it is.
				const applied = record.state === 'applied';
				const cell = (value: unknown): CellValue => {
					if (!applied) return null;
					const resistance = o.kind === 'component' && o.field === 'resistance';
					// An orifice plate with no entered C: ISO 5167-2's, the default.
					const coefficient = o.kind === 'component' && o.field === 'dischargeCoefficient';
					// A certified relief valve with no entered overpressure: ASME's, the default.
					const overpressure = o.kind === 'component' && o.field === 'capacity.overpressure';
					if (value === null || value === undefined) {
						return resistance
							? 'Default'
							: coefficient
								? ISO_COEFFICIENT_TEXT
								: overpressure
									? asmeRuleWords()
									: null;
					}
					if (resistance) {
						// A project library entry by its id and name in the case solved (exact text).
						if (isResistanceRef(value)) {
							const entry = resistanceEntryOf(solvedAs, value.id);
							return entry
								? `Project library ${value.id} “${entry.name}”`
								: `Project library ${value.id}`;
						}
						if (isRecord(value)) return `${String(value.kind)} ${String(value.value)}`;
						return String(value);
					}
					if (o.kind === 'component' && o.field === 'rating') {
						return isRecord(value) ? ratingCell(value, u) : String(value);
					}
					if (o.kind === 'component' && o.field === 'capacity') {
						return isRecord(value) ? capacityCell(value, u) : String(value);
					}
					if (o.kind === 'component' && o.field === 'capacity.letter') {
						const area = letterArea(String(value));
						return area === null
							? `API 526 ${String(value)}`
							: `API 526 ${String(value)} (${u.value(area, 'area')} ${u.label('area')})`;
					}
					if (o.kind === 'component' && o.field === 'rating.value') {
						// The coefficient as entered, with its kind in the case solved (exact text).
						const item = componentById(solvedAs, o.componentId);
						const kind =
							item?.type === 'equipment' && item.rating.kind !== 'point'
								? `${item.rating.kind} `
								: '';
						return `${kind}${String(value)}`;
					}
					if (category && typeof value === 'number') return u.value(value, category.category);
					return changeValueText(solvedAs, o, value, u.prefs, options);
				};
				const numeric =
					applied &&
					!!category &&
					(typeof record.value === 'number' || typeof record.baseValue === 'number');
				yield [
					record.index + 1,
					changeTargetLabel(c.names, o),
					o.kind === 'component' ? o.componentId : o.kind === 'pipe' ? o.connectionId : null,
					o.kind === 'pipe' ? o.pipeIndex + 1 : null,
					changeFieldLabel(solvedAs, o),
					o.field,
					CHANGE_STATES[record.state] ?? humanize(record.state),
					cell(record.value),
					cell(record.baseValue),
					numeric && category ? u.label(category.category, category.options) || null : null,
					canonicalJson(record.value ?? null),
					canonicalJson(record.baseValue ?? null),
					record.unit || null,
					record.message || null
				];
			}
		}
	);
}

// ---------------------------------------------------------------------------------------------
// Compare cases
// ---------------------------------------------------------------------------------------------

/**
 * Compare cases (§2.6): wide, one row per Compare row in the order chosen, after a Status row and a
 * Solved at row; each network extreme is followed by its "(where)" row. Values follow Compare's
 * rule (no values for a case without them); differences are exact, `fromSI(value − base)`, and
 * relative only for quantities with a true zero and a nonzero base. Names: the current project's,
 * as the Compare tab's, so a connection's values are read on it as it is now (compareValue): About
 * says which a reversal gave the other sign and which were left out, and why (compareNotes).
 */
export function compareSheet(ctx: ExportContext): SheetSpec | null {
	if (ctx.single || ctx.cases.length < 2) return null;
	const u = ctx.units;
	const project = ctx.input.project;
	const cases = ctx.cases;
	const columns: ExportColumn[] = [
		text('Element id'),
		text('Port id'),
		text('Row'),
		text('Quantity'),
		text('Unit')
	];
	cases.forEach((c, i) => {
		columns.push(number(c.label));
		if (i > 0) {
			columns.push(number(`${c.label}: difference from base`));
			columns.push(number(`${c.label}: difference from base`, '%'));
		}
	});
	const compareColumns = compareColumnsOf(ctx);
	const rows = ctx.input.compareRows.filter((r) => r.quantity !== 'status');
	const wide = (
		lead: CellValue[],
		values: CellValue[],
		diffs: (i: number) => [CellValue, CellValue]
	) => {
		const row: CellValue[] = [...lead];
		values.forEach((v, i) => {
			row.push(v);
			if (i > 0) row.push(...diffs(i));
		});
		return row;
	};
	const none = (): [CellValue, CellValue] => [null, null];
	const count = 2 + rows.reduce((n, r) => n + (QUANTITIES[r.quantity].where ? 2 : 1), 0);
	return {
		id: 'compare-cases',
		title: 'Compare cases',
		file: 'compare-cases.csv',
		kind: 'table',
		columns,
		rowCount: count,
		*rows() {
			const status = compareCells({ quantity: 'status' }, compareColumns, project, u.prefs);
			yield wide(
				[null, null, 'Status', 'Status', null],
				cases.map((c, i) => {
					const label = CASE_STATUS_LABELS[c.input.status];
					if (!c.response || c.input.status === 'not_converged') return label;
					return `${label}; ${status[i]?.text ?? ''}`;
				}),
				none
			);
			yield wide(
				[null, null, 'Solved at', 'Solved at', null],
				cases.map((c) => c.solved?.timestamp ?? null),
				none
			);
			for (const row of rows) {
				const spec = QUANTITIES[row.quantity];
				const si = cases.map((c, i) =>
					c.hasValues ? compareValue(row, compareColumns[i]!, project).value : null
				);
				const value = (v: number | string | null): CellValue =>
					typeof v === 'number' ? (spec.category ? u.value(v, spec.category) : v) : v;
				const base = si[0] ?? null;
				const label = rowLabel(project, row);
				yield wide(
					[
						row.elementId ?? null,
						row.portId ?? null,
						label,
						spec.label,
						spec.category ? u.label(spec.category, spec.options ?? {}) || null : null
					],
					si.map(value),
					(i) => {
						const v = si[i];
						if (typeof v !== 'number' || typeof base !== 'number' || !spec.category)
							return [null, null];
						const exact = v - base;
						return [
							u.value(exact, spec.category),
							spec.relative && base !== 0 ? (exact / Math.abs(base)) * 100 : null
						];
					}
				);
				if (spec.where) {
					yield wide(
						[
							row.elementId ?? null,
							row.portId ?? null,
							`${label} (where)`,
							`${spec.label} (where)`,
							null
						],
						cases.map((c, i) =>
							c.hasValues && si[i] !== null ? spec.where!(c.solved!, project) || null : null
						),
						none
					);
				}
			}
		}
	};
}

/**
 * The Compare sheet's columns: each case's solve, the project sent for it when out of date, and
 * the case as solved (a relief valve's status), as the screen's (CompareView).
 */
function compareColumnsOf(ctx: ExportContext): CompareColumn[] {
	return ctx.cases.map((c) => ({
		solved: c.solved,
		converged: c.hasValues,
		sent: c.stale ? c.input.sent : null,
		inputs: c.input.inputs
	}));
}

/** Why compareValue left a connection's value out, as About's "Not in this file" says it. */
const LEFT_OUT_REASONS: Readonly<Record<string, string>> = {
	[ENDS_NOTE]: "its connection's ends changed since that case was solved",
	[PIPES_NOTE]: "its connection's pipes changed since that case was solved"
};

/**
 * The Compare sheet's connection values that read otherwise than in their case's own tables
 * (compareValue's notes), as "row (case)": given with the other sign (reversed since that case was
 * solved), and left out, with the reason (an end moved since, or its pipes changed). Empty without
 * a Compare sheet.
 */
export function compareNotes(ctx: ExportContext): {
	reversed: string[];
	leftOut: { what: string; reason: string }[];
} {
	const notes = { reversed: [] as string[], leftOut: [] as { what: string; reason: string }[] };
	if (ctx.single || ctx.cases.length < 2) return notes;
	const project = ctx.input.project;
	const columns = compareColumnsOf(ctx);
	for (const row of ctx.input.compareRows) {
		if (QUANTITIES[row.quantity].element !== 'connection') continue;
		ctx.cases.forEach((c, i) => {
			if (!c.hasValues) return;
			const note = compareValue(row, columns[i]!, project).note;
			const what = `${rowLabel(project, row)} (${c.label})`;
			if (note === REVERSED_NOTE) notes.reversed.push(what);
			const reason = note ? LEFT_OUT_REASONS[note] : undefined;
			if (reason) notes.leftOut.push({ what, reason });
		});
	}
	return notes;
}

// ---------------------------------------------------------------------------------------------
// Trace
// ---------------------------------------------------------------------------------------------

/**
 * The trace of a single converged case (§2.6), long format, in SI as reported: elements in
 * component order, then connection order, then the others; each part as the trace view heads it.
 */
export function traceTable(ctx: ExportContext): SheetSpec | null {
	const c = ctx.single ? ctx.valued[0] : undefined;
	if (!c) return null;
	const elements = c.solved!.trace.elements;
	const keys = Object.keys(elements);
	const components = orderedIds(c.structure, keys).filter((k) => componentById(c.structure, k));
	const connections = orderedConnections(c.structure, keys).filter((k) =>
		connectionById(c.structure, k)
	);
	const seen = new Set([...components, ...connections]);
	const order = [...components, ...connections, ...keys.filter((k) => !seen.has(k))];
	const count = keys.reduce((n, k) => {
		const e = elements[k]!;
		return (
			n +
			e.inputs.length +
			e.equations.length +
			e.correlations.length +
			e.dataSources.length +
			e.intermediates.length +
			e.notes.length
		);
	}, 0);
	return table(
		ctx,
		'trace',
		'Trace',
		[
			text('Element id'),
			text('Element'),
			text('Element type'),
			text('Part'),
			number('#'),
			text('Name'),
			text('Value'),
			text('Unit'),
			text('Source'),
			text('Text')
		],
		[c],
		() => count,
		function* () {
			for (const key of order) {
				const e = elements[key]!;
				const lead = [key, elementLabel(c, key), e.elementType];
				for (const [i, x] of e.inputs.entries()) {
					yield [...lead, 'Inputs', i + 1, x.name, x.value, x.unit || null, x.source, null];
				}
				for (const [i, x] of e.equations.entries()) {
					yield [...lead, 'Equations', i + 1, null, null, null, null, x];
				}
				for (const [i, x] of e.correlations.entries()) {
					yield [...lead, 'Correlations', i + 1, x.name, null, null, null, x.citation];
				}
				for (const [i, x] of e.dataSources.entries()) {
					yield [...lead, 'Data sources', i + 1, x.name, null, null, null, x.citation];
				}
				for (const [i, x] of e.intermediates.entries()) {
					yield [
						...lead,
						'Intermediate values',
						i + 1,
						x.name,
						x.value,
						x.unit || null,
						null,
						null
					];
				}
				for (const [i, x] of e.notes.entries()) {
					yield [...lead, 'Notes', i + 1, null, null, null, null, x];
				}
			}
		}
	);
}
