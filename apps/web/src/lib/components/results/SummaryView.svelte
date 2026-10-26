<!--
	Summary of a solve, answers first (proposal ui-ux-refinement.md item 8): each pump's operating
	point and NPSH margin, then the extremes a designer checks, each with where it is (a link to that
	element's results and trace) and a link to the table sorted on it: the lowest and highest static
	pressure (Nodes), the highest velocity (Links) and the smallest NPSH margin (Pumps). The fluid
	properties and atmospheric pressure the solver used, with their sources, are one disclosure
	below (inputs, not answers). Flags come before the views, in the Results pane. All values are
	from the solved state.
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
		highestPressureNode,
		lowestPressureNode,
		pumpStatusLabel,
		smallestNpshMargin,
		type ElementRef,
		type ResultsView,
		type SortDirection
	} from '$lib/utils/results';

	interface Props {
		solved: SolvedState;
		/** Show a view sorted by one column (the extremes' "sorted" links). */
		onsort?: (view: ResultsView, key: string, direction: SortDirection) => void;
	}

	let { solved, onsort }: Props = $props();
	const ws = useWorkspace();
	const id = $props.id();
	const f = $derived(new Formatter(ws.displayUnits));

	const fluid = $derived(solved.fluid);
	const lowest = $derived(lowestPressureNode(solved));
	const highest = $derived(highestPressureNode(solved));
	const fastest = $derived(fastestLink(solved));
	const npsh = $derived(smallestNpshMargin(solved));
	const pumps = $derived(
		Object.entries(solved.pumpResults).map(([pumpId, result]) => ({
			element: { kind: 'component', id: pumpId } as ElementRef,
			name: componentById(ws.project, pumpId)?.name ?? pumpId,
			result
		}))
	);

	const portName = (componentId: string, portId: string) =>
		`${portLabel(portId)} of ${componentById(ws.project, componentId)?.name ?? componentId}`;

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
	/** The fluid's line when closed: its temperature (and concentration). */
	const fluidLine = $derived(
		[
			fluid.temperature === null ? null : f.value(fluid.temperature, 'temperature'),
			fluid.concentration === null ? null : f.value(fluid.concentration, 'fraction')
		]
			.filter(Boolean)
			.join(' · ')
	);
</script>

{#snippet link(element: ElementRef, label: string)}
	<button
		type="button"
		class="min-h-11 text-left text-blue-800 underline underline-offset-2"
		onclick={() => ws.inspect(element)}>{label}</button
	>
{/snippet}

{#snippet sorted(view: ResultsView, key: string, direction: SortDirection, label: string)}
	{#if onsort}
		<button
			type="button"
			class="ml-auto min-h-11 text-right text-xs text-slate-700 underline underline-offset-2 hover:text-slate-900"
			onclick={() => onsort(view, key, direction)}>{label}</button
		>
	{/if}
{/snippet}

{#snippet extreme(label: string)}
	<dt class="text-slate-600">{label}</dt>
{/snippet}

<div class="space-y-4 text-sm">
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
								)}{#if pump.result.npshMargin !== null && pump.result.npshMargin !== undefined}&nbsp;·
									NPSH margin {f.value(pump.result.npshMargin, 'head')}{/if}
							{:else}
								{pumpStatusLabel(pump.result, flagsForElement(solved.flags, pump.element))}
							{/if}
						</span>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if lowest || fastest || npsh}
		<section class="card space-y-1 p-3" aria-labelledby="{id}-extremes">
			<h3 id="{id}-extremes" class="font-semibold">Extremes</h3>
			<dl class="space-y-2">
				{#if lowest}
					<div>
						{@render extreme('Lowest static pressure')}
						<dd class="flex flex-wrap items-center gap-x-2">
							<span class="tabular-nums">
								{f.value(lowest.pressure, 'pressure', { gauge: true })}
								({f.value(lowest.absolutePressure, 'pressure', { absolute: true })})
							</span>
							{@render link(
								{ kind: 'component', id: lowest.componentId },
								portName(lowest.componentId, lowest.portId)
							)}
							{@render sorted('nodes', 'pressure', 'ascending', 'Nodes, lowest first')}
						</dd>
					</div>
				{/if}
				{#if highest && highest !== lowest}
					<div>
						{@render extreme('Highest static pressure')}
						<dd class="flex flex-wrap items-center gap-x-2">
							<span class="tabular-nums">
								{f.value(highest.pressure, 'pressure', { gauge: true })}
							</span>
							{@render link(
								{ kind: 'component', id: highest.componentId },
								portName(highest.componentId, highest.portId)
							)}
							{@render sorted('nodes', 'pressure', 'descending', 'Nodes, highest first')}
						</dd>
					</div>
				{/if}
				{#if fastest}
					<div>
						{@render extreme('Highest velocity')}
						<dd class="flex flex-wrap items-center gap-x-2">
							<span class="tabular-nums">{f.value(fastest.velocity, 'velocity')}</span>
							{@render link(
								{ kind: 'connection', id: fastest.id },
								connectionName(ws.project, fastest.id)
							)}
							{@render sorted('links', 'velocity', 'descending', 'Links, highest first')}
						</dd>
					</div>
				{/if}
				{#if npsh}
					<div>
						{@render extreme('Smallest NPSH margin')}
						<dd class="flex flex-wrap items-center gap-x-2">
							<span class="tabular-nums">{f.value(npsh.margin, 'head')}</span>
							{@render link(
								{ kind: 'component', id: npsh.id },
								componentById(ws.project, npsh.id)?.name ?? npsh.id
							)}
							{#if pumps.length > 1}
								{@render sorted('pumps', 'npshMargin', 'ascending', 'Pumps, smallest first')}
							{/if}
						</dd>
					</div>
				{/if}
			</dl>
		</section>
	{/if}

	<details class="card group p-3">
		<!-- At least 44 px tall, keeping the disclosure marker. -->
		<summary class="flex min-h-11 cursor-pointer list-none items-center gap-2">
			<span
				class="text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
				aria-hidden="true">▸</span
			>
			<h3 class="font-semibold">Fluid: {fluid.name}</h3>
			{#if fluidLine}<span class="text-slate-600">{fluidLine}</span>{/if}
		</summary>
		<dl class="mt-2 space-y-1">
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
	</details>
</div>
