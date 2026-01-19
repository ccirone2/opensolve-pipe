/**
 * Fluid definition and properties models.
 * Mirrors: apps/api/src/opensolve_pipe/models/fluids.py
 */

/** Available fluid types. */
export type FluidType =
	| 'water'
	| 'ethylene_glycol'
	| 'propylene_glycol'
	| 'diesel'
	| 'gasoline'
	| 'kerosene'
	| 'hydraulic_oil'
	| 'custom';

/** Display names for fluid types. */
export const FLUID_TYPE_LABELS: Record<FluidType, string> = {
	water: 'Water',
	ethylene_glycol: 'Ethylene Glycol',
	propylene_glycol: 'Propylene Glycol',
	diesel: 'Diesel',
	gasoline: 'Gasoline',
	kerosene: 'Kerosene',
	hydraulic_oil: 'Hydraulic Oil',
	custom: 'Custom Fluid'
};

/** Fluid types that require concentration. */
export const GLYCOL_FLUID_TYPES: FluidType[] = ['ethylene_glycol', 'propylene_glycol'];

/** Definition of the working fluid. */
export interface FluidDefinition {
	/** Type of fluid. Default: 'water' */
	type: FluidType;
	/** Operating temperature in project units (F or C). Default: 68.0 */
	temperature: number;
	/** Concentration percentage for glycol mixtures (0-100). */
	concentration?: number;
	/** Custom fluid density (kg/m³ for SI calculation). Required if type is 'custom'. */
	custom_density?: number;
	/** Custom fluid kinematic viscosity (m²/s for SI calculation). Required if type is 'custom'. */
	custom_kinematic_viscosity?: number;
	/** Custom fluid vapor pressure (Pa for SI calculation). Required if type is 'custom'. */
	custom_vapor_pressure?: number;
}

/** Calculated fluid properties at operating conditions (always in SI units). */
export interface FluidProperties {
	/** Density in kg/m³. */
	density: number;
	/** Kinematic viscosity in m²/s. */
	kinematic_viscosity: number;
	/** Dynamic viscosity in Pa·s. */
	dynamic_viscosity: number;
	/** Vapor pressure in Pa. */
	vapor_pressure: number;
	/** Specific gravity relative to water at 4°C. Default: 1.0 */
	specific_gravity: number;
}

/** Default fluid definition (water at 68°F). */
export const DEFAULT_FLUID_DEFINITION: FluidDefinition = {
	type: 'water',
	temperature: 68.0
};

/** Check if a fluid type requires concentration. */
export function requiresConcentration(type: FluidType): boolean {
	return GLYCOL_FLUID_TYPES.includes(type);
}

/** Check if a fluid type is custom (requires all custom properties). */
export function isCustomFluid(type: FluidType): boolean {
	return type === 'custom';
}

/** Validate fluid definition. Returns error message or null if valid. */
export function validateFluidDefinition(fluid: FluidDefinition): string | null {
	if (requiresConcentration(fluid.type) && fluid.concentration === undefined) {
		return `${FLUID_TYPE_LABELS[fluid.type]} requires concentration to be specified`;
	}

	if (isCustomFluid(fluid.type)) {
		const missing: string[] = [];
		if (fluid.custom_density === undefined) missing.push('custom_density');
		if (fluid.custom_kinematic_viscosity === undefined) missing.push('custom_kinematic_viscosity');
		if (fluid.custom_vapor_pressure === undefined) missing.push('custom_vapor_pressure');
		if (missing.length > 0) {
			return `Custom fluid requires: ${missing.join(', ')}`;
		}
	}

	if (fluid.concentration !== undefined && (fluid.concentration < 0 || fluid.concentration > 100)) {
		return 'Concentration must be between 0 and 100';
	}

	return null;
}
