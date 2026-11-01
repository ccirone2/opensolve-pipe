/**
 * The servers the end-to-end tests run against (playwright.config.ts starts them). Each has a
 * port of its own, not the development servers' (README: the API on 8000, whose CORS allows
 * only the dev app's origin, and Vite's 5173 and 4173), so Playwright never reuses a server
 * that was started for something else and would refuse or misdirect the app's requests.
 *
 * E2E_API_PORT and E2E_WEB_PORT move them, for a second suite in the same container (another
 * agent's worktree, docs/workflow.md §6): outside CI Playwright reuses a server already on its
 * port, which would be the other checkout's API or build.
 */
function port(name: string, fallback: number): number {
	const value = process.env[name];
	if (value === undefined || value === '') return fallback;
	const parsed = Number(value);
	if (!Number.isInteger(parsed) || parsed < 1024 || parsed > 65535) {
		throw new Error(`${name} must be an integer port from 1024 to 65535`);
	}
	return parsed;
}

export const API_PORT = port('E2E_API_PORT', 8010);
export const WEB_PORT = port('E2E_WEB_PORT', 4183);
if (API_PORT === WEB_PORT) throw new Error('E2E_API_PORT and E2E_WEB_PORT must differ');
export const API_ORIGIN = `http://localhost:${API_PORT}`;
export const WEB_ORIGIN = `http://localhost:${WEB_PORT}`;
