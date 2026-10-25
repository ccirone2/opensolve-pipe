<!--
	Modal dialog on the native <dialog> element: focus moves into it and is trapped there, Escape
	closes it, and focus returns to the opener when it closes, if the opener is still shown (an
	action that changes the view moves focus itself). Render it inside {#if} — it opens when
	mounted and closes when unmounted. On narrow screens it is a bottom sheet. Long titles wrap.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { focusableWhenScrollable } from '$lib/utils/scroll-focus';
	import Icon from './Icon.svelte';

	interface Props {
		title: string;
		onclose: () => void;
		children: Snippet;
		footer?: Snippet;
		/** Wider on large screens (forms with tables). */
		wide?: boolean;
		/** Wider still from 1024 px (two columns: a setup beside its result). */
		xl?: boolean;
	}

	let { title, onclose, children, footer, wide = false, xl = false }: Props = $props();
	const id = $props.id();
	let dialog: HTMLDialogElement | undefined = $state();

	$effect(() => {
		const element = dialog;
		if (!element) return;
		const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		if (typeof element.showModal === 'function') {
			if (!element.open) element.showModal();
		} else {
			element.setAttribute('open', '');
		}
		return () => {
			if (element.open && typeof element.close === 'function') element.close();
			// A hidden opener (e.g. in a pane the dialog's action switched away from) cannot take
			// focus; focus() would fail silently and leave it on <body>.
			if (opener?.isConnected && opener.checkVisibility?.() !== false) opener.focus();
		};
	});

	function cancel(event: Event) {
		event.preventDefault();
		onclose();
	}

	function backdrop(event: MouseEvent) {
		// Clicks on the backdrop target the <dialog> itself; its content fills the box.
		if (event.target === dialog) onclose();
	}
</script>

<dialog
	bind:this={dialog}
	aria-labelledby="{id}-title"
	oncancel={cancel}
	onclick={backdrop}
	class={[
		'm-0 mt-auto max-h-[92dvh] w-full max-w-full overflow-hidden rounded-t-xl bg-white p-0 text-slate-900 shadow-xl sm:m-auto sm:max-h-[85dvh] sm:rounded-xl',
		xl ? 'sm:max-w-2xl lg:max-w-5xl' : wide ? 'sm:max-w-2xl' : 'sm:max-w-lg'
	]}
>
	<div class="flex max-h-[inherit] flex-col">
		<!-- A div, not <header>: a header here would be read as a second page banner. -->
		<div class="flex items-start gap-2 border-b border-slate-200 py-1 pr-1 pl-4">
			<h2 id="{id}-title" class="min-w-0 flex-1 py-2 text-base font-semibold break-words">
				{title}
			</h2>
			<button type="button" class="btn btn-quiet btn-icon" aria-label="Close" onclick={onclose}>
				<Icon name="close" />
			</button>
		</div>
		<!-- relative: absolutely positioned content (sr-only captions) stays inside the scroll
		     body; otherwise it extends the overflow-hidden dialog, which a focus move then
		     scrolls past its title bar. -->
		<div
			class="relative min-h-0 flex-1 overflow-y-auto px-4 py-4"
			use:focusableWhenScrollable={`${id}-title`}
		>
			{@render children()}
		</div>
		{#if footer}
			<footer class="flex flex-wrap justify-end gap-2 border-t border-slate-200 px-4 py-3">
				{@render footer()}
			</footer>
		{/if}
	</div>
</dialog>
