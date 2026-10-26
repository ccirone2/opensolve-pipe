/**
 * The export dialog (proposal export.md §5.3-§5.4, §5.7), opened from the Results header through
 * its lazily loaded chunk: the choices it offers (Cases only with scenarios, by default the case
 * shown, or All cases on the Compare cases tab), the warnings of the cases it exports, what the
 * file holds and its name, Download focused on open, the file made and handed to the browser,
 * progress after 300 ms, Cancel, Close and Esc, a failure, and one build at a time. The choices
 * are kept for the page session and reset when another project is loaded. Nothing is sent.
 *
 * The real model and writers make the file. A build's yields go through MessageChannel, which
 * the slow-build tests replace with one whose messages wait until the test delivers them. The
 * solved states are made-up test inputs.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TopologyError } from '$lib/api/client';
import type { Project } from '$lib/api/types';
import WorkspaceView from '$lib/components/workspace/Workspace.svelte';
import type { Solver } from '$lib/state/project.svelte';
import { pumpTransferSolved, response } from '$lib/testing/results';
import { testWorkspace } from '$lib/testing/workspace';
import { gravityBranchExample, pumpTransferExample } from '$lib/utils/examples';
import { withScenarios } from '$lib/utils/scenarios';

const results = () => within(screen.getByRole('region', { name: 'Results' }));
const dialog = () => within(screen.getByRole('dialog', { name: 'Export results' }));
const STAMP = String.raw`\d{4}-\d\d-\d\d \d{4}`;

/** Files handed to the browser (saveBlob's link clicks). */
let saved: { name: string; blob: Blob }[] = [];
let fetches = 0;

beforeEach(() => {
	saved = [];
	fetches = 0;
	const blobs = new Map<string, Blob>();
	URL.createObjectURL = (blob: Blob) => {
		const url = `blob:made-up/${blobs.size}`;
		blobs.set(url, blob);
		return url;
	};
	URL.revokeObjectURL = () => {};
	vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
		this: HTMLAnchorElement
	) {
		saved.push({ name: this.download, blob: blobs.get(this.getAttribute('href') ?? '')! });
	});
	// Export sends nothing: any request fails the test.
	vi.stubGlobal('fetch', () => {
		fetches++;
		return Promise.reject(new Error('no request expected'));
	});
});

afterEach(() => {
	vi.useRealTimers();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

const solvesOk: Solver = { solve: async () => response(pumpTransferSolved()) };

async function solved(project: Project = pumpTransferExample(), solver: Solver = solvesOk) {
	const ws = testWorkspace(project, { solver });
	render(WorkspaceView, { workspace: ws });
	await fireEvent.click(screen.getByRole('button', { name: /^Solve/ }));
	await results().findByRole('heading', { name: /^(Converged|Did not converge)$/ });
	return ws;
}

async function openExport(name: string | RegExp = /^Export results/) {
	// A keyboard user's Enter: the button has the focus (jsdom does not focus on a click).
	const button = results().getByRole('button', { name });
	button.focus();
	await fireEvent.click(button);
	return screen.findByRole('dialog', { name: 'Export results' });
}

const fileName = () =>
	screen.getByRole('dialog').querySelector('[data-export-file-name]')!.textContent!.trim();
const contents = () =>
	screen.getByRole('dialog').querySelector('[data-export-contents]')!.textContent!.trim();
const status = () => dialog().getByRole('status');
const download = () => dialog().getByRole('button', { name: /^(Download|Preparing…)$/ });
/** The footer's Close (the title bar has one too). */
const closeButton = () => dialog().getAllByRole('button', { name: 'Close' }).at(-1)!;

/** A Blob's bytes (jsdom's Blob has no arrayBuffer()). */
function bytesOf(blob: Blob): Promise<Uint8Array> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
		reader.onerror = () => reject(reader.error);
		reader.readAsArrayBuffer(blob);
	});
}

/** A MessageChannel whose messages wait until the test delivers them (a build's yields). */
function holdYields() {
	const held: (() => void)[] = [];
	class HeldChannel {
		port1 = { onmessage: null as null | (() => void), close() {} };
		port2 = {
			postMessage: () => void held.push(() => this.port1.onmessage?.()),
			close() {}
		};
	}
	vi.stubGlobal('MessageChannel', HeldChannel);
	return {
		held,
		/** Deliver the waiting yields, one at a time, until the build has none waiting. */
		async release() {
			for (let i = 0; i < 1000 && held.length; i++) {
				held.shift()!();
				await vi.advanceTimersByTimeAsync(0);
			}
		}
	};
}

describe('the export dialog', () => {
	it('offers the format, the units and the link, with the defaults ready and Download focused', async () => {
		await solved();
		await openExport('Export results');
		expect(dialog().queryByRole('group', { name: 'Cases' })).toBeNull();
		expect(dialog().getByRole('radio', { name: /^Excel workbook \(\.xlsx\)/ })).toBeChecked();
		expect(dialog().getByRole('radio', { name: /^CSV files \(\.zip\)/ })).not.toBeChecked();
		expect(
			dialog().getByRole('radio', { name: 'Display units (L/s, kPa(g), m, as set in Settings)' })
		).toBeChecked();
		expect(
			dialog().getByRole('radio', { name: 'SI base units (m³/s, Pa, m, …)' })
		).not.toBeChecked();
		expect(dialog().getByRole('checkbox', { name: 'Include the project link' })).toBeChecked();
		expect(
			dialog().getByRole('checkbox', { name: 'Include the project link' })
		).toHaveAccessibleDescription(/^The link lets anyone open the whole project/);
		expect(dialog().getByRole('radio', { name: /^CSV files/ })).toHaveAccessibleDescription(
			/decimal commas can read these values wrongly without a warning/
		);
		expect(contents()).toMatch(/^About · Flags \(0\) · Nodes \(6\) · Links \(3\) · .* · Methods$/);
		expect(fileName()).toMatch(
			new RegExp(`^Pump transfer between two tanks - results ${STAMP}\\.xlsx$`)
		);
		expect(document.activeElement).toBe(download());
		expect(download()).toHaveTextContent('Download');
		expect(
			dialog().getByText('Files are made in this browser; nothing is sent to the server.')
		).toBeInTheDocument();
		expect(dialog().getByText(/use Download image under the chart \(Pumps\)/)).toBeInTheDocument();
		expect(dialog().queryByRole('button', { name: 'Cancel' })).toBeNull();
		expect(status().textContent).toBe('');
		expect(dialog().getByRole('alert').textContent).toBe('');
	});

	it('makes the workbook in the browser and says it is ready, sending nothing', async () => {
		await solved();
		await openExport();
		const name = fileName();
		await fireEvent.click(download());
		await vi.waitFor(() => expect(saved).toHaveLength(1));
		expect(saved[0]!.name).toBe(name);
		const bytes = await bytesOf(saved[0]!.blob);
		expect([...bytes.subarray(0, 4)]).toEqual([0x50, 0x4b, 0x03, 0x04]); // PK\3\4
		expect(saved[0]!.blob.type).toBe(
			'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
		);
		expect(status()).toHaveTextContent(
			new RegExp(
				`^“${name.replace(/[.()]/g, '\\$&')}” \\(\\d+(\\.\\d)? KB\\) is ready; your browser saves it to its downloads\\.$`
			)
		);
		expect(fetches).toBe(0);
	});

	it('lists the CSV files and names the zip; the choices stay for the session, until another project', async () => {
		const ws = await solved();
		await openExport();
		await fireEvent.click(dialog().getByRole('radio', { name: /^CSV files/ }));
		await fireEvent.click(dialog().getByRole('radio', { name: /^SI base units/ }));
		await fireEvent.click(dialog().getByRole('checkbox', { name: 'Include the project link' }));
		expect(contents()).toMatch(
			/^README\.txt · about\.csv · flags\.csv \(0\) · nodes\.csv \(6\) · .* · methods\.txt$/
		);
		expect(fileName()).toMatch(
			new RegExp(`^Pump transfer between two tanks - results \\(CSV\\) ${STAMP}\\.zip$`)
		);
		expect(
			within(
				screen.getByRole('dialog').querySelector('[data-export-omitted]') as HTMLElement
			).getByText('Project link: left out when exported')
		).toBeInTheDocument();
		await fireEvent.click(closeButton());
		expect(screen.queryByRole('dialog')).toBeNull();
		// The focus returns to Export.
		expect(document.activeElement).toBe(results().getByRole('button', { name: 'Export results' }));

		await openExport();
		expect(dialog().getByRole('radio', { name: /^CSV files/ })).toBeChecked();
		expect(dialog().getByRole('radio', { name: /^SI base units/ })).toBeChecked();
		expect(dialog().getByRole('checkbox', { name: 'Include the project link' })).not.toBeChecked();
		await fireEvent.click(closeButton());

		// Another project in the page: its choices start as a reload's would.
		ws.store.load(pumpTransferExample());
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: /^Solve/ }));
		await results().findByRole('heading', { name: 'Converged' });
		await openExport();
		expect(dialog().getByRole('radio', { name: /^Excel workbook/ })).toBeChecked();
		expect(dialog().getByRole('radio', { name: /^Display units/ })).toBeChecked();
		expect(dialog().getByRole('checkbox', { name: 'Include the project link' })).toBeChecked();
	});

	it('with scenarios: the case shown or all cases, all cases by default on Compare cases', async () => {
		const ws = testWorkspace(
			withScenarios(pumpTransferExample(), [{ id: 'S1', name: 'Winter', overrides: [] }]),
			{ solver: solvesOk }
		);
		render(WorkspaceView, { workspace: ws });
		await ws.solveAll();
		await tick();
		await openExport('Export results of Base case');
		const cases = dialog().getByRole('group', { name: 'Cases' });
		expect(within(cases).getByRole('radio', { name: 'Base case (the case shown)' })).toBeChecked();
		expect(
			within(cases).getByRole('radio', { name: 'All cases (base and 1 scenario)' })
		).not.toBeChecked();
		expect(fileName()).toMatch(
			new RegExp(`^Pump transfer between two tanks - Base case - results ${STAMP}\\.xlsx$`)
		);
		expect(contents()).not.toMatch(/Compare cases/);
		await fireEvent.click(within(cases).getByRole('radio', { name: /^All cases/ }));
		expect(fileName()).toMatch(
			new RegExp(`^Pump transfer between two tanks - All cases - results ${STAMP}\\.xlsx$`)
		);
		expect(contents()).toMatch(/^About · Flags \(0\) · Compare cases \(\d+\) · Nodes \(12\)/);
		expect(contents()).not.toMatch(/Trace/);
		await fireEvent.click(closeButton());

		await fireEvent.click(results().getByRole('tab', { name: 'Compare cases' }));
		// Named as its default: all cases (review W5).
		await openExport('Export results of all cases');
		expect(dialog().getByRole('radio', { name: /^All cases/ })).toBeChecked();
	});

	it('warns of a solve that did not converge, current or out of date (red)', async () => {
		const ws = await solved(pumpTransferExample(), {
			solve: async () => response(pumpTransferSolved({ converged: false }), { success: false })
		});
		await openExport();
		const warning = () => screen.getByRole('dialog').querySelector('[data-export-warning]')!;
		expect(warning()).toHaveAttribute('data-export-warning', 'not_converged');
		expect(warning()).toHaveClass('border-red-300');
		expect(warning()).toHaveTextContent(
			'This solve did not converge: its values are not a solution of the network. The file holds its convergence report, flags and methods, but no values.'
		);
		expect(fileName()).toMatch(/ \(not converged\)\.xlsx$/);
		expect(contents()).not.toMatch(/Nodes/);
		await fireEvent.click(closeButton());
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		await tick();
		await openExport();
		const warnings = screen.getByRole('dialog').querySelectorAll('[data-export-warning]');
		expect([...warnings].map((w) => w.getAttribute('data-export-warning'))).toEqual([
			'not_converged'
		]);
		expect(warnings[0]).toHaveTextContent(/out-of-date/);
		expect(fileName()).toMatch(/ \(not converged\)\.xlsx$/);
	});

	it('warns of out-of-date results (amber), and of earlier results shown after a failed solve', async () => {
		let calls = 0;
		const ws = await solved(pumpTransferExample(), {
			solve: async () => {
				if (++calls === 1) return response(pumpTransferSolved());
				throw new TopologyError('The network cannot be solved: 1 topology issue(s).', [
					{
						code: 'UNCONNECTED_PORT',
						message: "port 'V1:outlet' is not connected; connect it or add a plug",
						componentIds: ['V1'],
						connectionIds: []
					}
				]);
			}
		});
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		await tick();
		await openExport();
		const kinds = () =>
			[...screen.getByRole('dialog').querySelectorAll('[data-export-warning]')].map((w) => [
				w.getAttribute('data-export-warning'),
				w.textContent!.trim()
			]);
		expect(kinds()).toEqual([
			[
				'stale',
				'The project changed after this solve. The file holds the results, names and link of the project as it was solved, and says so in every row. Solve again for current results.'
			]
		]);
		expect(screen.getByRole('dialog').querySelector('[data-export-warning]')).toHaveClass(
			'border-amber-300'
		);
		await fireEvent.click(closeButton());

		expect(ws.remove('R2', false)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: 'Solve' }));
		await fireEvent.click(
			await results().findByRole('button', { name: 'Show the earlier results' })
		);
		await openExport();
		expect(kinds()).toEqual([
			[
				'failed_shown',
				'The latest solve failed. The results shown below the error are from an earlier version of the project and are not in the file.'
			]
		]);
		expect(contents()).not.toMatch(/Nodes/);
	});

	it('shows progress after 300 ms, at most once a second, and Cancel stops the build', async () => {
		await solved(gravityBranchExample());
		await openExport();
		const yields = holdYields();
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
		await fireEvent.click(download());
		await vi.advanceTimersByTimeAsync(299);
		expect(dialog().queryByRole('button', { name: 'Cancel' })).toBeNull();
		expect(status().textContent).toBe('');
		await vi.advanceTimersByTimeAsync(1);
		// The spinner, in a button of the same width, and Cancel beside it.
		expect(download()).toHaveTextContent('Preparing…');
		expect(download().querySelector('svg')).toHaveClass('motion-safe:animate-spin');
		expect(status()).toHaveTextContent(/^Preparing the workbook: About \(sheet 1 of \d+\)…$/);
		// The next sheet is named at the next second, not before.
		yields.held.shift()!();
		await vi.advanceTimersByTimeAsync(500);
		expect(status()).toHaveTextContent(/sheet 1 of/);
		await vi.advanceTimersByTimeAsync(500);
		expect(status()).toHaveTextContent(/^Preparing the workbook: Flags \(sheet 2 of \d+\)…$/);
		await fireEvent.click(dialog().getByRole('button', { name: 'Cancel' }));
		await yields.release();
		expect(status()).toHaveTextContent('Export cancelled; nothing was saved.');
		expect(saved).toEqual([]);
		expect(download()).toHaveTextContent('Download');
		expect(dialog().queryByRole('button', { name: 'Cancel' })).toBeNull();
		expect(dialog().getByRole('alert').textContent).toBe('');
	});

	it('Download, Cancel and the status lines are in the footer, always in view; the warnings describe Download (review W1)', async () => {
		const ws = await solved();
		ws.store.update((p) => {
			p.connections[0]!.piping.pipes[0]!.length = 500;
		}, 'change length');
		await tick();
		await openExport();
		const footer = screen.getByRole('dialog').querySelector('footer')!;
		expect(footer).not.toBeNull();
		expect(footer).toContainElement(download());
		expect(footer).toContainElement(status());
		expect(footer).toContainElement(dialog().getByRole('alert'));
		expect(document.activeElement).toBe(download());
		// The warnings come first in the body, and a screen reader hears them with Download.
		const warning = screen.getByRole('dialog').querySelector('[data-export-warning="stale"]')!;
		expect(footer).not.toContainElement(warning as HTMLElement);
		expect(download()).toHaveAccessibleDescription(
			'The project changed after this solve. The file holds the results, names and link of the project as it was solved, and says so in every row. Solve again for current results.'
		);
		// Cancel joins Download in the footer while a build runs.
		const yields = holdYields();
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
		await fireEvent.click(download());
		await vi.advanceTimersByTimeAsync(300);
		expect(footer).toContainElement(dialog().getByRole('button', { name: 'Cancel' }));
		expect(download()).toHaveAccessibleDescription(/A file is being prepared\.$/);
		await yields.release();
	});

	it('Cancel hands the focus to Download when it goes, cancelled or finished (review W2)', async () => {
		await solved(gravityBranchExample());
		await openExport();
		const yields = holdYields();
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
		await fireEvent.click(download());
		await vi.advanceTimersByTimeAsync(300);
		const cancel = dialog().getByRole('button', { name: 'Cancel' });
		cancel.focus();
		await fireEvent.click(cancel);
		await yields.release();
		expect(status()).toHaveTextContent('Export cancelled; nothing was saved.');
		expect(dialog().queryByRole('button', { name: 'Cancel' })).toBeNull();
		expect(document.activeElement).toBe(download());

		// The build finishes while Cancel has the focus.
		await fireEvent.click(download());
		await vi.advanceTimersByTimeAsync(300);
		dialog().getByRole('button', { name: 'Cancel' }).focus();
		await yields.release();
		await vi.waitFor(() => expect(saved).toHaveLength(1));
		expect(dialog().queryByRole('button', { name: 'Cancel' })).toBeNull();
		expect(document.activeElement).toBe(download());
	});

	it('Close and Esc stop a build, and the notice says so', async () => {
		const ws = await solved();
		await openExport();
		const yields = holdYields();
		await fireEvent.click(download());
		await vi.waitFor(() => expect(yields.held.length).toBeGreaterThan(0));
		await fireEvent.click(closeButton());
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(ws.notice).toMatchObject({ kind: 'info', text: 'Export cancelled; nothing was saved.' });
		while (yields.held.length) {
			yields.held.shift()!();
			await tick();
		}
		await new Promise((r) => setTimeout(r, 0));
		expect(saved).toEqual([]);

		ws.dismissNotice();
		const dialogElement = await openExport();
		await fireEvent.click(download());
		await vi.waitFor(() => expect(yields.held.length).toBeGreaterThan(0));
		// Esc: the native dialog's cancel event.
		await fireEvent(dialogElement, new Event('cancel', { cancelable: true }));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(ws.notice).toMatchObject({ kind: 'info', text: 'Export cancelled; nothing was saved.' });
		while (yields.held.length) {
			yields.held.shift()!();
			await tick();
		}
		await new Promise((r) => setTimeout(r, 0));
		expect(saved).toEqual([]);
	});

	it('one build at a time: the choices wait, with the reason', async () => {
		await solved();
		await openExport();
		const yields = holdYields();
		await fireEvent.click(download());
		await vi.waitFor(() => expect(yields.held.length).toBe(1));
		const csv = dialog().getByRole('radio', { name: /^CSV files/ });
		expect(csv).toHaveAttribute('aria-disabled', 'true');
		expect(csv).toHaveAccessibleDescription(/A file is being prepared\.$/);
		expect(download()).toHaveAttribute('aria-disabled', 'true');
		await fireEvent.click(csv);
		// The choice is refused (jsdom does not check the previous radio again, as browsers do).
		expect(csv).not.toBeChecked();
		expect(fileName()).toMatch(/\.xlsx$/);
		await fireEvent.click(dialog().getByRole('checkbox', { name: 'Include the project link' }));
		expect(dialog().getByRole('checkbox', { name: 'Include the project link' })).toBeChecked();
		await fireEvent.click(download());
		// Still one build: one yield waiting.
		expect(yields.held).toHaveLength(1);
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
		await yields.release();
		vi.useRealTimers();
		await vi.waitFor(() => expect(saved).toHaveLength(1));
		expect(csv).not.toHaveAttribute('aria-disabled', 'true');
	});

	it('says when the file could not be made, and saves nothing', async () => {
		await solved();
		await openExport();
		class FailingChannel {
			port1 = { onmessage: null, close() {} };
			port2 = {
				postMessage: () => {
					throw new Error('made-up failure');
				},
				close() {}
			};
		}
		vi.stubGlobal('MessageChannel', FailingChannel);
		await fireEvent.click(download());
		await vi.waitFor(() =>
			expect(dialog().getByRole('alert')).toHaveTextContent(
				'The file could not be made: made-up failure. Nothing was saved.'
			)
		);
		expect(status().textContent).toBe('');
		expect(saved).toEqual([]);
		// The dialog stays open, to try again.
		expect(download()).not.toHaveAttribute('aria-disabled', 'true');
	});
});
