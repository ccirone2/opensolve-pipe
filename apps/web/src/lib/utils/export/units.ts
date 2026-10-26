/**
 * The units of an exported file (proposal export.md §2.3): one unit system per file, the
 * project's display units or SI base units, never both side by side.
 *
 * - Display mode: the screen's unit for the category (`displayUnit`): power in hp when flow is in
 *   gpm, else kW; fractions (speed, efficiency) in %.
 * - SI mode: SI base units (m, m³/s, m/s, Pa, K, kg/m³, Pa·s), power in W, and fractions as the
 *   dimensionless 0–1 with no unit, as Re, f and K have (the API writes '' for none). Every number
 *   cell is then the API's own double: `fromSI(v, base unit)` is `(v − 0) / 1`, which is `v`.
 *
 * The app's sentences (flag messages, the goal seek report) take `exportPrefs` as their unit
 * preferences, so one code path serves both modes; `displayUnit` keeps % and kW (hp with gpm)
 * there whatever the preferences, which About says (decision 5).
 */
import type { UnitPreferences } from '../../api/types';
import {
	displayUnit,
	fromSI,
	unitLabel,
	type LabelOptions,
	type UnitCategory,
	type UnitId
} from '../units';

/** The file's unit system: the project's display units, or SI base units. */
export type ExportUnits = 'display' | 'si';

/** SI base units of every preference category (diameters in m, temperatures in K). */
export const SI_BASE_UNITS: Readonly<UnitPreferences> = Object.freeze({
	length: 'm',
	diameter: 'm',
	pressure: 'Pa',
	head: 'm',
	flow: 'm3/s',
	velocity: 'm/s',
	temperature: 'K',
	density: 'kg/m3',
	viscosity: 'Pa.s'
});

/** The unit preferences of a file: the display units, or SI base units. */
export function exportPrefs(units: ExportUnits, display: UnitPreferences): UnitPreferences {
	return units === 'si' ? SI_BASE_UNITS : display;
}

/**
 * The unit a category's numbers are written in. SI mode: the base unit, with power in W and a
 * fraction as the plain 0–1 (no unit).
 */
export function exportUnit(category: UnitCategory, units: ExportUnits, display: UnitPreferences) {
	if (units === 'si') {
		if (category === 'power') return 'W' satisfies UnitId;
		if (category === 'fraction') return '' satisfies UnitId;
		return displayUnit(category, SI_BASE_UNITS);
	}
	return displayUnit(category, display);
}

/** Converts SI values to a file's units and labels them. */
export class ExportUnitSystem {
	readonly units: ExportUnits;
	readonly display: UnitPreferences;

	constructor(units: ExportUnits, display: UnitPreferences) {
		this.units = units;
		this.display = display;
	}

	/** The unit preferences of the app's sentences in this file. */
	get prefs(): UnitPreferences {
		return exportPrefs(this.units, this.display);
	}

	unit(category: UnitCategory): UnitId {
		return exportUnit(category, this.units, this.display);
	}

	/** An SI value in the file's unit, unrounded; null for none (or a non-finite value). */
	value(si: number | null | undefined, category: UnitCategory): number | null {
		if (si === null || si === undefined || !Number.isFinite(si)) return null;
		return fromSI(si, this.unit(category));
	}

	/** The unit's label ("kPa(g)", "psia", "L/s"); '' for a pure number or a 0–1 fraction. */
	label(category: UnitCategory, options: LabelOptions = {}): string {
		return unitLabel(category, this.unit(category), options);
	}

	/** A header: "Label [unit]", or the label alone when the category has no unit. */
	header(label: string, category: UnitCategory, options: LabelOptions = {}): string {
		const unit = this.label(category, options);
		return unit ? `${label} [${unit}]` : label;
	}
}
