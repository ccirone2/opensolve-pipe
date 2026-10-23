/** Component kinds for the "add component" menus, grouped. */
import type { SelectOption } from '$lib/components/ui/SelectField.svelte';
import { KIND_LABELS, type ComponentKind } from '$lib/utils/factory';

const GROUPS: readonly { group: string; kinds: readonly ComponentKind[] }[] = [
	{ group: 'Boundaries and ends', kinds: ['reservoir', 'reference_node', 'plug'] },
	{ group: 'Branches', kinds: ['tee', 'wye'] },
	{ group: 'Pumps', kinds: ['pump'] },
	{ group: 'Isolation valves', kinds: ['gate', 'ball', 'butterfly', 'globe'] },
	{ group: 'Check valves', kinds: ['check', 'stop_check'] },
	{ group: 'Control valves', kinds: ['prv', 'psv', 'fcv'] }
];

/** Grouped select options for the kinds allowed by `include` (all by default). */
export function kindOptions(
	include: (kind: ComponentKind) => boolean = () => true
): SelectOption<ComponentKind>[] {
	return GROUPS.flatMap(({ group, kinds }) =>
		kinds.filter(include).map((kind) => ({ value: kind, label: KIND_LABELS[kind], group }))
	);
}
