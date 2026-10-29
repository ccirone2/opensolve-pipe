/**
 * The documents of an export (proposal export.md §2.7–§2.9, §3.1): About, the traceability record
 * that comes first in every file; README.txt, the CSV zip's first entry; the Methods document, the
 * Methods view's own "Copy as text" (`methodsText`) for each case with a response; and the Goal
 * seek document, the result's own "Copy report" (`goalSeekReport`) in the file's units.
 *
 * About is a three-column document (Section, Item, Value), in the order of decision 13: how to read
 * the file; the export (title, time, contents, units, numbers, sign conventions, what is left out);
 * one block per case; the project links; the goal seek; the software and source links; the
 * disclaimer, verbatim. Values are numbers where they are numbers, with the unit in the item's
 * words. Every local time is computed from the input's `now` and `utcOffsetMinutes`; the web app's
 * source link is `sourceLinks(input.appVersion)`, never the build's own constant.
 */
import type { Project } from '../../api/types';
import { DISCLAIMER, sourceLinks } from '../../components/links';
import { QUANTITIES } from '../compare';
import { projectUrl } from '../encoding';
import { flagText } from '../flag-text';
import { goalSeekReport, outcomeText } from '../goal-seek';
import { CASE_STATUS_LABELS } from '../labels';
import { compareVersions } from '../results';
import { findScenario } from '../scenarios';
import { methodsText, solveStatusLines } from '../trace';
import {
	componentName,
	curvesLeftOut,
	curvesOverlayOnly,
	GROUP_CURVES_ITEM,
	GROUP_CURVES_LEFT_OUT,
	groupCurvesLeftOut,
	noValuesReason,
	type CaseView,
	type ExportContext
} from './context';
import { localIso } from './filename';
import type { CellValue, SheetSpec } from './model';
import { caseColumns, casePrefix, compareNotes, text } from './tables';
import { CELL_LIMIT } from './xlsx';

/** The web app's license (CLAUDE.md, License). */
export const APP_LICENSE = 'AGPL-3.0-or-later';

/** The section that comes first: how to read the file (§2.7). */
export const READING = 'Reading this file';

/** "Each row's case and solve: …" (without scenarios, there is no Case column). */
function rowSolveText(ctx: ExportContext): string {
	return ctx.hasScenarios
		? "Each row's case and solve: the Case, Solved at and Results columns."
		: "Each row's solve: the Solved at and Results columns.";
}

/** The CSV files' reading notes: README.txt's and about.csv's first rows (§2.7, §3.1). */
export function csvReadingNotes(ctx: ExportContext): [string, string][] {
	return [
		[
			'Decimal mark',
			'These CSV files use a comma between fields and a point as the decimal mark (101.325 is about a hundred). For a spreadsheet, open the .xlsx export instead.'
		],
		[
			'Comma-decimal settings',
			'Opened with a comma-decimal setting (German, French and many others), a spreadsheet reads values such as 101.325 as 101325, or as text, without any warning.'
		],
		[
			'Opening in a spreadsheet',
			'LibreOffice: in the Text Import dialog choose Language: English (USA). Excel: use Data › From Text/CSV, File origin 65001: Unicode (UTF-8), then Transform Data, and for each number column Change Type › Using Locale… › English (United States).'
		],
		[
			'Scripts',
			"RFC 4180, UTF-8 with BOM. pandas reads every number exactly with float_precision='round_trip'; Python's csv module needs encoding='utf-8-sig'. A text cell that begins with =, +, -, @, a tab or a carriage return is written with a leading '; numbers and the JSON columns never are."
		],
		['Case and solve', rowSolveText(ctx)]
	];
}

/** The workbook's reading notes (§2.7). */
function xlsxReadingNotes(ctx: ExportContext): [string, string][] {
	return [
		[
			'Layout',
			'Row 1 of each sheet is a caption and row 3 holds the headers (pandas: read_excel(..., sheet_name=None, header=2)).'
		],
		['Case and solve', rowSolveText(ctx)]
	];
}

/** README.txt (§3.1): title, project and time, the reading notes, and where the record is. */
export function readmeLines(ctx: ExportContext): string[] {
	const input = ctx.input;
	return [
		'OpenSolve Pipe results',
		`Project: ${input.project.metadata.name}`,
		`Exported at: ${localIso(input.now, input.utcOffsetMinutes)}`,
		'',
		...csvReadingNotes(ctx).map(([, value]) => value),
		'',
		'The record of the cases, the solves and the software is in about.csv.'
	];
}

type AboutRow = [string, string, CellValue];

/** A project link and the cases it reproduces. */
interface ProjectLink {
	url: string;
	cases: CaseView[];
	/** The project as solved, before later changes (an out-of-date case's). */
	asSolved: boolean;
}

/**
 * Links already encoded, by project (projects are never mutated): the dialog builds the bundle
 * whenever a choice changes, and a large project's link takes a gzip at level 9.
 */
const encodedLinks = new WeakMap<Project, Map<string, string>>();

/** The link of `project`, with `methodVersion` written in (null: as it is). */
function linkOf(project: Project, methodVersion: string | null, origin: string): string {
	let known = encodedLinks.get(project);
	if (!known) {
		known = new Map();
		encodedLinks.set(project, known);
	}
	const key = `${methodVersion ?? '\u0000'}\u0000${origin}`;
	let url = known.get(key);
	if (url === undefined) {
		url = projectUrl(methodVersion === null ? project : { ...project, methodVersion }, origin);
		known.set(key, url);
	}
	return url;
}

/**
 * The distinct project links (§2.7): a current case gets the current project's link (its staleness
 * key equals its solve's, so it reproduces its results, with the current names); an out-of-date
 * case gets the project exactly as sent, with its solve's methods version written in (the store
 * records a version only after a current solve; the fingerprint leaves the version out).
 */
export function projectLinks(ctx: ExportContext): ProjectLink[] {
	const links: ProjectLink[] = [];
	for (const c of ctx.responded) {
		const sent = c.input.sent;
		const url = c.stale
			? sent && linkOf(sent, c.solved!.methodVersion, ctx.input.origin)
			: linkOf(ctx.input.project, null, ctx.input.origin);
		if (!url) continue;
		const known = links.find((l) => l.url === url);
		if (known) known.cases.push(c);
		else links.push({ url, cases: [c], asSolved: c.stale });
	}
	return links;
}

const units = (ctx: ExportContext) => ctx.units;

/**
 * The Units rows (§2.7): every category's unit, the gauge note and the exceptions. `equipment`: the
 * file has an Equipment sheet, whose flow ratio is written in the fraction category (signed and
 * unbounded, Q ÷ Q_r: no 0–1 fraction) and whose Cv or Kv is as entered (lines added only then,
 * so a file without equipment is as before).
 */
function unitRows(ctx: ExportContext, equipment: boolean): AboutRow[] {
	const u = units(ctx);
	const label = (unit: string) => unit || 'none (a pure number)';
	const fractions = equipment ? 'speed, efficiency, flow ÷ rated flow' : 'speed, efficiency';
	const rows: AboutRow[] = [
		['Export', 'Units: elevations and lengths', u.label('length')],
		['Export', 'Units: diameters and roughness', u.label('diameter')],
		['Export', 'Units: heads, grade lines, losses and NPSH', u.label('head')],
		['Export', 'Units: gauge pressure', u.label('pressure', { gauge: true })],
		['Export', 'Units: absolute pressure', u.label('pressure', { absolute: true })],
		['Export', 'Units: pressure difference', u.label('pressure')],
		['Export', 'Units: flow', u.label('flow')],
		['Export', 'Units: velocity', u.label('velocity')],
		['Export', 'Units: temperature', u.label('temperature')],
		['Export', 'Units: density', u.label('density')],
		['Export', 'Units: dynamic viscosity', u.label('viscosity')],
		['Export', 'Units: kinematic viscosity', 'm²/s'],
		['Export', 'Units: power', u.label('power')],
		['Export', `Units: fractions (${fractions})`, label(u.label('fraction'))],
		[
			'Export',
			'Units: gauge and absolute',
			'Pressures are gauge unless marked (a) or psia; differences carry no marker.'
		],
		[
			'Export',
			'Units: exceptions',
			"The trace, the methods text, the server's flag messages and the JSON columns are in SI as the server reported them. The app's sentences (flag messages, the goal seek report) give speeds and efficiencies in % and powers in kW (hp with gpm)." +
				(equipment
					? ' A Cv (US gpm of water at 1 psi) or Kv (m³/h of water at 1 bar) is as entered in every unit system.'
					: '')
		]
	];
	if (u.units === 'si') {
		rows.push([
			'Export',
			'Units: fractions',
			'Fractions (speed, efficiency) are 0–1 and carry no unit.' +
				(equipment
					? ' Flow ÷ rated flow is a signed ratio with no unit: 1 at the rated flow, negative when the flow runs from outlet to inlet.'
					: '')
		]);
	}
	return rows;
}

/** "a", "a and b", "a, b and c". */
function andList(items: readonly string[]): string {
	return items.length < 2
		? (items[0] ?? '')
		: `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/**
 * The Numbers row; `equipment`, `orifices`: the ≈ 0 rule names equipment's and orifice plates'
 * pressure differences too (a file with neither is as before).
 */
function numbersText(equipment: boolean, orifices = false): string {
	const drops = [
		'valve',
		...(equipment ? ['equipment'] : []),
		...(orifices ? ['orifice plate'] : [])
	];
	const losses = [
		...(equipment ? ['equipment pressure losses'] : []),
		...(orifices ? ['orifice plate permanent losses'] : [])
	];
	const pressures = andList([`${andList(drops)} pressure drops`, ...losses]);
	return `Full precision: each number is the value the calculation server returned, converted to these units, not rounded. The app shows 4 significant figures, and heads, elevations and lengths to at least 0.01 m (or its equivalent); it shows head differences below 1×10⁻⁷ m, ${pressures} below ρg·10⁻⁷ m and branch K below 1×10⁻⁴ as ≈ 0 (round-off). The file gives them as computed. Spreadsheets display and re-save at most 15 significant digits.`;
}

/** The orifice plates' sign row, only in a file with an Orifice plates sheet. */
const ORIFICE_SIGN: [string, string] = [
	'Sign: orifice plate flow',
	"+ inlet → outlet; the permanent pressure loss, the differential pressure at the taps and the head loss are signed like it; the static pressure drop, inlet minus outlet, also holds the ports' elevation and velocity terms, so its sign need not follow the flow."
];

/** The equipment sign row, only in a file with an Equipment sheet. */
const EQUIPMENT_SIGN: [string, string] = [
	'Sign: equipment flow',
	"+ inlet → outlet; flow ÷ rated flow, the pressure loss and the head loss are signed like it; the static pressure drop, inlet minus outlet, also holds the ports' elevation and velocity terms, so its sign need not follow the flow."
];

const SIGNS: [string, string][] = [
	['Sign: link flow', '+ from → to'],
	['Sign: valve flow', '+ inlet → outlet'],
	['Sign: pump flow', 'suction → discharge'],
	['Sign: boundary outflow', '+ into the network'],
	['Sign: assigned flow', '+ demand, − supply'],
	['Sign: branch port flow', '+ into the branch'],
	[
		'Sign: losses',
		"Losses are signed like the flow: negative where the flow runs to → from (outlet → inlet for valves); a branch path's loss is positive in the flow direction."
	],
	['Datum', 'Elevations and heads are measured from the project datum.']
];

/** FluidProperties' fields in words (its `sources` are keyed by them). */
const PROPERTY_WORDS: Readonly<Record<string, string>> = {
	density: 'density',
	dynamicViscosity: 'dynamic viscosity',
	kinematicViscosity: 'kinematic viscosity',
	vaporPressure: 'vapor pressure',
	temperature: 'temperature',
	concentration: 'concentration'
};

/** The block of one case (§2.7). */
function caseRows(ctx: ExportContext, c: CaseView, links: ProjectLink[]): AboutRow[] {
	const u = units(ctx);
	const section = ctx.hasScenarios ? `Case: ${c.label}` : 'Results';
	const rows: AboutRow[] = [];
	const add = (item: string, value: CellValue) => rows.push([section, item, value]);
	add('Status', CASE_STATUS_LABELS[c.input.status]);
	const reason = noValuesReason(c);
	add('Values in this file', reason ? `No: ${reason}.` : 'Yes');
	const solved = c.solved;
	const response = c.response;
	if (!solved || !response) {
		if (c.input.status === 'failed' && c.input.error) add('Error', c.input.error);
		return rows;
	}
	// The link only when the file holds one (review V5).
	const holds = ctx.input.options.link
		? 'This file holds the results, names the elements and links the project, as solved.'
		: 'This file holds the results and names the elements as solved (the project link was left out).';
	add('Out of date', c.stale ? `${solveStatusLines({ stale: true }).join(' ')} ${holds}` : 'No');
	add('Solved at', solved.timestamp);
	add('Compute time [s]', response.computeTime);
	add('Calculation methods version', solved.methodVersion);
	const loaded = ctx.input.loadedMethodVersion;
	if (loaded && solved.methodVersion && loaded !== solved.methodVersion) {
		const newer = compareVersions(solved.methodVersion, loaded) > 0;
		add(
			'Calculation methods changed',
			`This project was last solved with calculation methods version ${loaded}. These results use version ${solved.methodVersion}${newer ? '' : ', an older version'}, so some values may differ from the ones it was shared with.`
		);
	}
	for (const [name, version] of Object.entries(solved.trace.methods.libraries)) {
		add(`Server library: ${name}`, version);
	}
	const conv = solved.convergence;
	add('Converged', response.success && solved.converged);
	add('Inner iterations', conv.innerIterations);
	add('Outer iterations', conv.outerIterations);
	add('Largest continuity residual [m³/s]', conv.maxContinuityResidual.value);
	add('Largest continuity residual at', conv.maxContinuityResidual.elementId);
	add('Largest energy residual [m]', conv.maxEnergyResidual.value);
	add('Largest energy residual at', conv.maxEnergyResidual.elementId);
	add('Oscillating components', conv.oscillatingComponents.join('; ') || 'None');
	add('Convergence message', conv.message);
	add(
		`Atmospheric pressure used [${u.label('pressure', { absolute: true })}]`,
		u.value(solved.atmosphericPressure, 'pressure')
	);
	add(
		`Site elevation [${u.label('length')}]`,
		u.value(c.structure.settings.siteElevation, 'length')
	);
	const fluid = solved.fluid;
	add('Fluid', fluid.name);
	add(`Fluid temperature [${u.label('temperature')}]`, u.value(fluid.temperature, 'temperature'));
	add('Fluid concentration [mass fraction, 0–1]', fluid.concentration);
	add(`Fluid density [${u.label('density')}]`, u.value(fluid.density, 'density'));
	add(
		`Fluid dynamic viscosity [${u.label('viscosity')}]`,
		u.value(fluid.dynamicViscosity, 'viscosity')
	);
	add('Fluid kinematic viscosity [m²/s]', fluid.kinematicViscosity);
	if (fluid.vaporPressure === null) add('Fluid vapor pressure', 'Not available');
	else {
		add(
			`Fluid vapor pressure [${u.label('pressure', { absolute: true })}]`,
			u.value(fluid.vaporPressure, 'pressure')
		);
	}
	for (const [property, source] of Object.entries(fluid.sources)) {
		const words = PROPERTY_WORDS[property] ?? property;
		add(`Source of the fluid's ${words}`, `${source.origin}: ${source.citation}`);
	}
	if (c.hasValues) {
		const row = (quantity: 'lowestPressure' | 'highestVelocity') => ({ quantity });
		const lowest = QUANTITIES.lowestPressure;
		const pressure = lowest.value(solved, row('lowestPressure'));
		if (typeof pressure === 'number') {
			add(
				`Lowest static pressure [${u.label('pressure', { gauge: true })}]`,
				u.value(pressure, 'pressure')
			);
			add('Lowest static pressure at', lowest.where!(solved, c.names) || null);
		}
		const fastest = QUANTITIES.highestVelocity;
		const velocity = fastest.value(solved, row('highestVelocity'));
		if (typeof velocity === 'number') {
			add(`Highest velocity [${u.label('velocity')}]`, u.value(velocity, 'velocity'));
			add('Highest velocity in', fastest.where!(solved, c.names) || null);
		}
	}
	const scenario = response.scenario;
	if (scenario) {
		if (scenario.description) add('Scenario description', scenario.description);
		const applied = scenario.overrides.filter((o) => o.state === 'applied').length;
		add('Scenario changes applied', applied);
		add('Scenario changes not applied', scenario.overrides.length - applied);
	}
	if (c.hasValues) {
		const pumps = Object.keys(solved.pumpResults);
		if (pumps.length) {
			// One rule with the System curves sheet: a pump is included when any curve of it is
			// ready in the case's slot, its default range or a range another case's chart drew.
			const out = curvesLeftOut(c);
			const included = pumps.filter((p) => !out.some((o) => o.pumpId === p));
			add(
				'System curves included',
				included.length ? included.map((p) => componentName(c, p)).join('; ') : 'None'
			);
			for (const { pumpId, reason } of curvesOverlayOnly(c)) {
				add(
					`System curve of ${componentName(c, pumpId)}`,
					`Included only over another case's chart range (Flow from and Flow to in System curves), where it was drawn for comparison; its default range is not in the file (${reason})`
				);
			}
			for (const { pumpId, reason } of out) {
				add(`System curve of ${componentName(c, pumpId)}`, `Not included: ${reason}`);
			}
		}
	}
	if (ctx.input.options.link) {
		const index = links.findIndex((l) => l.cases.includes(c));
		add('Project link', index >= 0 ? `Link ${index + 1} below reproduces this case` : null);
	} else {
		add('Project link', 'Left out when exported');
	}
	return rows;
}

/** The goal seek on an exported case, when it finished with an answer. */
function exportedGoalSeek(ctx: ExportContext) {
	const gs = ctx.input.goalSeek;
	if (gs?.status !== 'done' || !gs.response) return null;
	const c = ctx.cases.find((x) => x.input.id === gs.run.caseId);
	return c ? { gs, response: gs.response, c } : null;
}

/** What a goal seek's words need, in the file's units (§2.9). */
function goalSeekContext(ctx: ExportContext) {
	const found = exportedGoalSeek(ctx);
	if (!found) return null;
	const { gs, response, c } = found;
	const project = ctx.input.project;
	const name = findScenario(project, gs.run.caseId)?.name ?? c.input.name;
	const words = {
		labels: project,
		sent: gs.run.project,
		prefs: units(ctx).prefs,
		caseWords: gs.run.caseId === null ? 'the base case' : `scenario ${name}`,
		caseId: gs.run.caseId,
		...(gs.stale ? { stale: true } : {})
	};
	const solved = response.solvedState;
	const valveTypes = solved
		? Object.fromEntries(Object.entries(solved.valveResults).map(([id, v]) => [id, v.valveType]))
		: {};
	const invalidFlags = (solved?.flags ?? [])
		.filter((f) => f.severity === 'invalid')
		.map((f) =>
			flagText(f, {
				project,
				prefs: words.prefs,
				fittingName: ctx.fittingName,
				valveTypes
			})
		);
	return {
		gs,
		response,
		c,
		name,
		words,
		report: {
			...words,
			projectName: project.metadata.name,
			caseText: gs.run.caseId === null ? 'base case' : `scenario ${name} (${gs.run.caseId})`,
			startedAt: gs.run.startedAt,
			utcOffsetMinutes: ctx.input.utcOffsetMinutes,
			stale: gs.stale,
			invalidFlags,
			converged: !!solved?.converged
		}
	};
}

/** The goal seek's About block (§2.7). */
function goalSeekRows(ctx: ExportContext): AboutRow[] {
	const g = goalSeekContext(ctx);
	if (!g) return [];
	const section = 'Goal seek';
	const applied = g.gs.applied;
	const appliedName =
		applied &&
		(applied.caseId === null
			? 'the base case'
			: `scenario ${findScenario(ctx.input.project, applied.caseId)?.name ?? applied.caseId}`);
	return [
		[section, 'Ran on', ctx.hasScenarios ? g.c.label : 'Base case'],
		[section, 'Ran at', localIso(g.gs.run.startedAt, ctx.input.utcOffsetMinutes)],
		[section, 'Outcome', outcomeText(g.response, g.words, g.gs.run.request).title],
		[section, 'Out of date', g.gs.stale ? 'Yes: the project changed after this goal seek' : 'No'],
		[
			section,
			'Values applied',
			applied ? `Yes, to ${appliedName}${g.gs.appliedCurrent ? '' : ' (changed since)'}` : 'No'
		],
		[
			section,
			'Report',
			'The Goal seek sheet (goal-seek.txt) holds the report, with the exact values found.'
		]
	];
}

/** The Goal seek document (§2.9): the report of Copy report, one row per line, tab parts in cells. */
export function goalSeekSheet(ctx: ExportContext): SheetSpec | null {
	const g = goalSeekContext(ctx);
	if (!g) return null;
	const lines = goalSeekReport(g.response, g.gs.run.request, g.report).split('\n');
	const width = Math.max(1, ...lines.map((l) => l.split('\t').length));
	return {
		id: 'goal-seek',
		title: 'Goal seek',
		file: 'goal-seek.txt',
		kind: 'document',
		columns: Array.from({ length: width }, (_, i) =>
			text(i === 0 ? 'Goal seek report' : `Part ${i + 1}`)
		),
		rowCount: lines.length,
		*rows() {
			for (const line of lines) yield line.split('\t');
		},
		*text() {
			yield* lines;
		}
	};
}

/** Each case's methods text, exactly as the Methods view's Copy as text gives it (§2.8). */
function methodsTexts(ctx: ExportContext): { c: CaseView; text: string }[] {
	return ctx.responded.map((c) => {
		const response = c.response!;
		const solved = response.solvedState;
		const text = methodsText(solved.trace.methods, {
			projectName: c.names.metadata.name,
			...(ctx.hasScenarios
				? {
						caseName: response.scenario
							? `scenario ${response.scenario.name} (${response.scenario.id})`
							: 'base case'
					}
				: {}),
			timestamp: solved.timestamp,
			converged: response.success && solved.converged,
			stale: c.stale
		});
		return { c, text };
	});
}

/** The Methods document: one row per line, with its case and solve; methods.txt, cases in order. */
export function methodsSheet(ctx: ExportContext): SheetSpec | null {
	if (!ctx.responded.length) return null;
	const texts = methodsTexts(ctx).map(({ c, text: t }) => ({
		c,
		lines: t.replace(/\n$/, '').split('\n')
	}));
	return {
		id: 'methods',
		title: 'Methods',
		file: 'methods.txt',
		kind: 'document',
		columns: [...caseColumns(ctx), text('Text')],
		rowCount: texts.reduce((n, t) => n + t.lines.length, 0),
		*rows() {
			for (const { c, lines } of texts) {
				const prefix = casePrefix(ctx, c);
				for (const line of lines) yield [...prefix, line];
			}
		},
		*text() {
			for (const [i, { lines }] of texts.entries()) {
				if (i > 0) yield '';
				yield* lines;
			}
		}
	};
}

/** Software and source links (§2.7). */
function softwareRows(ctx: ExportContext): AboutRow[] {
	const input = ctx.input;
	return [
		['Software', 'Web app version (build commit)', input.appVersion],
		['Software', 'Web app source, at that commit', sourceLinks(input.appVersion).source],
		['Software', 'Web app license', APP_LICENSE],
		['Software', 'Calculation server source (for the commit it runs now)', input.serverSource]
	];
}

/** The About rows. `sheets`: the other sheets of the file, for its contents. */
export function aboutRows(
	ctx: ExportContext,
	sheets: readonly Pick<SheetSpec, 'title' | 'file' | 'rowCount'>[]
): AboutRow[] {
	const input = ctx.input;
	const csv = input.options.format === 'csv';
	const rows: AboutRow[] = [];
	for (const [item, value] of csv ? csvReadingNotes(ctx) : xlsxReadingNotes(ctx)) {
		rows.push([READING, item, value]);
	}
	const project = input.project;
	rows.push(['Export', 'Title', 'OpenSolve Pipe results']);
	rows.push(['Export', 'Project', project.metadata.name]);
	if (project.metadata.description)
		rows.push(['Export', 'Project description', project.metadata.description]);
	rows.push(['Export', 'Exported at', localIso(input.now, input.utcOffsetMinutes)]);
	const shown = ctx.cases[0];
	rows.push([
		'Export',
		'Contents',
		!ctx.hasScenarios
			? 'The results'
			: ctx.single && shown
				? `Case shown: ${shown.label}`
				: 'All cases'
	]);
	for (const sheet of sheets) {
		rows.push(['Export', csv ? `File: ${sheet.file}` : `Sheet: ${sheet.title}`, sheet.rowCount]);
	}
	// Lines about equipment only with an Equipment sheet: a file without one is as before.
	const equipment = sheets.some((sheet) => sheet.file === 'equipment.csv');
	// And about orifice plates only with an Orifice plates sheet.
	const orifices = sheets.some((sheet) => sheet.file === 'orifices.csv');
	rows.push(...unitRows(ctx, equipment));
	rows.push(['Export', 'Numbers', numbersText(equipment, orifices)]);
	for (const [item, value] of SIGNS) {
		rows.push(['Export', item, value]);
		if (equipment && item === 'Sign: valve flow') rows.push(['Export', ...EQUIPMENT_SIGN]);
		if (orifices && item === 'Sign: valve flow') rows.push(['Export', ...ORIFICE_SIGN]);
	}
	// Design checks (D19), only in a file that has them.
	if (sheets.some((sheet) => sheet.file === 'design-checks.csv')) {
		rows.push([
			'Export',
			'Design checks',
			"Opt-in design practice the project turned on, not physics flags: a check never changes a value. Each row's value and limits are in its Unit (a pump's manufacturer data compared at rated speed, flow ÷ speed). " +
				(ctx.units.units === 'si'
					? "A pump's flow ÷ best efficiency flow is a ratio with no unit, 1 at the best efficiency flow, not a 0–1 fraction. "
					: "A pump's flow ÷ best efficiency flow is in the fractions' unit. ") +
				"The Result words are the app's sentences, which give fractions in % and powers in kW (hp with gpm). Pipe numbers count from 1."
		]);
	}
	// Compare cases names connections by their ends now: what reads otherwise than as solved.
	const compared = compareNotes(ctx);
	if (compared.reversed.length) {
		rows.push([
			'Export',
			'Sign: Compare cases',
			`A connection's flow and head loss are given in its direction now. Reversed since its case was solved, so with the other sign than in that case's tables: ${compared.reversed.join('; ')}.`
		]);
	}
	// Not in this file, and why.
	const left: [string, string][] = [];
	for (const { what, reason } of compared.leftOut) left.push([`Compare cases: ${what}`, reason]);
	if (!ctx.single)
		left.push(['Trace', 'not in an All cases export: export one case to include it']);
	for (const c of ctx.cases) {
		const reason = noValuesReason(c);
		if (reason) left.push([ctx.hasScenarios ? `Values of ${c.label}` : 'Values', reason]);
	}
	for (const c of ctx.valued) {
		for (const { pumpId, reason } of curvesLeftOut(c)) {
			const what = `System curve of ${componentName(c, pumpId)}`;
			left.push([ctx.hasScenarios ? `${what} (${c.label})` : what, reason]);
		}
	}
	if (groupCurvesLeftOut(ctx)) left.push([GROUP_CURVES_ITEM, GROUP_CURVES_LEFT_OUT]);
	if (!input.options.link) left.push(['Project link', 'left out when exported']);
	for (const [item, value] of left) rows.push(['Not in this file', item, value]);

	const links = input.options.link ? projectLinks(ctx) : [];
	for (const c of ctx.cases) rows.push(...caseRows(ctx, c, links));
	for (const [i, link] of links.entries()) {
		const section = 'Project links';
		const name = `Link ${i + 1}`;
		const value =
			!csv && link.url.length > CELL_LIMIT
				? `Not included: ${link.url.length} characters, more than a spreadsheet cell holds; copy it from Share in the app`
				: link.url;
		rows.push([section, name, value]);
		rows.push([
			section,
			`${name} reproduces`,
			ctx.hasScenarios ? link.cases.map((c) => c.label).join('; ') : 'These results'
		]);
		if (link.asSolved)
			rows.push([section, `${name} is`, 'the project as solved, before the later changes']);
		// Without scenarios the app has no Case choice to point to.
		if (ctx.hasScenarios) {
			rows.push([
				section,
				`${name}: case`,
				'It opens on the base case; choose the case under Case.'
			]);
		}
		rows.push([
			section,
			`${name}: contents`,
			'It holds the whole project: every input and every scenario.'
		]);
		rows.push([section, `${name}: form`, 'Plain text: copy it into a browser.']);
		rows.push([
			section,
			`${name}: later versions`,
			'A link may fail to open, or solve differently, after a later change to the app; the methods version above records what produced these results.'
		]);
	}
	rows.push(...goalSeekRows(ctx));
	rows.push(...softwareRows(ctx));
	rows.push(['Disclaimer', 'Disclaimer', DISCLAIMER]);
	return rows;
}

/** The About sheet (about.csv): Section, Item, Value. */
export function aboutSheet(ctx: ExportContext, sheets: readonly SheetSpec[]): SheetSpec {
	const rows = aboutRows(ctx, sheets);
	return {
		id: 'about',
		title: 'About',
		file: 'about.csv',
		kind: 'document',
		columns: [text('Section'), text('Item'), text('Value')],
		rowCount: rows.length,
		*rows() {
			yield* rows;
		}
	};
}
