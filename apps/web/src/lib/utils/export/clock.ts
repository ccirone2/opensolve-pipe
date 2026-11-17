/**
 * The export dialog's minute clock (proposal export.md §12 item 36). The file name the dialog
 * shows carries the local time to the minute (§3.5); the dialog stamps it when it opens and again
 * at each local minute boundary, so the name shown follows the clock while the dialog is open and
 * is never behind it by more than the timer's own delay.
 *
 * Every UTC offset in use is a whole number of minutes, so local minutes begin with UTC's: the
 * next boundary is the next multiple of 60 s in epoch time, whatever the time zone.
 */

const MINUTE = 60_000;

/** Milliseconds from `ms` (epoch time) to the next minute boundary: 60,000 on a boundary. */
export function untilNextMinute(ms: number): number {
	return MINUTE - (((ms % MINUTE) + MINUTE) % MINUTE);
}

/**
 * Calls `onMinute` with the time at each minute boundary after `from` (the time the name shown
 * was stamped), until the returned function is called. A boundary passed since `from` (the
 * dialog's first render crossed one) is called at once. Each call reads the clock afresh, so the
 * name follows a clock that is set or synchronized; a timer that fires early (browsers may, by a
 * millisecond) gives a time still in the old minute, and the next call comes at the boundary.
 */
export function everyMinute(from: Date, onMinute: (now: Date) => void): () => void {
	let timer: ReturnType<typeof setTimeout> | undefined;
	const schedule = (last: number) => {
		const due = last + untilNextMinute(last);
		timer = setTimeout(
			() => {
				const now = new Date();
				onMinute(now);
				schedule(now.getTime());
			},
			Math.max(0, due - Date.now())
		);
	};
	schedule(from.getTime());
	return () => clearTimeout(timer);
}
