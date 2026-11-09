<!--
	The other cases on the group chart (CLAUDE.md D21 slice 4d; proposal pumps-results-layout.md
	§5.3, §9 S2): which other cases' station duties are drawn as numbered rings ("Cases on this
	chart", at most six), and the switch that asks for them, with its cost kept visible. A section
	component of the Pumps together card, drawn by the group chart's (PumpGroupFigure) where 4d put
	these controls; S3 gives it its heading and puts the switch first. Presentation only.
-->
<script lang="ts">
	import { GROUP_OTHER, OTHER_SYMBOL, STATION_SYMBOL } from '$lib/utils/pump-group-chart';
	import { MAX_GROUP_CASES, type OtherGroupCase } from '$lib/utils/pump-group-one-off';

	interface Props {
		/** The other cases with values, each in its state, while the card shows a station. */
		others: readonly OtherGroupCase[];
		/** "Also show the other cases' station duties" is ticked. */
		othersOn: boolean;
		/** Tick or untick it. */
		onothers: (on: boolean) => void;
		/** Tick or untick a case under "Cases on this chart". */
		onotherstick?: (key: string, on: boolean) => void;
		/** The case shown. */
		caseName?: string;
	}

	let { others, othersOn, onothers, onotherstick, caseName }: Props = $props();
	const id = $props.id();

	const othersFull = $derived(others.filter((o) => o.onChart).length >= MAX_GROUP_CASES);
</script>

{#if othersOn && others.length}
	<fieldset class="space-y-1">
		<legend class="text-xs font-medium text-slate-700">Cases on this chart</legend>
		<div class="flex flex-wrap gap-x-4">
			<span class="flex min-h-11 items-center gap-2 text-sm"
				><span aria-hidden="true">{STATION_SYMBOL}</span>
				{caseName ?? 'This case'} (shown)</span
			>
			{#each others as other (other.key)}
				{@const capped = !other.onChart && othersFull}
				<label class="flex min-h-11 items-center gap-2 text-sm">
					<input
						type="checkbox"
						class="size-4"
						checked={other.onChart}
						aria-disabled={capped}
						aria-describedby={capped ? `${id}-cases-full` : undefined}
						onclick={(event) => {
							if (capped) {
								event.preventDefault();
								return;
							}
							onotherstick?.(other.key, event.currentTarget.checked);
						}}
					/>
					{#if other.number !== null}<span aria-hidden="true" style:color={GROUP_OTHER}
							>{OTHER_SYMBOL}</span
						>
						{other.number} ·{/if}
					{other.name}{other.stale ? ' (out of date)' : ''}
				</label>
			{/each}
		</div>
		{#if othersFull && others.some((o) => !o.onChart)}
			<p id="{id}-cases-full" class="hint">
				At most {MAX_GROUP_CASES} other cases at once.
			</p>
		{/if}
	</fieldset>
{/if}
<div>
	<label class="flex min-h-11 items-center gap-2 text-sm">
		<input
			type="checkbox"
			class="size-4"
			checked={othersOn}
			aria-describedby="{id}-others-hint"
			onchange={(event) => onothers(event.currentTarget.checked)}
		/>
		Also show the other cases' station duties
	</label>
	<p id="{id}-others-hint" class="hint">
		Each case's station duty is computed on request, one case at a time, for that case's last solve:
		a solve of that case and about 41 solves of the station (its group curve, which the card shows
		when that case is shown).
	</p>
</div>
