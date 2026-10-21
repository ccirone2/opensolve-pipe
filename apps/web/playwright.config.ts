import { defineConfig, devices } from '@playwright/test';
import { API_ORIGIN, API_PORT, WEB_ORIGIN, WEB_PORT } from './tests/servers';

export default defineConfig({
	testDir: 'tests',
	testMatch: '**/*.e2e.ts',
	fullyParallel: true,
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
			command: `uv run uvicorn opensolve_pipe.main:app --port ${API_PORT}`,
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
