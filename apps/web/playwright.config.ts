import { defineConfig, devices } from '@playwright/test';
import { API_ORIGIN, API_PORT, WEB_ORIGIN, WEB_PORT } from './tests/servers';

export default defineConfig({
	testDir: 'tests',
	testMatch: '**/*.e2e.ts',
	fullyParallel: true,
	// One worker: every test's browser reaches the one API from the same address, and the API
	// solves one request per client address at a time (CLAUDE.md D10), so two workers solving at
	// once raced into SERVER_BUSY (CI run 39726631693).
	workers: 1,
	forbidOnly: !!process.env.CI,
	retries: 0,
	reporter: process.env.CI ? 'github' : 'list',
	use: {
		baseURL: WEB_ORIGIN,
		trace: 'retain-on-failure'
	},
	projects: [
		{
			name: 'desktop',
			use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } }
		},
		{
			name: 'mobile',
			use: {
				...devices['Desktop Chrome'],
				viewport: { width: 390, height: 844 },
				isMobile: true,
				hasTouch: true,
				deviceScaleFactor: 3
			}
		}
	],
	webServer: [
		{
			// The shipped app with the per-client rate limit raised (apps/api/tests/e2e_app.py): every
			// test reaches it from one address, and on a fast runner the suite sends more than 60 solve
			// and system-curve requests a minute (CI run 40004435327, 429 RATE_LIMITED).
			command: `uv run uvicorn tests.e2e_app:app --port ${API_PORT}`,
			cwd: '../api',
			url: `${API_ORIGIN}/health`,
			env: { CORS_ORIGINS: WEB_ORIGIN },
			reuseExistingServer: !process.env.CI
		},
		{
			command: `pnpm build && pnpm preview --port ${WEB_PORT} --strictPort`,
			url: WEB_ORIGIN,
			env: { PUBLIC_API_URL: API_ORIGIN },
			reuseExistingServer: !process.env.CI
		}
	]
});
