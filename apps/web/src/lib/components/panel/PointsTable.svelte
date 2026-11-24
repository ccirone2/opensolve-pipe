<!--
	A table of curve points (x, y), each cell a unit-aware number. Edits are stored as soon as
	every row is complete and there are at least `minRows`; until then they stay in the table
	(e.g. while a new curve is typed in). Points are kept in the order entered; flows that do not
	increase are flagged. In a scenario (field-mode.ts) the curve is the same in every case: the
	cells are locked and rows cannot be added or removed.

	A column, or a table of both columns, pasted into a cell fills the table from that row, adding
	rows as needed (paste-points.ts; proposal usability-entry.md §6): from a spreadsheet or a data
	sheet, a heading row's units converted. A paste with one bad cell pastes nothing and says why.
	The line under the table says what a paste did while the table holds the rows it made, so an
	undo, an edit or a point added or removed takes it away.
-->
<script lang="ts" module>
	export interface Point {
		x: number;
		y: number;
	}
</script>

<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import { useFieldMode } from '$lib/components/ui/field-mode';
	import Icon from '$lib/components/ui/Icon.svelte';
	import NumberField from '$lib/components/ui/NumberField.svelte';
	import { inSentence, readPastedPoints, type PasteColumn } from '$lib/utils/paste-points';
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

	const mode = useFieldMode();
	const locked = $derived(!!mode?.scenario);

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
		pasted = null;
		update(draft.map((r, i) => (i === index ? { ...r, [key]: value } : r)));
	}

	/**
	 * What the last paste did, with the rows it made, or why it pasted nothing. A paste's note is
	 * shown while the table holds those rows (an undo, an edit elsewhere or another point takes it
	 * away); a refusal's until the next edit of the table.
	 */
	let pasted = $state<{ text: string; error: boolean; rows: Draft[] | null } | null>(null);
	const sameRows = (a: readonly Draft[], b: readonly Draft[]) =>
		a.length === b.length && a.every((row, i) => row.x === b[i]?.x && row.y === b[i]?.y);
	const note = $derived(
		pasted && (pasted.error || (pasted.rows && sameRows(draft, pasted.rows))) ? pasted : null
	);

	/** "point 4", "points 4 and 5", "points 4 to 6", "points 2, 4 and 7". */
	function pointsText(numbers: readonly number[]): string {
		const [first] = numbers;
		const last = numbers[numbers.length - 1];
		if (first === undefined || last === undefined) return '';
		if (numbers.length === 1) return `point ${first}`;
		if (numbers.length > 2 && last - first === numbers.length - 1)
			return `points ${first} to ${last}`;
		return `points ${numbers.slice(0, -1).join(', ')} and ${last}`;
	}

	/** A paste into row `index`'s cell in column `at`: true when it was a column or a table. */
	function paste(index: number, at: PasteColumn, text: string): boolean {
		const read = readPastedPoints(text, at, x, y, units);
		if (!read) return false;
		if (!read.ok) {
			pasted = { text: read.error, error: true, rows: null };
			return true;
		}
		const end = index + read.rows.length;
		if (end > maxRows) {
			pasted = {
				text: `Nothing was pasted: this table takes at most ${maxRows} points, and ${read.rows.length} from point ${index + 1} would make ${end}.`,
				error: true,
				rows: null
			};
			return true;
		}
		// Both columns: the pasted table is the curve from that point on, so no point of the old
		// curve is left after it unseen. One column: the other column stays, and points after the
		// pasted ones keep their values in this one, as the note says (usability-entry.md §10).
		const both = read.columns.length === 2;
		const next = draft.slice(0, both ? index : draft.length).map((r) => ({ ...r }));
		while (next.length < end) next.push({ x: null, y: null });
		read.rows.forEach((row, k) => {
			const target = next[index + k];
			if (!target) return;
			for (const column of read.columns) target[column] = row[column] ?? null;
		});
		// The points after the pasted ones that had a value: removed, or keeping it. A blank row
		// (a new curve's) is no point and goes unmentioned.
		const column = read.columns[0] === 'x' ? 'x' : 'y';
		const after = draft
			.map((row, i) => ({ row, number: i + 1 }))
			.slice(end)
			.filter(({ row }) => (both ? row.x !== null || row.y !== null : row[column] !== null))
			.map(({ number }) => number);
		const them = read.rows.length === 1 ? 'it' : 'them';
		const listed = pointsText(after);
		const left =
			after.length === 0
				? ''
				: both
					? ` The ${after.length === 1 ? 'point' : 'points'} after ${them} (${listed}) ${after.length === 1 ? 'was' : 'were'} removed.`
					: ` ${listed.replace(/^p/, 'P')} ${after.length === 1 ? 'keeps its' : 'keep their'} earlier ${inSentence((column === 'x' ? x : y).label)}.`;
		update(next);
		pasted = { text: read.summary + left, error: false, rows: next };
		return true;
	}
</script>

<div class="min-w-0">
	<table class="w-full table-fixed border-separate border-spacing-x-2 border-spacing-y-px">
		<caption class="caption-top text-left text-sm font-medium text-slate-700">{caption}</caption>
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
							onpaste={(text) => paste(i, 'x', text)}
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
							onpaste={(text) => paste(i, 'y', text)}
						/>
					</td>
					<td>
						{#if !locked}
							<button
								type="button"
								class="btn btn-quiet btn-icon"
								aria-label="Remove point {i + 1}"
								disabled={draft.length <= minRows}
								onclick={() => {
									pasted = null;
									update(draft.filter((_, j) => j !== i));
								}}
							>
								<Icon name="trash" />
							</button>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
	<div class="mt-1 flex flex-wrap items-center gap-2">
		{#if !locked}
			<button
				type="button"
				class="btn"
				disabled={draft.length >= maxRows}
				onclick={() => {
					pasted = null;
					draft = [...draft, { x: null, y: null }];
				}}
			>
				<Icon name="plus" class="size-4" /> Add point
			</button>
		{/if}
		{#if pending}
			<p class="text-sm text-amber-800">
				{enough
					? 'Not saved yet: complete or remove the unfinished rows.'
					: `Not saved yet: enter at least ${minRows} complete points.`}
			</p>
		{/if}
	</div>
	<!-- The paste's note in a region present from the start, so what is written in it is
		announced; the standing hint stays out of it, so an edit does not announce the hint. -->
	<p
		class={['text-sm', note ? 'mt-1' : 'sr-only', note?.error ? 'text-red-700' : 'text-slate-700']}
		aria-live="polite"
	>
		{note?.text ?? ''}
	</p>
	{#if !note && !locked}
		<p class="hint mt-1">
			Paste a column, or both columns with their headings, from a spreadsheet or data sheet.
		</p>
	{/if}
	{#if !increasing}
		<p class="mt-1 flex items-start gap-1 text-sm text-amber-800">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
			<span>{x.label} must increase from each point to the next.</span>
		</p>
	{/if}
</div>
