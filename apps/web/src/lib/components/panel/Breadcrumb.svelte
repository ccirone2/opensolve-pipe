<!--
	The path walked so far (SDD §3.1.1). Each step goes back to that component; the last step is
	the current one. The connection used to reach each step is in its tooltip. A long path scrolls
	sideways without a scroll bar (one would change the row's height as it appears): by touch,
	trackpad, Shift+wheel, the keyboard's focus, or a plain mouse wheel, turned sideways here.
-->
<script lang="ts">
	import { componentName } from '$lib/utils/labels';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	const ws = useWorkspace();
	let list: HTMLOListElement | undefined = $state();

	// Keep the current (last) step in view as the path grows.
	$effect(() => {
		void ws.nav.path.length;
		if (list) list.scrollLeft = list.scrollWidth;
	});

	// A mouse wheel scrolls the path sideways while it overflows (a non-passive listener, so the
	// page does not scroll too); a sideways gesture is left to the browser.
	$effect(() => {
		const element = list;
		if (!element) return;
		const wheel = (event: WheelEvent) => {
			if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
			if (element.scrollWidth <= element.clientWidth) return;
			event.preventDefault();
			element.scrollLeft += event.deltaY;
		};
		element.addEventListener('wheel', wheel, { passive: false });
		return () => element.removeEventListener('wheel', wheel);
	});
</script>

<nav aria-label="Path" class="min-w-0 flex-1">
	<ol
		bind:this={list}
		class="flex [scrollbar-width:none] items-center overflow-x-auto py-1 [&::-webkit-scrollbar]:hidden"
	>
		{#each ws.nav.path as step, i (`${i}:${step.componentId}`)}
			{@const last = i === ws.nav.path.length - 1}
			<li class="flex shrink-0 items-center">
				{#if i > 0}
					<span class="px-0.5 text-slate-400" aria-hidden="true">›</span>
				{/if}
				<button
					type="button"
					class={[
						'min-h-11 max-w-48 truncate rounded-md px-2 text-sm',
						last
							? 'font-semibold text-slate-900'
							: 'text-blue-800 underline-offset-2 hover:underline'
					]}
					aria-current={last ? 'step' : undefined}
					title={step.viaConnectionId
						? `Reached by connection ${step.viaConnectionId}`
						: 'Start of the path'}
					onclick={() => ws.nav.goToStep(i)}
				>
					{componentName(ws.project, step.componentId)}
				</button>
			</li>
		{/each}
	</ol>
</nav>
