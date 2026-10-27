<!--
	Choose the results Compare cases shows (proposal scenario-manager.md §6.12): the current rows,
	each with Move up, Move down and Remove; Add results (an element, grouped by kind, with a filter
	when there are more than six, then the quantities to add); and Reset to defaults. The choice is
	page state: a reload restores the defaults.
-->
<script lang="ts">
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import {
		ELEMENT_QUANTITIES,
		QUANTITIES,
		rowKey,
		rowLabel,
		type CompareRow,
		type Quantity
	} from '$lib/utils/compare';
	import { connectionName } from '$lib/utils/results';
	import { portLabel } from '$lib/utils/labels';

	let { rows, onclose }: { rows: readonly CompareRow[]; onclose: () => void } = $props();
	const ws = useWorkspace();
	const id = $props.id();

	type Kind = keyof typeof ELEMENT_QUANTITIES;
	interface Choice {
		value: string;
		label: string;
		group: string;
		kind: Kind;
		elementId?: string;
		portId?: string;
	}

	const choices = $derived.by((): Choice[] => {
		const project = ws.labelsProject;
		const list: Choice[] = [
			{ value: 'network', label: 'The whole network', group: 'Network', kind: 'network' }
		];
		for (const c of project.components) {
			const kind: Kind | null =
				c.type === 'pump'
					? 'pump'
					: c.type === 'valve'
						? 'valve'
						: c.type === 'equipment'
							? 'equipment'
							: c.type === 'reservoir' || c.type === 'reference_node'
								? 'boundary'
								: c.type === 'assigned_flow'
									? 'assigned'
									: null;
			if (kind) {
				list.push({
					value: `${kind}:${c.id}`,
					label: c.name,
					group: GROUPS[kind],
					kind,
					elementId: c.id
				});
			}
		}
		for (const c of project.connections) {
			list.push({
				value: `connection:${c.id}`,
				label: connectionName(project, c.id),
				group: 'Pipe connections',
				kind: 'connection',
				elementId: c.id
			});
		}
		for (const c of project.components) {
			for (const p of c.ports) {
				list.push({
					value: `port:${c.id}:${p.id}`,
					label: `${portLabel(p.id)} of ${c.name}`,
					group: 'Ports',
					kind: 'port',
					elementId: c.id,
					portId: p.id
				});
			}
		}
		return list;
	});

	const GROUPS: Record<Kind, string> = {
		network: 'Network',
		pump: 'Pumps',
		valve: 'Valves',
		equipment: 'Equipment',
		connection: 'Pipe connections',
		port: 'Ports',
		boundary: 'Reservoirs and reference nodes',
		assigned: 'Assigned-flow nodes'
	};

	let filter = $state('');
	const shownChoices = $derived(
		filter.trim()
			? choices.filter((c) => c.label.toLowerCase().includes(filter.trim().toLowerCase()))
			: choices
	);
	let selected = $state('network');
	const choice = $derived(shownChoices.find((c) => c.value === selected) ?? shownChoices[0]);
	let picked = $state<Quantity[]>([]);

	const current = $derived([...rows]);

	function set(next: CompareRow[]) {
		ws.compareRows = next;
	}

	function move(i: number, by: -1 | 1) {
		const to = i + by;
		if (to < 0 || to >= current.length) return;
		const next = [...current];
		const [row] = next.splice(i, 1);
		next.splice(to, 0, row as CompareRow);
		set(next);
	}

	function add() {
		if (!choice || !picked.length) return;
		const known = new Set(current.map(rowKey));
		const added = picked
			.map((quantity): CompareRow => ({
				quantity,
				...(choice.elementId ? { elementId: choice.elementId } : {}),
				...(choice.portId ? { portId: choice.portId } : {})
			}))
			.filter((row) => !known.has(rowKey(row)));
		set([...current, ...added]);
		picked = [];
	}
</script>

<Dialog title="Choose results to compare" wide {onclose}>
	<div class="space-y-5 text-sm">
		<section class="space-y-2" aria-labelledby="{id}-rows">
			<h3 id="{id}-rows" class="section-title">Results shown ({current.length})</h3>
			<ul class="divide-y divide-slate-100 rounded-md border border-slate-200">
				{#each current as row, i (rowKey(row))}
					{@const label = rowLabel(ws.labelsProject, row)}
					<li class="flex flex-wrap items-center gap-x-2 px-2 py-1">
						<span class="min-w-0 flex-1 basis-48 break-words">{label}</span>
						<button
							type="button"
							class="btn btn-quiet btn-icon"
							aria-label="Move {label} up"
							aria-disabled={i === 0}
							onclick={() => move(i, -1)}><Icon name="up" class="size-4" /></button
						>
						<button
							type="button"
							class="btn btn-quiet btn-icon"
							aria-label="Move {label} down"
							aria-disabled={i === current.length - 1}
							onclick={() => move(i, 1)}><Icon name="down" class="size-4" /></button
						>
						<button
							type="button"
							class="btn btn-quiet btn-icon text-red-800"
							aria-label="Remove {label}"
							onclick={() => set(current.filter((_, j) => j !== i))}
							><Icon name="trash" class="size-4" /></button
						>
					</li>
				{/each}
			</ul>
			<button type="button" class="btn" onclick={() => (ws.compareRows = null)}
				>Reset to defaults</button
			>
		</section>

		<section class="space-y-3" aria-labelledby="{id}-add">
			<h3 id="{id}-add" class="section-title">Add results</h3>
			{#if choices.length > 6}
				<div>
					<label for="{id}-filter" class="label mb-1">Filter elements</label>
					<input
						id="{id}-filter"
						class="input"
						type="search"
						autocomplete="off"
						bind:value={filter}
					/>
				</div>
			{/if}
			<div>
				<label for="{id}-element" class="label mb-1">Element</label>
				<select
					id="{id}-element"
					class="input pr-8"
					value={choice?.value ?? ''}
					onchange={(event) => {
						selected = event.currentTarget.value;
						picked = [];
					}}
				>
					{#each Object.entries(GROUPS) as [kind, group] (kind)}
						{@const members = shownChoices.filter((c) => c.kind === kind)}
						{#if members.length}
							<optgroup label={group}>
								{#each members as c (c.value)}
									<option value={c.value}>{c.label}</option>
								{/each}
							</optgroup>
						{/if}
					{/each}
				</select>
			</div>
			{#if choice}
				<fieldset class="space-y-1">
					<legend class="label mb-1">Results of {choice.label}</legend>
					{#each ELEMENT_QUANTITIES[choice.kind] as quantity (quantity)}
						<label class="flex min-h-11 items-center gap-3">
							<input type="checkbox" class="size-4" value={quantity} bind:group={picked} />
							{QUANTITIES[quantity].label}
						</label>
					{/each}
				</fieldset>
				<button type="button" class="btn" aria-disabled={!picked.length} onclick={add}>
					<Icon name="plus" class="size-4" /> Add
				</button>
			{/if}
		</section>
	</div>
	{#snippet footer()}
		<button type="button" class="btn btn-primary" onclick={onclose}>Done</button>
	{/snippet}
</Dialog>
