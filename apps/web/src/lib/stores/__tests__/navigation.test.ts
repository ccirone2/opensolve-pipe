import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { navigationStore, currentElementId, canGoBack, canGoForward } from '../navigation';

describe('navigationStore', () => {
	beforeEach(() => {
		navigationStore.clear();
	});

	describe('basic navigation', () => {
		it('starts with no selection', () => {
			expect(get(currentElementId)).toBeNull();
		});

		it('navigates to a component', () => {
			navigationStore.navigateTo('comp-1');
			expect(get(currentElementId)).toBe('comp-1');
		});

		it('builds navigation history', () => {
			navigationStore.navigateTo('comp-1');
			navigationStore.navigateTo('comp-2');
			navigationStore.navigateTo('comp-3');

			expect(get(currentElementId)).toBe('comp-3');
		});

		it('does not duplicate when navigating to same component', () => {
			navigationStore.navigateTo('comp-1');
			navigationStore.navigateTo('comp-1');

			expect(get(currentElementId)).toBe('comp-1');
			expect(get(canGoBack)).toBe(false);
		});
	});

	describe('back navigation', () => {
		it('cannot go back with no history', () => {
			expect(get(canGoBack)).toBe(false);
		});

		it('can go back after navigation', () => {
			navigationStore.navigateTo('comp-1');
			navigationStore.navigateTo('comp-2');

			expect(get(canGoBack)).toBe(true);

			const targetId = navigationStore.goBack();
			expect(targetId).toBe('comp-1');
			expect(get(currentElementId)).toBe('comp-1');
		});

		it('returns null when cannot go back', () => {
			navigationStore.navigateTo('comp-1');

			const targetId = navigationStore.goBack();
			expect(targetId).toBeNull();
		});
	});

	describe('forward navigation', () => {
		it('cannot go forward with no future history', () => {
			navigationStore.navigateTo('comp-1');
			expect(get(canGoForward)).toBe(false);
		});

		it('can go forward after going back', () => {
			navigationStore.navigateTo('comp-1');
			navigationStore.navigateTo('comp-2');
			navigationStore.goBack();

			expect(get(canGoForward)).toBe(true);

			const targetId = navigationStore.goForward();
			expect(targetId).toBe('comp-2');
			expect(get(currentElementId)).toBe('comp-2');
		});

		it('clears forward history on new navigation', () => {
			navigationStore.navigateTo('comp-1');
			navigationStore.navigateTo('comp-2');
			navigationStore.goBack();
			expect(get(canGoForward)).toBe(true);

			navigationStore.navigateTo('comp-3');
			expect(get(canGoForward)).toBe(false);
		});
	});

	describe('history cleanup', () => {
		it('removes deleted component from history', () => {
			navigationStore.navigateTo('comp-1');
			navigationStore.navigateTo('comp-2');
			navigationStore.navigateTo('comp-3');

			navigationStore.removeFromHistory('comp-2');

			// Should still be on comp-3
			expect(get(currentElementId)).toBe('comp-3');
		});

		it('updates current selection when current is removed', () => {
			navigationStore.navigateTo('comp-1');
			navigationStore.navigateTo('comp-2');

			navigationStore.removeFromHistory('comp-2');

			expect(get(currentElementId)).toBe('comp-1');
		});

		it('handles removing only component', () => {
			navigationStore.navigateTo('comp-1');
			navigationStore.removeFromHistory('comp-1');

			expect(get(currentElementId)).toBeNull();
		});
	});

	describe('clear', () => {
		it('clears all navigation state', () => {
			navigationStore.navigateTo('comp-1');
			navigationStore.navigateTo('comp-2');

			navigationStore.clear();

			expect(get(currentElementId)).toBeNull();
			expect(get(canGoBack)).toBe(false);
			expect(get(canGoForward)).toBe(false);
		});
	});
});
