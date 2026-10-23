/**
 * Errors from opening a shared project link (D3, SDD §5.2). The message is written for the
 * person who opened the link and says what they can do about it.
 *
 * - `corrupt`: the link text cannot be decoded (base64url, gzip, UTF-8 or JSON). Usually the
 *   link was cut short by an email or chat client.
 * - `newer_version`: the project was saved by a newer version of the app than this one.
 * - `invalid`: the link decodes, but what it holds is not a valid project.
 */
export type LinkErrorKind = 'corrupt' | 'newer_version' | 'invalid';

export class LinkError extends Error {
	readonly kind: LinkErrorKind;
	/** Individual problems found (for `invalid`), each a human-readable sentence. */
	readonly problems: readonly string[];

	constructor(kind: LinkErrorKind, message: string, problems: readonly string[] = []) {
		super(message);
		this.name = 'LinkError';
		this.kind = kind;
		this.problems = problems;
	}
}

export const CORRUPT_LINK_MESSAGE =
	'This link is incomplete or damaged, so the project in it cannot be read. Check that the ' +
	'whole link was copied: some email and chat apps cut long links short.';

export const NOT_A_PROJECT_MESSAGE = 'This link does not contain an OpenSolve Pipe project.';

export const INVALID_PROJECT_MESSAGE =
	'The project in this link is not valid, so it cannot be opened. The problems found are listed below.';
