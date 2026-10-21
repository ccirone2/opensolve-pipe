import { gzipSync } from 'node:zlib';
import { expect, test, type Page } from '@playwright/test';

/**
 * Results and sharing against the real API: open a pipe-only network from a link, solve it,
 * read a flow in the links table, share, reopen the shared link and get the same results.
 *
 * The network is an illustrative test input (made-up elevations and pipe lengths): an upper
 * tank with two outlets feeding two lower tanks through carbon steel schedule 40 pipes.
 */
const NPS3 = 3 * 0.0254;
const NPS4 = 4 * 0.0254;
const NOW = '2026-10-21T00:00:00Z';

const PROJECT = {
	schemaVersion: 1,
	methodVersion: '',
	id: 'e2e-pipe-only',
	metadata: { name: 'Pipe-only test network', created: NOW, modified: NOW },
	settings: {
		units: {
			length: 'm',
			diameter: 'mm',
			pressure: 'kPa',
			head: 'm',
			flow: 'L/s',
			velocity: 'm/s',
			temperature: 'C',
			density: 'kg/m3',
			viscosity: 'mPa.s'
		},
		siteElevation: 0,
		solverOptions: { frictionMethod: 'colebrook', maxIterations: 100, tolerance: 1e-9 }
	},
	fluid: { kind: 'builtin', fluidId: 'water', temperature: 293.15 },
	components: [
		{
			type: 'reservoir',
			id: 'R1',
			name: 'Upper tank',
			elevation: 20,
			liquidLevel: 2,
			surfacePressure: 0,
			ports: [
				{ id: 'port_1', nominalSize: NPS4, direction: 'bidirectional' },
				{ id: 'port_2', nominalSize: NPS3, direction: 'bidirectional' }
			]
		},
		{
			type: 'reservoir',
			id: 'R2',
			name: 'Lower tank A',
			elevation: 0,
			liquidLevel: 1,
			surfacePressure: 0,
			ports: [{ id: 'port_1', nominalSize: NPS4, direction: 'bidirectional' }]
		},
		{
			type: 'reservoir',
			id: 'R3',
			name: 'Lower tank B',
			elevation: 2,
			liquidLevel: 1,
			surfacePressure: 0,
			ports: [{ id: 'port_1', nominalSize: NPS3, direction: 'bidirectional' }]
		}
	],
	connections: [
		{
			id: 'L1',
			fromComponentId: 'R1',
			fromPortId: 'port_1',
			toComponentId: 'R2',
			toPortId: 'port_1',
			piping: {
				pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: NPS4, length: 50 }],
				fittings: [{ type: 'elbow_90_lr', quantity: 2, pipeIndex: 0 }]
			}
		},
		{
			id: 'L2',
			fromComponentId: 'R1',
			fromPortId: 'port_2',
			toComponentId: 'R3',
			toPortId: 'port_1',
			piping: {
				pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: NPS3, length: 40 }],
				fittings: []
			}
		}
	],
	pumpLibrary: []
};

/** The link format of D3: JSON → gzip → base64url without padding (the app reads any gzip). */
function encode(project: unknown): string {
	return gzipSync(Buffer.from(JSON.stringify(project))).toString('base64url');
}

const results = (page: Page) => page.getByRole('region', { name: 'Results' });

/** Solve, wait for the API's answer, and return the flows it reported (m³/s by connection). */
async function solve(page: Page): Promise<Record<string, number>> {
	const answer = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST'
	);
	await page.getByRole('button', { name: 'Solve', exact: true }).click();
	const body = (await (await answer).json()) as {
		solvedState: { linkResults: Record<string, { flow: number }> };
	};
	await expect(results(page).getByRole('heading', { name: 'Converged' })).toBeVisible();
	return Object.fromEntries(
		Object.entries(body.solvedState.linkResults).map(([id, link]) => [id, link.flow])
	);
}

/** The flow shown in the links table for a connection, as displayed. */
async function shownFlow(page: Page, connection: string): Promise<string> {
	await results(page).getByRole('tab', { name: 'Links' }).click();
	const table = results(page).getByRole('table', { name: 'Results per pipe connection' });
	await expect(table.getByRole('columnheader', { name: 'Flow L/s' })).toBeVisible();
	const row = table
		.getByRole('row')
		.filter({ has: page.getByRole('rowheader', { name: connection }) });
	const flow = row.getByRole('cell').first();
	await expect(flow).toBeVisible();
	return (await flow.textContent())?.trim() ?? '';
}

test('solves a pipe-only network, shares it, and the shared link gives the same results', async ({
	page,
	context
}) => {
	const origins = new Set<string>();
	context.on('request', (request) => origins.add(new URL(request.url()).origin));

	await page.goto(`/p#${encode(PROJECT)}`);
	await expect(
		page
			.getByRole('region', { name: 'Build' })
			.getByRole('heading', { level: 2, name: 'Upper tank' })
	).toBeVisible();

	const flows = await solve(page);
	expect(flows.L1).toBeGreaterThan(0);
	// The table shows the API's flow in L/s to 4 significant figures.
	const shown = await shownFlow(page, 'Upper tank → Lower tank A');
	expect(shown).toBe(String(Number((flows.L1! * 1000).toPrecision(4))));

	// Share: the link holds the project (and now the method version it was solved with).
	await page.getByRole('button', { name: 'Share' }).click();
	const dialog = page.getByRole('dialog', { name: 'Share this project' });
	const field = dialog.getByRole('textbox', { name: 'Link to this version of the project' });
	await expect(field).toHaveValue(/\/p#[A-Za-z0-9_-]+$/);
	const link = await field.inputValue();
	expect(link.length).toBeLessThan(8000);
	await dialog.getByRole('button', { name: 'Close' }).click();

	// Reopen the link in a new tab and solve again: the same project gives the same results.
	const reopened = await context.newPage();
	await reopened.goto(link);
	await expect(
		reopened
			.getByRole('region', { name: 'Build' })
			.getByRole('heading', { level: 2, name: 'Upper tank' })
	).toBeVisible();
	const again = await solve(reopened);
	expect(again).toEqual(flows);
	expect(await shownFlow(reopened, 'Upper tank → Lower tank A')).toBe(shown);
	expect(await shownFlow(reopened, 'Upper tank → Lower tank B')).toBe(
		await shownFlow(page, 'Upper tank → Lower tank B')
	);
	// Solved with the same calculation methods as the shared link: no notice.
	await expect(results(reopened).getByText('Calculation methods changed')).toHaveCount(0);

	// A row opens the element's results and trace.
	await results(reopened)
		.getByRole('button', { name: /^Upper tank → Lower tank A/ })
		.click();
	// A panel over the results on wide screens; a dialog on narrow ones, whose body (a scroll box
	// named after it) is also a region, hence the first match: the dialog.
	const trace = reopened
		.getByRole('dialog', { name: 'Upper tank → Lower tank A' })
		.or(reopened.getByRole('region', { name: 'Upper tank → Lower tank A' }))
		.first();
	await expect(trace).toBeVisible();
	await expect(trace.getByText(/Pipe connection · L1/)).toBeVisible();

	// Only the app and its calculation server are contacted (GOALS §4.5).
	const allowed = new Set(['http://localhost:4173', 'http://localhost:8000']);
	expect([...origins].filter((o) => !allowed.has(o))).toEqual([]);
});

test('results tables fit the screen and scroll inside their own box', async ({ page }) => {
	await page.goto(`/p#${encode(PROJECT)}`);
	await solve(page);
	for (const view of ['Summary', 'Nodes', 'Links', 'Boundaries', 'Methods']) {
		await results(page).getByRole('tab', { name: view }).click();
		const overflow = await page.evaluate(
			() => document.documentElement.scrollWidth - document.documentElement.clientWidth
		);
		expect(overflow, `${view}: the page does not scroll sideways`).toBe(0);
	}
});

/**
 * A connection of two pipes in series (illustrative test input: 4 in then 2 in, carbon steel
 * schedule 40) between two tanks. The links table shows each pipe's velocity, Re and regime,
 * exactly as the API reported them for that pipe.
 */
test('a connection of several pipes shows each pipe’s velocity and Re', async ({ page }) => {
	const project = structuredClone(PROJECT) as typeof PROJECT;
	project.id = 'e2e-two-pipes';
	project.components = project.components.filter((c) => c.id !== 'R3');
	project.components[0]!.ports = project.components[0]!.ports.slice(0, 1);
	project.connections = [
		{
			...project.connections[0]!,
			piping: {
				pipes: [
					{ materialId: 'carbon_steel', schedule: '40', nominalSize: NPS4, length: 20 },
					{ materialId: 'carbon_steel', schedule: '40', nominalSize: 2 * 0.0254, length: 20 }
				],
				fittings: [{ type: 'reducer_sudden', quantity: 1, pipeIndex: 0 }]
			}
		}
	];
	await page.goto(`/p#${encode(project)}`);
	const answer = page.waitForResponse(
		(r) => r.url().endsWith('/api/v1/solve') && r.request().method() === 'POST'
	);
	await page.getByRole('button', { name: 'Solve', exact: true }).click();
	const body = (await (await answer).json()) as {
		solvedState: {
			linkResults: Record<
				string,
				{ segments: { velocity: number; reynoldsNumber: number; flowRegime: string }[] }
			>;
		};
	};
	await expect(results(page).getByRole('heading', { name: 'Converged' })).toBeVisible();
	const segments = body.solvedState.linkResults.L1!.segments;
	expect(segments).toHaveLength(2);
	// The second, smaller pipe is the faster one: the first pipe's values alone would hide it.
	expect(Math.abs(segments[1]!.velocity)).toBeGreaterThan(Math.abs(segments[0]!.velocity));

	await results(page).getByRole('tab', { name: 'Links' }).click();
	const table = results(page).getByRole('table', { name: 'Results per pipe connection' });
	const row = table
		.getByRole('row')
		.filter({ has: page.getByRole('rowheader', { name: /^Upper tank → Lower tank A/ }) });
	const sig4 = (v: number) => String(Number(v.toPrecision(4)));
	const pipe = (n: number, value: number) =>
		new RegExp(`Pipe ${n}\\s*${sig4(value).replace('.', '\\.')}(?!\\d)`);
	const velocity = row.getByRole('cell').nth(1);
	await expect(velocity).toContainText(pipe(1, segments[0]!.velocity));
	await expect(velocity).toContainText(pipe(2, segments[1]!.velocity));
	const re = row.getByRole('cell').nth(3);
	await expect(re).toContainText(pipe(2, segments[1]!.reynoldsNumber));
	await expect(row.getByRole('rowheader')).toContainText('2 pipes');
});
