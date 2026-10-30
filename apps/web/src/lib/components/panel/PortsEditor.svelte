<!--
	The ports of a component: size (the default for new connections at the port), elevation where
	it matters, what each is connected to, and a way into its piping. Reservoirs can add and
	remove ports. A connected pipe of a project library spec (CLAUDE.md D22) is named by its spec,
	and compared with the port by the spec's nominal size when it states one.
-->
<script lang="ts">
	import type { Component, PipeConnection, PipeDefinition, Port } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import { addPort, canAddPort, removePort } from '$lib/utils/edit';
	import { connectionAtPort, otherEnd } from '$lib/utils/graph';
	import { componentName, npsLabel, portLabel, sameSize } from '$lib/utils/labels';
	import { pipeAtPort } from '$lib/utils/orifice';
	import { CUSTOM_MATERIAL_ID, updatePipe, withOptional } from '$lib/utils/piping';
	import { pipeSpecOf } from '$lib/utils/project-library';
	import { schemaBounds } from '$lib/utils/schema-bounds';
	import { formatValue } from '$lib/utils/units';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import NominalSizeField from './NominalSizeField.svelte';

	let { component }: { component: Component } = $props();
	const ws = useWorkspace();

	function editPort(portId: string, label: string, change: (port: Port) => Port) {
		return ws.editComponent(component.id, label, (c) => ({
			...c,
			ports: c.ports.map((p) => (p.id === portId ? change({ ...p }) : p))
		}));
	}

	/**
	 * The pipe segment that meets `port` (the first of its connection's pipes at the 'from' end,
	 * the last at the 'to' end): the solver sizes the port by it, not by the port's size.
	 */
	function pipeAt(connection: PipeConnection, port: Port): { pipe: PipeDefinition; index: number } {
		return pipeAtPort(connection, component.id, port.id);
	}

	/**
	 * "NPS 3", "a custom pipe (inner diameter 80 mm)", or for a pipe of a project library spec
	 * "pipe spec “NPS 60 STD” (NPS 60, inner diameter 1505 mm)".
	 */
	function pipeSize(pipe: PipeDefinition): string {
		if (pipe.specId != null) {
			const spec = pipeSpecOf(ws.project, pipe.specId);
			if (!spec) return `pipe spec ${pipe.specId} (not in the project library)`;
			const nps =
				spec.nominalSize != null ? `${npsLabel(spec.nominalSize, ws.library.nominalSizes)}, ` : '';
			return `pipe spec “${spec.name}” (${nps}inner diameter ${formatValue(spec.innerDiameter, 'diameter', ws.units)})`;
		}
		if (pipe.materialId === CUSTOM_MATERIAL_ID || pipe.nominalSize == null) {
			return `a custom pipe (inner diameter ${formatValue(pipe.innerDiameter, 'diameter', ws.units)})`;
		}
		return npsLabel(pipe.nominalSize, ws.library.nominalSizes);
	}

	/** A pipe's nominal size: its own, or its spec's (none for a custom pipe or a spec without one). */
	function nominalOf(pipe: PipeDefinition): number | null | undefined {
		if (pipe.specId != null) return pipeSpecOf(ws.project, pipe.specId)?.nominalSize;
		return pipe.materialId === CUSTOM_MATERIAL_ID ? null : pipe.nominalSize;
	}

	/** Ports needing attention: not connected, or sized unlike their pipe. */
	const unconnected = $derived(
		component.ports.filter((p) => !connectionAtPort(ws.project, component.id, p.id)).length
	);
	const mismatched = $derived(
		component.ports.filter((port) => {
			const connection = connectionAtPort(ws.project, component.id, port.id);
			const nominal = connection ? nominalOf(pipeAt(connection, port).pipe) : null;
			return nominal != null && !sameSize(nominal, port.nominalSize);
		}).length
	);
	const ownElevation = $derived(component.ports.some((p) => p.elevation != null));
	/** "2 ports, 1 not connected": what the closed list says (build-density.md §5). */
	const status = $derived(
		[
			`${component.ports.length} ${component.ports.length === 1 ? 'port' : 'ports'}`,
			unconnected && `${unconnected} not connected`,
			mismatched && `${mismatched} sized unlike its pipe`
		]
			.filter(Boolean)
			.join(', ')
	);
	/** Open while a port needs attention or has its own elevation (a reservoir's are shown). */
	const attention = $derived(
		unconnected + mismatched > 0 || ownElevation || component.type === 'reservoir'
	);
	let open = $state(false);
	$effect.pre(() => {
		if (attention) open = true;
	});

	function resizePipe(connection: PipeConnection, index: number, nominalSize: number) {
		ws.editConnection(connection.id, 'change pipe size', (c) => ({
			...c,
			piping: updatePipe(c.piping, index, (p) => ({ ...p, nominalSize }))
		}));
	}
</script>

<section aria-labelledby="{component.id}-ports">
	<details class="group" bind:open>
		<summary class="more-summary">
			<Icon
				name="right"
				class="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90 motion-reduce:transition-none"
			/>
			<h3 id="{component.id}-ports" class="section-title">Ports</h3>
			<span
				class={[
					'min-w-0 text-sm font-normal',
					unconnected + mismatched ? 'text-amber-800' : 'text-slate-600'
				]}>{status}</span
			>
		</summary>
		<ul class="space-y-2 pb-2">
			{#each component.ports as port (port.id)}
				{@const connection = connectionAtPort(ws.project, component.id, port.id)}
				{@const other = connection
					? otherEnd(connection, { componentId: component.id, portId: port.id })
					: undefined}
				{@const attached = connection ? pipeAt(connection, port) : undefined}
				{@const nominal = attached ? nominalOf(attached.pipe) : null}
				{@const mismatch = attached && nominal != null && !sameSize(nominal, port.nominalSize)}
				<li class="card space-y-2 p-2">
					<div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
						<span class="font-medium">{portLabel(port.id)}</span>
						<span class={['text-sm', other ? 'text-slate-600' : 'text-amber-800']}>
							{#if other}
								Connected to {componentName(ws.project, other.componentId)} ({portLabel(
									other.portId
								).toLowerCase()})
							{:else}
								<Icon name="alert" class="inline size-4 align-text-bottom" /> Not connected
							{/if}
						</span>
					</div>
					<div class="fields fields-pairs">
						<NominalSizeField
							label="Port size"
							value={port.nominalSize}
							sizes={ws.library.nominalSizes}
							units={ws.units}
							hint={attached
								? `Default size for new piping here. The solver uses the connected pipe: ${pipeSize(attached.pipe)}.`
								: 'Default size for new piping here; the solver uses the connected pipe.'}
							onchange={(size) =>
								editPort(port.id, 'change port size', (p) => ({ ...p, nominalSize: size }))}
						/>
						{#if component.type === 'reservoir' || port.elevation != null}
							<NumberField
								label="Port elevation"
								value={port.elevation}
								category="length"
								units={ws.units}
								optional
								placeholder="Same as the component"
								bounds={schemaBounds('Port', 'elevation')}
								help="Above the project datum; blank uses the component's elevation."
								onchange={(v) =>
									editPort(port.id, 'change port elevation', (p) =>
										withOptional(p, 'elevation', v)
									)}
							/>
						{/if}
					</div>
					{#if connection && attached && mismatch}
						{@const resizable =
							attached.pipe.specId == null &&
							ws.library.libraryStatus === 'ready' &&
							!!ws.library.size(attached.pipe.materialId, attached.pipe.schedule, port.nominalSize)}
						<div
							class="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900"
						>
							<p class="flex min-w-0 flex-1 basis-48 items-start gap-1">
								<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
								<span>
									The connected pipe is {pipeSize(attached.pipe)}, not {npsLabel(
										port.nominalSize,
										ws.library.nominalSizes
									)}: the solver uses the pipe, so this port size changes no result.
								</span>
							</p>
							{#if resizable && !ws.inScenario}
								<button
									type="button"
									class="btn py-1.5 text-left whitespace-normal"
									onclick={() => resizePipe(connection, attached.index, port.nominalSize)}
								>
									Make the pipe {npsLabel(port.nominalSize, ws.library.nominalSizes)}
								</button>
							{/if}
						</div>
					{/if}
					<div class="flex flex-wrap gap-2">
						<button type="button" class="btn" onclick={() => ws.nav.showConnection(port.id)}>
							{other ? 'Edit piping' : 'Connect…'}
							<Icon name="right" class="size-4" />
						</button>
						{#if component.type === 'reservoir' && !connection && component.ports.length > 1 && !ws.inScenario}
							<button
								type="button"
								class="btn btn-quiet text-red-800"
								onclick={() =>
									ws.edit((p) => removePort(p, component.id, port.id), `remove ${port.id}`)}
							>
								<Icon name="trash" class="size-4" /> Remove port
							</button>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
		{#if component.type === 'reservoir' && !ws.inScenario}
			<button
				type="button"
				class="btn"
				disabled={!canAddPort(component)}
				onclick={() => ws.edit((p) => addPort(p, component.id), 'add a reservoir port')}
			>
				<Icon name="plus" class="size-4" /> Add port
			</button>
		{/if}
	</details>
</section>
