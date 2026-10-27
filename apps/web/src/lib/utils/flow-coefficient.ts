/**
 * The words of a flow coefficient, shared by a valve's resistance (ResistanceField) and an
 * equipment item's rating by a Cv or Kv (EquipmentRatingFields): the option labels and the hints
 * that say what each one is. Cv and Kv are defined quantities, stored as entered; the solver
 * converts them with fluids' Cv_to_K / Kv_to_K (ISA-75.01.01; D9).
 */
import type { FlowCoefficient } from '../api/types';

export type CoefficientKind = FlowCoefficient['kind'];

/** The option label of each kind ("Cv (US flow coefficient)"). */
export const COEFFICIENT_LABELS: Readonly<Record<CoefficientKind, string>> = {
	K: 'K (loss coefficient)',
	Cv: 'Cv (US flow coefficient)',
	Kv: 'Kv (metric flow coefficient)'
};

/** What each kind is, under its field. */
export const COEFFICIENT_HINTS: Readonly<Record<CoefficientKind, string>> = {
	K: 'Loss coefficient, referenced to the velocity in the connected pipe.',
	Cv: 'US gpm of water at 1 psi pressure drop (stored as entered).',
	Kv: 'm³/h of water at 1 bar pressure drop (stored as entered).'
};
