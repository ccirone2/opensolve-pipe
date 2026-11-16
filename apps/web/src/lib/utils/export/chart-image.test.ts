/**
 * The chart image's caption and name (proposal export.md §3.4, §3.5, §7.1): the title with and
 * without a case, the solve's time in the export's UTC offset (never the machine's time zone), the
 * out-of-date line, and the footer: the figure's own notes, then the disclaimer and the app. jsdom
 * has no canvas, so the drawing itself is covered end to end (tests/export.e2e.ts); which caption
 * the drawing writes (a figure's notes read once its chart is drawn, D24 §9.3) is checked here on
 * stand-in canvases. The values are made-up inputs.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Chart } from 'chart.js';
import { DISCLAIMER } from '../../components/links';
import { designators } from '../../testing/helpers';
import { pumpResult, systemCurveResponse } from '../../testing/results';
import { chartNotes, offCasesNote, otherCasesData, pumpChartData } from '../pump-chart';
import { pumpChartConfig } from '../pump-chart-config';
import { SI_UNITS } from '../units';
import {
	casesNote,
	chartImageCaption,
	chartImageFileName,
	downloadChartImage,
	imageNoteLines,
	offsetDateTime,
	renderChartImage,
	wrapText,
	type ChartImageCaption,
	type ChartImageCaptionInput,
	type ChartImageRequest,
	IMAGE_REASONS_IN
} from './chart-image';

const input = (values: Partial<ChartImageCaptionInput> = {}): ChartImageCaptionInput => ({
	pumpName: 'Transfer pump',
	projectName: 'Pump transfer between two tanks',
	timestamp: '2026-10-25T12:32:05Z',
	methodVersion: '1.2.0',
	stale: false,
	notes: ['The system curve has not been computed for this solve.'],
	disclaimer: DISCLAIMER,
	origin: 'https://opensolve-pipe.app',
	utcOffsetMinutes: 120,
	...values
});

const TZ = process.env.TZ;
afterEach(() => {
	process.env.TZ = TZ;
});

describe('chart image caption', () => {
	it('names the pump, the project, the solve and its methods version', () => {
		expect(chartImageCaption(input())).toEqual({
			title: 'Pump and system curves: Transfer pump',
			subtitle:
				'Pump transfer between two tanks · solved 2026-10-25 14:32 (UTC+02:00) · OpenSolve Pipe calculation methods 1.2.0',
			warning: null,
			footer: [
				'The system curve has not been computed for this solve.',
				DISCLAIMER,
				'OpenSolve Pipe · https://opensolve-pipe.app'
			]
		});
	});

	it('names the case in a project with scenarios, and says when the results are out of date', () => {
		const caption = chartImageCaption(input({ caseName: 'Winter', stale: true }));
		expect(caption.title).toBe('Pump and system curves: Transfer pump, Winter');
		expect(caption.warning).toBe(
			'Out of date: the project had changed after this solve when this image was made.'
		);
	});

	it('writes the solve time in the given offset, whatever the machine’s time zone', () => {
		const at = (utcOffsetMinutes: number) =>
			chartImageCaption(input({ utcOffsetMinutes })).subtitle;
		process.env.TZ = 'America/New_York';
		const newYork = at(-300);
		process.env.TZ = 'Asia/Tokyo';
		expect(at(-300)).toBe(newYork);
		expect(newYork).toContain('solved 2026-10-25 07:32 (UTC-05:00)');
		expect(at(0)).toContain('solved 2026-10-25 12:32 (UTC+00:00)');
		expect(at(-780)).toContain('solved 2026-10-24 23:32 (UTC-13:00)');
		expect(at(330)).toContain('solved 2026-10-25 18:02 (UTC+05:30)');
		expect(offsetDateTime('not a time', 60)).toBe('not a time');
	});

	it('names the file after the project, the case and the pump, at the export time', () => {
		const now = new Date(Date.UTC(2026, 9, 25, 12, 32, 5));
		expect(
			chartImageFileName({
				projectName: 'Booster station',
				caseName: 'Base case',
				pumpName: 'Transfer pump',
				now,
				utcOffsetMinutes: 120
			})
		).toBe('Booster station - Base case - Transfer pump chart 2026-10-25 1432.png');
		expect(
			chartImageFileName({
				projectName: 'Pump transfer between two tanks',
				caseName: null,
				pumpName: 'P/1: main?',
				now,
				utcOffsetMinutes: 0
			})
		).toBe('Pump transfer between two tanks - P_1_ main_ chart 2026-10-25 1232.png');
	});
});

describe('wrapping the caption', () => {
	// A made-up measure: every character is 10 px wide.
	const measure = (text: string) => text.length * 10;

	it('breaks words into lines no wider than the width', () => {
		expect(wrapText('The system curve was not computed', 120, measure)).toEqual([
			'The system',
			'curve was',
			'not computed'
		]);
		expect(wrapText('  spaced   out  ', 1000, measure)).toEqual(['spaced out']);
		expect(wrapText('', 100, measure)).toEqual([]);
	});

	it('keeps a word wider than the width on its own line', () => {
		expect(wrapText('see https://opensolve-pipe.app/p now', 100, measure)).toEqual([
			'see',
			'https://opensolve-pipe.app/p',
			'now'
		]);
	});
});

describe('the image’s notes', () => {
	const others = otherCasesData(
		[
			{ key: '', name: 'Base case', result: pumpResult(), stale: false, system: null },
			{
				key: 'S1',
				name: 'Winter',
				result: pumpResult({ status: 'off', operatingFlow: 0 }),
				stale: true,
				system: null
			}
		],
		SI_UNITS,
		null,
		1,
		null,
		{ '': 'Base', S1: 1 }
	);

	// Nit 5 (owner, 2026-11-12; docs/proposals/pumps-nits.md item 5, slice 5b): each other case by
	// its number, no marker character (was "(slate, hollow markers): △ Base case; □ Winter …").
	it('names the other cases with their numbers', () => {
		expect(casesNote(others)).toBe(
			'Other cases on the chart (slate rings, each tagged with its case number): Base case; case 1: Winter (out of date): off.'
		);
		expect(casesNote([])).toBeNull();
	});

	it('are the figure’s sentences, pointing to where the reasons are, then the other cases', () => {
		const curve = systemCurveResponse('P1', [1]);
		const result = pumpResult({ operatingFlow: 0.034, operatingHead: 7.5, inCurveRange: false });
		const data = pumpChartData(result, SI_UNITS, [0, 0.03], curve);
		const system = { status: 'ready', curve } as const;
		const screen = chartNotes({ data, result, system });
		const image = chartNotes({ data, result, system, reasonsIn: IMAGE_REASONS_IN });
		expect(imageNoteLines(image, others)).toEqual([
			"1 of 4 system-curve points have no head: the line has gaps there, and the app's data " +
				'table and the System curves sheet of a results export say why for each (no steady ' +
				'state carries the flow, its head is undetermined, its solve did not converge, or it ' +
				'was not computed).',
			screen.method,
			screen.extrapolated,
			...screen.facts,
			casesNote(others)
		]);
		// Nit 5 (owner, 2026-11-12; docs/proposals/pumps-nits.md item 5): the dash named in words,
		// not "(–)".
		expect(screen.facts).toEqual(['Shutoff head (the dash at zero flow): 30 m.']);
	});

	it('name the best efficiency point and the shutoff head in words, on screen and in the image, with no mark in parentheses (nit 5; docs/proposals/pumps-nits.md item 5)', () => {
		const result = pumpResult({
			efficiencyCurve: [
				{ flow: 0.004, efficiency: 0.4 },
				{ flow: 0.012, efficiency: 0.7 },
				{ flow: 0.02, efficiency: 0.6 }
			],
			bestEfficiencyPoint: { flow: 0.012, efficiency: 0.7, head: 18, headExtrapolated: false }
		});
		const data = pumpChartData(result, SI_UNITS, [0, 0.03]);
		const screen = chartNotes({ data, result, system: undefined });
		const image = chartNotes({ data, result, system: undefined, reasonsIn: IMAGE_REASONS_IN });
		// "BEP", the cross's label on the chart (pump-chart-config.ts factDatasets); the dash at
		// zero flow, the shutoff head's mark, which has no label.
		expect(screen.facts).toEqual([
			"Best efficiency point (BEP): 70 % at 12 L/s and 18 m, the efficiency curve's highest point inside its data, at this speed.",
			'Shutoff head (the dash at zero flow): 30 m.'
		]);
		expect(image.facts).toEqual(screen.facts);
		const footer = imageNoteLines(image, []);
		expect(footer).toEqual(expect.arrayContaining(screen.facts));
		for (const line of screen.facts) expect(designators(line), line).toEqual([]);
	});

	// The five glyphs (△ □ ✳ × ▽) went with nit 5 (slice 5b): "names eight cases 1 to 8, each its
	// own number, none a marker" below replaces the test that named them.

	it('end with the cases in which the pump is off and that take no slot, in the screen’s words (§6.2 S8)', () => {
		const result = pumpResult();
		const data = pumpChartData(result, SI_UNITS, [0, 0.03]);
		const notes = chartNotes({ data, result, system: undefined, reasonsIn: IMAGE_REASONS_IN });
		const off = offCasesNote([
			{ tag: 2, label: 'Pump PA off' },
			{ tag: 4, label: 'Both pumps off' }
		]);
		const lines = imageNoteLines(notes, others, off);
		// Nit 5 (slice 5b): each case off by its number (was "…: Pump PA off; Both pumps off.").
		expect(lines.slice(-2)).toEqual([
			casesNote(others),
			'Off in this case (no operating point): case 2: Pump PA off; case 4: Both pumps off.'
		]);
		// Without such a case, the footer is as before.
		expect(imageNoteLines(notes, others, null)).toEqual(lines.slice(0, -1));
		expect(imageNoteLines(notes, others)).toEqual(lines.slice(0, -1));
	});
});

// Case numbers (owner, 2026-11-12, nit 5; Q1 "Shapes go too", Q2 "By list place";
// docs/proposals/pumps-nits.md item 5, slice 5b): the image's footer names each other case by its
// number, the one the chart's slate ring is tagged with, the same on screen and in every list; no
// marker character, so the symbols argument goes.
describe('the image’s notes name each other case by its number (nit 5, slice 5b)', () => {
	const winter = {
		key: 'S1',
		name: 'Winter',
		result: pumpResult({ status: 'off', operatingFlow: 0 }),
		stale: true,
		system: null
	};
	const base = { key: '', name: 'Base case', result: pumpResult(), stale: false, system: null };

	it('says the other cases are slate rings tagged with their numbers, each "case n: …", the base case by its name', () => {
		const tagged = otherCasesData([base, winter], SI_UNITS, null, 1, null, {
			'': 'Base',
			S1: 2
		});
		expect(casesNote(tagged)).toEqual(
			'Other cases on the chart (slate rings, each tagged with its case number): Base case; case 2: Winter (out of date): off.'
		);
		// Their system curves drawn: dotted, said in the same parentheses.
		const curves = otherCasesData(
			[{ ...winter, result: pumpResult(), stale: false, system: systemCurveResponse() }],
			SI_UNITS,
			null,
			1,
			null,
			{ S1: 2 }
		);
		expect(casesNote(curves)).toEqual(
			'Other cases on the chart (slate rings, each tagged with its case number; their system curves dotted): case 2: Winter.'
		);
		expect(casesNote([])).toBeNull();
	});

	it('names eight cases 1 to 8, each its own number, none a marker', () => {
		const ids = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8'];
		const eight = otherCasesData(
			ids.map((key) => ({
				key,
				name: `Case ${key}`,
				result: pumpResult(),
				stale: false,
				system: null
			})),
			SI_UNITS,
			null,
			1,
			null,
			Object.fromEntries(ids.map((id, i) => [id, i + 1]))
		);
		expect(casesNote(eight)).toEqual(
			`Other cases on the chart (slate rings, each tagged with its case number): ${ids
				.map((id, i) => `case ${i + 1}: Case ${id}`)
				.join('; ')}.`
		);
	});

	it('end with the other cases, then the cases off in this case, both by number, with no designator in the footer', () => {
		const result = pumpResult();
		const data = pumpChartData(result, SI_UNITS, [0, 0.03]);
		const notes = chartNotes({ data, result, system: undefined, reasonsIn: IMAGE_REASONS_IN });
		const tagged = otherCasesData([base, winter], SI_UNITS, null, 1, null, {
			'': 'Base',
			S1: 2
		});
		const off = offCasesNote([
			{ tag: 1, label: 'Pump PA off' },
			{ tag: 4, label: 'Both pumps off' }
		]);
		const lines = imageNoteLines(notes, tagged, off);
		expect(lines.slice(-2)).toEqual([
			'Other cases on the chart (slate rings, each tagged with its case number): Base case; case 2: Winter (out of date): off.',
			'Off in this case (no operating point): case 1: Pump PA off; case 4: Both pumps off.'
		]);
		expect(imageNoteLines(notes, tagged)).toEqual(lines.slice(0, -1));
		// The guard (nit 5): no character designates a case anywhere in the pump image's footer.
		for (const line of lines) expect(designators(line), line).toEqual([]);
	});
});

describe('downloading the image', () => {
	// A made-up Chart class: the render is replaced, so nothing of it is read.
	const FakeChart = {} as unknown as typeof Chart;
	const now = new Date(Date.UTC(2026, 9, 25, 12, 32, 5));

	function request(notices: { kind: string; text: string }[]): ChartImageRequest {
		const result = pumpResult();
		const data = pumpChartData(result, SI_UNITS, [0, 0.03]);
		return {
			config: pumpChartConfig(data, [], {
				speedText: '100 % speed',
				legendLabels: () => [],
				format: String,
				forImage: true
			}),
			notes: chartNotes({ data, result, system: undefined, reasonsIn: IMAGE_REASONS_IN }),
			others: [],
			pumpName: 'Transfer pump',
			caseName: 'Winter',
			disclaimer: DISCLAIMER,
			source: {
				projectName: 'Booster station',
				timestamp: '2026-10-25T12:00:00Z',
				methodVersion: '1.2.0',
				stale: false,
				unavailable: '',
				origin: 'https://opensolve-pipe.app',
				notify: (kind, text) => void notices.push({ kind, text })
			}
		};
	}

	it('draws the chart’s configuration at a fixed size with its caption, saves it and says so', async () => {
		const notices: { kind: string; text: string }[] = [];
		const drawn: { config: unknown; caption: ChartImageCaption }[] = [];
		const saved: { blob: Blob; name: string }[] = [];
		const sent = request(notices);
		await downloadChartImage(FakeChart, sent, {
			now,
			render: async (_chart, config, caption) => {
				drawn.push({ config, caption });
				return new Blob(['x'.repeat(28_400)]);
			},
			save: (blob, name) => void saved.push({ blob, name })
		});
		// The configuration the page built for the image, drawn as it is.
		expect(drawn).toHaveLength(1);
		expect(drawn[0]!.config).toBe(sent.config);
		// The solve's time in the export's offset (the machine's, from `now`).
		const offset = -now.getTimezoneOffset();
		expect(drawn[0]!.caption).toEqual(
			chartImageCaption({
				pumpName: 'Transfer pump',
				caseName: 'Winter',
				projectName: 'Booster station',
				timestamp: '2026-10-25T12:00:00Z',
				methodVersion: '1.2.0',
				stale: false,
				notes: [
					'The system curve has not been computed for this solve.',
					// Nit 5: the dash named in words, not "(–)".
					'Shutoff head (the dash at zero flow): 30 m.'
				],
				disclaimer: DISCLAIMER,
				origin: 'https://opensolve-pipe.app',
				utcOffsetMinutes: offset
			})
		);
		const name = chartImageFileName({
			projectName: 'Booster station',
			caseName: 'Winter',
			pumpName: 'Transfer pump',
			now,
			utcOffsetMinutes: offset
		});
		expect(name).toMatch(
			/^Booster station - Winter - Transfer pump chart \d{4}-\d\d-\d\d \d{4}\.png$/
		);
		expect(saved.map((s) => s.name)).toEqual([name]);
		expect(notices).toEqual([
			{ kind: 'info', text: `“${name}” (28 KB) is ready; your browser saves it to its downloads.` }
		]);
	});

	it('writes the line naming the cases that take no slot into the footer, after the other cases (§6.2 S8)', async () => {
		const drawn: ChartImageCaption[] = [];
		const sent = {
			...request([]),
			offCases: 'Off in this case (no operating point): Pump PA off.'
		};
		await downloadChartImage(FakeChart, sent, {
			now,
			render: async (_chart, _config, caption) => {
				drawn.push(caption);
				return new Blob(['x']);
			},
			save: () => {}
		});
		expect(drawn).toHaveLength(1);
		expect(drawn[0]!.footer.slice(0, 3)).toEqual([
			'The system curve has not been computed for this solve.',
			// Nit 5: the dash named in words, not "(–)".
			'Shutoff head (the dash at zero flow): 30 m.',
			'Off in this case (no operating point): Pump PA off.'
		]);
	});

	it('says when the image could not be made, and saves nothing', async () => {
		const notices: { kind: string; text: string }[] = [];
		const saved: string[] = [];
		await downloadChartImage(FakeChart, request(notices), {
			now,
			render: async () => {
				throw new Error('made-up failure');
			},
			save: (_blob, name) => void saved.push(name)
		});
		expect(saved).toEqual([]);
		expect(notices).toEqual([
			{ kind: 'error', text: 'The image could not be made: made-up failure. Nothing was saved.' }
		]);
	});
});

describe('an image of the Pumps together card (CLAUDE.md D21)', () => {
	const FakeChart = {} as unknown as typeof Chart;
	const now = new Date(Date.UTC(2026, 9, 28, 9, 32, 5));

	it('takes its title as a parameter, the case after it', () => {
		expect(chartImageCaption(input({ title: 'Pumps together: PA, PB (parallel)' })).title).toBe(
			'Pumps together: PA, PB (parallel)'
		);
		expect(
			chartImageCaption(input({ title: 'Pumps together: PA, PB (parallel)', caseName: 'Winter' }))
				.title
		).toBe('Pumps together: PA, PB (parallel), Winter');
	});

	it('draws the group configuration with the figure’s lines and names the file after the pumps', async () => {
		const notices: { kind: string; text: string }[] = [];
		const drawn: ChartImageCaption[] = [];
		const saved: string[] = [];
		const config = pumpChartConfig(pumpChartData(pumpResult(), SI_UNITS), [], {
			speedText: '100 % speed',
			legendLabels: () => [],
			format: String,
			forImage: true
		});
		await downloadChartImage(
			FakeChart,
			{
				config,
				title: 'Pumps together: PA, PB (parallel)',
				lines: ['Made-up first note.', 'Made-up second note.'],
				content: 'Pumps together PA, PB',
				disclaimer: DISCLAIMER,
				source: {
					projectName: 'Booster station',
					timestamp: '2026-10-28T09:30:00Z',
					methodVersion: '1.3.0',
					stale: true,
					unavailable: '',
					origin: 'https://opensolve-pipe.app',
					notify: (kind, text) => void notices.push({ kind, text })
				}
			},
			{
				now,
				render: async (_chart, _config, caption) => {
					drawn.push(caption);
					return new Blob(['x']);
				},
				save: (_blob, name) => void saved.push(name)
			}
		);
		expect(drawn[0]!.title).toBe('Pumps together: PA, PB (parallel)');
		expect(drawn[0]!.warning).toBe(
			'Out of date: the project had changed after this solve when this image was made.'
		);
		expect(drawn[0]!.footer).toEqual([
			'Made-up first note.',
			'Made-up second note.',
			DISCLAIMER,
			'OpenSolve Pipe · https://opensolve-pipe.app'
		]);
		expect(saved[0]).toMatch(
			/^Booster station - Pumps together PA, PB \d{4}-\d\d-\d\d \d{4}\.png$/
		);
		expect(notices[0]!.kind).toBe('info');
	});

	it('takes the footer from the image’s own drawing when the figure gives its drawn lines (D24 §9.3)', async () => {
		// The screen left out 4 curve labels; the image's chart, once built, none (made up).
		const screen = 'Labels of 4 curves are left out for space; the data table lists every curve.';
		let built = false;
		const drawn: { caption: ChartImageCaption; drawn: ChartImageCaption | undefined }[] = [];
		await downloadChartImage(
			FakeChart,
			{
				config: pumpChartConfig(pumpChartData(pumpResult(), SI_UNITS), [], {
					speedText: '100 % speed',
					legendLabels: () => [],
					format: String,
					forImage: true
				}),
				title: 'Pumps together: PA, PB (parallel)',
				lines: ['Made-up first note.', screen],
				drawnLines: () => (built ? ['Made-up first note.'] : ['Read before the chart was built.']),
				content: 'Pumps together PA, PB',
				disclaimer: DISCLAIMER,
				source: {
					projectName: 'Booster station',
					timestamp: '2026-10-28T09:30:00Z',
					methodVersion: '1.6.0',
					stale: false,
					unavailable: '',
					origin: 'https://opensolve-pipe.app',
					notify: () => {}
				}
			},
			{
				now,
				render: async (_chart, _config, caption, drawnCaption) => {
					built = true;
					drawn.push({ caption, drawn: drawnCaption?.() });
					return new Blob(['x']);
				},
				save: () => {}
			}
		);
		const tail = [DISCLAIMER, 'OpenSolve Pipe · https://opensolve-pipe.app'];
		expect(drawn[0]!.caption.footer).toEqual(['Made-up first note.', screen, ...tail]);
		expect(drawn[0]!.drawn?.footer).toEqual(['Made-up first note.', ...tail]);
		expect({ ...drawn[0]!.drawn, footer: [] }).toEqual({ ...drawn[0]!.caption, footer: [] });
	});
});

describe('drawing the image (renderChartImage, on stand-in canvases)', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('writes the caption read once its chart is drawn, when given one (D24 §9.3)', async () => {
		const written: string[] = [];
		const context = {
			font: '',
			fillStyle: '',
			textBaseline: '',
			measureText: (text: string) => ({ width: text.length * 6 }),
			scale() {},
			fillRect() {},
			drawImage() {},
			fillText: (text: string) => void written.push(text)
		};
		const canvas = () => ({
			width: 0,
			height: 0,
			getContext: () => context,
			toBlob: (done: (blob: Blob | null) => void) => done(new Blob(['png']))
		});
		vi.stubGlobal('document', { createElement: canvas });
		// A stand-in for Chart.js: drawn when made, as it is without animation; destroyed after.
		let charts = 0;
		let destroyed = 0;
		class DrawnChart {
			constructor() {
				charts++;
			}
			destroy() {
				destroyed++;
			}
		}
		const caption = (note: string): ChartImageCaption =>
			chartImageCaption(input({ title: 'Pumps together: PA, PB (parallel)', notes: [note] }));
		const config = pumpChartConfig(pumpChartData(pumpResult(), SI_UNITS), [], {
			speedText: '100 % speed',
			legendLabels: () => [],
			format: String,
			forImage: true
		});
		const blob = await renderChartImage(
			DrawnChart as unknown as typeof Chart,
			config,
			caption('The screen’s count.'),
			() => caption(charts ? 'The drawing’s count.' : 'Read before the chart was drawn.')
		);
		expect(blob.size).toBeGreaterThan(0);
		expect(written).toContain('The drawing’s count.');
		expect(written).not.toContain('The screen’s count.');
		expect(written).not.toContain('Read before the chart was drawn.');
		expect([charts, destroyed]).toEqual([1, 1]);
		// Without one, the caption given.
		written.length = 0;
		await renderChartImage(
			DrawnChart as unknown as typeof Chart,
			config,
			caption('The screen’s count.')
		);
		expect(written).toContain('The screen’s count.');
	});
});
