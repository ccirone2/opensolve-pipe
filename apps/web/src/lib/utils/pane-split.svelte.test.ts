import { afterEach, describe, expect, it } from 'vitest';
import {
	clampShare,
	defaultShare,
	loadShare,
	MIN_PANE_PX,
	saveShare,
	shareBounds,
	SPLIT_STORAGE_KEY
} from './pane-split';

describe('pane split', () => {
	afterEach(() => localStorage.clear());

	it('gives the default layout’s share: Build 3/5, at most 52 rem', () => {
		expect(defaultShare(1280)).toBeCloseTo(0.4);
		expect(defaultShare(1920)).toBeCloseTo(1 - 832 / 1920);
		expect(defaultShare(0)).toBe(0.4);
	});

	it('keeps both panes at least 22 rem wide and within 25–75 %', () => {
		expect(clampShare(0.9, 1920)).toBe(0.75);
		expect(clampShare(0.1, 1920)).toBe(0.25);
		// At 1024 px, 352 px is more than a quarter: the bounds tighten.
		expect(clampShare(0.9, 1024)).toBeCloseTo(1 - MIN_PANE_PX / 1024);
		expect(clampShare(0.1, 1024)).toBeCloseTo(MIN_PANE_PX / 1024);
		expect(clampShare(0.5, 1024)).toBe(0.5);
		// Too narrow for two such panes: an even split.
		expect(clampShare(0.7, 600)).toBe(0.5);
		// Before layout only the share bounds apply.
		expect(clampShare(0.9, 0)).toBe(0.75);
		expect(shareBounds(1920)).toEqual({ min: 0.25, max: 0.75 });
	});

	it('remembers a share in this browser, and forgets it for the default layout', () => {
		expect(loadShare()).toBeNull();
		saveShare(0.6123);
		expect(localStorage.getItem(SPLIT_STORAGE_KEY)).toBe('0.612');
		expect(loadShare()).toBe(0.612);
		saveShare(null);
		expect(localStorage.getItem(SPLIT_STORAGE_KEY)).toBeNull();
		for (const bad of ['', 'abc', '0', '1', '-0.2', 'Infinity']) {
			localStorage.setItem(SPLIT_STORAGE_KEY, bad);
			expect(loadShare()).toBeNull();
		}
	});
});
