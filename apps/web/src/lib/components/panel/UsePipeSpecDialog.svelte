<!--
	"Use a pipe spec for…" (proposal project-library.md §6.2): a project library spec for this pipe,
	for every pipe of the project of its size and material (or on its spec), or for every pipe of
	this connection. The count of pipes it changes is stated before anything changes (pipes that use
	the spec already are left as they are), and one press applies it as one undo step: each pipe
	keeps its length and its identity (scenario changes and the results shown stay on it). In the
	base case "New pipe spec…" goes on to the library's new spec form, whose spec those pipes then
	use, in the same undo step (offered disabled, saying so, when the library holds as many specs as
	a project may). In a scenario each pipe's spec is a change of that scenario. A press that is
	refused (a scenario's change limit, an invalid project) says why in this dialog, which stays
	open: the workspace's notice would be behind the modal dialog (inert, and under the sheet on
	phones), so it is shown here, as the library dialog shows its refusals (proposal §12.23).
-->
<script lang="ts">
	import type { PipeConnection } from '$lib/api/types';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
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
	import { libraryFull, newOptionLabel } from '$lib/components/workspace/library/limits';

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
	/** The library holds as many specs as a project may: no new one. */
	const specsFull = $derived(libraryFull(ws.project, 'pipe'));
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
	/** Why the last press was refused, until the next choice or press. */
	let refusal = $state('');
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
			if (ws.inScenario || specsFull) return;
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
		refusal = '';
		if (
			ws.edit(
				(p) => applyPipeSpec(p, specId, target).project,
				`use pipe spec ${name} for ${plural(n)}`
			)
		) {
			onclose();
			ws.notify('info', `${plural(n)} now use “${name}”. Undo reverts all of them.`);
			return;
		}
		// ws.edit reports a refusal as the workspace's notice, behind this modal dialog: it moves
		// here.
		const notice = ws.notice;
		if (notice?.kind === 'error') {
			refusal = notice.text;
			ws.dismissNotice();
		} else {
			refusal = 'The change was not applied.';
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
				...(ws.inScenario
					? []
					: [
							{
								value: NEW_SPEC,
								label: newOptionLabel('New pipe spec…', specsFull, 'pipe'),
								disabled: specsFull
							}
						])
			]}
			shared
			hint={specs.length
				? undefined
				: 'This project has no pipe specs yet: define one in the library, with its source.'}
			onchange={(v) => {
				chosen = v;
				refusal = '';
			}}
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
						onchange={() => {
							kind = option.kind;
							refusal = '';
						}}
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
		{#if refusal}
			<p
				role="alert"
				class="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 p-3 text-red-900"
			>
				<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
				<span class="min-w-0 break-words">{refusal}</span>
			</p>
		{/if}
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
