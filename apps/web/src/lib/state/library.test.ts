import { describe, expect, it, vi } from 'vitest';
import { NetworkError } from '../api/client';
import type { LibraryResponse } from '../api/types';
import { fakeLibrarySource, NOT_AVAILABLE } from '../testing/workspace';
import { INCH } from '../utils/units';
import { LibraryStore } from './library.svelte';

/** Library data for the tests (test inputs, not real pipe data). */
const LIBRARY: LibraryResponse = {
	materials: [
		{
			id: 'test_steel',
			name: 'Test steel',
			roughness: 4.5e-5,
			roughnessSource: 'test source',
			dimensionsSource: 'test source',
			notes: '',
			schedules: [
				{
					id: '40',
					sizes: [
						{
							nps: '4',
							nominalSize: 0.1016,
							innerDiameter: 0.1,
							outerDiameter: 0.11,
							wallThickness: 0.005,
							roughness: 1e-5
						},
						{
							nps: '2',
							nominalSize: 0.0508,
							innerDiameter: 0.05,
							outerDiameter: 0.06,
							wallThickness: 0.005,
							roughness: 1e-5
						}
					]
				}
			]
		},
		{
			id: 'other',
			name: 'Other',
			roughness: 1e-6,
			roughnessSource: 'test source',
			dimensionsSource: 'test source',
			notes: '',
			schedules: [
				{
					id: '10',
					sizes: [
						{
							nps: '3',
							nominalSize: 0.0762,
							innerDiameter: 0.08,
							outerDiameter: 0.09,
							wallThickness: 0.005,
							roughness: 1e-5
						},
						{
							nps: '4',
							nominalSize: 0.1016,
							innerDiameter: 0.105,
							outerDiameter: 0.11,
							wallThickness: 0.0025,
							roughness: 1e-5
						}
					]
				}
			]
		}
	],
	fittings: [
		{
			type: 'bend',
			name: 'Bend',
			correlation: 'f',
			parameters: ['angle', 'radiusRatio'],
			referenceDiameter: 'pipe',
			validInLaminarFlow: false,
			notes: [],
			source: 's'
		}
	]
};

describe('LibraryStore', () => {
	it('loads the library once and looks up materials, schedules and sizes', async () => {
		const getLibrary = vi.fn(() => Promise.resolve(LIBRARY));
		const library = new LibraryStore(fakeLibrarySource({ getLibrary }));
		expect(library.libraryStatus).toBe('idle');
		await library.loadLibrary();
		await library.loadLibrary();
		expect(getLibrary).toHaveBeenCalledTimes(1);
		expect(library.libraryStatus).toBe('ready');
		expect(library.material('test_steel')?.name).toBe('Test steel');
		expect(library.schedule('test_steel', '40')?.sizes).toHaveLength(2);
		// Sizes match within rounding: 3 × 0.0254 is not exactly 0.0762 in binary.
		expect(library.size('other', '10', 3 * INCH)?.nps).toBe('3');
		expect(library.size('other', '10', 0.05)).toBeUndefined();
		expect(library.nominalSizes.map((s) => s.nps)).toEqual(['2', '3', '4']);
		expect(library.fitting('bend')?.parameters).toEqual(['angle', 'radiusRatio']);
	});

	it('reports an unavailable library and can retry', async () => {
		const getLibrary = vi
			.fn<() => Promise<LibraryResponse>>()
			.mockRejectedValueOnce(new NetworkError(NOT_AVAILABLE, 501))
			.mockResolvedValueOnce(LIBRARY);
		const library = new LibraryStore(fakeLibrarySource({ getLibrary }));
		await library.loadLibrary();
		expect(library.libraryStatus).toBe('unavailable');
		expect(library.libraryMessage).toBe(NOT_AVAILABLE);
		expect(library.materials).toEqual([]);
		expect(library.nominalSizes).toEqual([]);
		await library.loadLibrary();
		expect(library.libraryStatus).toBe('ready');
	});

	it('loads the fluid list', async () => {
		const library = new LibraryStore(
			fakeLibrarySource({
				getFluids: () =>
					Promise.resolve([
						{
							id: 'water',
							name: 'Water',
							source: 'test',
							temperatureRange: { min: 273.16, max: 373.15, unit: 'K' },
							concentrationRange: null,
							freezingPoints: null,
							vaporPressureAvailable: true,
							notes: []
						}
					])
			})
		);
		await library.loadFluids();
		expect(library.fluidsStatus).toBe('ready');
		expect(library.fluid('water')?.temperatureRange.max).toBe(373.15);
		expect(library.fluid('propylene_glycol')).toBeUndefined();
	});

	it('loads the method-version changelog once, and again only when asked after a failure', async () => {
		const changelog = {
			current: '1.0.0',
			versions: [{ version: '1.0.0', date: '2026-10-21', changes: ['Test change.'] }]
		};
		const methodVersions = vi
			.fn()
			.mockRejectedValueOnce(new NetworkError(NOT_AVAILABLE, 501))
			.mockResolvedValue(changelog);
		const library = new LibraryStore(fakeLibrarySource({ methodVersions }));
		await library.loadMethodVersions();
		expect(library.methodVersionsStatus).toBe('unavailable');
		expect(library.methodVersionsMessage).toBe(NOT_AVAILABLE);
		await library.loadMethodVersions();
		expect(library.methodVersionsStatus).toBe('ready');
		expect(library.methodVersions).toEqual(changelog);
		await library.loadMethodVersions();
		expect(methodVersions).toHaveBeenCalledTimes(2);
	});

	it('reports the changelog unavailable when the source has none', async () => {
		const source = fakeLibrarySource();
		delete source.methodVersions;
		const library = new LibraryStore(source);
		await library.loadMethodVersions();
		expect(library.methodVersionsStatus).toBe('unavailable');
	});
});
