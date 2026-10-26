/**
 * The export's snapshot (proposal export.md §2.1): everything a file reads, taken from the
 * workspace's public getters at the moment Download is pressed (and whenever the dialog lists the
 * contents). The model (model.ts) then builds the file from this alone.
 *
 * - The page: `now` and its offset from UTC (every local time in the file is computed from these
 *   two), the build commit (`version`), the calculation server's source link and the page's origin.
 * - The current project, the display units and the library's names (as data).
 * - Each exported case in case order (the base, then the scenarios): its name and status, its
 *   response by Compare's rule (`caseResponse`: none for a failed case or one a stopped run did not
 *   reach), whether that response is out of date, the project as sent and the case as solved, and
 *   its computed system curves (read only: the export never computes one).
 * - The rows chosen on the Compare tab (or its defaults, as CompareView computes them), the latest
 *   finished goal seek, and the methods version the link recorded.
 *
 * The store replaces these objects and never mutates them, so the snapshot holds references.
 */
import { version } from '$app/environment';
import type { Project, UnitPreferences } from '../../api/types';
import { serverSourceHref } from '../../components/links';
import {
	finishedGoalSeek,
	type CaseStatus,
	type GoalSeekState,
	type ResultsState,
	type SystemCurveState
} from '../../state/project.svelte';
import { caseResponse, defaultRows, type CompareRow } from '../compare';
import { CANONICAL_ORIGIN } from '../encoding';
import { scenariosOf, type CaseId } from '../scenarios';
import type { ExportCase, ExportInput, ExportLibrary, ExportOptions } from './model';

/** What the snapshot reads from the workspace (its public getters; a Workspace satisfies it). */
export interface ExportSource {
	readonly store: {
		readonly project: Project;
		readonly activeCase: CaseId;
		readonly caseIds: CaseId[];
		caseStatus(caseId: CaseId): CaseStatus;
		resultsFor(caseId: CaseId): ResultsState;
		sentProjectFor(caseId: CaseId): Project | null;
		caseInputs(caseId: CaseId): Project | null;
		systemCurvesFor(caseId: CaseId): Readonly<Record<string, SystemCurveState>>;
		readonly goalSeek: GoalSeekState;
		readonly loadedMethodVersion: string;
	};
	readonly displayUnits: UnitPreferences;
	readonly library: {
		readonly materials: readonly { id: string; name: string }[];
		readonly fittings: readonly { type: string; name: string }[];
		readonly nominalSizes: readonly { nominalSize: number; nps: string }[];
	};
	readonly compareRows: readonly CompareRow[] | null;
	caseName(caseId: CaseId): string;
}

/** The page's own facts: the build commit, the server's source link and the origin. */
export interface PageFacts {
	appVersion: string;
	serverSource: string;
	origin: string;
}

/** The page's facts as the browser gives them (the build version, PUBLIC_API_URL, location). */
export function pageFacts(): PageFacts {
	const origin =
		typeof location !== 'undefined' && location.origin && location.origin !== 'null'
			? location.origin
			: CANONICAL_ORIGIN;
	return { appVersion: version, serverSource: serverSourceHref(), origin };
}

/** The library's names as data. */
function libraryOf(library: ExportSource['library']): ExportLibrary {
	return {
		materials: Object.fromEntries(library.materials.map((m) => [m.id, m.name])),
		fittings: Object.fromEntries(library.fittings.map((f) => [f.type, f.name])),
		nominalSizes: library.nominalSizes.map((s) => ({ nominalSize: s.nominalSize, nps: s.nps }))
	};
}

/** One case as the store holds it now. */
function caseOf(ws: ExportSource, caseId: CaseId): ExportCase {
	const store = ws.store;
	const status = store.caseStatus(caseId);
	const results = store.resultsFor(caseId);
	const response = caseResponse(status, results);
	return {
		id: caseId,
		name: ws.caseName(caseId),
		status,
		response,
		stale: !!response && results.stale,
		error: status === 'failed' ? (results.error?.message ?? null) : null,
		keptResponse: !response && !!results.response,
		sent: response ? store.sentProjectFor(caseId) : null,
		inputs: response ? store.caseInputs(caseId) : null,
		systemCurves: response ? store.systemCurvesFor(caseId) : {}
	};
}

/** The snapshot of `ws` for `options`, at `now` (§2.1). `page` defaults to the browser's. */
export function exportInput(
	ws: ExportSource,
	options: ExportOptions,
	now: Date,
	page: PageFacts = pageFacts()
): ExportInput {
	const store = ws.store;
	const project = store.project;
	const all = store.caseIds;
	const hasScenarios = scenariosOf(project).length > 0;
	const exported =
		options.cases === 'all' && hasScenarios
			? all
			: [all.includes(store.activeCase) ? store.activeCase : null];
	const cases = exported.map((c) => caseOf(ws, c));
	// The Compare tab's rows: chosen, or its defaults from every case's response (CompareView).
	const compareRows =
		ws.compareRows ??
		defaultRows(
			project,
			all.map((c) => caseResponse(store.caseStatus(c), store.resultsFor(c))?.solvedState ?? null)
		);
	return {
		options,
		now,
		utcOffsetMinutes: -now.getTimezoneOffset(),
		appVersion: page.appVersion,
		serverSource: page.serverSource,
		origin: page.origin.replace(/\/+$/, ''),
		project,
		prefs: ws.displayUnits,
		library: libraryOf(ws.library),
		shownCase: store.activeCase,
		cases,
		compareRows,
		goalSeek: finishedGoalSeek(store.goalSeek),
		loadedMethodVersion: store.loadedMethodVersion
	};
}
