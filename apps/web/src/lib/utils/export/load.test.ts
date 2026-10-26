/**
 * The export chunk's loader (proposal export.md §5.2, decision 3): one import, shared by the idle
 * preload and the click; a failed import is forgotten so the next call tries again; the preload
 * starts once, at idle, and its failure is silent (the click reports one).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createLoader } from './load';

afterEach(() => {
	vi.useRealTimers();
	vi.unstubAllGlobals();
});

describe('export chunk loader', () => {
	it('imports once, for the preload and every click', async () => {
		const module = { default: 'dialog' };
		const importer = vi.fn(() => Promise.resolve(module));
		const { load } = createLoader(importer);
		const [a, b] = await Promise.all([load(), load()]);
		expect(a).toBe(module);
		expect(b).toBe(module);
		expect(await load()).toBe(module);
		expect(importer).toHaveBeenCalledTimes(1);
	});

	it('forgets a failed import, so the next call tries again', async () => {
		const importer = vi
			.fn<() => Promise<string>>()
			.mockRejectedValueOnce(new TypeError('Failed to fetch dynamically imported module'))
			.mockResolvedValueOnce('dialog');
		const { load } = createLoader(importer);
		await expect(load()).rejects.toThrow('Failed to fetch');
		expect(await load()).toBe('dialog');
		expect(importer).toHaveBeenCalledTimes(2);
	});

	it('preloads once, at idle, and a failed preload stays silent', async () => {
		const idle: (() => void)[] = [];
		vi.stubGlobal('requestIdleCallback', (task: () => void) => idle.push(task));
		const importer = vi
			.fn<() => Promise<string>>()
			.mockRejectedValueOnce(new TypeError('Failed to fetch dynamically imported module'))
			.mockResolvedValue('dialog');
		const { load, preload } = createLoader(importer);
		preload();
		preload();
		expect(importer).not.toHaveBeenCalled();
		expect(idle).toHaveLength(1);
		idle[0]!();
		await vi.waitFor(() => expect(importer).toHaveBeenCalledTimes(1));
		// The click tries again.
		expect(await load()).toBe('dialog');
		expect(importer).toHaveBeenCalledTimes(2);
	});

	it('waits a moment instead where the browser has no idle callback', async () => {
		vi.stubGlobal('requestIdleCallback', undefined);
		vi.useFakeTimers();
		const importer = vi.fn(() => Promise.resolve('dialog'));
		createLoader(importer).preload();
		expect(importer).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(250);
		expect(importer).toHaveBeenCalledTimes(1);
	});
});
