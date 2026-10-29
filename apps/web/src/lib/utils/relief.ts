/**
 * The pressure relief valve's words and the few numbers the app shows before a solve (proposal
 * pressure-relief-valve.md §5, §6): its capacity kinds, statuses and states, API 526's letters
 * with their effective areas, and ASME's default overpressure at a set. Every number is read from
 * the API's `x-relief-data` (model-rules.ts RELIEF_DATA, the API's data/api526_orifices.json),
 * never copied (D10); nothing here is solved: the solve's results carry the values it used.
 */
import type { ReliefValve, ReliefValveResult, UnitPreferences } from '../api/types';
import type { CapacityField, CapacityKind } from './factory';
import { api526Letters, RELIEF_DATA } from './model-rules';
import { displayUnit, formatNumber, formatValue, fromSI } from './units';

/** A relief valve's capacity, as stored. */
export type ReliefCapacity = ReliefValve['capacity'];

/** How the capacity is given, in the form's Capacity choice and in tables. */
export const CAPACITY_KIND_LABELS: Readonly<Record<CapacityKind, string>> = {
	api526: 'API 526 orifice letter',
	effective: 'API 520 effective area',
	certified: 'Certified area and coefficient'
};

/** A kind of capacity in a sentence ("its capacity is given by an API 526 letter"). */
export const CAPACITY_KIND_WORDS: Readonly<Record<CapacityKind, string>> = {
	api526: 'an API 526 orifice letter',
	effective: 'an API 520 effective area',
	certified: 'a certified area and coefficient'
};

/** A relief valve's statuses (the check valve's vocabulary, decision 8). */
export const RELIEF_STATUS_LABELS = {
	active: 'Active',
	locked_closed: 'Locked closed (gagged or blocked: does not open)'
} as const;

/** A relief valve's solved states (ReliefValveResult.state). */
export const RELIEF_STATE_LABELS: Readonly<Record<ReliefValveResult['state'], string>> = {
	closed: 'Closed',
	partial_lift: 'Partial lift',
	full_lift: 'Full lift'
};

/** Where the overpressure a solve used came from (ReliefValveResult.overpressureSource). */
export const OVERPRESSURE_SOURCE_LABELS: Readonly<
	Record<ReliefValveResult['overpressureSource'], string>
> = {
	asme_default: "ASME's (the default)",
	user: 'Certified (entered)'
};

/** API 526's orifice letters, D to T, in the schema's order. */
export function reliefLetters(): string[] {
	return api526Letters();
}

/** API 526's effective area of a letter, m², or null for an unknown letter. */
export function letterArea(letter: string): number | null {
	return RELIEF_DATA.api526Areas[letter] ?? null;
}

/** "J: 830.3 mm²" (or "J: 1.287 in²"): a letter with its effective area in the display unit. */
export function letterOptionLabel(letter: string, units: UnitPreferences): string {
	const area = letterArea(letter);
	return area === null ? letter : `${letter}: ${formatValue(area, 'area', units)}`;
}

/** The lowest set ASME's default overpressure covers, ASME VIII's 15 psi (Pa, a difference). */
export function asmeMinimumSetPressure(): number {
	return RELIEF_DATA.asmeMinimumSetPressure;
}

/**
 * Whether a relief valve's overpressure is ASME's default: always for a letter or an effective
 * area (decision 6: API 520's preliminary pair comes with ASME's), and for a certified capacity
 * with none entered.
 */
export function reliefOnAsmeDefault(valve: Pick<ReliefValve, 'capacity'>): boolean {
	const capacity = valve.capacity;
	return capacity.kind !== 'certified' || typeof capacity.overpressure !== 'number';
}

/**
 * ASME's liquid certification overpressure at a set pressure difference, the default: 10 % of
 * the set or 3 psi, whichever is greater, max(fraction, floor ÷ set) (decision 6). Null below
 * ASME VIII's 15 psi scope, where no source gives it (the solve refuses a valve that would take
 * it), and for a set that is not a positive number.
 */
export function defaultOverpressure(setPressure: number | null | undefined): number | null {
	if (typeof setPressure !== 'number' || !Number.isFinite(setPressure)) return null;
	if (!(setPressure >= RELIEF_DATA.asmeMinimumSetPressure)) return null;
	return Math.max(
		RELIEF_DATA.asmeOverpressureFraction,
		RELIEF_DATA.asmeOverpressureFloor / setPressure
	);
}

/**
 * "ASME's 10 % or 3 psi (20.68 kPa)": the default's rule, its numbers read from x-relief-data, the
 * floor in psi as the source states it and, unless the display unit is psi, in that unit too.
 */
export function asmeRuleText(units: UnitPreferences): string {
	const fraction = formatNumber(RELIEF_DATA.asmeOverpressureFraction * 100);
	const floor = RELIEF_DATA.asmeOverpressureFloor;
	const psi = `${formatNumber(fromSI(floor, 'psi'))} psi`;
	const shown =
		displayUnit('pressure', units) === 'psi'
			? psi
			: `${psi} (${formatValue(floor, 'pressure', units)})`;
	return `ASME's ${fraction} % or ${shown}`;
}

/** ASME VIII's scope, the lowest set the default covers: "15 psi (103.4 kPa)" (or "15 psi"). */
export function asmeScopeText(units: UnitPreferences): string {
	const scope = RELIEF_DATA.asmeMinimumSetPressure;
	const psi = `${formatNumber(fromSI(scope, 'psi'))} psi`;
	return displayUnit('pressure', units) === 'psi'
		? psi
		: `${psi} (${formatValue(scope, 'pressure', units)})`;
}

/** "ASME's 10 % or 3 psi (20.68 kPa), whichever is greater (the default)". */
export function asmeDefaultText(units: UnitPreferences): string {
	return `${asmeRuleText(units)}, whichever is greater (the default)`;
}

/**
 * The line under a defaulted overpressure: its value at this set, or why it has none (below
 * ASME VIII's scope, where the overpressure must be entered on a certified capacity).
 */
export function defaultOverpressureLine(
	setPressure: number | null | undefined,
	units: UnitPreferences
): { text: string; warning: boolean } {
	const scope = asmeScopeText(units);
	if (typeof setPressure !== 'number' || !Number.isFinite(setPressure)) {
		return { text: `${asmeDefaultText(units)}, for a set of at least ${scope}.`, warning: false };
	}
	const op = defaultOverpressure(setPressure);
	if (op === null) {
		return {
			text: `Below ${scope} (ASME VIII's scope) no source gives the overpressure: enter the valve's certified area, rated coefficient and full-lift overpressure.`,
			warning: true
		};
	}
	return {
		text: `${asmeDefaultText(units)}: ${formatValue(op, 'fraction', units)} at this set.`,
		warning: false
	};
}

/**
 * The read-only line of the preliminary kinds (a letter, an effective area): API 520's effective
 * coefficient and ASME's overpressure, never changed (decision 7).
 */
export function preliminaryLine(units: UnitPreferences): string {
	const kd = formatNumber(RELIEF_DATA.effectiveDischargeCoefficient);
	return `API 520's effective coefficient of discharge ${kd} and ${asmeRuleText(units)} overpressure: preliminary sizing values, never mixed with a valve's certified ones.`;
}

/** The labels of a capacity's values, as the form names them. */
export const CAPACITY_FIELD_LABELS: Readonly<Record<CapacityField, string>> = {
	letter: 'API 526 orifice letter',
	area: 'Orifice area',
	dischargeCoefficient: 'Rated coefficient of discharge (K)',
	overpressure: 'Overpressure at full lift'
};

/** The label of capacity.area for a kind: an effective area, or a certified actual area. */
export function areaLabel(kind: CapacityKind | null | undefined): string {
	if (kind === 'effective') return 'API 520 effective area';
	if (kind === 'certified') return 'Actual orifice area';
	return CAPACITY_FIELD_LABELS.area;
}

/**
 * A capacity in display units, as scenario changes and the export name it (the API's
 * value_text in its words): "API 526 J (830.3 mm²), Kd 0.65 (preliminary)", "API 520 effective
 * area 447.1 mm², Kd 0.65 (preliminary)", "Certified area 250 mm², rated coefficient 0.7,
 * overpressure 8 %" (or ASME's, the default).
 */
export function capacityText(value: unknown, units: UnitPreferences): string {
	if (typeof value !== 'object' || value === null) return 'not a capacity';
	const capacity = value as Partial<Record<string, unknown>>;
	const kd = `Kd ${formatNumber(RELIEF_DATA.effectiveDischargeCoefficient)} (preliminary)`;
	const area = (v: unknown) => (typeof v === 'number' ? formatValue(v, 'area', units) : '—');
	if (capacity.kind === 'api526') {
		const letter = String(capacity.letter ?? '—');
		const known = letterArea(letter);
		return `API 526 ${letter}${known === null ? '' : ` (${area(known)})`}, ${kd}`;
	}
	if (capacity.kind === 'effective') return `API 520 effective area ${area(capacity.area)}, ${kd}`;
	if (capacity.kind === 'certified') {
		const k =
			typeof capacity.dischargeCoefficient === 'number'
				? formatValue(capacity.dischargeCoefficient, 'dimensionless', units)
				: '—';
		const op =
			typeof capacity.overpressure === 'number'
				? formatValue(capacity.overpressure, 'fraction', units)
				: overpressureDefaultText(units);
		return `Certified area ${area(capacity.area)}, rated coefficient ${k}, overpressure ${op}`;
	}
	return `unknown capacity kind ${JSON.stringify(capacity.kind)}`;
}

/**
 * ASME's rule in its source's own numbers, with no unit conversion (the export's words, where
 * every number is exact): "ASME's 10 % or 3 psi, whichever is greater (the default)".
 */
export function asmeRuleWords(): string {
	const fraction = formatNumber(RELIEF_DATA.asmeOverpressureFraction * 100);
	const psi = formatNumber(fromSI(RELIEF_DATA.asmeOverpressureFloor, 'psi'));
	return `ASME's ${fraction} % or ${psi} psi, whichever is greater (the default)`;
}

/** A certified capacity's overpressure when none is entered: ASME's, the default. */
export function overpressureDefaultText(units: UnitPreferences): string {
	return `${asmeRuleText(units)} (the default)`;
}

/** "API 526 J", "Effective area", "Certified": how a solve's capacity was given (export, tables). */
export function capacityGivenBy(capacity: ReliefValveResult['capacity']): string {
	if (capacity.kind === 'api526') return `API 526 ${capacity.letter}`;
	return capacity.kind === 'effective' ? 'Effective area' : 'Certified';
}
