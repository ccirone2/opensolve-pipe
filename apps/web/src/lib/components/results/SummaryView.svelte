<!--
	Summary of a solve: the fluid properties and atmospheric pressure the solver used (with their
	sources), each pump's operating point, and where the lowest pressure and the highest velocity
	are. All values are from the solved state.
-->
<script lang="ts">
	import type { SolvedState } from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { componentById } from '$lib/utils/graph';
	import { portLabel } from '$lib/utils/labels';
	import {
		connectionName,
		fastestLink,
		flagsForElement,
		Formatter,
		lowestPressureNode,
		pumpStatusLabel,
		type ElementRef
	} from '$lib/utils/results';

	let { solved }: { solved: SolvedState } = $props();
	const ws = useWorkspace();
	const id = $props.id();
	const f = $derived(new Formatter(ws.displayUnits));

	const fluid = $derived(solved.fluid);
	const lowest = $derived(lowestPressureNode(solved));
	const fastest = $derived(fastestLink(solved));
	const pumps = $derived(
		Object.entries(solved.pumpResults).map(([pumpId, result]) => ({
			element: { kind: 'component', id: pumpId } as ElementRef,
			name: componentById(ws.project, pumpId)?.name ?? pumpId,
			result
		}))
	);

	const properties = $derived(
		[
			{
				key: 'temperature',
				label: 'Temperature',
				value: fluid.temperature === null ? null : f.value(fluid.temperature, 'temperature')
			},
			{
				key: 'concentration',
				label: 'Concentration (mass)',
				value: fluid.concentration === null ? null : f.value(fluid.concentration, 'fraction')
			},
			{ key: 'density', label: 'Density', value: f.value(fluid.density, 'density') },
			{
				key: 'dynamicViscosity',
				label: 'Dynamic viscosity',
				value: f.value(fluid.dynamicViscosity, 'viscosity')
			},
			{
				key: 'vaporPressure',
				label: 'Vapor pressure',
				value:
					fluid.vaporPressure === null
						? 'Not available (no NPSH or vapor-pressure checks)'
						: f.value(fluid.vaporPressure, 'pressure', { absolute: true })
			}
		].filter((p) => p.value !== null)
	);
	const sources = $derived(
		properties.flatMap((p) => {
			const source = fluid.sources[p.key];
			return source ? [{ key: p.key, label: p.label, ...source }] : [];
		})
	);
</script>

{#snippet link(element: ElementRef, label: string)}
	<button
		type="button"
		class="min-h-11 text-left text-blue-800 underline underline-offset-2"
		onclick={() => ws.inspect(element)}>{label}</button
	>
{/snippet}

<div class="space-y-4 text-sm">
	<section class="card space-y-2 p-3" aria-labelledby="{id}-fluid">
		<h3 id="{id}-fluid" class="font-semibold">Fluid: {fluid.name}</h3>
		<dl class="space-y-1">
			{#each properties as property (property.key)}
				{@const source = fluid.sources[property.key]}
				<div class="grid grid-cols-[minmax(0,9rem)_1fr] gap-x-3">
					<dt class="text-slate-600">{property.label}</dt>
					<dd>
						<span class="tabular-nums">{property.value}</span>
						{#if source}
							<span class="text-xs text-slate-600">
								({source.origin === 'user' ? 'entered' : 'library'})</span
							>
						{/if}
					</dd>
				</div>
			{/each}
			<div class="grid grid-cols-[minmax(0,9rem)_1fr] gap-x-3">
				<dt class="text-slate-600">Atmospheric pressure</dt>
				<dd class="tabular-nums">
					{f.value(solved.atmosphericPressure, 'pressure', { absolute: true })}
				</dd>
			</div>
		</dl>
		{#if sources.length}
			<details class="text-xs text-slate-700">
				<!-- 16 px line + 2 × 14 px padding: a 44 px target, keeping the disclosure marker. -->
				<summary class="cursor-pointer py-3.5 font-medium text-blue-800">
					Sources of the fluid properties
				</summary>
				<dl class="space-y-2 pb-1">
					{#each sources as source (source.key)}
						<div>
							<dt class="font-medium">
								{source.label} ({source.origin === 'user' ? 'entered by the user' : 'library'})
							</dt>
							<dd class="break-words">{source.citation}</dd>
						</div>
					{/each}
				</dl>
			</details>
		{/if}
	</section>

	{#if pumps.length}
		<section class="card space-y-1 p-3" aria-labelledby="{id}-pumps">
			<h3 id="{id}-pumps" class="font-semibold">Pumps</h3>
			<ul class="space-y-1">
				{#each pumps as pump (pump.element.id)}
					<li class="flex flex-wrap items-center gap-x-2">
						{@render link(pump.element, pump.name)}
						<span class="text-slate-700">
							{#if pump.result.status === 'running'}
								{f.value(pump.result.operatingFlow, 'flow')} at {f.value(
									pump.result.operatingHead,
									'head'
								)}
							{:else}
								{pumpStatusLabel(pump.result, flagsForElement(solved.flags, pump.element))}
							{/if}
						</span>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if lowest || fastest}
		<section class="card space-y-1 p-3" aria-labelledby="{id}-extremes">
			<h3 id="{id}-extremes" class="font-semibold">Extremes</h3>
			<dl class="space-y-1">
				{#if lowest}
					<div>
						<dt class="text-slate-600">Lowest static pressure</dt>
						<dd class="flex flex-wrap items-center gap-x-2">
							<span class="tabular-nums">
								{f.value(lowest.pressure, 'pressure', { gauge: true })}
								({f.value(lowest.absolutePressure, 'pressure', { absolute: true })})
							</span>
							{@render link(
								{ kind: 'component', id: lowest.componentId },
								`${portLabel(lowest.portId)} of ${componentById(ws.project, lowest.componentId)?.name ?? lowest.componentId}`
							)}
						</dd>
					</div>
				{/if}
				{#if fastest}
					<div>
						<dt class="text-slate-600">Highest velocity</dt>
						<dd class="flex flex-wrap items-center gap-x-2">
							<span class="tabular-nums">{f.value(fastest.velocity, 'velocity')}</span>
							{@render link(
								{ kind: 'connection', id: fastest.id },
								connectionName(ws.project, fastest.id)
							)}
						</dd>
					</div>
				{/if}
			</dl>
		</section>
	{/if}
</div>
