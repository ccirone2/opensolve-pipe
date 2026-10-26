// @vitest-environment jsdom
/**
 * Saving a file (proposal export.md §5.6): an `<a download>` clicked with a Blob URL, removed at
 * once, and the URL revoked after 60 s (not at once: iOS Safari needs it while its prompt is
 * open). Nothing else is touched. And the file's size in words.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fileSizeText, REVOKE_AFTER_MS, saveBlob } from './download';

afterEach(() => {
	vi.useRealTimers();
	vi.restoreAllMocks();
});

describe('saving a file', () => {
	it('clicks a download link to a Blob URL and revokes the URL after 60 s', () => {
		vi.useFakeTimers();
		const blob = new Blob(['x'], { type: 'image/png' });
		const created: Blob[] = [];
		const revoked: string[] = [];
		URL.createObjectURL = (b: Blob) => {
			created.push(b);
			return 'blob:made-up';
		};
		URL.revokeObjectURL = (url: string) => void revoked.push(url);
		const clicks: HTMLAnchorElement[] = [];
		vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
			this: HTMLAnchorElement
		) {
			clicks.push(this);
			expect(this.isConnected).toBe(true);
		});

		saveBlob(blob, 'Pump transfer - P1 chart 2026-10-25 1432.png');
		expect(created).toEqual([blob]);
		expect(clicks).toHaveLength(1);
		const link = clicks[0]!;
		expect(link.getAttribute('href')).toBe('blob:made-up');
		expect(link.download).toBe('Pump transfer - P1 chart 2026-10-25 1432.png');
		expect(link.rel).toBe('noopener');
		expect(link.isConnected).toBe(false);
		vi.advanceTimersByTime(REVOKE_AFTER_MS - 1);
		expect(revoked).toEqual([]);
		vi.advanceTimersByTime(1);
		expect(revoked).toEqual(['blob:made-up']);
		expect(REVOKE_AFTER_MS).toBe(60_000);
	});

	it('says a file’s size in bytes, KB or MB', () => {
		expect(fileSizeText(1)).toBe('1 byte');
		expect(fileSizeText(812)).toBe('812 bytes');
		expect(fileSizeText(1000)).toBe('1 KB');
		expect(fileSizeText(28_400)).toBe('28 KB');
		expect(fileSizeText(234_567)).toBe('235 KB');
		expect(fileSizeText(999_499)).toBe('999 KB');
		expect(fileSizeText(999_500)).toBe('1 MB');
		expect(fileSizeText(1_812_000)).toBe('1.8 MB');
		expect(fileSizeText(39_100_000)).toBe('39 MB');
	});
});
