/**
 * Unit conversion for input and display (D4, TSD §6). Project data is always SI; these
 * functions are used only where a value is typed in or shown.
 *
 * Registry: value_SI = value × factor + offset.
 *
 * Every factor is exact by definition: NIST SP 811 (2008), Appendix B, and the international
 * yard and pound agreement (1959): 1 ft = 0.3048 m, 1 in = 0.0254 m, 1 lb = 0.45359237 kg.
 * The pound-force uses standard gravity g_n = 9.80665 m/s² (3rd CGPM, 1901). The US gallon is
 * 231 in³. Horsepower (mechanical) is 550 ft·lbf/s. Poise is 0.1 Pa·s (CGS), so 1 cP = 1 mPa·s.
 * Temperature: K = °C + 273.15; K = (°F + 459.67) × 5/9.
 *
 * Pressures are gauge at the edges (D4): pressure labels carry "(g)" / "psig" or, where a value
 * is absolute (NPSH, vapor pressure), "(a)" / "psia". Gauge ⇄ absolute is not a unit
 * conversion (it depends on the atmospheric pressure), so it is not done here.
 */
import type { UnitPreferences } from '../api/types';

export const FOOT = 0.3048; // m, exact
export const INCH = 0.0254; // m, exact
export const POUND_MASS = 0.45359237; // kg, exact
export const STANDARD_GRAVITY = 9.80665; // m/s², exact
export const POUND_FORCE = POUND_MASS * STANDARD_GRAVITY; // N
export const US_GALLON = 231 * INCH * INCH * INCH; // m³

export type PreferenceCategory = keyof UnitPreferences;

/** Categories with display units: those in UnitPreferences, plus power and fixed units. */
export type UnitCategory = PreferenceCategory | 'power' | 'dimensionless' | 'fraction' | 'angle';

export type PreferenceUnit = UnitPreferences[PreferenceCategory];
export type PowerUnit = 'W' | 'kW' | 'hp';
/** '' is a pure number; '%' shows a stored fraction (0–1) as a percentage; 'deg' is degrees. */
export type FixedUnit = '' | '%' | 'deg';
export type UnitId = PreferenceUnit | PowerUnit | FixedUnit;

interface UnitDefinition {
	factor: number;
	offset?: number;
	label: string;
}

const UNITS: Record<UnitId, UnitDefinition> = {
	// length, diameter, head → m
	m: { factor: 1, label: 'm' },
	mm: { factor: 1e-3, label: 'mm' },
	ft: { factor: FOOT, label: 'ft' },
	in: { factor: INCH, label: 'in' },
	// pressure → Pa
	Pa: { factor: 1, label: 'Pa' },
	kPa: { factor: 1e3, label: 'kPa' },
	MPa: { factor: 1e6, label: 'MPa' },
	bar: { factor: 1e5, label: 'bar' },
	psi: { factor: POUND_FORCE / (INCH * INCH), label: 'psi' },
	// flow → m³/s
	'm3/s': { factor: 1, label: 'm³/s' },
	'm3/h': { factor: 1 / 3600, label: 'm³/h' },
	'L/s': { factor: 1e-3, label: 'L/s' },
	'L/min': { factor: 1e-3 / 60, label: 'L/min' },
	gpm: { factor: US_GALLON / 60, label: 'gpm' },
	// velocity → m/s
	'm/s': { factor: 1, label: 'm/s' },
	'ft/s': { factor: FOOT, label: 'ft/s' },
	// temperature → K
	K: { factor: 1, label: 'K' },
	C: { factor: 1, offset: 273.15, label: '°C' },
	F: { factor: 5 / 9, offset: (459.67 * 5) / 9, label: '°F' },
	// density → kg/m³
	'kg/m3': { factor: 1, label: 'kg/m³' },
	'lb/ft3': { factor: POUND_MASS / (FOOT * FOOT * FOOT), label: 'lb/ft³' },
	// dynamic viscosity → Pa·s
	'Pa.s': { factor: 1, label: 'Pa·s' },
	'mPa.s': { factor: 1e-3, label: 'mPa·s' },
	cP: { factor: 1e-3, label: 'cP' },
	// power → W (display only)
	W: { factor: 1, label: 'W' },
	kW: { factor: 1e3, label: 'kW' },
	hp: { factor: 550 * FOOT * POUND_FORCE, label: 'hp' },
	// fixed
	'': { factor: 1, label: '' },
	'%': { factor: 0.01, label: '%' },
	deg: { factor: 1, label: '°' }
};

/** Units offered per category. The preference lists match `UnitPreferences` in the API. */
export const CATEGORY_UNITS = {
	length: ['m', 'mm', 'ft', 'in'],
	diameter: ['mm', 'm', 'in'],
	pressure: ['Pa', 'kPa', 'MPa', 'bar', 'psi'],
	head: ['m', 'ft'],
	flow: ['m3/s', 'm3/h', 'L/s', 'L/min', 'gpm'],
	velocity: ['m/s', 'ft/s'],
	temperature: ['K', 'C', 'F'],
	density: ['kg/m3', 'lb/ft3'],
	viscosity: ['Pa.s', 'mPa.s', 'cP'],
	power: ['W', 'kW', 'hp'],
	dimensionless: [''],
	fraction: ['%'],
	angle: ['deg']
} as const satisfies { [C in PreferenceCategory]: readonly UnitPreferences[C][] } & {
	power: readonly PowerUnit[];
	dimensionless: readonly FixedUnit[];
	fraction: readonly FixedUnit[];
	angle: readonly FixedUnit[];
};

export const PREFERENCE_CATEGORIES: readonly PreferenceCategory[] = [
	'length',
	'diameter',
	'pressure',
	'head',
	'flow',
	'velocity',
	'temperature',
	'density',
	'viscosity'
];

/** SI preset (the API's defaults). */
export const SI_UNITS: Readonly<UnitPreferences> = Object.freeze({
	length: 'm',
	diameter: 'mm',
	pressure: 'kPa',
	head: 'm',
	flow: 'L/s',
	velocity: 'm/s',
	temperature: 'C',
	density: 'kg/m3',
	viscosity: 'mPa.s'
});

/** US customary ("Imperial") preset. */
export const IMPERIAL_UNITS: Readonly<UnitPreferences> = Object.freeze({
	length: 'ft',
	diameter: 'in',
	pressure: 'psi',
	head: 'ft',
	flow: 'gpm',
	velocity: 'ft/s',
	temperature: 'F',
	density: 'lb/ft3',
	viscosity: 'cP'
});

export function isUnitId(unit: string): unit is UnitId {
	return Object.hasOwn(UNITS, unit);
}

function definition(unit: UnitId): UnitDefinition {
	const def = UNITS[unit];
	if (!def) throw new RangeError(`Unknown unit "${String(unit)}"`);
	return def;
}

/** Convert a value in `unit` to SI. */
export function toSI(value: number, unit: UnitId): number {
	const def = definition(unit);
	return value * def.factor + (def.offset ?? 0);
}

/** Convert an SI value to `unit`. */
export function fromSI(value: number, unit: UnitId): number {
	const def = definition(unit);
	return (value - (def.offset ?? 0)) / def.factor;
}

/**
 * The unit a category is displayed in. Preference categories follow the project's
 * preferences. Power has no preference of its own: it is shown in hp when flow is shown in
 * US gallons per minute, otherwise in kW. Fixed categories have one unit.
 */
export function displayUnit(category: UnitCategory, prefs: UnitPreferences): UnitId {
	switch (category) {
		case 'power':
			return prefs.flow === 'gpm' ? 'hp' : 'kW';
		case 'dimensionless':
			return '';
		case 'fraction':
			return '%';
		case 'angle':
			return 'deg';
		default:
			return prefs[category];
	}
}

export interface LabelOptions {
	/** A gauge pressure: "kPa(g)", "psig". */
	gauge?: boolean;
	/** An absolute pressure: "kPa(a)", "psia". */
	absolute?: boolean;
}

/** Display label of a unit, with the gauge/absolute marker for pressures. */
export function unitLabel(
	category: UnitCategory,
	unit: UnitId,
	options: LabelOptions = {}
): string {
	const label = definition(unit).label;
	if (category !== 'pressure' || !(options.gauge || options.absolute)) return label;
	const marker = options.absolute ? 'a' : 'g';
	return unit === 'psi' ? `psi${marker}` : `${label}(${marker})`;
}

/** Format a number to `sig` significant digits, without trailing zeros. */
export function formatNumber(value: number, sig = 4): string {
	if (!Number.isFinite(value)) return '—';
	if (value === 0) return '0';
	const magnitude = Math.abs(value);
	if (magnitude >= 1e-4 && magnitude < 1e9) return String(Number(value.toPrecision(sig)));
	const [mantissa = '', exponent = ''] = value.toExponential(sig - 1).split('e');
	const trimmed = mantissa.includes('.') ? mantissa.replace(/\.?0+$/, '') : mantissa;
	return `${trimmed}e${exponent.replace('+', '')}`;
}

/**
 * `value` rounded toward zero to `sig` significant digits, for a bound a value must stay below
 * (above, if negative): "below 573.4 gpm", where 573.46 rounded to the nearest, 573.5, would
 * admit values at or beyond the bound. A value within floating-point error of its rounding to
 * the nearest (36.17999999999999 for 36.18) keeps that rounding rather than losing a digit.
 */
export function formatNumberTowardZero(value: number, sig = 4): string {
	if (!Number.isFinite(value) || value === 0) return formatNumber(value, sig);
	const nearest = Number(formatNumber(value, sig));
	if (Math.abs(nearest) <= Math.abs(value) * (1 + 1e-12)) return formatNumber(nearest, sig);
	const scale = 10 ** (sig - 1 - Math.floor(Math.log10(Math.abs(value))));
	return formatNumber(Math.trunc(value * scale) / scale, sig);
}

export interface FormatOptions extends LabelOptions {
	/** Append the unit label (default true). */
	unit?: boolean;
	/** Round toward zero, for a bound (`formatNumberTowardZero`); to the nearest by default. */
	towardZero?: boolean;
}

/**
 * Format an SI value in the project's display unit for its category, e.g. "245.2 kPa(g)".
 * null and undefined show as "—".
 */
export function formatValue(
	si: number | null | undefined,
	category: UnitCategory,
	prefs: UnitPreferences,
	sig = 4,
	options: FormatOptions = {}
): string {
	if (si === null || si === undefined || !Number.isFinite(si)) return '—';
	const unit = displayUnit(category, prefs);
	const shown = fromSI(si, unit);
	const text = options.towardZero ? formatNumberTowardZero(shown, sig) : formatNumber(shown, sig);
	if (options.unit === false) return text;
	const label = unitLabel(category, unit, options);
	if (!label) return text;
	// SI style (NIST SP 811 §7.2): a space before the unit symbol, except for the degree of angle.
	return unit === 'deg' ? `${text}${label}` : `${text} ${label}`;
}

/** Significant figures enough to tell any two doubles apart. */
const MAX_DIGITS = 17;

/**
 * The significant figures, from 4 up to 17, at which `value` reads differently under `show` from
 * every one of `others` it is not equal to: a value just past a limit never reads as the limit
 * ("0.75005 is above 0.75", not "0.75 is above 0.75"). 17 when a unit conversion makes two doubles
 * read the same even there.
 */
export function digitsApart(
	value: number,
	others: readonly number[],
	show: (si: number, sig: number) => string
): number {
	const same = (sig: number) =>
		others.some((other) => other !== value && show(other, sig) === show(value, sig));
	let sig = 4;
	while (sig < MAX_DIGITS && same(sig)) sig += 1;
	return sig;
}

/**
 * Parse a typed number. Accepts an optional sign, decimals and an exponent ("1.5e-3"), with
 * surrounding spaces. Returns null for anything else, including empty text, so NaN is never
 * produced.
 */
export function parseNumber(text: string): number | null {
	const trimmed = text.trim();
	if (!/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(trimmed)) return null;
	const value = Number(trimmed);
	return Number.isFinite(value) ? value : null;
}

/** Parse a typed value in `unit` and convert it to SI; null when the text is not a number. */
export function parseInput(text: string, unit: UnitId): number | null {
	const value = parseNumber(text);
	return value === null ? null : toSI(value, unit);
}
