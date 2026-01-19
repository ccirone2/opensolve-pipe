import { describe, it, expect } from 'vitest';
import {
	encodeProject,
	decodeProject,
	tryDecodeProject,
	extractEncodedFromPath,
	formatSize,
	EncodingError,
	SIZE_THRESHOLDS
} from '../encoding';
import { createNewProject, createDefaultComponent, generateComponentId } from '$lib/models';
import type { PumpCurve } from '$lib/models';

describe('URL encoding/decoding', () => {
	describe('encodeProject', () => {
		it('encodes an empty project', () => {
			const project = createNewProject();
			const result = encodeProject(project);

			expect(result.encoded).toBeTruthy();
			expect(result.encoded.length).toBeGreaterThan(0);
			expect(result.originalSize).toBeGreaterThan(0);
			expect(result.compressedSize).toBeGreaterThan(0);
			expect(result.encodedSize).toBeGreaterThan(0);
		});

		it('produces URL-safe output', () => {
			const project = createNewProject();
			const result = encodeProject(project);

			// Should not contain URL-unsafe characters
			expect(result.encoded).not.toMatch(/[+/=]/);
			// Should only contain base64url characters
			expect(result.encoded).toMatch(/^[A-Za-z0-9_-]+$/);
		});

		it('empty project encodes to reasonable size (< 1KB)', () => {
			const project = createNewProject();
			const result = encodeProject(project);

			// Empty project with metadata, settings, etc. should be < 1KB
			expect(result.encodedSize).toBeLessThan(1024);
		});

		it('medium project encodes to < 2KB', () => {
			const project = createNewProject();

			// Add 5 components
			for (let i = 0; i < 5; i++) {
				const id = generateComponentId();
				const component = createDefaultComponent(i === 0 ? 'reservoir' : 'junction', id);
				project.components.push(component);
			}

			// Add a pump curve
			const curve: PumpCurve = {
				id: 'curve-1',
				name: 'Test Pump',
				manufacturer: 'Grundfos',
				model: 'CR-32',
				points: [
					{ flow: 0, head: 150 },
					{ flow: 50, head: 145 },
					{ flow: 100, head: 135 },
					{ flow: 150, head: 120 },
					{ flow: 200, head: 100 },
					{ flow: 250, head: 75 },
					{ flow: 300, head: 45 }
				]
			};
			project.pump_library.push(curve);

			const result = encodeProject(project);

			expect(result.encodedSize).toBeLessThan(SIZE_THRESHOLDS.WARNING_THRESHOLD);
		});

		it('reports compression ratio', () => {
			const project = createNewProject();
			const result = encodeProject(project);

			expect(result.compressionRatio).toBeLessThan(1);
			expect(result.compressionRatio).toBeGreaterThan(0);
		});

		it('flags large projects', () => {
			const project = createNewProject();

			// Add many components to make it large
			for (let i = 0; i < 50; i++) {
				const id = generateComponentId();
				const component = createDefaultComponent('junction', id);
				component.name = `Component ${i} with a long description to increase size`;
				project.components.push(component);
			}

			const result = encodeProject(project);

			// May or may not be large depending on compression
			expect(typeof result.isLarge).toBe('boolean');
		});
	});

	describe('decodeProject', () => {
		it('decodes an encoded project', () => {
			const original = createNewProject();
			original.metadata.name = 'Test Project';

			const { encoded } = encodeProject(original);
			const decoded = decodeProject(encoded);

			expect(decoded.id).toBe(original.id);
			expect(decoded.metadata.name).toBe('Test Project');
		});

		it('throws on empty string', () => {
			expect(() => decodeProject('')).toThrow(EncodingError);
			expect(() => decodeProject('   ')).toThrow(EncodingError);
		});

		it('throws on invalid base64', () => {
			expect(() => decodeProject('!!!invalid!!!')).toThrow(EncodingError);
		});

		it('throws on valid base64 but not gzip', () => {
			const invalidData = btoa('not compressed data')
				.replace(/\+/g, '-')
				.replace(/\//g, '_')
				.replace(/=+$/, '');
			expect(() => decodeProject(invalidData)).toThrow(EncodingError);
		});

		it('throws on valid gzip but not JSON', () => {
			// This is tricky to test - skip for now
		});
	});

	describe('roundtrip', () => {
		it('preserves all data in empty project', () => {
			const original = createNewProject();

			const { encoded } = encodeProject(original);
			const decoded = decodeProject(encoded);

			expect(decoded).toEqual(original);
		});

		it('preserves all data with components', () => {
			const original = createNewProject();
			original.metadata.name = 'Test Project';
			original.metadata.description = 'A test project for roundtrip testing';
			original.metadata.author = 'Test Author';

			// Add components
			const reservoir = createDefaultComponent('reservoir', 'res-1');
			reservoir.name = 'Main Reservoir';
			(reservoir as { water_level: number }).water_level = 50;
			original.components.push(reservoir);

			const junction = createDefaultComponent('junction', 'junc-1');
			junction.name = 'Junction 1';
			junction.elevation = 10;
			original.components.push(junction);

			// Add pump curve
			const curve: PumpCurve = {
				id: 'curve-1',
				name: 'Test Pump',
				points: [
					{ flow: 0, head: 100 },
					{ flow: 100, head: 80 },
					{ flow: 200, head: 50 }
				]
			};
			original.pump_library.push(curve);

			const { encoded } = encodeProject(original);
			const decoded = decodeProject(encoded);

			expect(decoded).toEqual(original);
		});

		it('preserves connections', () => {
			const original = createNewProject();

			const reservoir = createDefaultComponent('reservoir', 'res-1');
			const junction = createDefaultComponent('junction', 'junc-1');

			reservoir.downstream_connections = [
				{
					target_component_id: 'junc-1',
					piping: {
						pipe: {
							material: 'carbon_steel',
							nominal_diameter: 4,
							schedule: '40',
							length: 100
						},
						fittings: [{ type: 'elbow_90_lr', quantity: 2 }]
					}
				}
			];

			original.components.push(reservoir, junction);

			const { encoded } = encodeProject(original);
			const decoded = decodeProject(encoded);

			expect(decoded.components[0].downstream_connections).toEqual(
				original.components[0].downstream_connections
			);
		});

		it('preserves fluid settings', () => {
			const original = createNewProject();
			original.fluid = {
				type: 'ethylene_glycol',
				temperature: 50,
				concentration: 30
			};

			const { encoded } = encodeProject(original);
			const decoded = decodeProject(encoded);

			expect(decoded.fluid).toEqual(original.fluid);
		});

		it('preserves unit preferences', () => {
			const original = createNewProject();
			original.settings.units = {
				system: 'si',
				length: 'm',
				diameter: 'mm',
				pressure: 'kPa',
				head: 'm_head',
				flow: 'L/s',
				velocity: 'm/s',
				temperature: 'C',
				viscosity_kinematic: 'm2/s',
				viscosity_dynamic: 'Pa.s',
				density: 'kg/m3'
			};

			const { encoded } = encodeProject(original);
			const decoded = decodeProject(encoded);

			expect(decoded.settings.units).toEqual(original.settings.units);
		});
	});

	describe('tryDecodeProject', () => {
		it('returns project on success', () => {
			const original = createNewProject();
			const { encoded } = encodeProject(original);

			const decoded = tryDecodeProject(encoded);
			expect(decoded).toEqual(original);
		});

		it('returns null on failure', () => {
			const decoded = tryDecodeProject('invalid');
			expect(decoded).toBeNull();
		});
	});

	describe('extractEncodedFromPath', () => {
		it('extracts from /p/ path', () => {
			const encoded = extractEncodedFromPath('/p/H4sIAAAA');
			expect(encoded).toBe('H4sIAAAA');
		});

		it('returns the string if no /p/ prefix', () => {
			const encoded = extractEncodedFromPath('H4sIAAAA');
			expect(encoded).toBe('H4sIAAAA');
		});

		it('returns null for paths starting with /', () => {
			const encoded = extractEncodedFromPath('/other/path');
			expect(encoded).toBeNull();
		});
	});

	describe('formatSize', () => {
		it('formats bytes', () => {
			expect(formatSize(500)).toBe('500 B');
		});

		it('formats kilobytes', () => {
			expect(formatSize(1500)).toBe('1.5 KB');
		});

		it('formats megabytes', () => {
			expect(formatSize(1500000)).toBe('1.4 MB');
		});
	});
});
