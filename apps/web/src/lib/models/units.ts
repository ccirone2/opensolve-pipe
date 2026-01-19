/**
 * Unit system and solver configuration models.
 * Mirrors: apps/api/src/opensolve_pipe/models/units.py
 */

/** Available unit systems. */
export type UnitSystem = 'imperial' | 'si' | 'mixed';

/** User's preferred units for display and input. */
export interface UnitPreferences {
	system: UnitSystem;
	length: string;
	diameter: string;
	pressure: string;
	head: string;
	flow: string;
	velocity: string;
	temperature: string;
	viscosity_kinematic: string;
	viscosity_dynamic: string;
	density: string;
}

/** Preset unit configurations for each system. */
export const SYSTEM_PRESETS: Record<UnitSystem, Omit<UnitPreferences, 'system'>> = {
	imperial: {
		length: 'ft',
		diameter: 'in',
		pressure: 'psi',
		head: 'ft_head',
		flow: 'GPM',
		velocity: 'ft/s',
		temperature: 'F',
		viscosity_kinematic: 'ft2/s',
		viscosity_dynamic: 'cP',
		density: 'lb/ft3'
	},
	si: {
		length: 'm',
		diameter: 'mm',
		pressure: 'kPa',
		head: 'm_head',
		flow: 'L/s',
		velocity: 'm/s',
		temperature: 'C',
		viscosity_kinematic: 'm2/s',
		viscosity_dynamic: 'Pa.s',
		density: 'kg/m3'
	},
	mixed: {
		length: 'm',
		diameter: 'in',
		pressure: 'bar',
		head: 'm_head',
		flow: 'm3/h',
		velocity: 'm/s',
		temperature: 'C',
		viscosity_kinematic: 'cSt',
		viscosity_dynamic: 'cP',
		density: 'kg/m3'
	}
};

/** Create UnitPreferences from a preset system. */
export function createUnitPreferencesFromSystem(system: UnitSystem): UnitPreferences {
	return {
		system,
		...SYSTEM_PRESETS[system]
	};
}

/** Default unit preferences (Imperial). */
export const DEFAULT_UNIT_PREFERENCES: UnitPreferences = createUnitPreferencesFromSystem('imperial');

/** Configuration options for the hydraulic solver. */
export interface SolverOptions {
	/** Maximum solver iterations. Default: 100 */
	max_iterations: number;
	/** Convergence tolerance. Default: 0.001 */
	tolerance: number;
	/** Generate system curve in results. Default: true */
	include_system_curve: boolean;
	/** Minimum flow for system curve (project units). Default: 0 */
	flow_range_min: number;
	/** Maximum flow for system curve (project units). Default: 500 */
	flow_range_max: number;
	/** Number of points for system curve. Default: 51 */
	flow_points: number;
}

/** Default solver options. */
export const DEFAULT_SOLVER_OPTIONS: SolverOptions = {
	max_iterations: 100,
	tolerance: 0.001,
	include_system_curve: true,
	flow_range_min: 0,
	flow_range_max: 500,
	flow_points: 51
};
