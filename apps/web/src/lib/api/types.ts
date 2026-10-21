/**
 * Convenient names for the generated API types. The Pydantic models in apps/api are the source
 * of truth; regenerate schema.d.ts with `pnpm gen:types` after changing them.
 */
import type { components } from './schema';

type S = components['schemas'];

export type Project = S['Project'];
export type ProjectSettings = S['ProjectSettings'];
export type ProjectMetadata = S['ProjectMetadata'];
export type UnitPreferences = S['UnitPreferences'];
export type SolverOptions = S['SolverOptions'];
export type Port = S['Port'];
export type PipeConnection = S['PipeConnection'];
export type PipingSegment = S['PipingSegment'];
export type PipeDefinition = S['PipeDefinition'];
export type Fitting = S['Fitting'];
export type FittingType = Fitting['type'];
export type FlowCoefficient = S['FlowCoefficient'];
export type Reservoir = S['Reservoir'];
export type IdealReferenceNode = S['IdealReferenceNode'];
export type Plug = S['Plug'];
export type TeeBranch = S['TeeBranch'];
export type WyeBranch = S['WyeBranch'];
export type Pump = S['Pump'];
export type IsolationValve = S['IsolationValve'];
export type CheckValve = S['CheckValve'];
export type ControlValve = S['ControlValve'];
export type Component = Project['components'][number];
export type ComponentType = Component['type'];
export type PumpCurve = S['PumpCurve'];
export type FlowHeadPoint = S['FlowHeadPoint'];
export type BuiltinFluid = S['BuiltinFluid'];
export type CustomFluid = S['CustomFluid'];
export type FluidDefinition = Project['fluid'];

export type SolveRequest = S['SolveRequest'];
export type SolveResponse = S['SolveResponse'];
export type ErrorResponse = S['ErrorResponse'];
export type SolvedState = S['SolvedState'];
export type NodeResult = S['NodeResult'];
export type LinkResult = S['LinkResult'];
export type PumpResult = S['PumpResult'];
export type ValveResult = S['ValveResult'];
export type BranchResult = S['BranchResult'];
export type BoundaryResult = S['BoundaryResult'];
export type Flag = S['Flag'];
export type ElementTrace = S['ElementTrace'];
export type MethodsSummary = S['MethodsSummary'];
export type CurvePoint = S['CurvePoint'];
export type LibraryResponse = S['LibraryResponse'];
export type PipeMaterial = S['PipeMaterial'];
export type FittingInfo = S['FittingInfo'];
export type FluidInfo = S['FluidInfo'];
export type FluidProperties = S['FluidProperties'];
export type SystemCurveResponse = S['SystemCurveResponse'];
export type MethodVersionsResponse = S['MethodVersionsResponse'];
