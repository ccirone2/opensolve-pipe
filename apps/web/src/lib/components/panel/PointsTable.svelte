<!--
	A table of curve points (x, y), each cell a unit-aware number. Edits are stored as soon as
	every row is complete and there are at least `minRows`; until then they stay in the table
	(e.g. while a new curve is typed in). Points are kept in the order entered; flows that do not
	increase are flagged.
-->
<script lang="ts" module>
	export interface Point {
		x: number;
		y: number;
	}
</script>

<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import type { Bounds } from '$lib/utils/schema-bounds';
	import { displayUnit, unitLabel, type UnitCategory } from '$lib/utils/units';

	interface Axis {
		label: string;
		category: UnitCategory;
		bounds: Bounds;
	}

	interface Props {
		caption: string;
		rows: readonly Point[];
		x: Axis;
		y: Axis;
		units: UnitPreferences;
		minRows: number;
		maxRows?: number;
		/** Blank rows shown when there are no points yet. */
		emptyRows?: number;
		onchange: (rows: Point[]) => boolean | void;
	}

	let {
		caption,
		rows,
		x,
		y,
		units,
		minRows,
		maxRows = 50,
		emptyRows = minRows,
		onchange
	}: Props = $props();

	type Draft = { x: number | null; y: number | null };

	let draft = $derived<Draft[]>(
		rows.length
			? rows.map((r) => ({ x: r.x, y: r.y }))
			: Array.from({ length: emptyRows }, () => ({ x: null, y: null }))
	);

	const complete = $derived(draft.every((r) => r.x !== null && r.y !== null));
	const enough = $derived(draft.length >= minRows);
	const increasing = $derived(
		draft.every((r, i) => {
			const previous = draft[i - 1];
			return i === 0 || r.x === null || previous?.x == null || r.x > previous.x;
		})
	);
	const pending = $derived(!complete || !enough);

	function header(axis: Axis): string {
		const label = unitLabel(axis.category, displayUnit(axis.category, units));
		return label ? `${axis.label} (${label})` : axis.label;
	}

	function update(next: Draft[]) {
		draft = next;
		if (next.length >= minRows && next.every((r) => r.x !== null && r.y !== null)) {
			onchange(next.map((r) => ({ x: r.x as number, y: r.y as number })));
		}
	}

	function setCell(index: number, key: 'x' | 'y', value: number | null) {
		update(draft.map((r, i) => (i === index ? { ...r, [key]: value } : r)));
	}
</script>

<div class="min-w-0">
	<table class="w-full table-fixed border-separate border-spacing-x-2 border-spacing-y-1">
		<caption class="caption-top pb-1 text-left text-sm font-medium text-slate-700"
			>{caption}</caption
		>
		<thead>
			<tr class="text-left text-xs font-medium text-slate-600">
				<th scope="col" class="w-8 font-medium">#</th>
				<th scope="col" class="font-medium">{header(x)}</th>
				<th scope="col" class="font-medium">{header(y)}</th>
				<th scope="col" class="w-11"><span class="sr-only">Remove</span></th>
			</tr>
		</thead>
		<tbody>
			{#each draft as row, i (i)}
				<tr>
					<td class="text-sm text-slate-600">{i + 1}</td>
					<td>
						<NumberField
							label="Point {i + 1} {x.label.toLowerCase()}"
							hideLabel
							compact
							optional
							value={row.x}
							category={x.category}
							{units}
							bounds={x.bounds}
							onchange={(v) => setCell(i, 'x', v)}
						/>
					</td>
					<td>
						<NumberField
							label="Point {i + 1} {y.label.toLowerCase()}"
							hideLabel
							compact
							optional
							value={row.y}
							category={y.category}
							{units}
							bounds={y.bounds}
							onchange={(v) => setCell(i, 'y', v)}
						/>
					</td>
					<td>
						<button
							type="button"
							class="btn btn-quiet btn-icon"
							aria-label="Remove point {i + 1}"
							disabled={draft.length <= minRows}
							onclick={() => update(draft.filter((_, j) => j !== i))}
						>
							<Icon name="trash" />
						</button>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
	<div class="mt-1 flex flex-wrap items-center gap-2">
		<button
			type="button"
			class="btn"
			disabled={draft.length >= maxRows}
			onclick={() => (draft = [...draft, { x: null, y: null }])}
		>
			<Icon name="plus" class="size-4" /> Add point
		</button>
		{#if pending}
			<p class="text-sm text-amber-800">
				{enough
					? 'Not saved yet: complete or remove the unfinished rows.'
					: `Not saved yet: enter at least ${minRows} complete points.`}
			</p>
		{/if}
	</div>
	{#if !increasing}
		<p class="mt-1 flex items-start gap-1 text-sm text-amber-800">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
			<span>{x.label} must increase from each point to the next.</span>
		</p>
	{/if}
</div>
