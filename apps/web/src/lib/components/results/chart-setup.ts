/**
 * Chart.js with only the pieces the pump chart uses (line chart, linear scales, tooltip,
 * legend), so the rest of the library stays out of the bundle. Loaded on demand by PumpChart.
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
