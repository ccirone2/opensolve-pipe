/**
 * The project library's list limits (limits.ts): the schema's maxItems for Project.pipeLibrary
 * and Project.resistanceLibrary (the API's MAX_LIBRARY_ENTRIES, CLAUDE.md D22), a list full at
 * that count, and the sentences that say so. Test inputs: made-up entries.
 */
import { describe, expect, it } from 'vitest';
import type { PipeSpec, Project, ResistanceSpec } from '$lib/api/types';
import openapi from '$lib/api/openapi.json';
import { createEmptyProject } from '$lib/utils/factory';
import {
	libraryFull,
	libraryLimitText,
	MAX_PIPE_SPECS,
	MAX_RESISTANCE_ENTRIES,
	newOptionLabel
} from './limits';

const specs = (n: number): PipeSpec[] =>
	Array.from({ length: n }, (_, i) => ({
		id: `PS${i + 1}`,
		name: `Spec ${i + 1}`,
		source: 'Test input',
		materialId: 'custom',
		innerDiameter: 0.05,
		roughness: 1e-5
	}));
const entries = (n: number): ResistanceSpec[] =>
	Array.from({ length: n }, (_, i) => ({
		id: `RS${i + 1}`,
		name: `Entry ${i + 1}`,
		source: 'Test input',
		kind: 'Cv',
		value: 100
	}));

describe('library limits', () => {
	it("are the schema's maxItems for each list", () => {
		const project = openapi.components.schemas.Project.properties;
		expect(MAX_PIPE_SPECS).toBe(project.pipeLibrary.maxItems);
		expect(MAX_RESISTANCE_ENTRIES).toBe(project.resistanceLibrary.maxItems);
		expect(MAX_PIPE_SPECS).toBe(100);
		expect(MAX_RESISTANCE_ENTRIES).toBe(100);
	});

	it('a list is full at its limit, each list on its own', () => {
		const project: Project = createEmptyProject();
		expect(libraryFull(project, 'pipe')).toBe(false);
		expect(libraryFull(project, 'resistance')).toBe(false);
		project.pipeLibrary = specs(99);
		project.resistanceLibrary = entries(100);
		expect(libraryFull(project, 'pipe')).toBe(false);
		expect(libraryFull(project, 'resistance')).toBe(true);
		project.pipeLibrary = specs(100);
		expect(libraryFull(project, 'pipe')).toBe(true);
	});

	it('says why no new entry can be added, in the list and in a picker', () => {
		expect(libraryLimitText('pipe')).toBe('A project holds at most 100 pipe specs.');
		expect(libraryLimitText('resistance')).toBe('A project holds at most 100 resistance entries.');
		expect(newOptionLabel('New entry…', false, 'resistance')).toBe('New entry…');
		expect(newOptionLabel('New pipe spec…', true, 'pipe')).toBe(
			'New pipe spec… (a project holds at most 100)'
		);
	});
});
