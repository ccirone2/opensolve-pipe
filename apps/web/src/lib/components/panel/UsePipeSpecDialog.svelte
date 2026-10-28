<!--
	"Use a pipe spec for…" (proposal project-library.md §6.2): a project library spec for this pipe,
	for every pipe of the project of its size and material (or on its spec), or for every pipe of
	this connection. The count of pipes it changes is stated before anything changes (pipes that use
	the spec already are left as they are), and one press applies it as one undo step: each pipe
	keeps its length and its identity (scenario changes and the results shown stay on it). In the
	base case "New pipe spec…" goes on to the library's new spec form, whose spec those pipes then
	use, in the same undo step. In a scenario each pipe's spec is a change of that scenario.
-->
<script lang="ts">
	import type { PipeConnection } from '$lib/api/types';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import SelectField from '$lib/components/ui/SelectField.svelte';
	import { componentById } from '$lib/utils/graph';
	import {
		applyPipeSpec,
		pipeSpecOf,
		pipeSpecs,
		pipeSpecScope,
		type PipeSpecScope
	} from '$lib/utils/project-library';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	interface Props {
		connection: PipeConnection;
		index: number;
		onclose: () => void;
	}

	let { connection, index, onclose }: Props = $props();
	const ws = useWorkspace();
	const id = $props.id();

	const NEW_SPEC = 'new-spec';
	const specs = $derived(pipeSpecs(ws.project));
	const pipe = $derived(connection.piping.pipes[index]);
	const onSpec = $derived(pipe?.specId != null);
	let chosen = $state<string>(
		(() => {
			const own = connection.piping.pipes[index]?.specId;
			const list = pipeSpecs(ws.project);
			if (own && list.some((s) => s.id === own)) return own;
			return list[0]?.id ?? NEW_SPEC;
		})()
	);
	let kind = $state<PipeSpecScope['kind']>('same');
	const scope = $derived<PipeSpecScope>({ kind, connectionId: connection.id, pipeIndex: index });
	const spec = $derived(chosen === NEW_SPEC ? undefined : pipeSpecOf(ws.project, chosen));

	/** The pipes a scope reaches (none when this pipe is gone). */
	function pipesOf(k: PipeSpecScope['kind']): { connectionId: string; pipeIndex: number }[] {
		try {
			return pipeSpecScope(ws.project, { kind: k, connectionId: connection.id, pipeIndex: index });
		} catch {
			return [];
		}
	}

	/** The pipes a scope reaches that do not use the chosen spec already: those it changes. */
	function reached(k: PipeSpecScope['kind']): number {
		return pipesOf(k).filter((p) => {
			const target = ws.project.connections.find((c) => c.id === p.connectionId)?.piping.pipes[
				p.pipeIndex
			];
			return chosen === NEW_SPEC || target?.specId !== chosen;
		}).length;
	}

	const plural = (n: number) => `${n} pipe${n === 1 ? '' : 's'}`;
	const ends = $derived.by(() => {
		const name = (cid: string) => componentById(ws.project, cid)?.name ?? cid;
		return `${name(connection.fromComponentId)} → ${name(connection.toComponentId)}`;
	});
	const SCOPES = $derived([
		{ kind: 'pipe' as const, label: `This pipe (pipe ${index + 1} of ${ends})`, count: '' },
		{
			kind: 'same' as const,
			label: onSpec
				? 'Every pipe on the same spec as this one'
				: 'Every pipe of the same material and size as this one',
			count: plural(pipesOf('same').length)
		},
		{
			kind: 'connection' as const,
			label: `Every pipe of ${ends}`,
			count: plural(pipesOf('connection').length)
		}
	]);
	const changed = $derived(reached(kind));
	const summary = $derived(
		chosen === NEW_SPEC
			? `The new spec will be used for ${plural(changed)}, each keeping its length.`
			: changed === 0
				? 'Every pipe there uses this spec already.'
				: `${plural(changed)} will use ${spec ? `“${spec.name}”` : 'this spec'}, each keeping its length; their own material, schedule, size and overrides are replaced.${ws.inScenario ? ` In ${ws.activeScenario?.name ?? 'this scenario'}, each is a change of the scenario.` : ''} One undo step reverts it.`
	);

	function apply() {
		if (chosen === NEW_SPEC) {
			if (ws.inScenario) return;
			const target = { ...scope };
			const n = changed;
			onclose();
			ws.openLibrary({
				list: 'pipe',
				create: true,
				use: {
					label: n === 1 && target.kind === 'pipe' ? `pipe ${index + 1} of ${ends}` : plural(n),
					apply: (project, specId) => applyPipeSpec(project, specId, target).project
				}
			});
			return;
		}
		if (!spec || changed === 0) return;
		const target = { ...scope };
		const name = spec.name;
		const specId = spec.id;
		const n = changed;
		if (
			ws.edit(
				(p) => applyPipeSpec(p, specId, target).project,
				`use pipe spec ${name} for ${plural(n)}`
			)
		) {
			onclose();
			ws.notify('info', `${plural(n)} now use “${name}”. Undo reverts all of them.`);
		}
	}
</script>

<Dialog title="Use a pipe spec" {onclose}>
	<div class="space-y-4 text-sm">
		<SelectField
			label="Pipe spec"
			value={chosen}
			options={[
				...specs.map((s) => ({ value: s.id, label: `${s.name} (${s.id})` })),
				...(ws.inScenario ? [] : [{ value: NEW_SPEC, label: 'New pipe spec…' }])
			]}
			shared
			hint={specs.length
				? undefined
				: 'This project has no pipe specs yet: define one in the library, with its source.'}
			onchange={(v) => (chosen = v)}
		/>
		<fieldset class="space-y-1">
			<legend class="label mb-1">For</legend>
			{#each SCOPES as option (option.kind)}
				<label class="flex min-h-11 items-start gap-3 rounded-md px-1 py-2 hover:bg-slate-50">
					<input
						type="radio"
						class="mt-0.5 size-5 shrink-0"
						name="{id}-scope"
						value={option.kind}
						checked={kind === option.kind}
						onchange={() => (kind = option.kind)}
					/>
					<span class="min-w-0 break-words">
						{option.label}
						{#if option.count}<span class="text-slate-600">({option.count})</span>{/if}
					</span>
				</label>
			{/each}
		</fieldset>
		<p id="{id}-summary" class="rounded-md bg-slate-50 p-3 text-slate-800" role="status">
			{summary}
		</p>
	</div>
	{#snippet footer()}
		<button type="button" class="btn" onclick={onclose}>Cancel</button>
		<button
			type="button"
			class="btn btn-primary"
			aria-disabled={chosen !== NEW_SPEC && changed === 0}
			aria-describedby="{id}-summary"
			onclick={apply}
		>
			{chosen === NEW_SPEC ? 'Define the spec…' : `Use for ${plural(changed)}`}
		</button>
	{/snippet}
</Dialog>
