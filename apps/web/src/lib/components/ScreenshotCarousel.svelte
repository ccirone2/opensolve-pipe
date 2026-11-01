<!--
	Screenshots of the app, one per slide, swiped sideways (proposal landing-page.md §7). The slides
	are a scroll-snap row: touch swipe, a trackpad's sideways scroll and Shift+wheel move it natively,
	with no script or dependency for the motion. Previous and Next wrap around, a dot per slide jumps
	to it, ← and → move it while it has focus, and the slide shown is announced (WAI-ARIA APG
	carousel, without rotation, so there is nothing to pause). A phone shows the phone shots only (a
	laptop's are too small to read there); from 640 px, all of them. Taken by hand, retaken after a
	visible UI change (§3).
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { asset } from '$app/paths';
	import Icon from './ui/Icon.svelte';

	interface Slide {
		/** The file in static/landing/, without its extension. */
		file: string;
		screen: 'laptop' | 'phone';
		caption: string;
		alt: string;
	}

	const SLIDES: Slide[] = [
		{
			file: 'desktop',
			screen: 'laptop',
			caption: 'A pump and its system curve, crossing at the duty point',
			alt: "The pump transfer example, solved, on a laptop: the transfer pump's inputs and its head curve on the left; on the right, its results with the pump and system curves crossing at the duty point, and its efficiency and power below."
		},
		{
			file: 'phone',
			screen: 'phone',
			caption: 'The results summary on a phone',
			alt: "The pump transfer example, solved, on a phone: the results summary with the pump's flow, head and NPSH margin, and the lowest and highest pressures in the network."
		},
		{
			file: 'compare',
			screen: 'laptop',
			caption: 'Scenarios solved and compared side by side',
			alt: 'The chiller plant example on a laptop, comparing its base case with the winter scenario (tower bypassed): each pump’s flow, head and NPSH margin in both cases, with the difference from the base case under each scenario value.'
		},
		{
			file: 'phone-build',
			screen: 'phone',
			caption: 'Editing a pump on a phone',
			alt: "The transfer pump's form on a phone: its last solved status, flow, head and NPSH margin above its status, control and speed, with Previous and Next at the bottom to walk the network."
		},
		{
			file: 'trace',
			screen: 'laptop',
			caption: 'Every result shows its working',
			alt: "The transfer pump's trace on a laptop: the equations used for its curve, head, system curve, power and efficiency, after its inputs, each labelled with its source."
		},
		{
			file: 'phone-nodes',
			screen: 'phone',
			caption: 'Results as a sortable list on a phone',
			alt: 'The nodes of the pump transfer example on a phone, as a list with Sort and Fields controls: each node’s elevation, gauge and absolute pressure, velocity, HGL and EGL.'
		},
		{
			file: 'phone-chart',
			screen: 'phone',
			caption: 'The pump chart on a phone',
			alt: 'The pump chart on a phone: head with the system curve and the best efficiency point, then efficiency, shaft power, and NPSH required against NPSH available, on one flow axis.'
		}
	];

	/** From 640 px (Tailwind's sm), every slide; below, the phone shots. */
	let wide = $state(true);
	const slides = $derived(wide ? SLIDES : SLIDES.filter((s) => s.screen === 'phone'));
	let current = $state(0);
	let scroller: HTMLElement | undefined = $state();

	/** A media query, or null where there is no matchMedia (all slides, smooth motion). */
	const media = (query: string) => (typeof matchMedia === 'function' ? matchMedia(query) : null);

	onMount(() => {
		const query = media('(min-width: 40rem)');
		if (!query) return;
		const apply = () => {
			wide = query.matches;
			current = 0;
			scroller?.scrollTo({ left: 0 });
		};
		apply();
		query.addEventListener('change', apply);
		return () => query.removeEventListener('change', apply);
	});

	/** Show slide `index` (wrapping around). */
	function go(index: number) {
		if (!scroller) return;
		const n = slides.length;
		const target = ((index % n) + n) % n;
		const reduced = media('(prefers-reduced-motion: reduce)')?.matches ?? false;
		scroller.scrollTo({
			left: target * scroller.clientWidth,
			behavior: reduced ? 'auto' : 'smooth'
		});
		current = target;
	}

	/** The slide in view, from the row's scroll position (a swipe, a trackpad, a button). */
	let frame = 0;
	function onscroll() {
		cancelAnimationFrame(frame);
		frame = requestAnimationFrame(() => {
			if (!scroller || !scroller.clientWidth) return;
			current = Math.min(
				slides.length - 1,
				Math.max(0, Math.round(scroller.scrollLeft / scroller.clientWidth))
			);
		});
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
		event.preventDefault();
		go(current + (event.key === 'ArrowRight' ? 1 : -1));
	}
</script>

<section class="mt-10" aria-roledescription="carousel" aria-label="Screenshots">
	<!-- The row scrolls: it takes focus so that ← and → move it (a scrollable region must be focusable). -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
	<div
		bind:this={scroller}
		role="group"
		aria-label="Slides: swipe, or use ← and →"
		tabindex="0"
		{onscroll}
		{onkeydown}
		class="flex snap-x snap-mandatory [scrollbar-width:none] overflow-x-auto overscroll-x-contain rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 [&::-webkit-scrollbar]:hidden"
	>
		{#each slides as slide, i (slide.file)}
			<figure
				role="group"
				aria-roledescription="slide"
				aria-label="{i + 1} of {slides.length}"
				class="w-full shrink-0 snap-center snap-always"
			>
				<div
					class="flex h-[min(70svh,34rem)] items-center justify-center rounded-md border border-slate-200 bg-slate-100 p-2 sm:aspect-[16/10] sm:h-auto sm:p-3"
				>
					<img
						src={asset(`/landing/${slide.file}.webp`)}
						width={slide.screen === 'laptop' ? 1280 : 390}
						height={slide.screen === 'laptop' ? 800 : 844}
						alt={slide.alt}
						loading={i === 0 ? 'eager' : 'lazy'}
						draggable="false"
						class="h-full w-auto max-w-full rounded-sm object-contain shadow-sm"
					/>
				</div>
				<figcaption class="mt-2 text-center text-sm text-slate-600">{slide.caption}</figcaption>
			</figure>
		{/each}
	</div>

	<div class="mt-2 flex items-center justify-center gap-1">
		<button
			type="button"
			class="btn btn-quiet btn-icon"
			aria-label="Previous screenshot"
			onclick={() => go(current - 1)}
		>
			<Icon name="left" />
		</button>
		{#each slides as slide, i (slide.file)}
			<button
				type="button"
				class="flex size-6 items-center justify-center rounded-full pointer-coarse:size-11"
				aria-label="Screenshot {i + 1}: {slide.caption}"
				aria-current={i === current ? 'true' : undefined}
				onclick={() => go(i)}
			>
				<span
					class={[
						'size-2 rounded-full',
						i === current ? 'bg-blue-700' : 'bg-slate-300 hover:bg-slate-400'
					]}
				></span>
			</button>
		{/each}
		<button
			type="button"
			class="btn btn-quiet btn-icon"
			aria-label="Next screenshot"
			onclick={() => go(current + 1)}
		>
			<Icon name="right" />
		</button>
	</div>
	<p class="sr-only" aria-live="polite">
		Screenshot {current + 1} of {slides.length}: {slides[current]?.caption}
	</p>
</section>
