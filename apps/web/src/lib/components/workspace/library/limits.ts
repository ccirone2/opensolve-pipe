/**
 * The project library's list limits (CLAUDE.md D22: at most 100 entries in each list), read from
 * the published schema (Project.pipeLibrary and Project.resistanceLibrary maxItems) by
 * utils/project-library.ts, whose setPipeSpec and setResistanceSpec refuse one more, as
 * scenarios.ts reads its own. A full list is said where a new entry starts (the library's New
 * button, and "New pipe spec…" or "New entry…" in a picker, offered disabled), not after its form
 * is filled in: the API refuses one more, and the schema's words would say so.
 */
import type { Project } from '$lib/api/types';
import {
	libraryLimitText,
	MAX_PIPE_SPECS,
	MAX_RESISTANCE_ENTRIES
} from '$lib/utils/project-library';

export { libraryLimitText, MAX_PIPE_SPECS, MAX_RESISTANCE_ENTRIES };

export type LibraryList = 'pipe' | 'resistance';

const limitOf = (list: LibraryList) => (list === 'pipe' ? MAX_PIPE_SPECS : MAX_RESISTANCE_ENTRIES);

/** The list holds as many entries as a project may: no new one can be added. */
export function libraryFull(project: Project, list: LibraryList): boolean {
	const held =
		list === 'pipe' ? (project.pipeLibrary?.length ?? 0) : (project.resistanceLibrary?.length ?? 0);
	return held >= limitOf(list);
}

/**
 * A picker's "New…" option, offered disabled on a full list: "New entry… (a project holds at
 * most 100)".
 */
export const newOptionLabel = (label: string, full: boolean, list: LibraryList): string =>
	full ? `${label} (a project holds at most ${limitOf(list)})` : label;
