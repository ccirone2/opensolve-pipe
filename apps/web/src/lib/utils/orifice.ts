/**
 * An orifice plate's pipe bore D and diameter ratio β = d ÷ D, as far as the browser can know them
 * before a solve (proposal orifice-plate.md §6 W3): D is the inner diameter of the inlet pipe's end
 * segment at the inlet port (decision 3), the one the solver uses, resolved as the piping editor
 * resolves a pipe (piping.ts resolvedPipe: a user override, else the library size entry; a pipe of
 * a project library spec, its spec's inner diameter, CLAUDE.md D21). Nothing
 * here is a hydraulic value: β is a ratio of two inputs, shown read-only beside the bore, and the
 * solve's own β is in its results (OrificeResult.beta). No ISO 5167-2 range is checked here: those
 * limits are the API's (D10, read never copy), and the solve flags them.
 */
import type {
	OrificeTaps,
	PipeConnection,
	PipeDefinition,
	PipeSize,
	PipeSpec,
	Project,
	UnitPreferences
} from '../api/types';
import { connectionAtPort } from './graph';
import { npsLabel } from './labels';
import { CUSTOM_MATERIAL_ID, resolvedPipe } from './piping';
import { entryName, pipeSpecOf } from './project-library';
import { formatValue } from './units';

/** A plate's pressure taps in words (the form's choice, the export's Taps column). */
export const TAP_LABELS: Readonly<Record<OrificeTaps, string>> = {
	corner: 'Corner',
	flange: 'Flange',
	d_and_d_2: 'D and D/2'
};

/** A plate without pressure taps: a restriction orifice, with no reading. */
export const NO_TAPS_LABEL = 'None (a restriction orifice)';

/**
 * The pipe segment of `connection` that meets port `portId` of `componentId`: its first pipe at
 * the 'from' end, its last at the 'to' end. The solver sizes the port by that pipe, not by the
 * port's nominal size.
 */
export function pipeAtPort(
	connection: PipeConnection,
	componentId: string,
	portId: string
): { pipe: PipeDefinition; index: number } {
	const pipes = connection.piping.pipes;
	const atFrom = connection.fromComponentId === componentId && connection.fromPortId === portId;
	const index = atFrom ? 0 : pipes.length - 1;
	return { pipe: pipes[index] as PipeDefinition, index };
}

/** What the pipe library must answer for D (a LibraryStore, or a fake in tests). */
export interface PipeSizes {
	readonly libraryStatus: 'idle' | 'loading' | 'ready' | 'unavailable';
	size(
		materialId: string,
		scheduleId: string | null | undefined,
		nominalSize: number | null | undefined
	): PipeSize | undefined;
}

/** The inlet pipe's inner diameter D, or why it is not known yet. */
export type InletBore =
	/** The inlet port has no connection (the solve reports UNCONNECTED_PORT). */
	| { state: 'unconnected' }
	/** A library pipe while the pipe library has not loaded (or could not be reached). */
	| { state: 'library'; pipe: PipeDefinition }
	/**
	 * A pipe whose inner diameter neither the pipe nor the library gives (a topology issue), or a
	 * pipe of a project library spec the project does not have (UNKNOWN_PIPE_SPEC).
	 */
	| { state: 'unknown'; pipe: PipeDefinition }
	/** `spec`: the project library spec the pipe refers to, which gives D. */
	| { state: 'known'; diameter: number; pipe: PipeDefinition; spec?: PipeSpec };

/** D for the orifice plate `componentId` of `project`: its inlet pipe's end segment's bore. */
export function inletBore(project: Project, componentId: string, library: PipeSizes): InletBore {
	const connection = connectionAtPort(project, componentId, 'inlet');
	if (!connection) return { state: 'unconnected' };
	const { pipe } = pipeAtPort(connection, componentId, 'inlet');
	if (!pipe) return { state: 'unconnected' };
	if (pipe.specId != null) {
		// A project library spec gives the bore itself (CLAUDE.md D21): no library lookup.
		const spec = pipeSpecOf(project, pipe.specId);
		return spec && spec.innerDiameter > 0
			? { state: 'known', diameter: spec.innerDiameter, pipe, spec }
			: { state: 'unknown', pipe };
	}
	const custom = pipe.materialId === CUSTOM_MATERIAL_ID;
	if (pipe.innerDiameter == null && !custom && library.libraryStatus !== 'ready') {
		return { state: 'library', pipe };
	}
	const size =
		custom || pipe.materialId == null
			? undefined
			: library.size(pipe.materialId, pipe.schedule, pipe.nominalSize);
	const diameter = resolvedPipe(pipe, size).innerDiameter;
	return diameter != null && diameter > 0
		? { state: 'known', diameter, pipe }
		: { state: 'unknown', pipe };
}

/**
 * "NPS 4, Sch 40", "NPS 4, Sch 40, inner diameter override", "a custom pipe", or "pipe spec “NPS 60
 * STD”" (a project library spec).
 */
function pipeWords(
	pipe: PipeDefinition,
	nominalSizes: readonly { nominalSize: number; nps: string }[],
	spec?: PipeSpec
) {
	if (spec) return `pipe spec ${entryName(spec)}`;
	if (pipe.materialId === CUSTOM_MATERIAL_ID || pipe.nominalSize == null) return 'a custom pipe';
	const parts = [npsLabel(pipe.nominalSize, nominalSizes)];
	if (pipe.schedule) parts.push(`Sch ${pipe.schedule}`);
	if (pipe.innerDiameter != null) parts.push('inner diameter override');
	return parts.join(', ');
}

/** The β line beside the bore: its text, and whether it warns (β ≥ 1: the solve refuses it). */
export interface BetaLine {
	text: string;
	warning: boolean;
	/** β = d ÷ D when D is known (absent otherwise). */
	beta?: number;
}

/**
 * The β line of the form (W3): "β = d ÷ D = 0.4890, with D = 102.3 mm, the inner diameter of the
 * inlet pipe (NPS 4, Sch 40)"; until D is known, when it will be shown; and, as a warning, a bore
 * not smaller than D, which the solve refuses (ORIFICE_OUT_OF_RANGE). β to 4 decimals, D in the
 * display unit of diameters.
 */
export function betaLine(
	boreDiameter: number,
	inlet: InletBore,
	units: UnitPreferences,
	nominalSizes: readonly { nominalSize: number; nps: string }[] = []
): BetaLine {
	switch (inlet.state) {
		case 'unconnected':
			return { text: 'β is shown once the inlet is connected.', warning: false };
		case 'library':
			return { text: 'β is shown once the pipe library loads.', warning: false };
		case 'unknown':
			return {
				text: "β is shown once the inlet pipe's inner diameter is known.",
				warning: false
			};
	}
	const d = formatValue(inlet.diameter, 'diameter', units);
	const beta = boreDiameter / inlet.diameter;
	if (!(beta < 1)) {
		return {
			text: `β ≥ 1: the bore is not smaller than the inlet pipe's (${d}); the solve refuses it.`,
			warning: true,
			beta
		};
	}
	return {
		text: `β = d ÷ D = ${beta.toFixed(4)}, with D = ${d}, the inner diameter of the inlet pipe (${pipeWords(inlet.pipe, nominalSizes, inlet.spec)})`,
		warning: false,
		beta
	};
}
