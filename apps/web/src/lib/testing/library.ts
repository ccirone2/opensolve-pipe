/**
 * A small pipe library for component tests: carbon steel schedule 40 at NPS 3, 4 and 6. Test
 * inputs, not library data: the material's representative roughness deliberately differs from
 * every size's, so a test can tell which one is shown. Not used by the app.
 */
import type { LibraryResponse } from '../api/types';
import { INCH } from '../utils/units';

export const TEST_LIBRARY: LibraryResponse = {
	materials: [
		{
			id: 'carbon_steel',
			name: 'Carbon steel',
			roughness: 3.6e-5,
			roughnessSource: 'test roughness source',
			dimensionsSource: 'test dimensions source',
			notes: '',
			schedules: [
				{
					id: '40',
					sizes: [
						{
							nps: '3',
							nominalSize: 3 * INCH,
							innerDiameter: 0.07792,
							outerDiameter: 0.0889,
							wallThickness: 0.00549,
							roughness: 3.512e-5
						},
						{
							nps: '4',
							nominalSize: 4 * INCH,
							innerDiameter: 0.10226,
							outerDiameter: 0.1143,
							wallThickness: 0.00602,
							roughness: 3.501e-5
						},
						{
							nps: '6',
							nominalSize: 6 * INCH,
							innerDiameter: 0.15405,
							outerDiameter: 0.1683,
							wallThickness: 0.00711,
							roughness: 3.48e-5
						}
					]
				}
			]
		}
	],
	fittings: []
};
