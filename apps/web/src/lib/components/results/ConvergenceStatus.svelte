<!--
	Status of a solve: converged or not, the solver's message, iterations, compute time and the
	calculation-method version. When the solve did not converge, the convergence report: where the
	largest continuity and energy errors are, and which components kept switching state.
-->
<script lang="ts">
	import type { SolveResponse } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { componentById, connectionById } from '$lib/utils/graph';
	import { portLabel } from '$lib/utils/labels';
	import { connectionName, Formatter, type ElementRef } from '$lib/utils/results';

	let { response }: { response: SolveResponse } = $props();
	const ws = useWorkspace();
	const id = $props.id();

	const solved = $derived(response.solvedState);
	const report = $derived(solved.convergence);
	const converged = $derived(response.success && solved.converged);
	const f = $derived(new Formatter(ws.units));

	/** A residual location or oscillating element: "T1:run_inlet" (a port), a connection or a component. */
	function locate(elementId: string | null): { label: string; element: ElementRef | null } | null {
		if (!elementId) return null;
		const [componentId = '', portId] = elementId.split(':');
		if (portId !== undefined) {
			const component = componentById(ws.project, componentId);
			return {
				label: `${portLabel(portId)} of ${component?.name ?? componentId}`,
				element: component ? { kind: 'component', id: componentId } : null
			};
		}
		if (connectionById(ws.project, elementId)) {
			return {
				label: connectionName(ws.project, elementId),
				element: { kind: 'connection', id: elementId }
			};
		}
		const component = componentById(ws.project, elementId);
		return component
			? { label: component.name, element: { kind: 'component', id: elementId } }
			: { label: elementId, element: null };
	}

	/** The solver's converged message when it only repeats the iteration counts shown above. */
	const repeatsCounts = $derived(
		/^converged: \d+ Newton iterations in \d+ outer iteration\(s\)\.?$/.test(report.message)
	);

	const time = $derived(
		response.computeTime < 0.01 ? '< 0.01 s' : `${response.computeTime.toFixed(2)} s`
	);
</script>

{#snippet link(where: { label: string; element: ElementRef | null })}
	{#if where.element}
		{@const target = where.element}
		<button
			type="button"
			class="inline-flex min-h-11 items-center rounded px-1 text-left text-blue-800 underline underline-offset-2 hover:bg-white/60"
			onclick={() => ws.inspect(target)}>{where.label}</button
		>
	{:else}
		<span class="inline-flex min-h-11 items-center px-1">{where.label}</span>
	{/if}
{/snippet}

{#snippet residual(label: string, value: string, elementId: string | null)}
	{@const where = locate(elementId)}
	<li>
		<span class="block pt-1">{label}: {value}{where ? ', at' : ''}</span>
		{#if where}
			<span class="block">{@render link(where)}</span>
		{/if}
	</li>
{/snippet}

<section
	class={['space-y-1 rounded-lg border p-3', converged ? 'card' : 'border-red-300 bg-red-50']}
	aria-labelledby="{id}-title"
>
	<div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
		<h3 id="{id}-title" class="flex items-center gap-2 self-center font-semibold">
			{#if converged}
				<Icon name="check" class="size-5 text-green-700" /> Converged
			{:else}
				<Icon name="alert" class="size-5 text-red-700" /> Did not converge
			{/if}
		</h3>
		<p class="text-sm text-slate-600">
			{report.innerIterations} iterations ({report.outerIterations} outer) · {time} · method version
			{solved.methodVersion}
		</p>
	</div>
	{#if !converged || !repeatsCounts}
		<p class={converged ? 'text-xs text-slate-600' : 'text-sm text-slate-800'}>{report.message}</p>
	{/if}
	{#if !converged}
		<p class="text-sm font-medium text-red-900">
			The values below are from the last iteration. They are not a solution of the network: do not
			use them. Check the inputs near the places listed here, then solve again.
		</p>
		<ul class="list-disc space-y-1 pl-5 text-sm text-red-950">
			{@render residual(
				'Largest continuity error',
				f.value(report.maxContinuityResidual.value, 'flow'),
				report.maxContinuityResidual.elementId
			)}
			{@render residual(
				'Largest energy error',
				f.value(report.maxEnergyResidual.value, 'head'),
				report.maxEnergyResidual.elementId
			)}
			{#if report.oscillatingComponents.length}
				<li>
					<span class="block pt-1">Kept switching state (open, closed, active):</span>
					<ul class="space-y-0">
						{#each report.oscillatingComponents as elementId (elementId)}
							<li>{@render link(locate(elementId) ?? { label: elementId, element: null })}</li>
						{/each}
					</ul>
				</li>
			{/if}
		</ul>
	{/if}
</section>
