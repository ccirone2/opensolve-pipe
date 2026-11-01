<!--
	"How it works": the app's workflow and capabilities as a story of seven steps, one screenshot per
	step, swiped sideways (proposal landing-page.md §6–§7). Each step has a laptop shot and a phone
	shot of the same moment; a <picture> serves the phone's below 640 px and the laptop's from there,
	so every screen tells the same story at a readable size and downloads only its own shots.

	The slides are a scroll-snap row: touch swipe, a trackpad's sideways scroll and Shift+wheel move it
	natively, with no script or dependency for the motion. Previous and Next wrap around, a dot per step
	jumps to it, ← and → move it while it has focus, and the step shown is announced (WAI-ARIA APG
	carousel, without rotation, so there is nothing to pause).

	Each frame has its shots' exact aspect ratio (390:560 for a phone's crop, 16:10 for a laptop) and
	the image fills it absolutely with object-fit: contain, so no browser can stretch or squash it.
	The shots were taken by hand; retake them after a visible UI change (§7).
-->
<script lang="ts">
	import { asset } from '$app/paths';
	import Icon from './ui/Icon.svelte';

	interface Step {
		/** The shots: static/landing/<file>-laptop.webp and <file>-phone.webp. */
		file: string;
		title: string;
		text: string;
		/** What both shots show (the same moment on each screen). */
		alt: string;
	}

	const STEPS: Step[] = [
		{
			file: 'add',
			title: 'Lay out the network',
			text: 'Add each element in the order the flow meets it: tanks, pumps, valves, equipment, tees and wyes.',
			alt: 'Adding a component after the transfer pump: quick buttons for a gate, check or globe valve, a list of every component type, and where it goes in the network.'
		},
		{
			file: 'build',
			title: 'Describe each element',
			text: 'The fields that define it come first; the rest wait under More, each default labelled.',
			alt: "The transfer pump's form: its status as On or Off, its control, its speed, and its rating with the pump curve."
		},
		{
			file: 'solve',
			title: 'Solve',
			text: 'Flows, pressures and each pump’s duty, with anything physically invalid flagged.',
			alt: "The solved pump transfer example: converged, with a summary of the pump's flow, head and NPSH margin and the network's extreme pressures."
		},
		{
			file: 'chart',
			title: 'Check the pumps',
			text: 'Each pump on its system curve, with efficiency, power and NPSH on the same flow axis.',
			alt: "The transfer pump's chart: its head curve crossing the system curve at the operating point, with the best efficiency point, and efficiency, shaft power, and NPSH required against available below on one flow axis."
		},
		{
			file: 'trace',
			title: 'See the working',
			text: 'Every result has a trace: its inputs with their sources, the equations and the data used.',
			alt: "The transfer pump's trace: inputs labelled with their sources (default, library), then the equations for its curve, head, system curve and power."
		},
		{
			file: 'compare',
			title: 'Compare scenarios',
			text: 'Named cases, such as winter operation, solved and compared with the base case side by side.',
			alt: "The chiller plant example's base case and its winter scenario (tower bypassed) compared: each pump's flow and head in both, with the scenario's difference from the base case."
		},
		{
			file: 'share',
			title: 'Share the link',
			text: 'The whole project travels in the link: nothing is stored on a server. Or export a workbook.',
			alt: 'Sharing the project: its link to copy, with a note that the whole project is in the link, after the “#”, which browsers do not send to any server.'
		}
	];

	let current = $state(0);
	let scroller: HTMLElement | undefined = $state();

	/**
	 * The step a button or key is scrolling to: until the row arrives there, the scroll events on
	 * the way do not move `current` back (a second press during the motion goes on from the target).
	 * Cleared on arrival, when the scroll ends (or after a second, where there is no scrollend), and
	 * as soon as the user touches, presses or wheels the row.
	 */
	let pending: number | null = null;
	let pendingTimer: ReturnType<typeof setTimeout> | undefined;

	/** Show step `index` (wrapping around); instant when the user asks for reduced motion. */
	function go(index: number) {
		if (!scroller) return;
		const n = STEPS.length;
		const target = ((index % n) + n) % n;
		pending = target;
		clearTimeout(pendingTimer);
		pendingTimer = setTimeout(settle, 1000);
		const reduced =
			typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
		scroller.scrollTo({
			left: target * scroller.clientWidth,
			behavior: reduced ? 'auto' : 'smooth'
		});
		current = target;
	}

	/** The step in view, from the row's scroll position (a swipe, a trackpad, a button). */
	let frame = 0;
	function onscroll() {
		cancelAnimationFrame(frame);
		frame = requestAnimationFrame(() => {
			if (!scroller || !scroller.clientWidth) return;
			const shown = Math.min(
				STEPS.length - 1,
				Math.max(0, Math.round(scroller.scrollLeft / scroller.clientWidth))
			);
			if (pending !== null) {
				// On the way to a step a button or key chose: wait until the row is there.
				if (Math.abs(scroller.scrollLeft - pending * scroller.clientWidth) > 1) return;
				pending = null;
			}
			current = shown;
		});
	}

	/** The motion is over (scrollend, or the timer where there is none): show where the row is. */
	function settle() {
		clearTimeout(pendingTimer);
		pending = null;
		onscroll();
	}

	/** A touch, a press or a wheel on the row: the user steers now, not the last button. */
	function release() {
		clearTimeout(pendingTimer);
		pending = null;
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
		event.preventDefault();
		go(current + (event.key === 'ArrowRight' ? 1 : -1));
	}
</script>

<section class="mt-10" aria-roledescription="carousel" aria-labelledby="how-title">
	<h2 id="how-title" class="text-xl font-semibold">How it works</h2>
	<!-- The row scrolls: it takes focus so that ← and → move it (a scrollable region must be focusable). -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
	<div
		bind:this={scroller}
		role="group"
		aria-label="Steps: swipe, or use ← and →"
		tabindex="0"
		{onscroll}
		onscrollend={settle}
		onpointerdown={release}
		ontouchstart={release}
		onwheel={release}
		{onkeydown}
		class="mt-3 flex snap-x snap-mandatory [scrollbar-width:none] overflow-x-auto overscroll-x-contain rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 [&::-webkit-scrollbar]:hidden"
	>
		{#each STEPS as step, i (step.file)}
			<figure
				role="group"
				aria-roledescription="slide"
				aria-label="Step {i + 1} of {STEPS.length}"
				class="w-full shrink-0 snap-center snap-always"
			>
				<div
					class="relative aspect-[390/560] overflow-hidden rounded-md border border-slate-200 bg-white sm:aspect-[16/10]"
				>
					<picture>
						<source
							media="(min-width: 40rem)"
							srcset={asset(`/landing/${step.file}-laptop.webp`)}
							width="1280"
							height="800"
						/>
						<img
							src={asset(`/landing/${step.file}-phone.webp`)}
							width="390"
							height="560"
							alt={step.alt}
							loading={i === 0 ? 'eager' : 'lazy'}
							draggable="false"
							class="absolute inset-0 size-full object-contain"
						/>
					</picture>
				</div>
				<figcaption class="mx-auto mt-3 max-w-2xl text-center">
					<span class="block font-medium">{i + 1}. {step.title}</span>
					<span class="mt-0.5 block text-sm text-slate-600">{step.text}</span>
				</figcaption>
			</figure>
		{/each}
	</div>

	<div class="mt-2 flex items-center justify-center gap-1">
		<button
			type="button"
			class="btn btn-quiet btn-icon"
			aria-label="Previous step"
			onclick={() => go(current - 1)}
		>
			<Icon name="left" />
		</button>
		{#each STEPS as step, i (step.file)}
			<button
				type="button"
				class="flex size-6 items-center justify-center rounded-full pointer-coarse:size-11"
				aria-label="Step {i + 1}: {step.title}"
				aria-current={i === current ? 'step' : undefined}
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
			aria-label="Next step"
			onclick={() => go(current + 1)}
		>
			<Icon name="right" />
		</button>
	</div>
	<p class="sr-only" aria-live="polite">
		Step {current + 1} of {STEPS.length}: {STEPS[current]?.title}
	</p>
</section>
