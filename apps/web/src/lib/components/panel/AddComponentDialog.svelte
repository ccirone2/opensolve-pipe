<!--
	Add a component next to the current one: after it at a free port, before it (inserted into
	a connection), or as a branch (a tee inserted into a connection, its branch port left free).
	A kind with no default for a value (an assigned-flow node's flow, an equipment item's rating)
	asks for it here first, wherever it goes (after, before or inserted).
-->
<script lang="ts" module>
	import type { ComponentKind as Kind } from '$lib/utils/factory';

	export type AddMode = 'after' | 'insert' | 'branch';

	/**
	 * Kinds added in one step (build-density.md §11): the kinds added last in this page (page
	 * state, never in the project), then common ones. Kinds that ask for a value first are chosen
	 * in the list below, where their fields are.
	 */
	let recentKinds: Kind[] = [];
	const COMMON: Readonly<Record<AddMode, readonly Kind[]>> = {
		after: ['gate', 'pump', 'reservoir', 'check'],
		insert: ['gate', 'check', 'globe'],
		branch: ['tee', 'wye']
	};

	const MODES = [
		{ value: 'after', label: 'At a free port (after it)' },
		{ value: 'insert', label: 'Into one of its connections' },
		{ value: 'branch', label: 'As a branch (inserts a tee)' }
	] as const;
</script>

<script lang="ts">
	import type { Component } from '$lib/api/types';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { addsUpstream, flowRole } from '$lib/utils/edit';
	import {
		createComponent,
		DEFAULT_MATERIAL_ID,
		ENTRY_KINDS,
		KIND_LABELS,
		DEFAULT_PIPE_LENGTH,
		DEFAULT_SCHEDULE,
		missingEntries,
		missingEntry,
		SHORT_PIPE_LENGTH,
		type ComponentKind,
		type EnteredValues,
		type MissingEntry
	} from '$lib/utils/factory';
	import { freePorts, neighbors, onwardFreePort } from '$lib/utils/graph';
	import { componentName, portLabel } from '$lib/utils/labels';
	import { formatValue } from '$lib/utils/units';
	import { INLINE_KINDS, useWorkspace } from '$lib/state/workspace.svelte';
	import { kindOptions } from './kinds';
	import NewComponentFields from './NewComponentFields.svelte';

	interface Props {
		component: Component;
		mode: AddMode;
		/** Connection to insert into (default: the one the walk arrived by). */
		connectionId?: string;
		/** Free port to add at (default: the way onward, the active port first; see onwardFreePort). */
		portId?: string;
		onclose: () => void;
	}

	let { component, mode: initialMode, connectionId, portId, onclose }: Props = $props();
	const ws = useWorkspace();
	const formId = $props.id();

	const free = $derived(freePorts(ws.project, component.id));
	const links = $derived(neighbors(ws.project, component.id));

	let mode = $derived<AddMode>(initialMode === 'after' && !free.length ? 'insert' : initialMode);
	// An explicit port, else the way onward: "after" a valve or pump is its outlet (see onwardFreePort).
	let port = $derived(
		free.find((p) => p.id === portId)?.id ??
			onwardFreePort(ws.project, component.id, ws.nav.activePortId)?.id ??
			''
	);
	// "Add after" on a component whose ports are all taken inserts into the way onward;
	// "Add before" and "Add branch" default to the connection the walk arrived by.
	const preferred = $derived(
		connectionId ??
			(initialMode === 'after'
				? links.find((n) => n.connection.id !== ws.nav.arrivalConnectionId)?.connection.id
				: ws.nav.arrivalConnectionId)
	);
	let connection = $derived(
		links.find((n) => n.connection.id === preferred)?.connection.id ?? links[0]?.connection.id ?? ''
	);
	let kind = $derived<ComponentKind>(mode === 'branch' ? 'tee' : 'gate');
	/** Values entered for a kind with no default for them (see NewComponentFields). */
	let values = $state<EnteredValues>({});
	/** The values still to enter, shown at their fields after Add was pressed without them. */
	let missing = $state<readonly MissingEntry[]>([]);

	const kinds = $derived(
		kindOptions((k) =>
			mode === 'after'
				? true
				: mode === 'branch'
					? k === 'tee' || k === 'wye'
					: INLINE_KINDS.includes(k)
		)
	);
	const canSubmit = $derived(mode === 'after' ? !!port : !!connection);
	// Before = into the connection the walk arrived by; at the start of the walk there is none.
	const title = $derived(
		mode === 'after'
			? `Add after ${component.name}`
			: mode === 'branch'
				? `Add a branch at ${component.name}`
				: connection && connection === ws.nav.arrivalConnectionId
					? `Add before ${component.name}`
					: initialMode === 'after'
						? `Add after ${component.name}`
						: `Insert next to ${component.name}`
	);
	/** Why a placement cannot be chosen, shown next to it. */
	function unavailable(value: AddMode): string | null {
		if (value === 'after') return free.length ? null : 'every port is connected';
		return links.length ? null : 'no connections yet';
	}
	const pipeText = $derived(
		`${formatValue(DEFAULT_PIPE_LENGTH, 'length', ws.units)} of ${(ws.library.material(DEFAULT_MATERIAL_ID)?.name ?? 'carbon steel').toLowerCase()} schedule ${DEFAULT_SCHEDULE} pipe`
	);
	const shortText = $derived(formatValue(SHORT_PIPE_LENGTH, 'length', ws.units));
	/**
	 * The losses the new connection gets where it meets a reservoir (edit.ts withReservoirLosses):
	 * an entrance where it leaves one (its upstream end, by the expected flow), an exit where it
	 * arrives at one. The expected flow is the one the connection will be made with (edit.ts
	 * addsUpstream), so an assigned-flow node's entered flow sets it; before that flow is entered
	 * only the port decides.
	 */
	const reservoirLosses = $derived.by(() => {
		if (mode !== 'after' || !port) return [];
		const added = missingEntry(kind, values) ? null : createComponent(kind, ws.project, values);
		const upstream = added
			? addsUpstream(component, port, added)
			: flowRole(component, port) === 'in';
		const ends = { from: upstream ? kind : component.type, to: upstream ? component.type : kind };
		return [
			...(ends.from === 'reservoir'
				? ['a sharp-edged pipe entrance fitting (the default loss where flow leaves a reservoir)']
				: []),
			...(ends.to === 'reservoir'
				? ['a pipe exit fitting (the default loss where flow enters a reservoir)']
				: [])
		];
	});
	const afterHint = $derived(
		`Connected at its ${portLabel(port).toLowerCase()} with ${pipeText} of the port's size` +
			(reservoirLosses.length ? ` and ${reservoirLosses.join(' and ')}` : ', no fittings') +
			'. Change it under Piping.'
	);

	/** Up to four kinds this placement takes and that need no value first, the latest first. */
	const quick = $derived(
		[...new Set([...recentKinds, ...COMMON[mode]])]
			.filter((k) => kinds.some((o) => o.value === k) && !ENTRY_KINDS.includes(k))
			.slice(0, 4)
	);

	function addNow(chosen: ComponentKind) {
		kind = chosen;
		add();
	}

	function submit(event: SubmitEvent) {
		event.preventDefault();
		add();
	}

	function add() {
		if (!canSubmit) return;
		// Every mode but a branch (a tee or wye, which need no entry) may add a kind that does.
		missing = mode === 'branch' ? [] : missingEntries(kind, values);
		if (missing.length) return;
		const added =
			mode === 'after'
				? ws.addAfter(component.id, port, kind, values)
				: mode === 'branch'
					? ws.addBranch(connection, kind === 'wye' ? 'wye' : 'tee')
					: ws.insert(connection, kind, values);
		if (added) {
			recentKinds = [kind, ...recentKinds.filter((k) => k !== kind)];
			onclose();
		}
	}
</script>

<Dialog {title} {onclose}>
	<!-- What first, then where (build-density.md §6): the choice made most often leads, and the
		placement, preset to the way onward, is one compact row of options. -->
	<form id={formId} class="space-y-3" onsubmit={submit}>
		{#if quick.length}
			<!-- One step: a press adds the kind here (2 actions from the panel: Add after, a kind). -->
			<div class="field">
				<span class="label" id="{formId}-quick">Add now</span>
				<div role="group" aria-labelledby="{formId}-quick" class="flex flex-wrap gap-1">
					{#each quick as k (k)}
						<button
							type="button"
							class="btn btn-tight"
							disabled={!canSubmit}
							onclick={() => addNow(k)}
						>
							<Icon name="plus" class="size-4 shrink-0" />{KIND_LABELS[k]}
						</button>
					{/each}
				</div>
			</div>
		{/if}
		<SelectField
			label="Component"
			value={kind}
			options={kinds}
			onchange={(v) => {
				kind = v;
				missing = [];
			}}
		/>
		<div class="fields">
			<NewComponentFields {kind} units={ws.units} bind:values bind:errors={missing} />
		</div>

		{#if initialMode === 'after' && !free.length}
			<p class="text-sm text-slate-700">
				Every port of {component.name} is connected, so the new component goes into one of its connections.
			</p>
		{/if}
		<fieldset>
			<legend class="label mb-1">Where</legend>
			<div class="flex flex-wrap gap-1">
				{#each MODES as option (option.value)}
					{@const why = unavailable(option.value)}
					<label
						class={[
							'flex min-h-ctl items-center gap-2 rounded-md border border-slate-200 px-2',
							why && 'cursor-not-allowed bg-slate-50 text-slate-500'
						]}
					>
						<input
							type="radio"
							name="{formId}-mode"
							value={option.value}
							checked={mode === option.value}
							disabled={!!why}
							onchange={() => (mode = option.value)}
						/>
						<span class="text-sm">{why ? `${option.label} (${why})` : option.label}</span>
					</label>
				{/each}
			</div>
		</fieldset>

		{#if mode === 'after'}
			{#if free.length > 1}
				<SelectField
					label="Port"
					value={port}
					options={free.map((p) => ({ value: p.id, label: portLabel(p.id) }))}
					onchange={(v) => (port = v)}
				/>
			{/if}
			<p class="hint">{afterHint}</p>
		{:else if links.length}
			<SelectField
				label="Connection"
				value={connection}
				options={links.map((n) => ({
					value: n.connection.id,
					label: `${portLabel(n.portId)}: to ${componentName(ws.project, n.otherId)} (${n.connection.id})${n.connection.id === ws.nav.arrivalConnectionId ? ', arrived by' : ''}`
				}))}
				onchange={(v) => (connection = v)}
			/>
			<p class="hint">
				The connection is split in two: its pipes and fittings stay on the upstream side, and the
				new component joins the downstream side with {shortText} of pipe like the last one.
				{#if mode === 'branch'}The new tee's branch port is left free for the branch.{/if}
			</p>
		{:else}
			<p class="text-sm text-slate-700">
				{component.name} has no connections yet. Add a component at one of its ports instead.
			</p>
		{/if}
	</form>
	{#snippet footer()}
		<button type="button" class="btn" onclick={onclose}>Cancel</button>
		<button type="submit" form={formId} class="btn btn-primary" disabled={!canSubmit}>Add</button>
	{/snippet}
</Dialog>
