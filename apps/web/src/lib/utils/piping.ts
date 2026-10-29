/**
 * Edits to the piping of one connection (pipes in series and inline fittings). Pure: each
 * function returns new objects and never modifies its input.
 *
 * Fittings refer to pipes by index (`pipeIndex`; a reducer sits between pipeIndex and
 * pipeIndex + 1), so adding or removing a pipe keeps those references pointing at the same
 * pipes where they still exist.
 */
import type {
	Fitting,
	PipeDefinition,
	PipeMaterial,
	PipeSchedule,
	PipeSize,
	PipingSegment,
	Project
} from '../api/types';
import { DEFAULT_PIPE_LENGTH } from './factory';
import { markCopy } from './identity';
import { sameSize } from './labels';
import { REDUCER_TYPES } from './model-rules';

export const CUSTOM_MATERIAL_ID = 'custom';

/**
 * The nominal size the web sizes ports by for `pipe` (a component inserted in its connection):
 * for a pipe of a project library spec, the spec's (CLAUDE.md D22: for display and the web's port
 * sizes only; none when the spec gives none or the project does not have it); else its own.
 */
export function pipeNominalSize(
	project: Pick<Project, 'pipeLibrary'>,
	pipe: PipeDefinition | undefined
): number | undefined {
	if (!pipe) return undefined;
	const size =
		pipe.specId != null
			? project.pipeLibrary?.find((spec) => spec.id === pipe.specId)?.nominalSize
			: pipe.nominalSize;
	return size ?? undefined;
}

/** A fitting that sits between two pipes (x-reducer-types, model-rules.ts). */
export function isReducer(fitting: Pick<Fitting, 'type'>): boolean {
	return REDUCER_TYPES.has(fitting.type);
}

/** Highest valid pipeIndex for a fitting in piping with `pipeCount` pipes. */
export function maxPipeIndex(fitting: Pick<Fitting, 'type'>, pipeCount: number): number {
	return Math.max(0, isReducer(fitting) ? pipeCount - 2 : pipeCount - 1);
}

/**
 * Append a pipe segment: a copy of the last pipe's material, schedule and size (or inner
 * diameter and roughness for a custom pipe), with the default length for new pipes.
 */
export function addPipe(piping: PipingSegment, pipe?: PipeDefinition): PipingSegment {
	const last = piping.pipes[piping.pipes.length - 1];
	const next = pipe ?? (last ? { ...last, length: DEFAULT_PIPE_LENGTH } : undefined);
	if (!next) return piping;
	return { ...piping, pipes: [...piping.pipes, next] };
}

/**
 * Remove pipe `index` (a connection keeps at least one). Fittings on later pipes move down one
 * index; fittings on the removed pipe move to the pipe before it (or the new first pipe).
 * Indices are then clamped to the pipes that remain.
 */
export function removePipe(piping: PipingSegment, index: number): PipingSegment {
	if (piping.pipes.length <= 1 || index < 0 || index >= piping.pipes.length) return piping;
	const pipes = piping.pipes.filter((_, i) => i !== index);
	const fittings = piping.fittings.map((f) => {
		const shifted =
			f.pipeIndex > index ? f.pipeIndex - 1 : f.pipeIndex === index ? index - 1 : f.pipeIndex;
		const pipeIndex = Math.min(Math.max(0, shifted), maxPipeIndex(f, pipes.length));
		return pipeIndex === f.pipeIndex ? f : { ...f, pipeIndex };
	});
	return { pipes, fittings };
}

/**
 * Replace pipe `index` with `update(copy of it)`. The result is the same pipe, edited
 * (identity.ts), so scenario changes stay on it.
 */
export function updatePipe(
	piping: PipingSegment,
	index: number,
	update: (pipe: PipeDefinition) => PipeDefinition
): PipingSegment {
	const pipe = piping.pipes[index];
	if (!pipe) return piping;
	const edited = (p: PipeDefinition) => {
		const next = update({ ...p });
		markCopy(next, p);
		return next;
	};
	return { ...piping, pipes: piping.pipes.map((p, i) => (i === index ? edited(p) : p)) };
}

export function addFitting(piping: PipingSegment, fitting: Fitting): PipingSegment {
	return { ...piping, fittings: [...piping.fittings, fitting] };
}

export function removeFitting(piping: PipingSegment, index: number): PipingSegment {
	return { ...piping, fittings: piping.fittings.filter((_, i) => i !== index) };
}

export function updateFitting(
	piping: PipingSegment,
	index: number,
	update: (fitting: Fitting) => Fitting
): PipingSegment {
	const fitting = piping.fittings[index];
	if (!fitting) return piping;
	return {
		...piping,
		fittings: piping.fittings.map((f, i) => (i === index ? update({ ...f }) : f))
	};
}

/**
 * A new fitting of `type` on pipe `pipeIndex` (clamped to the valid range). Fields the type
 * needs (angle, radius ratio, K) are left empty for the user to enter: they are flagged until
 * then, never guessed.
 */
export function newFitting(type: Fitting['type'], pipeIndex: number, pipeCount: number): Fitting {
	const fitting: Fitting = { type, quantity: 1, pipeIndex: 0 };
	fitting.pipeIndex = Math.min(Math.max(0, pipeIndex), maxPipeIndex(fitting, pipeCount));
	return fitting;
}

/** The size in `sizes` closest to `nominalSize` (by nominal size), or the first size. */
export function nearestSize(
	sizes: readonly PipeSize[],
	nominalSize: number | null | undefined,
	innerDiameter?: number | null
): PipeSize | undefined {
	if (!sizes.length) return undefined;
	const key = (s: PipeSize) =>
		nominalSize != null
			? Math.abs(s.nominalSize - nominalSize)
			: innerDiameter != null
				? Math.abs(s.innerDiameter - innerDiameter)
				: 0;
	return [...sizes].sort((a, b) => key(a) - key(b))[0];
}

/** Library values a custom pipe can start from, so switching to custom keeps the pipe's bore. */
export interface ResolvedPipe {
	innerDiameter?: number;
	roughness?: number;
}

/**
 * The inner diameter and roughness the calculation server resolves a library pipe to (SDD §4.3),
 * as far as the browser can know them: a user override wins; otherwise the library size entry
 * (roughness is per size: the Farshad & Rieke correlation evaluated at that size's bore, not the
 * material's representative average). With an inner-diameter override and no roughness
 * override the server evaluates the correlation at the override bore, which the browser does
 * not compute, so the roughness is left unknown here rather than approximated.
 */
export function resolvedPipe(pipe: PipeDefinition, size: PipeSize | undefined): ResolvedPipe {
	const resolved: ResolvedPipe = {};
	const innerDiameter = pipe.innerDiameter ?? size?.innerDiameter;
	const roughness = pipe.roughness ?? (pipe.innerDiameter == null ? size?.roughness : undefined);
	if (innerDiameter != null) resolved.innerDiameter = innerDiameter;
	if (roughness != null) resolved.roughness = roughness;
	return resolved;
}

/**
 * The pipe with a new material. To a library material: the same schedule if it has one, else
 * its first; the same nominal size if that schedule has it, else the nearest (by nominal size, or
 * by the inner diameter it resolved to: a custom pipe's, or a project library spec's); overrides
 * are dropped. To 'custom': the pipe keeps its length and takes its inner diameter and roughness
 * from its own overrides or the values it resolved to (left empty when neither is known, for the
 * user to enter). Either way a reference to a project library spec (specId) is dropped: the pipe
 * has its own values now.
 */
export function withMaterial(
	pipe: PipeDefinition,
	material: PipeMaterial | typeof CUSTOM_MATERIAL_ID,
	resolved: ResolvedPipe = {}
): PipeDefinition {
	if (material === CUSTOM_MATERIAL_ID) {
		const custom: PipeDefinition = { materialId: CUSTOM_MATERIAL_ID, length: pipe.length };
		const innerDiameter = pipe.innerDiameter ?? resolved.innerDiameter;
		const roughness = pipe.roughness ?? resolved.roughness;
		if (innerDiameter != null) custom.innerDiameter = innerDiameter;
		if (roughness != null) custom.roughness = roughness;
		return custom;
	}
	const schedule =
		material.schedules.find((s) => s.id === pipe.schedule) ?? material.schedules[0] ?? null;
	const next: PipeDefinition = { materialId: material.id, length: pipe.length };
	if (!schedule) return { ...next, nominalSize: pipe.nominalSize ?? null };
	const sizes = schedule.sizes;
	const keep =
		pipe.nominalSize != null &&
		sizes.some((s) => sameSize(s.nominalSize, pipe.nominalSize as number));
	const size = keep
		? undefined
		: nearestSize(sizes, pipe.nominalSize, pipe.innerDiameter ?? resolved.innerDiameter);
	return {
		...next,
		schedule: schedule.id,
		nominalSize: keep ? pipe.nominalSize : (size?.nominalSize ?? pipe.nominalSize ?? null)
	};
}

/** The pipe with a new schedule: the same nominal size if the schedule has it, else the nearest. */
export function withSchedule(pipe: PipeDefinition, schedule: PipeSchedule): PipeDefinition {
	const keep =
		pipe.nominalSize != null &&
		schedule.sizes.some((s) => sameSize(s.nominalSize, pipe.nominalSize as number));
	const size = keep ? undefined : nearestSize(schedule.sizes, pipe.nominalSize);
	return {
		...pipe,
		schedule: schedule.id,
		nominalSize: keep ? pipe.nominalSize : (size?.nominalSize ?? pipe.nominalSize)
	};
}

/** Set or clear an optional numeric field (null removes it, keeping projects tidy). */
export function withOptional<T extends object, K extends keyof T>(
	value: T,
	key: K,
	next: T[K] | null | undefined
): T {
	const copy = { ...value };
	if (next === null || next === undefined) delete copy[key];
	else copy[key] = next;
	return copy;
}
