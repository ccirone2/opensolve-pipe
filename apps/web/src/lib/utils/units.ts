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

/**
 * Categories with display units: those in UnitPreferences, plus power and area (derived from a
 * preference) and fixed units.
 */
export type UnitCategory =
	PreferenceCategory | 'power' | 'area' | 'dimensionless' | 'fraction' | 'angle';

export type PreferenceUnit = UnitPreferences[PreferenceCategory];
export type PowerUnit = 'W' | 'kW' | 'hp';
/** Areas (a relief valve's orifice area): the square of a diameter unit. */
export type AreaUnit = 'mm2' | 'm2' | 'in2';
/** '' is a pure number; '%' shows a stored fraction (0–1) as a percentage; 'deg' is degrees. */
export type FixedUnit = '' | '%' | 'deg';
export type UnitId = PreferenceUnit | PowerUnit | AreaUnit | FixedUnit;

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
	// area → m² (the squares of exact lengths)
	mm2: { factor: 1e-6, label: 'mm²' },
	m2: { factor: 1, label: 'm²' },
	in2: { factor: INCH * INCH, label: 'in²' },
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
	area: ['mm2', 'm2', 'in2'],
	dimensionless: [''],
	fraction: ['%'],
	angle: ['deg']
} as const satisfies { [C in PreferenceCategory]: readonly UnitPreferences[C][] } & {
	power: readonly PowerUnit[];
	area: readonly AreaUnit[];
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

/** The area unit of each diameter unit: its square (mm², m², in²). */
const AREA_UNITS: Readonly<Record<UnitPreferences['diameter'], AreaUnit>> = {
	mm: 'mm2',
	m: 'm2',
	in: 'in2'
};

/**
 * The unit a category is displayed in. Preference categories follow the project's
 * preferences. Power has no preference of its own: it is shown in hp when flow is shown in
 * US gallons per minute, otherwise in kW. Area has none either: it is the square of the diameter
 * unit (mm², m², in²; proposal pressure-relief-valve.md W7). Fixed categories have one unit.
 */
export function displayUnit(category: UnitCategory, prefs: UnitPreferences): UnitId {
	switch (category) {
		case 'power':
			return prefs.flow === 'gpm' ? 'hp' : 'kW';
		case 'area':
			return AREA_UNITS[prefs.diameter];
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

/**
 * What may follow a typed number, per unit (proposal usability-entry.md §3): the registry's
 * label, its id and the spellings engineers type. Every spelling names a unit of the registry
 * above, so no conversion factor is added here. Matched without regard to case, except where case
 * tells two units apart (MPa, a pressure, from mPa·s, a viscosity): those are `exact`.
 */
const SPELLINGS: Readonly<Partial<Record<UnitId, readonly string[]>>> = {
	m: ['metre', 'metres', 'meter', 'meters'],
	mm: ['millimetre', 'millimetres', 'millimeter', 'millimeters'],
	ft: ['ft', 'ft.', 'foot', 'feet', "'", '′', '’'],
	in: ['in', 'inch', 'inches', '"', 'in.', '″', '”'],
	Pa: ['Pa'],
	kPa: ['kPa'],
	bar: ['bar'],
	psi: ['psi', 'lbf/in2', 'lbf/in²'],
	'm3/s': ['m3/s', 'm³/s'],
	'm3/h': ['m3/h', 'm³/h', 'm3/hr', 'm³/hr', 'cmh'],
	'L/s': ['L/s', 'l/s', 'lps'],
	'L/min': ['L/min', 'l/min', 'lpm'],
	gpm: ['gpm', 'usgpm', 'gal/min', 'US gpm', 'U.S. gpm'],
	'm/s': ['m/s'],
	'ft/s': ['ft/s', 'fps'],
	C: ['°C', '° C', 'C', 'degC', 'deg C', 'ºC', 'º C'],
	F: ['°F', '° F', 'F', 'degF', 'deg F', 'ºF', 'º F'],
	'kg/m3': ['kg/m3', 'kg/m³'],
	'lb/ft3': ['lb/ft3', 'lb/ft³', 'lbm/ft3', 'lbm/ft³', 'pcf'],
	'Pa.s': ['Pa.s', 'Pa·s', 'Pa s', 'Pas'],
	cP: ['cP', 'cp', 'centipoise'],
	W: ['W'],
	kW: ['kW'],
	hp: ['hp', 'bhp'],
	mm2: ['sq mm'],
	m2: ['m2', 'm²', 'sq m'],
	in2: ['in2', 'in²', 'sq in', 'sq. in.'],
	'%': ['%'],
	deg: ['°', 'º', 'deg', 'degrees']
};

/**
 * Spellings matched with their case, where case tells units or numbers apart: MPa (mega) from
 * mPa·s (milli), m and mm from M and MM ("million" in US practice), K (kelvin) from k ("thousand").
 */
const EXACT_SPELLINGS: Readonly<Partial<Record<UnitId, readonly string[]>>> = {
	m: ['m'],
	mm: ['mm'],
	mm2: ['mm2', 'mm²'],
	MPa: ['MPa'],
	'mPa.s': ['mPa.s', 'mPa·s', 'mPa s'],
	K: ['K']
};

/** Units a typed value of each category may carry: every unit of the same physical quantity. */
const LENGTHS: readonly UnitId[] = ['m', 'mm', 'ft', 'in'];
const ACCEPTED: Readonly<Record<UnitCategory, readonly UnitId[]>> = {
	length: LENGTHS,
	diameter: LENGTHS,
	head: LENGTHS,
	pressure: CATEGORY_UNITS.pressure,
	flow: CATEGORY_UNITS.flow,
	velocity: CATEGORY_UNITS.velocity,
	temperature: CATEGORY_UNITS.temperature,
	density: CATEGORY_UNITS.density,
	viscosity: CATEGORY_UNITS.viscosity,
	power: CATEGORY_UNITS.power,
	area: CATEGORY_UNITS.area,
	dimensionless: [],
	fraction: ['%'],
	angle: ['deg']
};

/** The unit a spelling names, among `accepted`; null for none. */
function unitOf(spelling: string, accepted: readonly UnitId[]): UnitId | null {
	const lower = spelling.toLowerCase();
	for (const unit of accepted) {
		if (EXACT_SPELLINGS[unit]?.includes(spelling)) return unit;
		if (SPELLINGS[unit]?.some((s) => s.toLowerCase() === lower)) return unit;
	}
	return null;
}

/** The case-exact spelling, among `accepted`, of a spelling typed in another case ("mpa"). */
function caseOf(spelling: string, accepted: readonly UnitId[]): string | null {
	const lower = spelling.toLowerCase();
	for (const unit of accepted) {
		const exact = EXACT_SPELLINGS[unit]?.find((s) => s.toLowerCase() === lower);
		if (exact) return exact;
	}
	return null;
}

/** A pressure's gauge or absolute mark after its unit: "psig", "kPa(g)", "bara", "kPa a". */
function splitPressureMark(spelling: string): { base: string; mark: 'g' | 'a' } | null {
	const match = /^(.+?)\s*(?:\(\s*([ga])\s*\)|([ga]))$/i.exec(spelling);
	if (!match?.[1]) return null;
	const mark = (match[2] ?? match[3] ?? '').toLowerCase();
	return mark === 'g' || mark === 'a' ? { base: match[1], mark } : null;
}

const ALL_UNITS = Object.keys(UNITS).filter((u): u is UnitId => u !== '' && isUnitId(u));

/**
 * True when a word names a unit, of any quantity, with or without a pressure's mark ("gpm",
 * "psig", "kPa(a)"), or would but for its capitals ("MPA"): a heading's words are read for units
 * with it (paste-points.ts), so that a unit is never passed over unread.
 */
export function namesUnit(word: string): boolean {
	const spelling = word.trim();
	if (spelling === '') return false;
	if (unitOf(spelling, ALL_UNITS) !== null || caseOf(spelling, ALL_UNITS) !== null) return true;
	const marked = splitPressureMark(spelling);
	return !!marked && unitOf(marked.base, CATEGORY_UNITS.pressure) !== null;
}

/** The accepted units of a category, as their labels: "m, mm, ft or in". */
function acceptedList(
	category: UnitCategory,
	accepted: readonly UnitId[],
	options: LabelOptions
): string {
	const labels = accepted.map((u) => unitLabel(category, u, options));
	return labels.length < 2
		? (labels[0] ?? '')
		: `${labels.slice(0, -1).join(', ')} or ${labels[labels.length - 1]}`;
}

export type QuantityParse =
	| {
			ok: true;
			/** The value in SI. */
			si: number;
			/** The unit it was typed in: the display unit when none was typed. */
			unit: UnitId;
			/** True when the text named a unit other than the display unit. */
			converted: boolean;
	  }
	| { ok: false; error: string };

/** The message for text that is not a number at all. */
export const NOT_A_NUMBER = 'Enter a number, e.g. 12.5 or 1.2e-3.';

/**
 * Parse a typed value of `category` (proposal usability-entry.md §3): a number, optionally
 * followed by a unit of the same quantity ("50 psi", "3in", "120 gpm", "68 °F"). With no unit it
 * is in `display`, the field's unit. A pressure's gauge or absolute mark must agree with the
 * field: a gauge field takes "psig" or "psi", never "psia", and an absolute field the reverse;
 * a difference takes none. Gauge ⇄ absolute needs the atmospheric pressure, so it is refused,
 * never guessed (D4). Returns null for empty text.
 */
export function parseQuantity(
	text: string,
	category: UnitCategory,
	display: UnitId,
	options: LabelOptions & {
		/** Take only the field's own unit (a designation in inches, an NPS: not a length). */
		ownUnitOnly?: boolean;
	} = {}
): QuantityParse | null {
	const trimmed = text.trim();
	if (trimmed === '') return null;
	const match = /^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s*(.*)$/i.exec(trimmed);
	const numberText = match?.[1];
	if (!match || numberText === undefined) return { ok: false, error: NOT_A_NUMBER };
	const number = Number(numberText);
	if (!Number.isFinite(number)) return { ok: false, error: NOT_A_NUMBER };
	const spelling = (match[2] ?? '').trim();
	// What goes on as a number would ("1,5", "1.2.3", "1 000") is a malformed number; any other
	// mark after the number is read as a unit, and refused as one it does not know.
	if (/^[\d.,+-]/.test(spelling)) return { ok: false, error: NOT_A_NUMBER };
	if (spelling === '')
		return { ok: true, si: toSI(number, display), unit: display, converted: false };

	const accepted = options.ownUnitOnly ? [display] : ACCEPTED[category];
	const shownLabel = unitLabel(category, display, options);
	const takes = accepted.length
		? `Enter it in ${acceptedList(category, accepted, options)}.`
		: 'Enter a number without a unit.';
	let unit = unitOf(spelling, accepted);
	if (unit === null && category === 'pressure') {
		const marked = splitPressureMark(spelling);
		const base = marked && unitOf(marked.base, accepted);
		if (marked && base) {
			const wanted = options.gauge ? 'g' : options.absolute ? 'a' : null;
			if (wanted === null) {
				return {
					ok: false,
					error: `This is a pressure difference: enter it in ${shownLabel}, without a gauge (g) or absolute (a) mark.`
				};
			}
			if (marked.mark !== wanted) {
				return {
					ok: false,
					error:
						wanted === 'g'
							? `This is a gauge pressure (${shownLabel}): an absolute value needs the atmospheric pressure subtracted first.`
							: `This is an absolute pressure (${shownLabel}): a gauge value needs the atmospheric pressure added first.`
				};
			}
			unit = base;
		}
	}
	if (unit === null) {
		const exact = caseOf(spelling, accepted);
		return {
			ok: false,
			error: exact
				? `“${spelling}”: mind the capitals, “${exact}”.`
				: `“${spelling}” is not a unit this field takes. ${takes}`
		};
	}
	return { ok: true, si: toSI(number, unit), unit, converted: unit !== display };
}
