<!--
	The physics flags of a solve (GOALS §4.6), grouped by severity: physically invalid, warnings,
	information. Each has an icon and text (names and display units); a flag about an element
	starts with that element, a link to its results and trace. A connection is named as it was
	solved once the results are out of date (utils/results.ts resultsProject), as the Links table
	names it: its flags number its pipes as solved. Long groups show their first few
	flags with "Show all", and a skip button leads past the flags to the results views, so a long
	list does not push the results several screens down.

	A valve's Crane default K outside its table (CORRELATION_OUT_OF_RANGE with the bore it was
	evaluated at; its text advises entering the manufacturer's coefficient, proposal
	project-library.md §4.3) offers "Enter a datasheet value": it shows the valve in Build with the
	focus on its resistance, which takes a K, Cv or Kv, or a project library entry.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import type { Flag } from '$lib/api/types';
	import { componentById } from '$lib/utils/graph';
	import {
		elementName,
		flagElement,
		groupFlags,
		resultsProject,
		SEVERITY_TITLES,
		type ElementRef,
		type Severity
	} from '$lib/utils/results';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import FlagIcon from './FlagIcon.svelte';

	interface Props {
		flags: readonly Flag[];
		/** Moves focus past the flags, to the results views (shown when there are several flags). */
		onskip?: () => void;
	}

	let { flags, onskip }: Props = $props();
	const ws = useWorkspace();
	const id = $props.id();
	const groups = $derived(groupFlags(flags));
	/** These flags are the shown solve's: a connection is named as that solve has it. */
	const solved = $derived(ws.store.solved);
	const nameOf = (element: ElementRef) =>
		element.kind === 'connection' && solved
			? elementName(resultsProject(ws.labelsProject, solved), element)
			: elementName(ws.project, element);

	/**
	 * The valve whose Crane default K a flag says is outside its table (the flag carries the bore
	 * the K was evaluated at), if it is still a valve of the case shown: its resistance can be
	 * entered from the datasheet.
	 */
	function datasheetValve(flag: Flag): { id: string; name: string } | null {
		if (flag.code !== 'CORRELATION_OUT_OF_RANGE' || !flag.componentId) return null;
		if (typeof flag.details?.referenceDiameter !== 'number') return null;
		const component = componentById(ws.project, flag.componentId);
		return component?.type === 'valve' ? { id: component.id, name: component.name } : null;
	}

	/** Show the valve in Build, its form open, with the focus on its resistance. */
	async function enterDatasheet(valveId: string) {
		ws.show(valveId);
		ws.nav.showComponent();
		await tick();
		const select = document.querySelector<HTMLElement>('[data-resistance-field] select');
		select?.scrollIntoView?.({ block: 'center' });
		select?.focus();
	}

	/** Flags shown per group before "Show all". */
	const SHOWN = 5;
	let expanded = $state<Severity[]>([]);

	function toggle(severity: Severity) {
		expanded = expanded.includes(severity)
			? expanded.filter((s) => s !== severity)
			: [...expanded, severity];
	}

	const NOUNS: Readonly<Record<Severity, [string, string]>> = {
		invalid: ['physically invalid flag', 'physically invalid flags'],
		warning: ['warning', 'warnings'],
		info: ['information flag', 'information flags']
	};
</script>

{#if groups.length}
	<section class="space-y-2" aria-labelledby="{id}-title">
		<div class="flex flex-wrap items-center gap-2">
			<h3 id="{id}-title" class="section-title">Flags ({flags.length})</h3>
			{#if onskip && flags.length > 3}
				<button
					type="button"
					class="btn btn-quiet sr-only px-2 text-blue-800 focus:not-sr-only"
					onclick={onskip}
				>
					Skip to the results views
				</button>
			{/if}
		</div>
		{#each groups as group (group.severity)}
			{@const open = expanded.includes(group.severity)}
			{@const shown = open ? group.flags : group.flags.slice(0, SHOWN)}
			<div
				class={[
					'rounded-lg border p-2',
					group.severity === 'invalid'
						? 'border-red-300 bg-red-50'
						: group.severity === 'warning'
							? 'border-amber-300 bg-amber-50'
							: 'border-slate-200 bg-white'
				]}
			>
				<h4 id="{id}-{group.severity}" class="flex items-center gap-2 px-1 text-sm font-semibold">
					<FlagIcon severity={group.severity} />
					{SEVERITY_TITLES[group.severity]} ({group.flags.length})
				</h4>
				<ul
					id="{id}-{group.severity}-list"
					class="mt-1 space-y-1"
					aria-labelledby="{id}-{group.severity}"
				>
					{#each shown as flag, i (i)}
						{@const element = flagElement(flag)}
						{@const text = ws.flagText(flag)}
						<li class="text-sm">
							{#if element}
								{@const name = nameOf(element)}
								{@const valve = datasheetValve(flag)}
								<!-- The whole flag opens its element: name first, then what the flag says. -->
								<button
									type="button"
									class="flex min-h-11 w-full flex-col items-start rounded px-1 py-1.5 text-left hover:bg-white/60"
									aria-label="Show {name}: {text}"
									onclick={() => ws.inspect(element)}
								>
									<span class="font-medium break-words text-blue-800 underline underline-offset-2"
										>{name}</span
									>
									<span class="break-words text-slate-800">{text}</span>
								</button>
								{#if valve}
									<button
										type="button"
										class="btn btn-quiet ml-1 px-2 text-blue-800"
										aria-label="Enter a datasheet value for {valve.name}"
										onclick={() => enterDatasheet(valve.id)}
									>
										Enter a datasheet value
									</button>
								{/if}
							{:else}
								<p class="px-1 py-1.5 break-words text-slate-800">{text}</p>
							{/if}
						</li>
					{/each}
				</ul>
				{#if group.flags.length > SHOWN}
					{@const [one, many] = NOUNS[group.severity]}
					<button
						type="button"
						class="btn btn-quiet mt-1 px-2 text-blue-800"
						aria-expanded={open}
						aria-controls="{id}-{group.severity}-list"
						onclick={() => toggle(group.severity)}
					>
						{open
							? `Show the first ${SHOWN} ${many} only`
							: `Show all ${group.flags.length} ${group.flags.length === 1 ? one : many}`}
					</button>
				{/if}
			</div>
		{/each}
	</section>
{/if}
