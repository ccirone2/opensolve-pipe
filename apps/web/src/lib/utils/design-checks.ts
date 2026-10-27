/**
 * Design check results (CLAUDE.md D19; proposal design-checks.md §4–5) in words and display
 * units. The API's results are the data: the value checked, its limits and the outcome, in SI.
 * The words here are built from those numbers, never parsed from the API's message (which is
 * SI and kept under Details); a value that rounds to its limit's text gets more digits (up to
 * 17, enough for any two doubles), and one that still reads as its limit in display units
 * (two doubles a unit conversion makes equal) is said to differ by round-off, so a failure
 * never reads as equal to its limit. Checks are design practice, not flags: nothing here
 * changes a result or a flag.
 */
import type { DesignCheckResult, UnitPreferences } from '$lib/api/types';
import type { ElementRef } from './results';
import { designCheckPresets } from './model-rules';
import { formatValue, type UnitCategory } from './units';

export type DesignCheckId = DesignCheckResult['check'];
/** A check's source as set: the user's values or a preset (each check allows its own). */
export type DesignCheckSource = { kind: 'user' } | { kind: 'preset'; preset: string };
export type DesignCheckOutcome = DesignCheckResult['outcome'];

export const CHECK_TITLES: Readonly<Record<DesignCheckId, string>> = {
	npsh_margin: 'NPSH margin',
	operating_region: 'Operating region',
	allowable_region: 'Allowable operating region',
	minimum_flow: 'Minimum flow',
	motor_power: 'Motor power',
	pipe_velocity: 'Pipe velocity'
};

/** The display category of each check's value and limits (the API's `unit`, in SI). */
export const CHECK_CATEGORIES: Readonly<Record<DesignCheckId, UnitCategory>> = {
	npsh_margin: 'head',
	operating_region: 'fraction',
	allowable_region: 'flow',
	minimum_flow: 'flow',
	motor_power: 'power',
	pipe_velocity: 'velocity'
};

export const OUTCOME_TITLES: Readonly<Record<DesignCheckOutcome, string>> = {
	fail: 'Not met',
	pass: 'Met',
	not_evaluated: 'Not evaluated'
};

/** Failures first, then passes, then the checks not evaluated (proposal §5). */
export const OUTCOME_ORDER: readonly DesignCheckOutcome[] = ['fail', 'pass', 'not_evaluated'];

/** The results of a solve, by outcome in OUTCOME_ORDER (each in the API's order), empty ones left out. */
export function groupChecks(
	results: readonly DesignCheckResult[]
): { outcome: DesignCheckOutcome; results: DesignCheckResult[] }[] {
	return OUTCOME_ORDER.map((outcome) => ({
		outcome,
		results: results.filter((r) => r.outcome === outcome)
	})).filter((g) => g.results.length);
}

/** "2 not met · 5 met · 1 not evaluated" (counts that are zero left out). */
export function checkCounts(results: readonly DesignCheckResult[]): string {
	return groupChecks(results)
		.map((g) => `${g.results.length} ${OUTCOME_TITLES[g.outcome].toLowerCase()}`)
		.join(' · ');
}

export function checkElement(result: DesignCheckResult): ElementRef | null {
	if (result.componentId) return { kind: 'component', id: result.componentId };
	if (result.connectionId) return { kind: 'connection', id: result.connectionId };
	return null;
}

/**
 * Where a limit came from, short: "your values", the pump curve's manufacturer data, or the
 * preset's name. The API's `source` is "user", "manufacturer data (user)" or the preset's
 * citation (published with the presets, x-design-check-presets).
 */
export function sourceLabel(source: string): string {
	if (source === 'user') return 'your values';
	if (source === 'manufacturer data (user)') return "the pump curve's manufacturer data";
	const preset = designCheckPresets().find((p) => p.citation === source);
	if (preset) return PRESET_NAMES[preset.id] ?? source;
	return source;
}

export const PRESET_NAMES: Readonly<Record<string, string>> = {
	api610_por: 'API 610 preset',
	hi961_2012_general: 'HI 9.6.1-2012 (general) preset'
};

/** A check's limits' source as set (Settings → Design checks): "your values" or the preset's name. */
export function settingsSourceLabel(source: DesignCheckSource): string {
	return source.kind === 'user' ? 'your values' : (PRESET_NAMES[source.preset] ?? source.preset);
}

/** Significant figures enough to tell any two doubles apart. */
const MAX_DIGITS = 17;

/**
 * The value and its limits in display units, with as many digits as tell them apart (4 to 17
 * significant figures), and whether a limit the value is not equal to still reads as it (a
 * unit conversion can make two doubles equal).
 */
function formatter(
	result: DesignCheckResult,
	prefs: UnitPreferences
): { fmt: (si: number | null | undefined) => string; tied: boolean } {
	const category = CHECK_CATEGORIES[result.check];
	const limits = [result.limits.min, result.limits.max].filter(
		(l): l is number => l !== null && l !== undefined
	);
	const value = result.value;
	const same = (sig: number) =>
		value !== null &&
		value !== undefined &&
		limits.some(
			(l) =>
				l !== value &&
				formatValue(l, category, prefs, sig) === formatValue(value, category, prefs, sig)
		);
	let sig = 4;
	while (sig < MAX_DIGITS && same(sig)) sig += 1;
	return { fmt: (si) => formatValue(si, category, prefs, sig), tied: same(sig) };
}

/** "within 70 %–120 %", "below 70 %", "at most 120 %" …, for the limits set. */
function against(
	ok: boolean,
	low: number | null | undefined,
	high: number | null | undefined,
	fmt: (si: number) => string
): string {
	const hasLow = low !== null && low !== undefined;
	const hasHigh = high !== null && high !== undefined;
	if (hasLow && hasHigh) return `${ok ? 'within' : 'outside'} ${fmt(low)} to ${fmt(high)}`;
	if (hasLow) return ok ? `at least ${fmt(low)}` : `below ${fmt(low)}`;
	if (hasHigh) return ok ? `at most ${fmt(high)}` : `above ${fmt(high)}`;
	return '';
}

/**
 * One check result in words and display units: the value, how it stands against its limits,
 * and for a check not evaluated, why (the API's reason, which quotes no number or id).
 */
export function checkText(result: DesignCheckResult, prefs: UnitPreferences): string {
	if (result.outcome === 'not_evaluated' || result.value === null || result.value === undefined) {
		const reason = result.message.replace(/^not evaluated: /, '');
		return reason.charAt(0).toUpperCase() + reason.slice(1);
	}
	const { fmt, tied } = formatter(result, prefs);
	const text = words(result, result.value, fmt);
	return tied ? `${text} (by round-off)` : text;
}

function words(
	result: DesignCheckResult,
	v: number,
	fmt: (si: number | null | undefined) => string
): string {
	const ok = result.outcome === 'pass';
	const { min, max } = result.limits;
	switch (result.check) {
		case 'npsh_margin':
			return `NPSHa ${fmt(v)}, ${ok ? 'at least' : 'below'} the ${fmt(min)} required`;
		case 'operating_region':
			return `Flow ${fmt(v)} of the best efficiency flow, ${against(ok, min, max, fmt)}`;
		case 'allowable_region':
			return `Flow at rated speed ${fmt(v)}, ${ok ? 'within' : 'outside'} the allowable region ${fmt(min)} to ${fmt(max)}`;
		case 'minimum_flow':
			return `Flow at rated speed ${fmt(v)}, ${ok ? 'at least' : 'below'} the minimum ${fmt(min)}`;
		case 'motor_power':
			return `Shaft power ${fmt(v)}, ${ok ? 'within' : 'above'} the motor's rated ${fmt(max)}`;
		case 'pipe_velocity': {
			const pipe = (result.pipeIndex ?? 0) + 1;
			if (ok) {
				const which = max !== null && max !== undefined ? 'highest' : 'lowest';
				return `Every pipe ${against(true, min, max, fmt)} (${which} ${fmt(v)}, pipe ${pipe})`;
			}
			const side = max !== null && max !== undefined && v > max ? 'above' : 'below';
			const limit = side === 'above' ? max : min;
			const outside = result.pipesOutside ?? [];
			const others =
				outside.length > 1 ? `; pipes outside: ${outside.map((i) => i + 1).join(', ')}` : '';
			return `Velocity ${fmt(v)} in pipe ${pipe}, ${side} ${fmt(limit)}${others}`;
		}
	}
}
