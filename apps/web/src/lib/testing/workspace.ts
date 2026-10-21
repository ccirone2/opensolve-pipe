/**
 * Test helpers for the workspace: a Workspace over a project, with the API replaced by fakes
 * (by default every endpoint answers 501, as an API that does not provide it yet). Not used by
 * the app.
 */
import { NetworkError } from '../api/client';
import type { Project } from '../api/types';
import { LibraryStore, type LibrarySource } from '../state/library.svelte';
import { ProjectStore, type Solver } from '../state/project.svelte';
import { Workspace } from '../state/workspace.svelte';

export const NOT_AVAILABLE = 'This feature is not available on the calculation server yet.';

function unavailable(): Promise<never> {
	return Promise.reject(new NetworkError(NOT_AVAILABLE, 501));
}

/** A library source whose endpoints all fail (501) unless overridden. */
export function fakeLibrarySource(overrides: Partial<LibrarySource> = {}): LibrarySource {
	return {
		getLibrary: unavailable,
		getFluids: unavailable,
		fluidProperties: unavailable,
		methodVersions: unavailable,
		...overrides
	};
}

export interface TestWorkspaceOptions {
	library?: Partial<LibrarySource>;
	solver?: Solver;
	origin?: string;
	writeUrl?: (path: string) => void;
}

/** A workspace over `project` that writes no URL and calls no API. */
export function testWorkspace(project: Project, options: TestWorkspaceOptions = {}): Workspace {
	const store = new ProjectStore(project, {
		writeUrl: options.writeUrl ?? (() => {}),
		origin: options.origin ?? 'https://opensolve-pipe.app',
		solver: options.solver ?? { solve: unavailable }
	});
	return new Workspace(store, new LibraryStore(fakeLibrarySource(options.library)));
}
