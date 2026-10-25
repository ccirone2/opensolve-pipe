/**
 * How inputs behave in the case shown (proposal scenario-manager.md §6.6). Workspace.svelte
 * provides it; NumberField, SelectField and TextField read it. In a scenario a field is locked
 * (read-only, still focusable, "Same in every scenario") unless it is a scenario value (its form
 * gives it a `change`) or shared by every case (names, the project's description, display units,
 * and choices that only change the view, such as which pump's chart is shown: `shared`). Locked
 * by default: a field added later is never editable in a scenario by accident. Outside a
 * workspace (no context) every field is as it always was.
 */
import { getContext, setContext } from 'svelte';

export interface FieldMode {
	/** A scenario is shown: fields without a `change` or `shared` are locked. */
	readonly scenario: boolean;
}

/**
 * What a form shows about one scenario value: in a scenario, that the value is the scenario's to
 * change (`inScenario`), whether it changes it (`changed`), the base value (`baseText`) and Reset;
 * in the base case, the scenarios that set their own value (`setBy`).
 */
export interface FieldChange {
	inScenario: boolean;
	changed: boolean;
	/** The base value as shown ("2.50 m"). */
	baseText: string;
	/** The field's name ("Liquid level"), for Reset's accessible name. */
	label: string;
	/** Remove the change: the base value applies again (one undo step). */
	reset: () => void;
	/** In the base case: names of the scenarios that set their own value. */
	setBy: string[];
}

const KEY = Symbol('opensolve-pipe:field-mode');

export function provideFieldMode(mode: FieldMode): FieldMode {
	return setContext(KEY, mode);
}

export function useFieldMode(): FieldMode | undefined {
	return getContext<FieldMode | undefined>(KEY);
}

/** Whether a field is locked: in a scenario, neither a scenario value nor shared. */
export function isLocked(
	mode: FieldMode | undefined,
	change: FieldChange | null | undefined,
	shared: boolean
): boolean {
	return !!mode?.scenario && !change && !shared;
}

/**
 * Whether ChangeNote shows something for `change`: in a scenario that changes the value, or in
 * the base case when scenarios set their own value. A group's members are described by the note
 * only then (aria-describedby never names a missing element).
 */
export function hasChangeNote(change: FieldChange | null | undefined): boolean {
	return !!change && (change.inScenario ? change.changed : change.setBy.length > 0);
}

/** "Winter sets its own value." or "3 scenarios set their own value: Winter, Peak, Night." */
export function setByText(names: readonly string[]): string {
	if (names.length === 1) return `${names[0]} sets its own value.`;
	return `${names.length} scenarios set their own value: ${names.join(', ')}.`;
}
