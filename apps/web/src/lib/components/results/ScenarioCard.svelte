<!--
	Which case produced the results shown (proposal scenario-manager.md §6.11): for a scenario, its
	name, id and description and the changes the server applied to the base project before it
	built the network, with their base values (the server's record, SolveResponse.scenario, never
	the app's own mirror), each linked to its element's trace; then the changes it ignored, with the
	server's reason. Each value's field and unit are those of the project as it was solved (a
	control valve's setpoint is a pressure or a flow by its type then, a pump's speed its maximum
	when it was speed-controlled), names the project's current ones, but a pipe's: its number is
	the solve's, so its connection is named as solved once the results are out of date
	(utils/results.ts resultsProject), as the Links table names it. For the base case, nothing: its
	tab and the Compare cases tab beside it say it (proposal build-density.md §15).
-->
<script lang="ts">
	import type { Override, ScenarioResult } from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { resultsProject } from '$lib/utils/results';
	import { changeElement } from '$lib/utils/scenario-problems';
	import { changeFieldLabel, changeTargetLabel, changeValueText } from '$lib/utils/scenarios';

	let { scenario }: { scenario: ScenarioResult | null } = $props();
	const ws = useWorkspace();
	const id = $props.id();

	const applied = $derived(scenario?.overrides.filter((o) => o.state === 'applied') ?? []);
	const ignored = $derived(scenario?.overrides.filter((o) => o.state !== 'applied') ?? []);
	/** The project as it was solved (the base and its scenarios as sent), for fields and units. */
	const solvedAs = $derived(ws.store.solvedProject ?? ws.labelsProject);
	/** "Pipe 2 of A → B": a pipe by the connection as solved, its number being the solve's. */
	const target = (override: Override) => {
		const solved = ws.store.solved;
		return changeTargetLabel(
			override.kind === 'pipe' && solved
				? resultsProject(ws.labelsProject, solved)
				: ws.labelsProject,
			override
		);
	};

	function text(record: ScenarioResult['overrides'][number], value: unknown): string {
		return changeValueText(solvedAs, record.override, value, ws.displayUnits, {
			materialName: (m) => ws.library.material(m)?.name,
			nominalSizes: ws.library.nominalSizes
		});
	}
</script>

{#if scenario}
	<section
		class="space-y-2 rounded-md border border-l-4 border-teal-600 bg-teal-50 p-3 text-sm text-teal-950"
		aria-labelledby="{id}-title"
	>
		<h3 id="{id}-title" class="font-semibold">
			Scenario: {scenario.name} <span class="font-mono text-xs font-normal">({scenario.id})</span>
		</h3>
		{#if scenario.description}
			<p class="break-words whitespace-pre-line">{scenario.description}</p>
		{/if}
		{#if applied.length}
			<p>
				The base case with {applied.length === 1
					? 'this change'
					: `these ${applied.length} changes`}:
			</p>
			<ul class="list-disc space-y-1 pl-5">
				{#each applied as record (record.index)}
					{@const element = changeElement(ws.labelsProject, record.override)}
					<li class="break-words">
						{#if element}
							<button
								type="button"
								class="text-left text-blue-800 underline underline-offset-2"
								onclick={() => ws.inspect(element)}>{target(record.override)}</button
							>
						{:else}
							{target(record.override)}
						{/if}
						· {changeFieldLabel(solvedAs, record.override)}:
						<strong>{text(record, record.value)}</strong>
						<span class="text-teal-900">(base: {text(record, record.baseValue)})</span>
					</li>
				{/each}
			</ul>
		{:else}
			<p>No change applied: these are the base case's values.</p>
		{/if}
		{#if ignored.length}
			<p class="font-medium">Ignored, no longer applies:</p>
			<ul class="list-disc space-y-1 pl-5">
				{#each ignored as record (record.index)}
					<li class="break-words">
						{target(record.override)} · {changeFieldLabel(solvedAs, record.override)}: {record.message}
					</li>
				{/each}
			</ul>
		{/if}
	</section>
{/if}
