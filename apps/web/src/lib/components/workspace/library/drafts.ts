/**
 * The project library's forms (CLAUDE.md D21; proposal project-library.md §6.1): an entry as its
 * form holds it while it is entered (a draft, its required values possibly not entered yet), what
 * is still to enter (each said at its field when the form is saved), and the entry it makes.
 * Nothing has a default but the material a new spec starts on: a name, a source and the values
 * come from the user (decision 2: every entry has a source).
 */
import type { PipeSpec, ResistanceSpec } from '$lib/api/types';
import { CUSTOM_MATERIAL_ID } from '$lib/utils/piping';

/** A pipe spec being entered: its id and material, and what is entered of the rest. */
export type PipeSpecDraft = Pick<PipeSpec, 'id' | 'materialId'> &
	Partial<Omit<PipeSpec, 'id' | 'materialId'>>;

/** A resistance entry being entered: its id and kind, and what is entered of the rest. */
export type ResistanceDraft = Pick<ResistanceSpec, 'id' | 'kind'> &
	Partial<Omit<ResistanceSpec, 'id' | 'kind'>>;

/** What is still to enter, by field ('name', 'source', 'innerDiameter', ...). */
export type FieldErrors = Partial<Record<string, string>>;

const NAME = 'Enter a name: results and lists show the entry by it.';
const SOURCE =
	'Enter where the values come from (a standard and its table, a datasheet, a measurement): every result that uses the entry cites it.';

const missingText = (value: string | null | undefined) => !value || !value.trim();
const missingNumber = (value: number | null | undefined) =>
	value === null || value === undefined || !Number.isFinite(value);

/** The values a pipe spec draft still needs (none: it can be saved), in the form's order. */
export function pipeSpecMissing(draft: PipeSpecDraft): FieldErrors {
	const errors: FieldErrors = {};
	if (missingText(draft.name)) errors.name = NAME;
	if (missingNumber(draft.innerDiameter)) errors.innerDiameter = 'Enter the inner diameter.';
	if (draft.materialId === CUSTOM_MATERIAL_ID && missingNumber(draft.roughness)) {
		errors.roughness = 'Enter the roughness: a custom pipe spec has no cited one.';
	}
	if (missingText(draft.source)) errors.source = SOURCE;
	return errors;
}

/** The values a resistance draft still needs (none: it can be saved), in the form's order. */
export function resistanceMissing(draft: ResistanceDraft): FieldErrors {
	const errors: FieldErrors = {};
	if (missingText(draft.name)) errors.name = NAME;
	if (missingNumber(draft.value)) errors.value = `Enter the ${draft.kind} from the source.`;
	if (draft.kind === 'K' && missingNumber(draft.referenceDiameter)) {
		errors.referenceDiameter =
			'Enter the bore the K is stated at: a K means nothing without the velocity it is on.';
	}
	if (missingText(draft.source)) errors.source = SOURCE;
	return errors;
}

/** The pipe spec a complete draft makes: optional values only where entered. */
export function pipeSpecOf(draft: PipeSpecDraft): PipeSpec {
	const spec: PipeSpec = {
		id: draft.id,
		name: (draft.name ?? '').trim(),
		source: (draft.source ?? '').trim(),
		materialId: draft.materialId,
		innerDiameter: draft.innerDiameter as number
	};
	if (draft.roughness != null) spec.roughness = draft.roughness;
	if (draft.outerDiameter != null) spec.outerDiameter = draft.outerDiameter;
	if (draft.nominalSize != null) spec.nominalSize = draft.nominalSize;
	return spec;
}

/** The resistance entry a complete draft makes: a K with its bore, a Cv or Kv without one. */
export function resistanceOf(draft: ResistanceDraft): ResistanceSpec {
	const entry: ResistanceSpec = {
		id: draft.id,
		name: (draft.name ?? '').trim(),
		source: (draft.source ?? '').trim(),
		kind: draft.kind,
		value: draft.value as number
	};
	if (draft.kind === 'K' && draft.referenceDiameter != null) {
		entry.referenceDiameter = draft.referenceDiameter;
	}
	return entry;
}

/**
 * A draft with another kind: neither the value (a Cv is not a K) nor a K's bore (a Cv or Kv takes
 * none) is carried over; its name and source stay.
 */
export function withKind(draft: ResistanceDraft, kind: ResistanceSpec['kind']): ResistanceDraft {
	if (kind === draft.kind) return draft;
	const next: ResistanceDraft = { id: draft.id, kind };
	if (draft.name !== undefined) next.name = draft.name;
	if (draft.source !== undefined) next.source = draft.source;
	return next;
}
