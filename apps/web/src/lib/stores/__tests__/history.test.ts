import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { historyStore, canUndo, canRedo, undoCount, redoCount } from '../history';
import type { Project } from '$lib/models';
import { createNewProject } from '$lib/models';

describe('historyStore', () => {
	let baseProject: Project;

	beforeEach(() => {
		baseProject = createNewProject();
		historyStore.initialize(baseProject);
	});

	describe('initialization', () => {
		it('starts with no undo/redo available', () => {
			expect(get(canUndo)).toBe(false);
			expect(get(canRedo)).toBe(false);
			expect(get(undoCount)).toBe(0);
			expect(get(redoCount)).toBe(0);
		});

		it('stores the initial state', () => {
			const present = historyStore.getPresent();
			expect(present).not.toBeNull();
			expect(present?.id).toBe(baseProject.id);
		});
	});

	describe('push', () => {
		it('enables undo after push', () => {
			const modifiedProject = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified' } };
			historyStore.push(modifiedProject, 'Edit name');

			expect(get(canUndo)).toBe(true);
			expect(get(undoCount)).toBe(1);
		});

		it('clears redo stack on push', () => {
			// Push, undo, then push again
			const modified1 = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified 1' } };
			historyStore.push(modified1, 'Edit 1');
			historyStore.undo();
			expect(get(canRedo)).toBe(true);

			const modified2 = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified 2' } };
			historyStore.push(modified2, 'Edit 2');
			expect(get(canRedo)).toBe(false);
		});
	});

	describe('undo', () => {
		it('restores previous state', () => {
			const modified = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified' } };
			historyStore.push(modified, 'Edit');

			const restored = historyStore.undo();
			expect(restored).not.toBeNull();
			expect(restored?.metadata.name).toBe(baseProject.metadata.name);
		});

		it('returns null when nothing to undo', () => {
			const restored = historyStore.undo();
			expect(restored).toBeNull();
		});

		it('enables redo after undo', () => {
			const modified = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified' } };
			historyStore.push(modified, 'Edit');
			historyStore.undo();

			expect(get(canRedo)).toBe(true);
			expect(get(redoCount)).toBe(1);
		});

		it('can undo multiple times', () => {
			const modified1 = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified 1' } };
			const modified2 = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified 2' } };
			const modified3 = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified 3' } };

			historyStore.push(modified1, 'Edit 1');
			historyStore.push(modified2, 'Edit 2');
			historyStore.push(modified3, 'Edit 3');

			expect(get(undoCount)).toBe(3);

			historyStore.undo();
			historyStore.undo();
			historyStore.undo();

			expect(get(undoCount)).toBe(0);
			expect(get(canUndo)).toBe(false);
		});
	});

	describe('redo', () => {
		it('restores undone state', () => {
			const modified = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified' } };
			historyStore.push(modified, 'Edit');
			historyStore.undo();

			const restored = historyStore.redo();
			expect(restored).not.toBeNull();
			expect(restored?.metadata.name).toBe('Modified');
		});

		it('returns null when nothing to redo', () => {
			const restored = historyStore.redo();
			expect(restored).toBeNull();
		});

		it('decreases redo count', () => {
			const modified = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified' } };
			historyStore.push(modified, 'Edit');
			historyStore.undo();
			expect(get(redoCount)).toBe(1);

			historyStore.redo();
			expect(get(redoCount)).toBe(0);
		});
	});

	describe('clear', () => {
		it('clears history but keeps present', () => {
			const modified = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified' } };
			historyStore.push(modified, 'Edit');
			historyStore.undo();

			historyStore.clear();

			expect(get(canUndo)).toBe(false);
			expect(get(canRedo)).toBe(false);
			expect(historyStore.getPresent()).not.toBeNull();
		});
	});

	describe('deep cloning', () => {
		it('does not mutate stored states', () => {
			const modified = { ...baseProject, metadata: { ...baseProject.metadata, name: 'Modified' } };
			historyStore.push(modified, 'Edit');

			// Mutate the original
			modified.metadata.name = 'Mutated';

			// Undo should return the original value
			historyStore.undo();
			const present = historyStore.getPresent();
			expect(present?.metadata.name).not.toBe('Mutated');
		});
	});
});
