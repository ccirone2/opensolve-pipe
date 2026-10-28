/**
 * The export model (proposal export.md §2, §3.6): what a file holds, built from a snapshot of the
 * page taken at the click (`ExportInput`, input.ts) and nothing else. `buildExport` is pure and
 * deterministic: it imports no module constant that depends on the build or the environment
 * (SOURCE_URL, apiBaseUrl), reads no clock, time zone or random source, and builds no cells: each
 * sheet's rows are an iterable built on the fly as a writer asks for them (rows built in advance
 * would double the memory of a large workbook, §4.4), so the dialog can call it whenever a choice
 * changes and list the sheets, their row counts, what is left out and the file name, from the very
 * function that makes the file.
 *
 * What a case gives is decided by its response (Compare's rule, `caseResponse`), `hasValues`
 * (the response converged) and `stale` (results out of date), never by its status alone (§2.4):
 * a converged response gives every table, labelled when out of date; one that did not converge,
 * current or out of date, gives its About block, flags, scenario changes and methods only; a case
 * without a response is a line in About.
 */
import type { Project, SolveResponse, UnitPreferences } from '../../api/types';
import type { GoalSeekFinished, CaseStatus, SystemCurveState } from '../../state/project.svelte';
import type { CompareRow } from '../compare';
import type { CaseId } from '../scenarios';
import { aboutSheet, goalSeekSheet, methodsSheet, readmeLines } from './about';
import { caption, exportContext, warnings, omitted, type ExportContext } from './context';
import { exportFileName, zipFolderName } from './filename';
import {
	compareNotes,
	compareSheet,
	elementTables,
	designChecksTable,
	flagsTable,
	projectLibraryTable,
	scenarioChangesTable,
	traceTable
} from './tables';

/** A cell: a number, text, a boolean, or none (an empty cell). */
export type CellValue = string | number | boolean | null;

export interface ExportColumn {
	label: string;
	/** The unit label in the header ("kPa(g)"): "Label [unit]". */
	unit?: string;
	/** How the CSV writer guards text: a `json` cell that is a JSON number is never guarded. */
	kind: 'text' | 'number' | 'boolean' | 'json';
	/** Width in characters (XLSX); default from the header and the first 200 rows. */
	width?: number;
}

export interface ExportSheet {
	/** 'nodes'. */
	id: string;
	/** The sheet's name: 'Nodes'. */
	title: string;
	/** The CSV zip's file: 'nodes.csv', or 'methods.txt' for a text document. */
	file: string;
	kind: 'table' | 'document';
	/** XLSX row 1. */
	caption: string;
	columns: readonly ExportColumn[];
	rowCount: number;
	/** The rows, built on the fly. */
	rows: () => Iterable<readonly CellValue[]>;
	/** A text document's lines, for its .txt file (the sheet holds `rows`). */
	text?: () => Iterable<string>;
}

export interface ExportWarning {
	kind: 'not_converged' | 'stale' | 'failed_shown';
	text: string;
}

export interface ExportBundle {
	sheets: readonly ExportSheet[];
	/** What the dialog lists as left out. */
	omitted: readonly { what: string; reason: string }[];
	warnings: readonly ExportWarning[];
	fileName: string;
	/** The CSV zip's inner folder; null for XLSX. */
	folder: string | null;
	/** The workbook's title (docProps/core.xml): the project's name. */
	title: string;
	/** The export's time. */
	created: Date;
	/** The local time's offset from UTC at the export (minutes): the zip's DOS times. */
	utcOffsetMinutes: number;
	/** README.txt's lines (the CSV zip's first entry). */
	readme: readonly string[];
}

export interface WriteOptions {
	signal?: AbortSignal;
	onProgress?: (p: { sheet: number; sheets: number; title: string }) => void;
}

/** The dialog's choices (§2.1, §5.3). */
export interface ExportOptions {
	/** The case shown, or every case (with scenarios). */
	cases: 'shown' | 'all';
	format: 'xlsx' | 'csv';
	/** The project's display units, or SI base units. */
	units: 'display' | 'si';
	/** Include the project link. */
	link: boolean;
}

/** The library's names, as data (the material and fitting names, the NPS designations). */
export interface ExportLibrary {
	/** Material id → name. */
	materials: Readonly<Record<string, string>>;
	/** Fitting type → name. */
	fittings: Readonly<Record<string, string>>;
	nominalSizes: readonly { nominalSize: number; nps: string }[];
}

/** One exported case, as the page holds it at the click. */
export interface ExportCase {
	/** null: the base case. */
	id: CaseId;
	/** "Base case" or the scenario's name (ws.caseName). */
	name: string;
	/** Its status: for the words only, never for convergence. */
	status: CaseStatus;
	/** Its response by Compare's rule (caseResponse): null when failed or not reached. */
	response: SolveResponse | null;
	/** The response's results are out of date (false without a response). */
	stale: boolean;
	/** The latest solve failed: its error message (else null). */
	error: string | null;
	/** A response is kept on screen that Compare's rule does not use (failed, not reached). */
	keptResponse: boolean;
	/** The project exactly as sent for the response's solve. */
	sent: Project | null;
	/** The case as solved (the scenario applied to the project sent). */
	inputs: Project | null;
	/** Its computed system curves (the case's slot: pump id, or pump id NUL min NUL max). */
	systemCurves: Readonly<Record<string, SystemCurveState>>;
}

/** Everything an export reads, taken at the click (§2.1). */
export interface ExportInput {
	options: ExportOptions;
	now: Date;
	/** −now.getTimezoneOffset(): every local time is computed from `now` and this. */
	utcOffsetMinutes: number;
	/** The build commit (`version` from $app/environment). */
	appVersion: string;
	/** The calculation server's source link (serverSourceHref()). */
	serverSource: string;
	/** location.origin, for links. */
	origin: string;
	/** The current project (base and scenarios). */
	project: Project;
	/** The display units. */
	prefs: UnitPreferences;
	library: ExportLibrary;
	/** The case shown (null: the base case). */
	shownCase: CaseId;
	/** The exported cases, in case order (the base, then the scenarios). */
	cases: readonly ExportCase[];
	/** The rows chosen on the Compare tab (or its defaults). */
	compareRows: readonly CompareRow[];
	/** The latest finished goal seek (done or failed), or null. */
	goalSeek: GoalSeekFinished | null;
	/** The methods version the link recorded when it was opened ('' if none). */
	loadedMethodVersion: string;
}

/** A sheet without its caption, as the tables give it. */
export type SheetSpec = Omit<ExportSheet, 'caption'>;

/** The sheets of a context in the order of §2.5. */
function sheetsOf(ctx: ExportContext): SheetSpec[] {
	const tables = elementTables(ctx);
	const before: SheetSpec[] = [flagsTable(ctx)];
	// Design checks (D19), only when a case has some: a file without them is as before.
	const checks = designChecksTable(ctx);
	if (checks.rowCount > 0) before.push(checks);
	const compare = compareSheet(ctx);
	if (compare) before.push(compare);
	const after = [
		// The project library (D21), only in a file with one: a file without one is as before.
		projectLibraryTable(ctx),
		scenarioChangesTable(ctx),
		goalSeekSheet(ctx),
		methodsSheet(ctx),
		traceTable(ctx)
	];
	return [
		...before,
		...tables.filter((t) => t.rowCount > 0),
		...after.filter((t): t is SheetSpec => !!t && t.rowCount > 0)
	];
}

/** The file of `input`: its sheets (rows built on the fly), what is left out, warnings, names. */
export function buildExport(input: ExportInput): ExportBundle {
	const ctx = exportContext(input);
	const rest = sheetsOf(ctx);
	const about = aboutSheet(ctx, rest);
	const sheets = [about, ...rest].map((sheet): ExportSheet => ({
		...sheet,
		caption: caption(ctx, sheet)
	}));
	const { options } = input;
	const project = input.project.metadata.name;
	const shown = ctx.single ? ctx.cases[0] : undefined;
	return {
		sheets,
		omitted: [
			...omitted(ctx),
			...compareNotes(ctx).leftOut.map(({ what, reason }) => ({
				what: `Compare cases: ${what}`,
				reason
			}))
		],
		warnings: warnings(ctx),
		fileName: exportFileName({
			project,
			case: ctx.hasScenarios ? (shown ? shown.input.name : 'All cases') : null,
			content: options.format === 'csv' ? 'results (CSV)' : 'results',
			ext: options.format === 'csv' ? 'zip' : 'xlsx',
			now: input.now,
			utcOffsetMinutes: input.utcOffsetMinutes,
			notConverged: !!shown?.response && !shown.hasValues
		}),
		folder: options.format === 'csv' ? zipFolderName(input.now, input.utcOffsetMinutes) : null,
		title: project,
		created: input.now,
		utcOffsetMinutes: input.utcOffsetMinutes,
		readme: readmeLines(ctx)
	};
}
