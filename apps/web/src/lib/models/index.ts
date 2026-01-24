/**
 * OpenSolve Pipe TypeScript Models
 *
 * This module exports all TypeScript interfaces and types that mirror
 * the backend Pydantic models in apps/api/src/opensolve_pipe/models/
 */

// Units
export type { UnitSystem, UnitPreferences, SolverOptions } from './units';
export {
	SYSTEM_PRESETS,
	createUnitPreferencesFromSystem,
	DEFAULT_UNIT_PREFERENCES,
	DEFAULT_SOLVER_OPTIONS
} from './units';

// Fluids
export type { FluidType, FluidDefinition, FluidProperties } from './fluids';
export {
	FLUID_TYPE_LABELS,
	GLYCOL_FLUID_TYPES,
	DEFAULT_FLUID_DEFINITION,
	requiresConcentration,
	isCustomFluid,
	validateFluidDefinition
} from './fluids';

// Piping
export type {
	PipeMaterial,
	PipeSchedule,
	FittingType,
	PipeDefinition,
	Fitting,
	PipingSegment
} from './piping';
export {
	PIPE_MATERIAL_LABELS,
	PIPE_SCHEDULE_LABELS,
	FITTING_TYPE_LABELS,
	FITTING_CATEGORIES,
	createDefaultPipeDefinition,
	createDefaultFitting,
	createDefaultPipingSegment
} from './piping';

// Pump
export type {
	FlowHeadPoint,
	FlowEfficiencyPoint,
	NPSHRPoint,
	PumpCurve
} from './pump';
export {
	validatePumpCurve,
	createDefaultPumpCurve,
	interpolatePumpHead
} from './pump';

// Components
export type {
	PortDirection,
	Port,
	PipeConnection,
	ComponentType,
	ValveType,
	Connection,
	Reservoir,
	Tank,
	Junction,
	PumpComponent,
	ValveComponent,
	HeatExchanger,
	Strainer,
	Orifice,
	Sprinkler,
	FlowPressurePoint,
	IdealReferenceNode,
	NonIdealReferenceNode,
	Plug,
	TeeBranch,
	WyeBranch,
	CrossBranch,
	Component
} from './components';
export {
	COMPONENT_TYPE_LABELS,
	COMPONENT_CATEGORIES,
	VALVE_TYPE_LABELS,
	CONTROL_VALVE_TYPES,
	isReservoir,
	isTank,
	isJunction,
	isPump,
	isValve,
	isHeatExchanger,
	isStrainer,
	isOrifice,
	isSprinkler,
	isIdealReferenceNode,
	isNonIdealReferenceNode,
	isPlug,
	isTeeBranch,
	isWyeBranch,
	isCrossBranch,
	isNodeComponent,
	isLinkComponent,
	getReservoirTotalHead,
	generateComponentId,
	getDefaultPorts,
	createReservoirPorts,
	createTankPorts,
	createJunctionPorts,
	createPumpPorts,
	createValvePorts,
	createHeatExchangerPorts,
	createStrainerPorts,
	createOrificePorts,
	createSprinklerPorts,
	createReferenceNodePorts,
	createPlugPorts,
	createTeePorts,
	createWyePorts,
	createCrossPorts,
	createDefaultComponent
} from './components';

// Results
export type {
	FlowRegime,
	ComponentResult,
	PipingResult,
	PumpResult,
	WarningCategory,
	WarningSeverity,
	Warning,
	SolvedState
} from './results';
export {
	FLOW_REGIME_LABELS,
	WARNING_CATEGORY_LABELS,
	isSolveSuccessful,
	getWarningsBySeverity,
	getWarningsForComponent,
	hasErrors,
	getComponentResult,
	getPipingResult,
	getPumpResult
} from './results';

// Project
export type { ProjectMetadata, ProjectSettings, Project } from './project';
export {
	generateProjectId,
	generateConnectionId,
	createDefaultMetadata,
	createDefaultSettings,
	createNewProject,
	getComponentById,
	getPumpCurveById,
	getConnectionById,
	getConnectionsFromComponent,
	getConnectionsToComponent,
	getConnectionsForPort,
	validateComponentIds,
	validateConnectionReferences,
	validatePumpCurveIds,
	validatePumpCurveReferences,
	validatePipeConnectionIds,
	validatePipeConnectionReferences,
	validateProject,
	touchProject,
	branchProject
} from './project';
