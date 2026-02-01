<script lang="ts">
	import { Chart, registerables } from 'chart.js';
	import type { ChartDataset, ScatterDataPoint } from 'chart.js';
	import type { PumpCurve, PumpResult } from '$lib/models';
	import { calculateBEP, interpolateEfficiency, generateEfficiencyBestFitCurve, generatePumpBestFitCurve } from '$lib/models/pump';
	import { isDarkMode } from '$lib/stores';

	// Register Chart.js components
	Chart.register(...registerables);

	interface Props {
		/** The pump curve data. */
		curve: PumpCurve;
		/** The pump result with operating point and system curve. */
		result?: PumpResult;
	}

	let { curve, result }: Props = $props();

	// Get chart colors based on theme
	function getChartColors(dark: boolean) {
		return {
			gridColor: dark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.05)',
			textColor: dark ? 'rgba(255, 255, 255, 0.8)' : 'rgba(0, 0, 0, 0.8)'
		};
	}

	// Calculate BEP from efficiency curve
	let bep = $derived(calculateBEP(curve));

	// Check if efficiency curve data is available
	let hasEfficiencyCurve = $derived(curve?.efficiency_curve && curve.efficiency_curve.length > 0);

	let canvas: HTMLCanvasElement | null = $state(null);
	let chart: Chart | null = null;

	function destroyChart() {
		if (chart) {
			try {
				chart.destroy();
			} catch {
				// Ignore errors during cleanup
			}
			chart = null;
		}
	}

	function createChart(canvasEl: HTMLCanvasElement, dark: boolean) {
		try {
			// Destroy existing chart first
			destroyChart();

			// Ensure curve has points
			if (!curve?.points || curve.points.length === 0) return;

			// Get theme-aware colors
			const colors = getChartColors(dark);

			// Build datasets
			const datasets: ChartDataset<'scatter', ScatterDataPoint[]>[] = [];

			// System curve - smooth line only, no points (drawn first/behind)
			// Legend: line only (no marker)
			if (result?.system_curve && result.system_curve.length > 0) {
				datasets.push({
					label: 'System Curve',
					data: result.system_curve.map((p) => ({ x: p.flow, y: p.head })),
					borderColor: 'rgb(239, 68, 68)',
					backgroundColor: 'rgba(239, 68, 68, 0.1)',
					fill: false,
					showLine: true,
					tension: 0.4,
					pointRadius: 0,
					pointHoverRadius: 4,
					borderWidth: 2,
					order: 3,
					// Legend shows line only (dash pattern to indicate line)
					pointStyle: 'line'
				});
			}

			// Pump curve - quadratic best-fit line with data points shown
			// Legend: solid circle with line
			const pumpBestFit = generatePumpBestFitCurve(curve);
			if (pumpBestFit) {
				// Smooth best-fit curve (no points)
				datasets.push({
					label: 'Pump Curve',
					data: pumpBestFit.map((p) => ({ x: p.flow, y: p.head })),
					borderColor: 'rgb(59, 130, 246)',
					backgroundColor: 'rgba(59, 130, 246, 0.1)',
					fill: false,
					showLine: true,
					tension: 0,
					pointRadius: 0,
					pointHoverRadius: 0,
					borderWidth: 2,
					order: 2,
					pointStyle: 'line'
				});
				// Data points overlay (for reference)
				datasets.push({
					label: 'Pump Data',
					data: curve.points.map((p) => ({ x: p.flow, y: p.head })),
					borderColor: 'rgb(59, 130, 246)',
					backgroundColor: 'rgb(59, 130, 246)',
					showLine: false,
					pointRadius: 4,
					pointHoverRadius: 6,
					order: 1,
					pointStyle: 'circle'
				});
			} else {
				// Fallback: direct line through points (fewer than 3 points)
				datasets.push({
					label: 'Pump Curve',
					data: curve.points.map((p) => ({ x: p.flow, y: p.head })),
					borderColor: 'rgb(59, 130, 246)',
					backgroundColor: 'rgb(59, 130, 246)',
					fill: false,
					showLine: true,
					tension: 0.4,
					pointRadius: 5,
					pointHoverRadius: 7,
					borderWidth: 2,
					order: 2,
					pointStyle: 'circle'
				});
			}

			// Efficiency curve (if available) - quadratic best-fit on secondary Y-axis
			if (hasEfficiencyCurve && curve.efficiency_curve) {
				// Generate smooth best-fit curve
				const bestFitCurve = generateEfficiencyBestFitCurve(curve);
				if (bestFitCurve) {
					datasets.push({
						label: 'Efficiency',
						data: bestFitCurve.map((p) => ({ x: p.flow, y: p.efficiency * 100 })),
						borderColor: 'rgb(156, 163, 175)',
						backgroundColor: 'rgba(156, 163, 175, 0.1)',
						fill: false,
						showLine: true,
						tension: 0,
						pointRadius: 0,
						pointHoverRadius: 0,
						borderWidth: 1.5,
						order: 4,
						yAxisID: 'yEfficiency',
						pointStyle: 'line'
					});
				} else {
					// Fallback to raw points if best-fit fails (< 3 points)
					datasets.push({
						label: 'Efficiency',
						data: curve.efficiency_curve.map((p) => ({ x: p.flow, y: p.efficiency * 100 })),
						borderColor: 'rgb(156, 163, 175)',
						backgroundColor: 'rgba(156, 163, 175, 0.3)',
						fill: false,
						showLine: true,
						tension: 0.4,
						pointRadius: 3,
						pointHoverRadius: 5,
						borderWidth: 1.5,
						order: 4,
						yAxisID: 'yEfficiency',
						pointStyle: 'circle'
					});
				}
			}

			// Operating point
			if (result?.operating_flow !== undefined && result?.operating_head !== undefined) {
				datasets.push({
					label: 'Operating Point',
					data: [{ x: result.operating_flow, y: result.operating_head }],
					borderColor: 'rgb(34, 197, 94)',
					backgroundColor: 'rgb(34, 197, 94)',
					pointRadius: 8,
					pointHoverRadius: 10,
					showLine: false,
					pointStyle: 'circle'
				});
			}

			// Best Efficiency Point (BEP) - cross-hair marker with orange/amber color
			if (bep) {
				datasets.push({
					label: 'BEP',
					data: [{ x: bep.flow, y: bep.head }],
					borderColor: 'rgb(245, 158, 11)',
					backgroundColor: 'rgb(245, 158, 11)',
					pointRadius: 10,
					pointHoverRadius: 12,
					pointStyle: 'crossRot',
					borderWidth: 3,
					showLine: false
				});
			}

			// Calculate axis ranges
			const allFlows = curve.points.map((p) => p.flow);
			const allHeads = curve.points.map((p) => p.head);

			if (result?.system_curve) {
				allFlows.push(...result.system_curve.map((p) => p.flow));
				allHeads.push(...result.system_curve.map((p) => p.head));
			}

			if (result?.operating_flow !== undefined) {
				allFlows.push(result.operating_flow);
			}
			if (result?.operating_head !== undefined) {
				allHeads.push(result.operating_head);
			}

			// Include BEP in axis range
			if (bep) {
				allFlows.push(bep.flow);
				allHeads.push(bep.head);
			}

			// Include efficiency curve flows
			if (hasEfficiencyCurve && curve.efficiency_curve) {
				allFlows.push(...curve.efficiency_curve.map((p) => p.flow));
			}

			const maxFlow = Math.max(...allFlows) * 1.1 || 100;
			const maxHead = Math.max(...allHeads) * 1.1 || 100;

			// Calculate efficiency axis range to fill vertical space
			let minEfficiency = 0;
			let maxEfficiency = 100;
			if (hasEfficiencyCurve && curve.efficiency_curve) {
				const efficiencies = curve.efficiency_curve.map((p) => p.efficiency * 100);
				const effMin = Math.min(...efficiencies);
				const effMax = Math.max(...efficiencies);
				// Add padding and round to nice numbers
				const effRange = effMax - effMin;
				minEfficiency = Math.max(0, Math.floor((effMin - effRange * 0.1) / 5) * 5);
				maxEfficiency = Math.min(100, Math.ceil((effMax + effRange * 0.1) / 5) * 5);
			}

			// Define scales configuration
			const scales: Record<string, object> = {
				x: {
					type: 'linear',
					min: 0,
					max: maxFlow,
					title: {
						display: true,
						text: 'Flow (GPM)',
						font: { weight: 'bold' },
						color: colors.textColor
					},
					grid: {
						color: colors.gridColor
					},
					ticks: {
						color: colors.textColor
					}
				},
				y: {
					type: 'linear',
					position: 'left',
					min: 0,
					max: maxHead,
					title: {
						display: true,
						text: 'Head (ft)',
						font: { weight: 'bold' },
						color: colors.textColor
					},
					grid: {
						color: colors.gridColor
					},
					ticks: {
						color: colors.textColor
					}
				}
			};

			// Add efficiency Y-axis if efficiency curve exists
			if (hasEfficiencyCurve) {
				scales['yEfficiency'] = {
					type: 'linear',
					position: 'right',
					min: minEfficiency,
					max: maxEfficiency,
					title: {
						display: true,
						text: 'Efficiency (%)',
						font: { weight: 'bold' },
						color: 'rgb(156, 163, 175)'
					},
					grid: {
						drawOnChartArea: false
					},
					ticks: {
						color: 'rgb(156, 163, 175)'
					}
				};
			}

			chart = new Chart(canvasEl, {
				type: 'scatter',
				data: { datasets },
				options: {
					responsive: true,
					maintainAspectRatio: false,
					interaction: {
						intersect: false,
						mode: 'index'
					},
					plugins: {
						legend: {
							position: 'bottom',
							labels: {
								usePointStyle: true,
								padding: 16,
								color: colors.textColor,
								filter: (item) => item.text !== 'Pump Data'
							}
						},
						tooltip: {
							filter: (tooltipItem) => {
								// Don't show duplicate tooltips for same data point
								const label = tooltipItem.dataset.label;
								// Skip efficiency curve in main tooltip (it has different y-axis)
								if (label === 'Efficiency') return false;
								// Skip pump curve line (we show Pump Data points instead)
								if (label === 'Pump Curve') return false;
								return true;
							},
							callbacks: {
								label(context) {
									const point = context.raw as { x: number; y: number };
									let label = context.dataset.label;
									// Show "Pump Curve" for pump data points
									if (label === 'Pump Data') label = 'Pump Curve';
									if (label === 'BEP' && bep) {
										return `BEP: ${point.x.toFixed(1)} GPM @ ${point.y.toFixed(1)} ft (${(bep.efficiency * 100).toFixed(1)}% eff.)`;
									}
									if (label === 'Operating Point' && hasEfficiencyCurve && curve.efficiency_curve) {
										const eff = interpolateEfficiency(curve, point.x);
										if (eff !== null) {
											return `${label}: ${point.x.toFixed(1)} GPM @ ${point.y.toFixed(1)} ft (${(eff * 100).toFixed(1)}% eff.)`;
										}
									}
									return `${label}: ${point.x.toFixed(1)} GPM @ ${point.y.toFixed(1)} ft`;
								}
							}
						}
					},
					scales
				}
			});
		} catch (error) {
			console.error('Error creating pump curve chart:', error);
		}
	}

	// Effect for chart lifecycle - creates chart when canvas is available, destroys on cleanup
	$effect(() => {
		// Track dependencies - these variables ensure the effect re-runs when props change
		const currentCanvas = canvas;
		const currentCurve = curve;
		const currentDarkMode = $isDarkMode; // Track theme changes to re-render chart
		// eslint-disable-next-line @typescript-eslint/no-unused-vars
		const _trackResult = result; // Track result changes to trigger re-render
		// eslint-disable-next-line @typescript-eslint/no-unused-vars
		const _trackBep = bep; // Track BEP changes to trigger re-render

		if (currentCanvas && currentCurve?.points?.length > 0) {
			// Use setTimeout to ensure we're not in the middle of a render
			const timeoutId = setTimeout(() => {
				createChart(currentCanvas, currentDarkMode);
			}, 0);

			// Cleanup function
			return () => {
				clearTimeout(timeoutId);
				destroyChart();
			};
		}

		// Return cleanup if no canvas
		return () => {
			destroyChart();
		};
	});
</script>

<div class="relative h-64 w-full rounded-lg bg-[var(--color-surface)] p-2 sm:h-80">
	<canvas bind:this={canvas} class="w-full h-full" style="background: transparent;"></canvas>
</div>

<!-- BEP Info (shown when efficiency curve exists, even without solver results) -->
{#if bep}
	<div class="mt-4 rounded-lg border border-purple-500/30 bg-purple-500/10 p-3">
		<p class="text-xs font-medium uppercase tracking-wide text-purple-500">Best Efficiency Point (BEP)</p>
		<div class="mt-2 flex flex-wrap gap-4 text-sm text-[var(--color-text)]">
			<span><strong>Flow:</strong> {bep.flow.toFixed(1)} GPM</span>
			<span><strong>Head:</strong> {bep.head.toFixed(1)} ft</span>
			<span><strong>Efficiency:</strong> {(bep.efficiency * 100).toFixed(1)}%</span>
		</div>
	</div>
{/if}
