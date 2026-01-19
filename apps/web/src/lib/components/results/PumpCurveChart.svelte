<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { PumpCurve, PumpResult } from '$lib/models';

	// Register Chart.js components
	Chart.register(...registerables);

	interface Props {
		/** The pump curve data. */
		curve: PumpCurve;
		/** The pump result with operating point and system curve. */
		result?: PumpResult;
	}

	let { curve, result }: Props = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// Reactive chart data
	let chartData = $derived.by(() => {
		const datasets: Chart['data']['datasets'] = [];

		// Pump curve
		datasets.push({
			label: 'Pump Curve',
			data: curve.points.map((p) => ({ x: p.flow, y: p.head })),
			borderColor: 'rgb(59, 130, 246)',
			backgroundColor: 'rgba(59, 130, 246, 0.1)',
			fill: false,
			tension: 0.4,
			pointRadius: 3,
			pointHoverRadius: 5
		});

		// System curve
		if (result?.system_curve && result.system_curve.length > 0) {
			datasets.push({
				label: 'System Curve',
				data: result.system_curve.map((p) => ({ x: p.flow, y: p.head })),
				borderColor: 'rgb(239, 68, 68)',
				backgroundColor: 'rgba(239, 68, 68, 0.1)',
				fill: false,
				tension: 0.4,
				pointRadius: 0,
				borderDash: [5, 5]
			});
		}

		// Operating point
		if (result) {
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

		return { datasets };
	});

	function createChart() {
		if (!canvas) return;

		// Destroy existing chart
		if (chart) {
			chart.destroy();
			chart = null;
		}

		// Calculate axis ranges
		const allFlows = curve.points.map((p) => p.flow);
		const allHeads = curve.points.map((p) => p.head);

		if (result?.system_curve) {
			allFlows.push(...result.system_curve.map((p) => p.flow));
			allHeads.push(...result.system_curve.map((p) => p.head));
		}

		if (result) {
			allFlows.push(result.operating_flow);
			allHeads.push(result.operating_head);
		}

		const maxFlow = Math.max(...allFlows) * 1.1;
		const maxHead = Math.max(...allHeads) * 1.1;

		chart = new Chart(canvas, {
			type: 'scatter',
			data: chartData,
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
							padding: 16
						}
					},
					tooltip: {
						callbacks: {
							label(context) {
								const point = context.raw as { x: number; y: number };
								return `${context.dataset.label}: ${point.x.toFixed(1)} GPM @ ${point.y.toFixed(1)} ft`;
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
							font: { weight: 'bold' }
						},
						grid: {
							color: 'rgba(0, 0, 0, 0.05)'
						}
					},
					y: {
						type: 'linear',
						min: 0,
						max: maxHead,
						title: {
							display: true,
							text: 'Head (ft)',
							font: { weight: 'bold' }
						},
						grid: {
							color: 'rgba(0, 0, 0, 0.05)'
						}
					}
				}
			}
		});
	}

	// Update chart when data changes
	$effect(() => {
		// Access reactive dependencies to trigger effect
		void chartData;
		void curve;
		void result;

		// Recreate chart
		if (canvas) {
			createChart();
		}
	});

	onMount(() => {
		createChart();
	});

	onDestroy(() => {
		if (chart) {
			chart.destroy();
		}
	});
</script>

<div class="relative h-64 w-full sm:h-80">
	<canvas bind:this={canvas}></canvas>
</div>

{#if result}
	<div class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
		<div class="rounded-lg bg-gray-50 p-3">
			<p class="text-xs font-medium uppercase tracking-wide text-gray-500">Flow</p>
			<p class="mt-1 text-lg font-semibold text-gray-900">{result.operating_flow.toFixed(1)} GPM</p>
		</div>
		<div class="rounded-lg bg-gray-50 p-3">
			<p class="text-xs font-medium uppercase tracking-wide text-gray-500">Head</p>
			<p class="mt-1 text-lg font-semibold text-gray-900">{result.operating_head.toFixed(1)} ft</p>
		</div>
		<div class="rounded-lg bg-gray-50 p-3">
			<p class="text-xs font-medium uppercase tracking-wide text-gray-500">NPSH Available</p>
			<p class="mt-1 text-lg font-semibold text-gray-900">{result.npsh_available.toFixed(1)} ft</p>
		</div>
		{#if result.efficiency !== undefined}
			<div class="rounded-lg bg-gray-50 p-3">
				<p class="text-xs font-medium uppercase tracking-wide text-gray-500">Efficiency</p>
				<p class="mt-1 text-lg font-semibold text-gray-900">{(result.efficiency * 100).toFixed(1)}%</p>
			</div>
		{:else if result.power !== undefined}
			<div class="rounded-lg bg-gray-50 p-3">
				<p class="text-xs font-medium uppercase tracking-wide text-gray-500">Power</p>
				<p class="mt-1 text-lg font-semibold text-gray-900">{result.power.toFixed(2)} kW</p>
			</div>
		{:else}
			<div class="rounded-lg bg-gray-50 p-3">
				<p class="text-xs font-medium uppercase tracking-wide text-gray-500">NPSH Margin</p>
				<p class="mt-1 text-lg font-semibold text-gray-900">
					{result.npsh_margin !== undefined ? `${result.npsh_margin.toFixed(1)} ft` : '-'}
				</p>
			</div>
		{/if}
	</div>
{/if}
