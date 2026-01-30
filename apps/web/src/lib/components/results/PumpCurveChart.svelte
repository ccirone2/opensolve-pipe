<script lang="ts">
	import { Chart, registerables } from 'chart.js';
	import type { PumpCurve, PumpResult } from '$lib/models';
	import { calculateBEP } from '$lib/models/pump';
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
			const datasets: Chart['data']['datasets'] = [];

			// System curve - smooth line only, no points (drawn first/behind)
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
					pointHoverRadius: 0,
					borderWidth: 2,
					order: 3
				});
			}

			// Pump curve line (drawn behind points)
			datasets.push({
				label: 'Pump Curve',
				data: curve.points.map((p) => ({ x: p.flow, y: p.head })),
				borderColor: 'rgb(59, 130, 246)',
				backgroundColor: 'rgba(59, 130, 246, 0.1)',
				fill: false,
				showLine: true,
				tension: 0.4,
				pointRadius: 0,
				borderWidth: 2,
				order: 2
			});

			// Pump curve points (drawn on top of line)
			datasets.push({
				label: 'Pump Curve Points',
				data: curve.points.map((p) => ({ x: p.flow, y: p.head })),
				borderColor: 'rgb(59, 130, 246)',
				backgroundColor: 'rgb(59, 130, 246)',
				showLine: false,
				pointRadius: 5,
				pointHoverRadius: 7,
				order: 1
			});

			// Operating point
			if (result?.operating_flow !== undefined && result?.operating_head !== undefined) {
				datasets.push({
					label: 'Operating Point',
					data: [{ x: result.operating_flow, y: result.operating_head }],
					borderColor: 'rgb(34, 197, 94)',
					backgroundColor: 'rgb(34, 197, 94)',
					pointRadius: 8,
					pointHoverRadius: 10,
					showLine: false
				});
			}

			// Best Efficiency Point (BEP) - only if efficiency data exists
			if (bep) {
				datasets.push({
					label: 'BEP',
					data: [{ x: bep.flow, y: bep.head }],
					borderColor: 'rgb(168, 85, 247)',
					backgroundColor: 'rgb(168, 85, 247)',
					pointRadius: 8,
					pointHoverRadius: 10,
					pointStyle: 'star',
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

			const maxFlow = Math.max(...allFlows) * 1.1 || 100;
			const maxHead = Math.max(...allHeads) * 1.1 || 100;

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
								filter: (item) => item.text !== 'Pump Curve Points',
								color: colors.textColor
							}
						},
						tooltip: {
							callbacks: {
								label(context) {
									const point = context.raw as { x: number; y: number };
									const label = context.dataset.label === 'Pump Curve Points' ? 'Pump Curve' : context.dataset.label;
									if (label === 'BEP' && bep) {
										return `BEP: ${point.x.toFixed(1)} GPM @ ${point.y.toFixed(1)} ft (${(bep.efficiency * 100).toFixed(1)}% eff.)`;
									}
									return `${label}: ${point.x.toFixed(1)} GPM @ ${point.y.toFixed(1)} ft`;
								}
							}
						}
					},
					scales: {
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
					}
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

{#if result}
	<div class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
		<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-3">
			<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Flow</p>
			<p class="mt-1 text-lg font-semibold text-[var(--color-text)]">{result.operating_flow.toFixed(1)} GPM</p>
		</div>
		<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-3">
			<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Head</p>
			<p class="mt-1 text-lg font-semibold text-[var(--color-text)]">{result.operating_head.toFixed(1)} ft</p>
		</div>
		<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-3">
			<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">NPSH Available</p>
			<p class="mt-1 text-lg font-semibold text-[var(--color-text)]">{result.npsh_available.toFixed(1)} ft</p>
		</div>
		{#if result.efficiency !== undefined}
			<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-3">
				<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Efficiency</p>
				<p class="mt-1 text-lg font-semibold text-[var(--color-text)]">{(result.efficiency * 100).toFixed(1)}%</p>
			</div>
		{:else if result.power !== undefined}
			<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-3">
				<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Power</p>
				<p class="mt-1 text-lg font-semibold text-[var(--color-text)]">{result.power.toFixed(2)} kW</p>
			</div>
		{:else}
			<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-elevated)] p-3">
				<p class="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">NPSH Margin</p>
				<p class="mt-1 text-lg font-semibold text-[var(--color-text)]">
					{result.npsh_margin !== undefined ? `${result.npsh_margin.toFixed(1)} ft` : '-'}
				</p>
			</div>
		{/if}
	</div>
{/if}

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
