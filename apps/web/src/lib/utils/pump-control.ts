/**
 * Speed control of a pump (CLAUDE.md D11, `Pump.control`) as the Build panel enters it.
 *
 * Switching a pump to flow control needs two values the user has to give: the flow setpoint and
 * the minimum speed, which has no default (no cited value exists; the drive's data gives it). They
 * are held as a draft in the form until both are within the schema's bounds and the minimum speed
 * is below the pump's speed (the maximum, `x-ordered-fields`). Then one undoable edit writes the
 * whole control, so a project, and every link to it, never holds a partial control or a value the
 * user did not enter. Bounds and the order come from the API schema (schema-bounds.ts,
 * model-rules.ts), never from here.
 */
import type { Pump } from '../api/types';
import { intersectBounds, orderedBounds, orderViolations } from './model-rules';
import { boundsProblem, schemaBounds, type Bounds } from './schema-bounds';

/** A pump's speed control (the API's PumpControl). */
export type PumpControl = NonNullable<Pump['control']>;

/** The fields of a flow control being entered; null until entered. */
export interface ControlDraft {
	setpoint: number | null;
	minSpeed: number | null;
}

export const EMPTY_CONTROL_DRAFT: Readonly<ControlDraft> = Object.freeze({
	setpoint: null,
	minSpeed: null
});

/** The control fields the panel enters, by their path in `Pump`. */
export type ControlField = 'setpoint' | 'minSpeed';

/** The pump as it would be with `draft` as its control: entered fields only, for the order rule. */
function withDraft(pump: Pump, draft: ControlDraft): Record<string, unknown> {
	const control: Record<string, unknown> = { mode: 'flow' };
	if (draft.setpoint !== null) control.setpoint = draft.setpoint;
	if (draft.minSpeed !== null) control.minSpeed = draft.minSpeed;
	return { ...pump, control };
}

/**
 * The bounds of a control field of `pump` (SI): the schema's (`PumpControl`), tightened by the
 * ordered fields (the minimum speed below the speed). `draft` is the control being entered,
 * when the pump has none yet.
 */
export function controlFieldBounds(pump: Pump, field: ControlField, draft?: ControlDraft): Bounds {
	const subject = !pump.control && draft ? withDraft(pump, draft) : pump;
	return intersectBounds(
		schemaBounds('PumpControl', field),
		orderedBounds(subject, `control.${field}`)
	);
}

/**
 * The bounds of the pump's speed (SI): the schema's (`Pump.speed`), and for a speed-controlled
 * pump (or one whose control is being entered) above its minimum speed, since the speed is then
 * the maximum.
 */
export function speedBounds(pump: Pump, draft?: ControlDraft | null): Bounds {
	const subject = !pump.control && draft ? withDraft(pump, draft) : pump;
	return intersectBounds(schemaBounds('Pump', 'speed'), orderedBounds(subject, 'speed'));
}

/** Why `draft` does not yet make a control for `pump`: 'incomplete', 'invalid', or null. */
export function draftProblem(pump: Pump, draft: ControlDraft): 'incomplete' | 'invalid' | null {
	if (draft.setpoint === null || draft.minSpeed === null) return 'incomplete';
	for (const field of ['setpoint', 'minSpeed'] as const) {
		const value = draft[field] as number;
		if (boundsProblem(value, schemaBounds('PumpControl', field), String)) return 'invalid';
	}
	return orderViolations(withDraft(pump, draft)).length ? 'invalid' : null;
}

/** The control `draft` completes for `pump`, or null while it is incomplete or not valid. */
export function completedControl(pump: Pump, draft: ControlDraft): PumpControl | null {
	if (draftProblem(pump, draft) !== null) return null;
	return { mode: 'flow', setpoint: draft.setpoint as number, minSpeed: draft.minSpeed as number };
}
