/**
 * URL encoding/decoding for projects.
 *
 * Pipeline: Project → JSON → gzip → base64url → URL
 * Reverse: URL → base64url → ungzip → JSON → Project
 */

import pako from 'pako';
import type { Project } from '$lib/models';

/** Size thresholds for warnings. */
export const SIZE_THRESHOLDS = {
	/** Warn if encoded URL exceeds this size (bytes). */
	WARNING_THRESHOLD: 2048,
	/** Error if encoded URL exceeds this size (bytes). */
	ERROR_THRESHOLD: 50000
};

/** Custom error for encoding/decoding failures. */
export class EncodingError extends Error {
	constructor(
		message: string,
		public readonly cause?: Error
	) {
		super(message);
		this.name = 'EncodingError';
	}
}

/** Result of encoding with metadata. */
export interface EncodingResult {
	/** The encoded string. */
	encoded: string;
	/** Original JSON size in bytes. */
	originalSize: number;
	/** Compressed size in bytes. */
	compressedSize: number;
	/** Final URL-safe string size in bytes. */
	encodedSize: number;
	/** Compression ratio (compressedSize / originalSize). */
	compressionRatio: number;
	/** Whether the encoded size exceeds warning threshold. */
	isLarge: boolean;
}

/**
 * Convert a Uint8Array to base64url string.
 * base64url is URL-safe base64: '+' → '-', '/' → '_', no padding '='
 */
function uint8ArrayToBase64Url(bytes: Uint8Array): string {
	// Convert to regular base64
	const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join('');
	const base64 = btoa(binary);

	// Convert to base64url
	return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * Convert a base64url string to Uint8Array.
 */
function base64UrlToUint8Array(base64url: string): Uint8Array {
	// Convert base64url to regular base64
	let base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');

	// Add padding if needed
	const paddingNeeded = (4 - (base64.length % 4)) % 4;
	base64 += '='.repeat(paddingNeeded);

	// Decode base64 to binary
	const binary = atob(base64);

	// Convert to Uint8Array
	const bytes = new Uint8Array(binary.length);
	for (let i = 0; i < binary.length; i++) {
		bytes[i] = binary.charCodeAt(i);
	}

	return bytes;
}

/** Valid pako compression levels. */
type CompressionLevel = -1 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;

/**
 * Encode a project to a URL-safe string.
 *
 * @param project The project to encode
 * @param compressionLevel Compression level (0-9, default 6)
 * @returns Encoding result with metadata
 * @throws EncodingError if encoding fails
 */
export function encodeProject(
	project: Project,
	compressionLevel: CompressionLevel = 6
): EncodingResult {
	try {
		// Step 1: Convert to JSON
		const json = JSON.stringify(project);
		const originalSize = new TextEncoder().encode(json).length;

		// Step 2: Compress with gzip
		const jsonBytes = new TextEncoder().encode(json);
		const compressed = pako.gzip(jsonBytes, { level: compressionLevel });
		const compressedSize = compressed.length;

		// Step 3: Convert to base64url
		const encoded = uint8ArrayToBase64Url(compressed);
		const encodedSize = encoded.length;

		// Calculate compression ratio
		const compressionRatio = compressedSize / originalSize;

		// Check size thresholds
		const isLarge = encodedSize > SIZE_THRESHOLDS.WARNING_THRESHOLD;

		if (encodedSize > SIZE_THRESHOLDS.ERROR_THRESHOLD) {
			throw new EncodingError(
				`Encoded project is too large (${encodedSize} bytes). ` +
					`Maximum allowed is ${SIZE_THRESHOLDS.ERROR_THRESHOLD} bytes. ` +
					`Consider storing this project on the server.`
			);
		}

		return {
			encoded,
			originalSize,
			compressedSize,
			encodedSize,
			compressionRatio,
			isLarge
		};
	} catch (error) {
		if (error instanceof EncodingError) {
			throw error;
		}
		throw new EncodingError('Failed to encode project', error instanceof Error ? error : undefined);
	}
}

/**
 * Decode a URL-safe string back to a project.
 *
 * @param encoded The encoded string from the URL
 * @returns The decoded project
 * @throws EncodingError if decoding fails
 */
export function decodeProject(encoded: string): Project {
	if (!encoded || encoded.trim() === '') {
		throw new EncodingError('Empty encoded string');
	}

	try {
		// Step 1: Convert from base64url
		const compressed = base64UrlToUint8Array(encoded);

		// Step 2: Decompress with gzip
		const jsonBytes = pako.ungzip(compressed);

		// Step 3: Parse JSON
		const json = new TextDecoder().decode(jsonBytes);
		const project = JSON.parse(json) as Project;

		// Basic validation
		if (!project || typeof project !== 'object') {
			throw new EncodingError('Decoded data is not a valid project');
		}

		if (!project.id || !project.metadata || !project.components) {
			throw new EncodingError('Decoded project is missing required fields');
		}

		return project;
	} catch (error) {
		if (error instanceof EncodingError) {
			throw error;
		}

		// Handle specific error types
		if (error instanceof SyntaxError) {
			throw new EncodingError(
				'Invalid project data: corrupted or invalid JSON',
				error
			);
		}

		if (error instanceof Error && error.message.includes('incorrect header check')) {
			throw new EncodingError(
				'Invalid project data: not a valid compressed format',
				error
			);
		}

		throw new EncodingError(
			'Failed to decode project. The URL may be corrupted or from an incompatible version.',
			error instanceof Error ? error : undefined
		);
	}
}

/**
 * Try to decode a project, returning null on failure.
 *
 * @param encoded The encoded string from the URL
 * @returns The decoded project or null if decoding fails
 */
export function tryDecodeProject(encoded: string): Project | null {
	try {
		return decodeProject(encoded);
	} catch {
		return null;
	}
}

/**
 * Get the size of an encoded project in a human-readable format.
 */
export function formatSize(bytes: number): string {
	if (bytes < 1024) {
		return `${bytes} B`;
	}
	if (bytes < 1024 * 1024) {
		return `${(bytes / 1024).toFixed(1)} KB`;
	}
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Create a shareable URL for a project.
 *
 * @param project The project to share
 * @param baseUrl The base URL (default: current origin + /p/)
 * @returns The shareable URL
 */
export function createShareableUrl(project: Project, baseUrl?: string): string {
	const result = encodeProject(project);
	const base = baseUrl ?? `${typeof window !== 'undefined' ? window.location.origin : ''}/p/`;
	return `${base}${result.encoded}`;
}

/**
 * Extract encoded project data from a URL path.
 *
 * @param path The URL path (e.g., "/p/H4sIAAAA...")
 * @returns The encoded string or null if not found
 */
export function extractEncodedFromPath(path: string): string | null {
	// Remove leading /p/ if present
	const match = path.match(/^\/p\/(.+)$/);
	if (match) {
		return match[1];
	}

	// If no /p/ prefix, return the whole path (might be just the encoded part)
	if (path && !path.startsWith('/')) {
		return path;
	}

	return null;
}
