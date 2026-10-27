<!--
	The connection at a chosen port of the current component (SDD §3.1.1 ConnectionPanel): its key
	results from the last solve (ResultStrip), its pipes and fittings, or — for a port that is not connected — ways to connect it: add a
	component there, plug it, or connect it to a free port elsewhere (to close a loop).
-->
<script lang="ts">
	import type { Component } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { removePort } from '$lib/utils/edit';
	import {
		ENTRY_KINDS,
		missingEntries,
		type ComponentKind,
		type EnteredValues,
		type MissingEntry
	} from '$lib/utils/factory';
	import { connectionAtPort, freePorts, otherEnd } from '$lib/utils/graph';
	import { componentName, npsLabel, portLabel } from '$lib/utils/labels';
	import { addPipe } from '$lib/utils/piping';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import AddComponentDialog, { type AddMode } from './AddComponentDialog.svelte';
	import FittingsEditor from './FittingsEditor.svelte';
	import { kindOptions } from './kinds';
	import NewComponentFields from './NewComponentFields.svelte';
	import PipeSegmentForm from './PipeSegmentForm.svelte';
	import ResultStrip from './ResultStrip.svelte';

	let { component }: { component: Component } = $props();
	const ws = useWorkspace();
	const id = $props.id();

	const portId = $derived(ws.nav.activePortId);
	const port = $derived(component.ports.find((p) => p.id === portId));
	const connection = $derived(
		portId ? connectionAtPort(ws.project, component.id, portId) : undefined
	);
	const other = $derived(
		connection && portId ? otherEnd(connection, { componentId: component.id, portId }) : undefined
	);

	let dialog = $state<AddMode | null>(null);
	let kind = $state<ComponentKind>('gate');
	/** Values entered for a kind with no default for them (see NewComponentFields). */
	let values = $state<EnteredValues>({});
	let missing = $state<readonly MissingEntry[]>([]);
	let target = $state('');

	function addHere(portId: string) {
		missing = missingEntries(kind, values);
		if (!missing.length) ws.addAfter(component.id, portId, kind, values);
	}

	/** Free ports of other components, for closing a loop. */
	const targets = $derived(
		ws.project.components
			.filter((c) => c.id !== component.id)
			.flatMap((c) =>
				freePorts(ws.project, c.id).map((p) => ({
					value: `${c.id}\u0000${p.id}`,
					label: `${c.name}: ${portLabel(p.id).toLowerCase()}`
				}))
			)
	);
	const chosenTarget = $derived(
		targets.some((t) => t.value === target) ? target : (targets[0]?.value ?? '')
	);

	function connect() {
		const [componentId, targetPort] = chosenTarget.split('\u0000');
		if (!portId || !componentId || !targetPort) return;
		ws.connect({ componentId: component.id, portId }, { componentId, portId: targetPort });
	}
</script>

<div class="space-y-4">
	<div role="group" aria-label="Ports of {component.name}" class="flex flex-wrap gap-2">
		{#each component.ports as p (p.id)}
			{@const linked = connectionAtPort(ws.project, component.id, p.id)}
			<button
				type="button"
				class={[
					'btn h-auto flex-col items-start gap-0 py-1.5 text-left',
					p.id === portId && 'border-blue-700 bg-blue-50 ring-1 ring-blue-700'
				]}
				aria-pressed={p.id === portId}
				onclick={() => ws.nav.showConnection(p.id)}
			>
				<span>{portLabel(p.id)}</span>
				<span class="text-xs font-normal text-slate-600">
					{linked
						? `to ${componentName(ws.project, otherEnd(linked, { componentId: component.id, portId: p.id }).componentId)}`
						: 'not connected'}
				</span>
			</button>
		{/each}
	</div>

	{#if connection && other && portId}
		<section aria-labelledby="{id}-conn" class="space-y-4">
			<div class="space-y-2">
				<h3 id="{id}-conn" class="text-base font-semibold">
					Connection <span class="font-mono">{connection.id}</span>
				</h3>
				<p class="text-sm text-slate-700">
					From {componentName(ws.project, connection.fromComponentId)} ({portLabel(
						connection.fromPortId
					).toLowerCase()}) to {componentName(ws.project, connection.toComponentId)} ({portLabel(
						connection.toPortId
					).toLowerCase()}). Positive flow runs this way, and the pipes are listed in that order.
				</p>
				<ResultStrip element={{ kind: 'connection', id: connection.id }} />
				<div class="flex flex-wrap gap-2">
					<button type="button" class="btn" onclick={() => ws.nav.follow(connection.id)}>
						Go to {componentName(ws.project, other.componentId)}
						<Icon name="right" class="size-4" />
					</button>
					{#if !ws.inScenario}
						<button type="button" class="btn" onclick={() => (dialog = 'insert')}>
							<Icon name="insert" class="size-4" /> Insert component
						</button>
						<button type="button" class="btn" onclick={() => (dialog = 'branch')}>
							<Icon name="branch" class="size-4" /> Add branch
						</button>
						<button
							type="button"
							class="btn btn-quiet text-red-800"
							onclick={() => {
								const removed = connection.id;
								if (ws.disconnect(removed)) {
									ws.notify('info', `Connection ${removed} removed. Undo restores it.`);
								}
							}}
						>
							<Icon name="trash" class="size-4" /> Disconnect
						</button>
					{/if}
				</div>
			</div>

			<div class="space-y-3">
				<h3 class="section-title">Pipes</h3>
				{#each connection.piping.pipes as pipe, i (i)}
					<PipeSegmentForm {connection} index={i} {pipe} />
				{/each}
				{#if !ws.inScenario}
					<button
						type="button"
						class="btn"
						disabled={connection.piping.pipes.length >= 100}
						onclick={() =>
							ws.editConnection(connection.id, 'add pipe segment', (c) => ({
								...c,
								piping: addPipe(c.piping)
							}))}
					>
						<Icon name="plus" class="size-4" /> Add pipe segment
					</button>
				{/if}
			</div>

			<FittingsEditor {connection} />
		</section>
	{:else if portId && port}
		<section aria-labelledby="{id}-free" class="card space-y-4 p-3">
			<div>
				<h3 id="{id}-free" class="flex items-center gap-2 text-base font-semibold text-amber-900">
					<Icon name="alert" class="size-5" />
					{portLabel(portId)} is not connected
				</h3>
				<p class="mt-1 text-sm text-slate-700">
					Every port must be connected or plugged before the network can be solved. New piping here
					starts at the port size ({npsLabel(port.nominalSize, ws.library.nominalSizes)}).
				</p>
			</div>
			{#if ws.inScenario}
				<div class="flex flex-wrap items-center gap-2">
					<p class="min-w-0 flex-1 basis-48 text-sm text-slate-700">
						Switch to the base case to connect or plug this port: the layout of the network is the
						same in every scenario.
					</p>
					<button type="button" class="btn" onclick={() => ws.setCase(null)}>
						Switch to base case
					</button>
				</div>
			{:else}
				<div class="flex flex-wrap items-end gap-2">
					<SelectField
						label="Add a component here"
						value={kind}
						options={kindOptions()}
						class="min-w-48 flex-1"
						onchange={(v) => {
							kind = v;
							missing = [];
						}}
					/>
					{#if ENTRY_KINDS.includes(kind)}
						<div class="grid basis-full gap-3 sm:grid-cols-2">
							<NewComponentFields {kind} units={ws.units} bind:values bind:errors={missing} />
						</div>
					{/if}
					<button type="button" class="btn btn-primary" onclick={() => addHere(portId)}>
						<Icon name="plus" class="size-4" /> Add
					</button>
				</div>
				<div class="flex flex-wrap gap-2">
					<button type="button" class="btn" onclick={() => ws.plug(component.id, portId)}>
						Plug this port
					</button>
					{#if component.type === 'reservoir' && component.ports.length > 1}
						<button
							type="button"
							class="btn btn-quiet text-red-800"
							onclick={() =>
								ws.edit((p) => removePort(p, component.id, portId), `remove ${portId}`)}
						>
							<Icon name="trash" class="size-4" /> Remove this port
						</button>
					{/if}
				</div>
				{#if targets.length}
					<div class="border-t border-slate-200 pt-3">
						<div class="flex flex-wrap items-end gap-2">
							<SelectField
								label="Or connect to a free port"
								value={chosenTarget}
								options={targets}
								class="min-w-48 flex-1"
								onchange={(v) => (target = v)}
							/>
							<button type="button" class="btn" onclick={connect}>Connect</button>
						</div>
						<p class="hint">For example to close a loop. The new connection gets a default pipe.</p>
					</div>
				{/if}
			{/if}
		</section>
	{/if}
</div>

{#if dialog && connection}
	<AddComponentDialog
		{component}
		mode={dialog}
		connectionId={connection.id}
		onclose={() => (dialog = null)}
	/>
{/if}
