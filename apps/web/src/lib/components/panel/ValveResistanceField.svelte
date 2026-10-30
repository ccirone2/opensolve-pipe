<!--
	A valve's resistance (ResistanceField) in the workspace: the case's value, a scenario value in a
	scenario, and the project library's entries (CLAUDE.md D22). "New entry…" opens the library's
	new entry form, and the entry saved is used for this valve in the same undo step (offered
	disabled when the library holds as many entries as a project may).
-->
<script lang="ts">
	import type { CheckValve, ControlValve, IsolationValve } from '$lib/api/types';
	import { withOptional } from '$lib/utils/piping';
	import { resistanceEntries, setValveResistance } from '$lib/utils/project-library';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { libraryFull } from '$lib/components/workspace/library/limits';
	import ResistanceField from './ResistanceField.svelte';

	interface Props {
		component: IsolationValve | CheckValve | ControlValve;
		/** What "default" means for this valve. */
		defaultLabel: string;
	}

	let { component, defaultLabel }: Props = $props();
	const ws = useWorkspace();

	function library(entryId: string | null) {
		if (entryId !== null) {
			ws.openLibrary({ list: 'resistance', edit: entryId });
			return;
		}
		const valveId = component.id;
		ws.openLibrary({
			list: 'resistance',
			create: true,
			use: {
				label: component.name,
				apply: (project, id) => setValveResistance(project, valveId, { kind: 'library', id })
			}
		});
	}
</script>

<ResistanceField
	value={component.resistance}
	units={ws.units}
	{defaultLabel}
	entries={resistanceEntries(ws.project)}
	onlibrary={library}
	editLibrary={!ws.inScenario}
	libraryFull={libraryFull(ws.project, 'resistance')}
	change={ws.componentChange(component.id, 'resistance')}
	onchange={(r) =>
		ws.editComponent<IsolationValve | CheckValve | ControlValve>(
			component.id,
			'change valve resistance',
			(c) => withOptional(c, 'resistance', r)
		)}
/>
