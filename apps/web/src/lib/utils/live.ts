/**
 * A polite line's words written two animation frames after it is emptied or drawn (ui-guide.md,
 * One strip of live lines): a line inserted already speaking is not announced, and one emptied
 * and filled in one task shows the accessibility tree no change, so the same words twice would
 * not be said. Without animation frames (a test's DOM) two macrotasks stand in for them.
 */
export function afterTwoFrames(write: () => void): () => void {
	let cancelled = false;
	const next =
		typeof requestAnimationFrame === 'function'
			? (step: () => void) => requestAnimationFrame(step)
			: (step: () => void) => setTimeout(step, 0);
	next(() => next(() => !cancelled && write()));
	return () => {
		cancelled = true;
	};
}
