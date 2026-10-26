/**
 * The pump chart as a PNG (proposal export.md §3.4, decision 22): the chart shown, drawn again
 * off screen from the same configuration as the screen's (utils/pump-chart-config.ts),
 * 800 × 440 CSS px at 2× (1600 × 880 px), on an opaque white canvas with a caption: a header
 * (the title, the project, the solve's time and methods version, and an out-of-date warning) and
 * a footer (the figure's own notes, the disclaimer and the app). The on-screen canvas is not used:
 * it is transparent, and its size depends on the device, while this render gives the same image
 * on a desktop and a phone. The plot keeps its size and the height grows with the text.
 *
 * Nothing is sent and nothing is hidden: the visible caption is the record, so the PNG has no
 * metadata chunks, and the project link never goes into an image. This module is in the chart
 * chunk (components/results/chart-setup.ts re-exports it), loaded before any chart is drawn. It
 * takes the configuration, the notes and the disclaimer from the page rather than importing the
 * page's modules, so the bundler keeps them where they are and the page loads no extra chunk.
 */
import type { Chart as ChartInstance } from 'chart.js';
import type { ChartNotes, OtherCaseData } from '../pump-chart';
import type { PumpChartConfig } from '../pump-chart-config';
import { fileSizeText, saveBlob } from './download';
import { exportFileName, localTime, offsetText } from './filename';

/** What an image of a pump's chart names, and whether one can be made (PumpChart's `image`). */
export interface ChartImageSource {
	/** The project's name. */
	projectName: string;
	/** The solve's time (SolvedState.timestamp: ISO 8601, UTC) and methods version. */
	timestamp: string;
	methodVersion: string;
	/** The project changed after this solve. */
	stale: boolean;
	/**
	 * Why no image can be made of these results ('' when one can): a solve that did not converge,
	 * the results of an earlier project shown after a failed solve, a calculation in flight.
	 */
	unavailable: string;
	/** The page's origin, for the footer's app line. */
	origin: string;
	/** Tells the outcome (the page's polite notice). */
	notify: (kind: 'info' | 'error', text: string) => void;
}

export interface ChartImageCaptionInput {
	pumpName: string;
	/** The case shown, in a project with scenarios ("Winter", "Base case"). */
	caseName?: string;
	projectName: string;
	/** SolvedState.timestamp (ISO 8601, UTC). */
	timestamp: string;
	methodVersion: string;
	stale: boolean;
	/** The figure's notes, in its order (imageNoteLines). */
	notes: readonly string[];
	/** The disclaimer (components/links.ts DISCLAIMER, GOALS §4.8), verbatim. */
	disclaimer: string;
	origin: string;
	/** The local time's offset from UTC (−Date.getTimezoneOffset()), in minutes. */
	utcOffsetMinutes: number;
}

export interface ChartImageCaption {
	/** "Pump and system curves: Transfer pump, Winter" (the figcaption's words). */
	title: string;
	/** "{project} · solved 2026-10-25 14:32 (UTC+02:00) · OpenSolve Pipe calculation methods 1.2.0". */
	subtitle: string;
	/** The out-of-date warning, or null. */
	warning: string | null;
	/** The figure's notes, then the disclaimer, then the app line. */
	footer: string[];
}

const pad = (n: number, width = 2) => String(n).padStart(width, '0');

/**
 * An ISO 8601 time as "YYYY-MM-DD HH:mm (UTC±hh:mm)" in the given offset, computed by arithmetic
 * (no time-zone lookup, filename.ts localTime); a time that cannot be read is written as it is.
 */
export function offsetDateTime(iso: string, utcOffsetMinutes: number): string {
	const ms = Date.parse(iso);
	if (!Number.isFinite(ms)) return iso;
	const t = localTime(ms, utcOffsetMinutes);
	return (
		`${pad(t.year, 4)}-${pad(t.month)}-${pad(t.day)} ${pad(t.hour)}:${pad(t.minute)} ` +
		`(UTC${offsetText(utcOffsetMinutes)})`
	);
}

/** The caption of a chart image: pure, so its words are tested without a canvas. */
export function chartImageCaption(input: ChartImageCaptionInput): ChartImageCaption {
	return {
		title: `Pump and system curves: ${input.pumpName}${input.caseName ? `, ${input.caseName}` : ''}`,
		subtitle:
			`${input.projectName} · solved ${offsetDateTime(input.timestamp, input.utcOffsetMinutes)} · ` +
			`OpenSolve Pipe calculation methods ${input.methodVersion}`,
		warning: input.stale
			? 'Out of date: the project had changed after this solve when this image was made.'
			: null,
		footer: [...input.notes, input.disclaimer, `OpenSolve Pipe · ${input.origin}`]
	};
}

export interface ChartImageNameInput {
	projectName: string;
	/** The case shown, in a project with scenarios (null: none, the name leaves it out). */
	caseName: string | null;
	pumpName: string;
	now: Date;
	utcOffsetMinutes: number;
}

/** "Booster station - Base case - Transfer pump chart 2026-10-25 1432.png" (export.md §3.5). */
export function chartImageFileName(input: ChartImageNameInput): string {
	return exportFileName({
		project: input.projectName,
		case: input.caseName,
		content: `${input.pumpName} chart`,
		ext: 'png',
		now: input.now,
		utcOffsetMinutes: input.utcOffsetMinutes,
		notConverged: false
	});
}

/** The chart's size in CSS px; it is drawn at 2×. */
export const CHART_WIDTH = 800;
export const CHART_HEIGHT = 440;
/** Each panel below the head (efficiency, power, NPSH: proposal pump-chart.md §4.5) adds this. */
export const PANEL_HEIGHT = 150;

/** The plot's height for a configuration: the head panel's, plus each stacked panel's. */
export function plotHeight(config: PumpChartConfig): number {
	const scales = Object.keys(config.options?.scales ?? {}).filter((id) => id.startsWith('y'));
	return CHART_HEIGHT + Math.max(0, scales.length - 1) * PANEL_HEIGHT;
}
const SCALE = 2;
/** Text is wrapped at 760 CSS px (1,520 px), with 20 CSS px on each side. */
const MARGIN = 20;
const TEXT_WIDTH = CHART_WIDTH - 2 * MARGIN;

const FONTS = {
	title: '600 18px system-ui, sans-serif',
	text: '13px system-ui, sans-serif'
} as const;
/** The screen's validated palette, on white: ink, slate, and amber for a warning (≥ 7:1). */
const COLORS = { ink: '#0f172a', slate: '#475569', amber: '#92400e' } as const;

/** Words broken into lines no wider than `width` (a word wider than that stays on its own). */
export function wrapText(text: string, width: number, measure: (text: string) => number): string[] {
	const lines: string[] = [];
	let line = '';
	for (const word of text.split(/\s+/).filter(Boolean)) {
		const candidate = line ? `${line} ${word}` : word;
		if (!line || measure(candidate) <= width) line = candidate;
		else {
			lines.push(line);
			line = word;
		}
	}
	if (line) lines.push(line);
	return lines;
}

interface Block {
	lines: string[];
	font: string;
	color: string;
	lineHeight: number;
	/** Space before the block (CSS px). */
	before: number;
}

/** The PNG of a pump chart: `config` drawn at a fixed size with `caption`. */
export async function renderChartImage(
	Chart: typeof ChartInstance,
	config: PumpChartConfig,
	caption: ChartImageCaption
): Promise<Blob> {
	// The chart, on a detached canvas: Chart.js reads its CSS size from these attributes when it
	// is not responsive, and draws it synchronously without animation.
	const plot = document.createElement('canvas');
	const plotH = plotHeight(config);
	plot.width = CHART_WIDTH;
	plot.height = plotH;
	const plotContext = plot.getContext('2d');
	if (!plotContext) throw new Error('this browser cannot draw the chart');
	const chart = new Chart(plotContext, config);
	try {
		const image = document.createElement('canvas');
		const context = image.getContext('2d');
		if (!context) throw new Error('this browser cannot draw the image');
		const measure = (font: string) => (text: string) => {
			context.font = font;
			return context.measureText(text).width;
		};
		const block = (text: string, font: string, color: string, lineHeight: number, before = 0) => ({
			lines: wrapText(text, TEXT_WIDTH, measure(font)),
			font,
			color,
			lineHeight,
			before
		});
		const header: Block[] = [
			block(caption.title, FONTS.title, COLORS.ink, 24),
			block(caption.subtitle, FONTS.text, COLORS.slate, 18, 4),
			...(caption.warning ? [block(caption.warning, FONTS.text, COLORS.amber, 18, 4)] : [])
		];
		const footer = caption.footer.map((text, i) =>
			block(text, FONTS.text, COLORS.slate, 18, i === 0 ? 0 : 6)
		);
		const height = (blocks: Block[]) =>
			blocks.reduce((sum, b) => sum + b.before + b.lines.length * b.lineHeight, 0);
		const headerHeight = MARGIN + height(header) + 12;
		const total = headerHeight + plotH + 12 + height(footer) + MARGIN;

		// Setting the size clears the canvas and its state: measure first, then paint.
		image.width = CHART_WIDTH * SCALE;
		image.height = Math.ceil(total * SCALE);
		context.scale(SCALE, SCALE);
		context.fillStyle = '#ffffff';
		context.fillRect(0, 0, CHART_WIDTH, total);
		context.textBaseline = 'middle';
		const paint = (blocks: Block[], top: number) => {
			let y = top;
			for (const b of blocks) {
				y += b.before;
				context.font = b.font;
				context.fillStyle = b.color;
				for (const line of b.lines) {
					context.fillText(line, MARGIN, y + b.lineHeight / 2);
					y += b.lineHeight;
				}
			}
		};
		paint(header, MARGIN);
		context.drawImage(plot, 0, headerHeight, CHART_WIDTH, plotH);
		paint(footer, headerHeight + plotH + 12);

		return await new Promise<Blob>((resolve, reject) =>
			image.toBlob(
				(blob) => (blob ? resolve(blob) : reject(new Error('the image could not be encoded'))),
				'image/png'
			)
		);
	} finally {
		chart.destroy();
	}
}

/** Where the image says the reasons of points without a head are: it has no data table. */
export const IMAGE_REASONS_IN =
	"the app's data table and the System curves sheet of a results export say";

/** The other cases on the chart with their markers (on screen, the case checkboxes say it). */
export function casesNote(
	others: readonly OtherCaseData[],
	symbols: Readonly<Record<string, string>>
): string | null {
	if (!others.length) return null;
	const dotted = others.some((o) => o.system) ? '; their system curves dotted' : '';
	const cases = others.map(
		(o) =>
			`${symbols[o.marker]} ${o.label}${o.row.state === 'Running' ? '' : `: ${o.row.state.toLowerCase()}`}`
	);
	return `Other cases on the chart (slate, hollow markers${dotted}): ${cases.join('; ')}.`;
}

/** The image's footer notes: the figure's own sentences, in its order, then the other cases. */
export function imageNoteLines(
	notes: ChartNotes,
	others: readonly OtherCaseData[],
	symbols: Readonly<Record<string, string>>
): string[] {
	return [
		notes.pump,
		notes.curve?.text,
		notes.method,
		notes.extrapolated,
		...notes.panels,
		...notes.facts,
		casesNote(others, symbols)
	].filter((line): line is string => !!line);
}

/** An image of what PumpChart shows, as the page gives it. */
export interface ChartImageRequest {
	/** The chart's configuration for the image (pump-chart-config.ts pumpChartConfig, `forImage`). */
	config: PumpChartConfig;
	/** The figure's notes (pump-chart.ts chartNotes, with `reasonsIn: IMAGE_REASONS_IN`). */
	notes: ChartNotes;
	/** The other cases drawn, and their markers as text (pump-chart.ts MARKER_SYMBOLS). */
	others: readonly OtherCaseData[];
	markerSymbols: Readonly<Record<string, string>>;
	pumpName: string;
	/** The case shown, in a project with scenarios. */
	caseName?: string;
	/** The disclaimer (components/links.ts DISCLAIMER). */
	disclaimer: string;
	source: ChartImageSource;
}

/** What draws and saves the image (replaced in tests: jsdom has no canvas). */
export interface ChartImageIO {
	now?: Date;
	render?: typeof renderChartImage;
	save?: typeof saveBlob;
}

/**
 * Draw the chart again at a fixed size with its caption, hand the PNG to the browser and say so
 * in the page's notice, in the export's words ("your browser saves it", never "saved": the user
 * can still cancel a browser's prompt), or say why it could not be made (export.md §5.5).
 */
export async function downloadChartImage(
	Chart: typeof ChartInstance,
	request: ChartImageRequest,
	{ now = new Date(), render = renderChartImage, save = saveBlob }: ChartImageIO = {}
): Promise<void> {
	const { source } = request;
	try {
		const utcOffsetMinutes = -now.getTimezoneOffset();
		const caption = chartImageCaption({
			pumpName: request.pumpName,
			...(request.caseName ? { caseName: request.caseName } : {}),
			projectName: source.projectName,
			timestamp: source.timestamp,
			methodVersion: source.methodVersion,
			stale: source.stale,
			notes: imageNoteLines(request.notes, request.others, request.markerSymbols),
			disclaimer: request.disclaimer,
			origin: source.origin,
			utcOffsetMinutes
		});
		const blob = await render(Chart, request.config, caption);
		const fileName = chartImageFileName({
			projectName: source.projectName,
			caseName: request.caseName ?? null,
			pumpName: request.pumpName,
			now,
			utcOffsetMinutes
		});
		save(blob, fileName);
		source.notify(
			'info',
			`“${fileName}” (${fileSizeText(blob.size)}) is ready; your browser saves it to its downloads.`
		);
	} catch (error) {
		source.notify(
			'error',
			`The image could not be made: ${error instanceof Error ? error.message : String(error)}. Nothing was saved.`
		);
	}
}
