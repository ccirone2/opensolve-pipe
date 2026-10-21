import { defineConfig, devices } from '@playwright/test';

const API_PORT = 8000;
const WEB_PORT = 4173;

export default defineConfig({
	testDir: 'tests',
	testMatch: '**/*.e2e.ts',
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: 0,
	reporter: process.env.CI ? 'github' : 'list',
	use: {
		baseURL: `http://localhost:${WEB_PORT}`,
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
			url: `http://localhost:${API_PORT}/health`,
			env: { CORS_ORIGINS: `http://localhost:${WEB_PORT}` },
			reuseExistingServer: !process.env.CI
		},
		{
			command: `pnpm build && pnpm preview --port ${WEB_PORT} --strictPort`,
			url: `http://localhost:${WEB_PORT}`,
			env: { PUBLIC_API_URL: `http://localhost:${API_PORT}` },
			reuseExistingServer: !process.env.CI
		}
	]
});
