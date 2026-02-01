/**
 * OpenSolve Pipe Utilities
 */

// URL encoding/decoding
export {
	encodeProject,
	decodeProject,
	tryDecodeProject,
	createShareableUrl,
	extractEncodedFromPath,
	formatSize,
	EncodingError,
	SIZE_THRESHOLDS
} from './encoding';

export type { EncodingResult } from './encoding';

// Topology validation
export {
	validateTopology,
	wouldCreateInvalidLoop,
	getOrphanedComponents,
	hasLoops
} from './topology';

export type {
	TopologyIssue,
	TopologyIssueType,
	IssueSeverity,
	TopologyValidationResult
} from './topology';
