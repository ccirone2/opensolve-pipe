/**
 * The servers the end-to-end tests run against (playwright.config.ts starts them). Each has a
 * port of its own, not the development servers' (README: the API on 8000, whose CORS allows
 * only the dev app's origin, and Vite's 5173 and 4173), so Playwright never reuses a server
 * that was started for something else and would refuse or misdirect the app's requests.
 */
export const API_PORT = 8010;
export const WEB_PORT = 4183;
export const API_ORIGIN = `http://localhost:${API_PORT}`;
export const WEB_ORIGIN = `http://localhost:${WEB_PORT}`;
