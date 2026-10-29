/**
 * Chart.js with only the pieces the pump chart uses (line chart, linear scales, tooltip,
 * legend), so the rest of the library stays out of the bundle, and the chart's configuration.
 * Loaded on demand by PumpChart,
 * with the chart image (proposal export.md §3.4): the same chunk draws the chart and its PNG and
 * hands the PNG to the browser, so Download image never waits for another chunk, and no image
 * code is in the page's own.
 */
import {
	Chart,
	Legend,
	LinearScale,
	LineController,
	LineElement,
	PointElement,
	Tooltip
} from 'chart.js';

Chart.register(LineController, LineElement, PointElement, LinearScale, Tooltip, Legend);

export { Chart };
export { pumpChartConfig, pumpGroupConfig } from '$lib/utils/pump-chart-config';
export { downloadChartImage, IMAGE_REASONS_IN } from '$lib/utils/export/chart-image';
