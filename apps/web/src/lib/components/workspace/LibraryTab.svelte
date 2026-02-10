<script lang="ts">
	import { pumpLibrary } from '$lib/stores';
	import PumpCurveList from './PumpCurveList.svelte';

	// Collapsible section state
	let pumpCurvesOpen = $state(true);
	let lossCurvesOpen = $state(false);
	let refProfilesOpen = $state(false);
</script>

<div class="flex h-full flex-col bg-[var(--color-surface)]">
	<!-- Header -->
	<div class="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
		<span class="text-[0.6875rem] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
			Library
		</span>
	</div>

	<!-- Sections -->
	<div class="flex-1 overflow-y-auto">
		<!-- Pump Curves Section -->
		<div class="border-b border-[var(--color-border)]">
			<button
				type="button"
				onclick={() => pumpCurvesOpen = !pumpCurvesOpen}
				class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-tree-hover)]"
			>
				<svg
					class="h-3 w-3 flex-shrink-0 text-[var(--color-text-subtle)] transition-transform {pumpCurvesOpen ? 'rotate-90' : ''}"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
					stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
				</svg>
				<svg class="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
				</svg>
				<span class="text-xs font-medium text-[var(--color-text)]">Pump Curves</span>
				<span class="ml-auto text-[0.625rem] text-[var(--color-text-subtle)]">
					{$pumpLibrary.length}
				</span>
			</button>
			{#if pumpCurvesOpen}
				<div class="px-2 pb-2">
					<PumpCurveList />
				</div>
			{/if}
		</div>

		<!-- Loss Curves Section (Coming Soon) -->
		<div class="border-b border-[var(--color-border)]">
			<button
				type="button"
				onclick={() => lossCurvesOpen = !lossCurvesOpen}
				class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-tree-hover)]"
			>
				<svg
					class="h-3 w-3 flex-shrink-0 text-[var(--color-text-subtle)] transition-transform {lossCurvesOpen ? 'rotate-90' : ''}"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
					stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
				</svg>
				<svg class="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
				</svg>
				<span class="text-xs font-medium text-[var(--color-text)]">Loss Curves</span>
				<span class="ml-auto rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[0.5625rem] text-[var(--color-text-subtle)]">
					Coming Soon
				</span>
			</button>
			{#if lossCurvesOpen}
				<div class="px-3 pb-3">
					<p class="text-[0.6875rem] leading-relaxed text-[var(--color-text-subtle)]">
						Define custom K-factor or Cv curves for orifices, specialty valves, or other components
						where the loss characteristic is not a simple constant.
					</p>
				</div>
			{/if}
		</div>

		<!-- Reference Profiles Section (Coming Soon) -->
		<div class="border-b border-[var(--color-border)]">
			<button
				type="button"
				onclick={() => refProfilesOpen = !refProfilesOpen}
				class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-[var(--color-tree-hover)]"
			>
				<svg
					class="h-3 w-3 flex-shrink-0 text-[var(--color-text-subtle)] transition-transform {refProfilesOpen ? 'rotate-90' : ''}"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
					stroke-width="2"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
				</svg>
				<svg class="h-3.5 w-3.5 flex-shrink-0 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
				</svg>
				<span class="text-xs font-medium text-[var(--color-text)]">Reference Profiles</span>
				<span class="ml-auto rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-[0.5625rem] text-[var(--color-text-subtle)]">
					Coming Soon
				</span>
			</button>
			{#if refProfilesOpen}
				<div class="px-3 pb-3">
					<p class="text-[0.6875rem] leading-relaxed text-[var(--color-text-subtle)]">
						Define pressure, head, or level profiles for reservoirs, tanks, or boundary conditions
						such as time-varying supply pressures or tank level profiles.
					</p>
				</div>
			{/if}
		</div>
	</div>
</div>
