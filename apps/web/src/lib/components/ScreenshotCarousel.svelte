<!--
	"How it works": the app's workflow and capabilities as a story of eight steps, one screenshot per
	step, swiped sideways (proposal landing-page.md §6–§8): the everyday work first (lay out, describe,
	solve, check, see the working, share), then the power tools (scenarios, goal seek). Each step's
	caption sits above its shot. Each step has a laptop shot and a phone
	shot of the same moment; a <picture> serves the phone's below 640 px and the laptop's from there,
	so every screen tells the same story at a readable size and downloads only its own shots.

	The slides are a scroll-snap row: touch swipe, a trackpad's sideways scroll and Shift+wheel move it
	natively, with no script or dependency for the motion. Previous and Next wrap around, a dot per step
	jumps to it, ← and → move it while it has focus, and the step shown is announced (WAI-ARIA APG
	carousel, without rotation, so there is nothing to pause). A press always advances the row, in
	every browser: see go().

	Each frame has its shots' exact aspect ratio (390:560 for a phone's crop, 16:10 for a laptop) and
	the image fills it absolutely with object-fit: contain, so no browser can stretch or squash it.
	The shots were taken by hand; retake them after a visible UI change (§7–§8).
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
			file: 'share',
			title: 'Share the link',
			text: 'The whole project travels in the link: nothing is stored on a server. Or export a workbook.',
			alt: 'Sharing the project: its link to copy, with a note that the whole project is in the link, after the “#”, which browsers do not send to any server.'
		},
		{
			file: 'compare',
			title: 'Compare scenarios',
			text: 'Named cases, such as winter operation, solved and compared with the base case side by side.',
			alt: "The chiller plant example's base case and its winter scenario (tower bypassed) compared: each pump's flow and head in both, with the scenario's difference from the base case."
		},
		{
			file: 'goal',
			title: 'Goal seek',
			text: 'Find the inputs that reach your targets, each trial a full solve: here, the pump speed for 15 L/s.',
			alt: 'Goal seek on the pump transfer example: the flow into the discharge valve set to reach 15 L/s by varying the pump’s speed from 20 % to 100 %; goal met at 86.1 % speed, with Apply to base case and Apply as new scenario.'
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

	/**
	 * Show step `index` (wrapping around); instant when the user asks for reduced motion. Snapping
	 * is off while a press drives the row: WebKit can snap a smooth programmatic scroll back to
	 * where it began, so the press would not advance it. arrive() puts the row exactly on the step
	 * when the motion is over, or after 0.9 s where the browser did not move it, and snaps again.
	 */
	function go(index: number) {
		if (!scroller) return;
		const n = STEPS.length;
		const target = ((index % n) + n) % n;
		pending = target;
		scroller.style.scrollSnapType = 'none';
		clearTimeout(pendingTimer);
		pendingTimer = setTimeout(arrive, 900);
		const reduced =
			typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
		scroller.scrollTo({
			left: target * scroller.clientWidth,
			behavior: reduced ? 'auto' : 'smooth'
		});
		current = target;
	}

	/** A press's motion is over: the row exactly on its step, then snapping again. */
	function arrive() {
		clearTimeout(pendingTimer);
		if (scroller && pending !== null) {
			const left = pending * scroller.clientWidth;
			if (Math.abs(scroller.scrollLeft - left) > 1) scroller.scrollTo({ left, behavior: 'auto' });
			current = pending;
		}
		pending = null;
		if (scroller) scroller.style.scrollSnapType = '';
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
				if (Math.abs(scroller.scrollLeft - pending * scroller.clientWidth) <= 1) arrive();
				return;
			}
			current = shown;
		});
	}

	/** A scroll ended: a press's motion arrives; otherwise the dots read where the row is. */
	function onscrollend() {
		if (pending !== null) arrive();
		else onscroll();
	}

	/** A touch, a press or a wheel on the row: the user steers now, not the last button. */
	function release() {
		clearTimeout(pendingTimer);
		pending = null;
		if (scroller) scroller.style.scrollSnapType = '';
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
		{onscrollend}
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
				class="flex w-full shrink-0 snap-center snap-always flex-col"
			>
				<!-- The caption above its shot; the slides are as tall as the tallest, and each caption
					sits at its slide's foot above the shot, so every shot is at the same height. -->
				<figcaption class="mx-auto mb-3 flex max-w-2xl flex-1 flex-col justify-end text-center">
					<span class="block font-medium">{i + 1}. {step.title}</span>
					<span class="mt-0.5 block text-sm text-slate-600">{step.text}</span>
				</figcaption>
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
			</figure>
		{/each}
	</div>

	<!-- Eight dots and two 44 px arrows on one row: the dots 24 px (WCAG 2.5.8), 32 px on touch
		from 360 px, so the row fits a 320 px screen and a 390 px one. -->
	<div class="mt-2 flex items-center justify-center sm:gap-1">
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
				class="flex size-6 items-center justify-center rounded-full pointer-coarse:min-[22.5rem]:size-8"
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
