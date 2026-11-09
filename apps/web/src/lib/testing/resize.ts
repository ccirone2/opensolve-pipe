/**
 * Test helpers for boxes that measure themselves (utils/scroll-focus.ts): jsdom lays nothing out
 * and has no ResizeObserver, so a test gives a box the sizes a browser would and runs the
 * observers itself (proposal pumps-results-layout.md §9 S7: a box a Tab stop only while it
 * overflows, "resize in jsdom via a mocked ResizeObserver"). Not used by the app.
 */

interface Watcher {
	callback: ResizeObserverCallback;
	targets: Set<Element>;
}

/**
 * Install a ResizeObserver whose callbacks run only when `resize` is called, as a browser runs
 * them after a layout. `restore` puts back what was there (none, in jsdom).
 */
export function fakeResizeObserver() {
	const watchers = new Set<Watcher>();
	const before = Object.getOwnPropertyDescriptor(globalThis, 'ResizeObserver');
	class FakeResizeObserver {
		private watcher: Watcher;
		constructor(callback: ResizeObserverCallback) {
			this.watcher = { callback, targets: new Set() };
			watchers.add(this.watcher);
		}
		observe(target: Element) {
			this.watcher.targets.add(target);
		}
		unobserve(target: Element) {
			this.watcher.targets.delete(target);
		}
		disconnect() {
			this.watcher.targets.clear();
			watchers.delete(this.watcher);
		}
	}
	Object.defineProperty(globalThis, 'ResizeObserver', {
		configurable: true,
		writable: true,
		value: FakeResizeObserver
	});
	return {
		/** Run the observers watching `target` (every one, without it), as after a layout. */
		resize(target?: Element) {
			for (const w of [...watchers]) {
				if (target && !w.targets.has(target)) continue;
				w.callback([], w as unknown as ResizeObserver);
			}
		},
		/** How many elements are watched. */
		watched() {
			return [...watchers].reduce((n, w) => n + w.targets.size, 0);
		},
		restore() {
			if (before) Object.defineProperty(globalThis, 'ResizeObserver', before);
			else delete (globalThis as { ResizeObserver?: unknown }).ResizeObserver;
		}
	};
}

/** The sizes a browser would give a box and its content, in px. */
export interface BoxSizes {
	clientWidth?: number;
	scrollWidth?: number;
	clientHeight?: number;
	scrollHeight?: number;
}

/** Give a box the sizes of a layout (jsdom's are 0). */
export function sizeBox(box: Element, sizes: BoxSizes) {
	for (const [key, value] of Object.entries(sizes)) {
		Object.defineProperty(box, key, { configurable: true, get: () => value });
	}
}
