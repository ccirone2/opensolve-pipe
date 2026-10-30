/**
 * The API's reference data, loaded once per page: pipe materials (schedules and sizes) and
 * fitting types (GET /api/v1/library), the built-in fluids with their valid ranges
 * (GET /api/v1/fluids), and the calculation-method changelog (GET /api/v1/method-versions,
 * loaded only when a results notice needs it).
 *
 * Hydraulic data is never invented in the browser: when the API cannot be reached, these stay
 * null and the UI falls back to what needs no data (custom pipes with a user-entered bore and
 * roughness, custom fluids, and fitting types by id). Projects remain editable either way.
 */
import { getContext, setContext } from 'svelte';
import { ApiError, defaultClient } from '../api/client';
import type {
	FittingInfo,
	FluidDefinition,
	FluidInfo,
	FluidProperties,
	LibraryResponse,
	MethodVersionsResponse,
	PipeDefinition,
	PipeMaterial,
	PipeSchedule,
	PipeSize,
	Project
} from '../api/types';
import { sameSize } from '../utils/labels';
import { resolvePipe, type PipeResolution } from '../utils/project-library';

export type LoadStatus = 'idle' | 'loading' | 'ready' | 'unavailable';

/** What the store needs from the API client (an ApiClient, or a fake in tests). */
export interface LibrarySource {
	getLibrary(): Promise<LibraryResponse>;
	getFluids(): Promise<FluidInfo[]>;
	/** Properties of a fluid definition (POST /api/v1/fluids/properties: the fluid in the body). */
	fluidProperties(fluid: FluidDefinition): Promise<FluidProperties>;
	/** The method-version changelog; optional (unavailable when absent). */
	methodVersions?(): Promise<MethodVersionsResponse>;
}

function messageOf(error: unknown): string {
	if (error instanceof ApiError || error instanceof Error) return error.message;
	return 'The calculation server could not be reached.';
}

export class LibraryStore {
	library = $state.raw<LibraryResponse | null>(null);
	libraryStatus = $state<LoadStatus>('idle');
	libraryMessage = $state<string | null>(null);
	fluids = $state.raw<FluidInfo[] | null>(null);
	fluidsStatus = $state<LoadStatus>('idle');
	fluidsMessage = $state<string | null>(null);
	methodVersions = $state.raw<MethodVersionsResponse | null>(null);
	methodVersionsStatus = $state<LoadStatus>('idle');
	methodVersionsMessage = $state<string | null>(null);
	readonly #source: () => LibrarySource;

	constructor(source?: LibrarySource) {
		this.#source = () => source ?? defaultClient();
	}

	/** Load the pipe and fitting library (again after a failure, or when `force` is set). */
	async loadLibrary(force = false): Promise<void> {
		if (!force && (this.libraryStatus === 'loading' || this.libraryStatus === 'ready')) return;
		this.libraryStatus = 'loading';
		try {
			this.library = await this.#source().getLibrary();
			this.libraryStatus = 'ready';
			this.libraryMessage = null;
		} catch (error) {
			this.libraryStatus = 'unavailable';
			this.libraryMessage = messageOf(error);
		}
	}

	/** Load the built-in fluid list (again after a failure, or when `force` is set). */
	async loadFluids(force = false): Promise<void> {
		if (!force && (this.fluidsStatus === 'loading' || this.fluidsStatus === 'ready')) return;
		this.fluidsStatus = 'loading';
		try {
			this.fluids = await this.#source().getFluids();
			this.fluidsStatus = 'ready';
			this.fluidsMessage = null;
		} catch (error) {
			this.fluidsStatus = 'unavailable';
			this.fluidsMessage = messageOf(error);
		}
	}

	/** Load the calculation-method changelog (again after a failure, or when `force` is set). */
	async loadMethodVersions(force = false): Promise<void> {
		if (
			!force &&
			(this.methodVersionsStatus === 'loading' || this.methodVersionsStatus === 'ready')
		) {
			return;
		}
		const source = this.#source();
		this.methodVersionsStatus = 'loading';
		try {
			if (!source.methodVersions) throw new Error('The method-version list is not available.');
			this.methodVersions = await source.methodVersions();
			this.methodVersionsStatus = 'ready';
			this.methodVersionsMessage = null;
		} catch (error) {
			this.methodVersionsStatus = 'unavailable';
			this.methodVersionsMessage = messageOf(error);
		}
	}

	/** Calculated properties of a fluid definition (throws when the API cannot answer). */
	fluidProperties(fluid: FluidDefinition): Promise<FluidProperties> {
		return this.#source().fluidProperties(fluid);
	}

	get materials(): readonly PipeMaterial[] {
		return this.library?.materials ?? [];
	}

	get fittings(): readonly FittingInfo[] {
		return this.library?.fittings ?? [];
	}

	/**
	 * The library material `id`, if any. No id (a pipe of a project library spec has no material of
	 * its own, CLAUDE.md D22) gives none.
	 */
	material(id: string | null | undefined): PipeMaterial | undefined {
		return id == null ? undefined : this.materials.find((m) => m.id === id);
	}

	schedule(
		materialId: string | null | undefined,
		scheduleId: string | null | undefined
	): PipeSchedule | undefined {
		if (scheduleId == null) return undefined;
		return this.material(materialId)?.schedules.find((s) => s.id === scheduleId);
	}

	size(
		materialId: string | null | undefined,
		scheduleId: string | null | undefined,
		nominalSize: number | null | undefined
	): PipeSize | undefined {
		if (nominalSize == null) return undefined;
		return this.schedule(materialId, scheduleId)?.sizes.find((s) =>
			sameSize(s.nominalSize, nominalSize)
		);
	}

	/**
	 * The inner diameter and roughness the server resolves `pipe` of `project` to, as far as the
	 * browser knows them, with where they come from (utils/project-library.ts resolvePipe): a pipe of
	 * a project library spec takes the spec's values; a library pipe its size's, once the library
	 * has loaded.
	 */
	resolvePipe(project: Project, pipe: PipeDefinition): PipeResolution {
		return resolvePipe(project, pipe, this);
	}

	/** Every nominal size in the library (any material or schedule), smallest first. */
	get nominalSizes(): { nominalSize: number; nps: string }[] {
		const sizes: { nominalSize: number; nps: string }[] = [];
		for (const material of this.materials) {
			for (const schedule of material.schedules) {
				for (const size of schedule.sizes) {
					if (!sizes.some((s) => sameSize(s.nominalSize, size.nominalSize))) {
						sizes.push({ nominalSize: size.nominalSize, nps: size.nps });
					}
				}
			}
		}
		return sizes.sort((a, b) => a.nominalSize - b.nominalSize);
	}

	fitting(type: string): FittingInfo | undefined {
		return this.fittings.find((f) => f.type === type);
	}

	fluid(id: string): FluidInfo | undefined {
		return this.fluids?.find((f) => f.id === id);
	}
}

const LIBRARY_KEY = Symbol('opensolve-pipe:library');

export function provideLibrary(library: LibraryStore): LibraryStore {
	return setContext(LIBRARY_KEY, library);
}

export function useLibrary(): LibraryStore {
	const library = getContext<LibraryStore | undefined>(LIBRARY_KEY);
	if (!library) throw new Error('No LibraryStore: call provideLibrary in a parent component.');
	return library;
}
