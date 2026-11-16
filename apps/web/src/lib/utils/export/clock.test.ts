/**
 * The export dialog's minute clock (proposal export.md §12 item 36): the file name the dialog shows
 * is stamped when it opens and again at each local minute boundary, by a timer aligned to the next
 * minute and cleared when the dialog closes. Every offset in use is a whole number of minutes, so
 * local minutes begin with UTC's; the test runs in a zone 45 minutes off the hour to say so.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { everyMinute, untilNextMinute } from './clock';

const savedTz = process.env.TZ;

afterEach(() => {
	vi.useRealTimers();
	process.env.TZ = savedTz;
});

const at = (local: string) => new Date(`${local}+05:45`);

describe('the dialog’s minute clock', () => {
	it('waits until the next minute boundary: a whole minute on one', () => {
		expect(untilNextMinute(Date.parse('2026-11-13T10:35:30.250Z'))).toBe(29_750);
		expect(untilNextMinute(Date.parse('2026-11-13T10:35:59.999Z'))).toBe(1);
		expect(untilNextMinute(Date.parse('2026-11-13T10:36:00.000Z'))).toBe(60_000);
		// Before 1970, a negative time, the same.
		expect(untilNextMinute(-1)).toBe(1);
		expect(untilNextMinute(-60_000)).toBe(60_000);
	});

	it('calls at each local minute boundary after the time it starts from, until stopped', () => {
		process.env.TZ = 'Asia/Kathmandu';
		vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] });
		vi.setSystemTime(at('2026-11-13T16:20:30'));
		const calls: Date[] = [];
		const stop = everyMinute(new Date(), (now) => calls.push(now));
		vi.advanceTimersByTime(29_999);
		expect(calls).toEqual([]);
		vi.advanceTimersByTime(1);
		expect(calls).toEqual([at('2026-11-13T16:21:00')]);
		// The local clock's minute, in a zone 5 h 45 min ahead of UTC.
		expect([calls[0]!.getHours(), calls[0]!.getMinutes(), calls[0]!.getSeconds()]).toEqual([
			16, 21, 0
		]);
		vi.advanceTimersByTime(120_000);
		expect(calls).toEqual([
			at('2026-11-13T16:21:00'),
			at('2026-11-13T16:22:00'),
			at('2026-11-13T16:23:00')
		]);
		expect(vi.getTimerCount()).toBe(1);
		stop();
		expect(vi.getTimerCount()).toBe(0);
		vi.advanceTimersByTime(600_000);
		expect(calls).toHaveLength(3);
	});

	it('a boundary passed since the time it starts from is called at once', () => {
		// The dialog stamps its name, then renders: a render that crosses a boundary is not left a
		// minute behind.
		vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] });
		vi.setSystemTime(at('2026-11-13T16:20:59.990'));
		const from = new Date();
		vi.setSystemTime(at('2026-11-13T16:21:00.030'));
		const calls: Date[] = [];
		everyMinute(from, (now) => calls.push(now));
		vi.advanceTimersByTime(0);
		expect(calls).toEqual([at('2026-11-13T16:21:00.030')]);
		vi.advanceTimersByTime(59_969);
		expect(calls).toHaveLength(1);
		vi.advanceTimersByTime(1);
		expect(calls.at(-1)).toEqual(at('2026-11-13T16:22:00'));
	});

	it('a timer that fires early calls again at the boundary', () => {
		// A browser may run a timer a millisecond or so early: that call reads the old minute, and
		// the next comes at the boundary, not a minute later.
		vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] });
		vi.setSystemTime(at('2026-11-13T16:20:30'));
		const calls: Date[] = [];
		everyMinute(new Date(), (now) => calls.push(now));
		// Setting the clock back keeps the timer's own delay: it now fires 5 ms before 16:21.
		vi.setSystemTime(at('2026-11-13T16:20:29.995'));
		vi.advanceTimersByTime(30_000);
		expect(calls).toEqual([at('2026-11-13T16:20:59.995')]);
		vi.advanceTimersByTime(5);
		expect(calls).toEqual([at('2026-11-13T16:20:59.995'), at('2026-11-13T16:21:00')]);
	});
});
