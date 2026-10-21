/**
 * Focus after an edit that removes the focused control's subject (deleting a component): the
 * heading of what the navigator shows now, marked `data-current-heading` (with tabindex -1), so
 * keyboard and screen-reader users continue from there instead of from a reused button.
 */
import { tick } from 'svelte';

export async function focusCurrentHeading(): Promise<void> {
	await tick();
	document.querySelector<HTMLElement>('[data-current-heading]')?.focus();
}
