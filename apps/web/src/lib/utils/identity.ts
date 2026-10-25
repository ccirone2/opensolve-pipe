/**
 * Which pipe a pipe object is, across edits that copy it (scenario manager, proposal §6.7).
 *
 * Pipes have no ids: a scenario's change of a pipe names it by its connection and index. A base
 * edit can move pipes (a join, a reversal, an insertion that turns a connection to the flow
 * direction) or remove one, and a scenario's changes must follow the pipe they were made on.
 * Edit functions keep pipe objects when they move them; where one copies a pipe (an edit of the
 * pipe itself, or a copy of a whole connection to edit), it records the copy here as the same
 * pipe (`markCopy`). `originOf` then leads back from any copy to the object it started from, so
 * utils/scenarios.ts (carryChanges) can tell where each pipe went. A new pipe (the short pipe an
 * insertion adds, a pipe segment added) is never marked: it is another pipe.
 */

const copies = new WeakMap<object, object>();

/** Record `copy` as the same pipe as `original` (both objects, never modified here). */
export function markCopy(copy: object, original: object): void {
	if (copy !== original) copies.set(copy, original);
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
