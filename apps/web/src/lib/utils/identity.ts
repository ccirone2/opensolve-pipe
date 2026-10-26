/**
 * Which pipe a pipe object is, across edits that copy it (scenario manager, proposal §6.7).
 *
 * Pipes have no ids: a scenario's change of a pipe names it by its connection and index, and so
 * do a solve's results (SegmentResult.index). A base edit can move pipes (a join, a reversal, an
 * insertion that turns a connection to the flow direction) or remove one, and a scenario's
 * changes, and the results shown in Build, must follow the pipe they were made on or solved for.
 * Edit functions keep pipe objects when they move them; where one copies a pipe (an edit of the
 * pipe itself, or a copy of a whole connection or project to edit), it records the copy here as
 * the same pipe (`markCopy`; the store records its draft of every edit, `markProjectCopy`).
 * `originOf` then leads back from any copy to the object it started from, so utils/scenarios.ts
 * (carryChanges) can tell where each pipe went, and utils/results.ts (linkReading) which solved
 * pipe a pipe of the current project is. A new pipe (the short pipe an insertion adds, a pipe
 * segment added) is never marked: it is another pipe.
 */
import type { Project } from '../api/types';

const copies = new WeakMap<object, object>();

/**
 * Record `copy` as the same pipe as `original` (both objects, never modified here). The copy is
 * recorded against the original's own origin, so a pipe edited many times leads back in one step.
 */
export function markCopy(copy: object, original: object): void {
	if (copy !== original) copies.set(copy, originOf(original));
}

/** The object `value` was first copied from (itself when it is not a recorded copy). */
export function originOf(value: object): object {
	let current = value;
	// A chain of copies ends at an object that is not a copy; the guard stops a malformed cycle.
	for (let guard = 0; guard < 10_000; guard++) {
		const next = copies.get(current);
		if (!next) return current;
		current = next;
	}
	return current;
}

/**
 * Record each pipe of `copy`, a structured clone of `original` (the store's draft of an edit), as
 * the same pipe as the original's in its place.
 */
export function markProjectCopy(copy: Project, original: Project): void {
	original.connections.forEach((connection, i) => {
		const pipes = copy.connections[i]?.piping.pipes;
		connection.piping.pipes.forEach((pipe, j) => {
			const drafted = pipes?.[j];
			if (drafted) markCopy(drafted, pipe);
		});
	});
}
