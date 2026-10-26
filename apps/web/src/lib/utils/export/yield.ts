/**
 * Cooperative building on the main thread (proposal export.md §3.6, decision 18): the writers
 * hand control back to the browser after every 500 rows or 64 KiB of text, so a large workbook
 * never blocks the page for more than a slice (24–31 ms measured), and check the AbortSignal at
 * each yield (Cancel, Close and Esc stop a build).
 *
 * A yield goes through a MessageChannel: a message is a task, so the browser paints and handles
 * input in between, without setTimeout's 4 ms clamp once nested (0.0075 ms against 4.0 ms per
 * yield, measured: §4.4 S3). No Web Worker: Vite does not run the notices plugin on worker
 * bundles (§4.3).
 */

/** Rows between yields. */
export const ROWS_PER_SLICE = 500;
/** Characters of text (XML or CSV) between yields. */
export const CHARS_PER_SLICE = 64 * 1024;

/** Wait for the next task (a MessageChannel message), then go on. */
export function nextTask(): Promise<void> {
	return new Promise((resolve) => {
		const channel = new MessageChannel();
		channel.port1.onmessage = () => {
			channel.port1.close();
			channel.port2.close();
			resolve();
		};
		channel.port2.postMessage(null);
	});
}

/** The error an aborted build throws (as fetch does). */
export function abortError(): DOMException {
	return new DOMException('The export was cancelled.', 'AbortError');
}

export function isAbortError(error: unknown): boolean {
	return error instanceof DOMException && error.name === 'AbortError';
}

/**
 * Counts rows and characters, and yields after every slice of them, checking `signal` first and
 * after each yield.
 */
export class Pacer {
	readonly #signal: AbortSignal | undefined;
	readonly #yieldTo: () => Promise<void>;
	#rows = 0;
	#chars = 0;

	constructor(signal?: AbortSignal, yieldTo: () => Promise<void> = nextTask) {
		this.#signal = signal;
		this.#yieldTo = yieldTo;
	}

	/** Throws an AbortError when the build was cancelled. */
	check(): void {
		if (this.#signal?.aborted) throw abortError();
	}

	/** Count a row of `chars` characters; yield when a slice is full. */
	async row(chars: number): Promise<void> {
		this.#rows++;
		this.#chars += chars;
		if (this.#rows >= ROWS_PER_SLICE || this.#chars >= CHARS_PER_SLICE) await this.pause();
	}

	/** Yield now (between files), checking the signal before and after. */
	async pause(): Promise<void> {
		this.check();
		this.#rows = 0;
		this.#chars = 0;
		await this.#yieldTo();
		this.check();
	}
}
