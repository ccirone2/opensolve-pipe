import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// In the browser, SvelteKit fills `$env/dynamic/public` from a global the app sets at startup,
// which component tests do not have. Give them an empty public environment instead (the API
// base URL then falls back to its default; tests mock fetch anyway).
vi.mock('$env/dynamic/public', () => ({ env: {} }));

// jsdom has no canvas: getContext would log "not implemented" and return null. Return null
// quietly, as a browser without canvas support would (charts then show their data tables).
HTMLCanvasElement.prototype.getContext = (() =>
	null) as typeof HTMLCanvasElement.prototype.getContext;
