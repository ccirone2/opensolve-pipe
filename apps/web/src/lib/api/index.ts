/**
 * API Client Module
 *
 * Provides functions for communicating with the OpenSolve Pipe backend API.
 * Includes error handling, retry logic, and timeout handling.
 */

// Client functions
export {
	solveNetwork,
	listFluids,
	getFluidProperties,
	calculateFluidProperties,
	solveSimple,
	type FluidInfo,
	type GetFluidPropertiesOptions,
	type SimpleSolveRequest,
	type SimpleSolveResponse
} from './client';

// Error types
export {
	ApiError,
	NetworkError,
	TimeoutError,
	ValidationError,
	ServerError
} from './client';
