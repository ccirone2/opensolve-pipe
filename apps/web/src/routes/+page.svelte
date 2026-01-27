<script lang="ts">
	import Header from '$lib/components/Header.svelte';
	import { getExampleProjectUrl } from '$lib/data/exampleProject';

	const exampleUrl = getExampleProjectUrl();
</script>

<svelte:head>
	<title>OpenSolve Pipe - Free Hydraulic Network Analysis</title>
	<meta
		name="description"
		content="Free, browser-based hydraulic network design tool for steady-state pipe flow analysis. No installation required."
	/>
</svelte:head>

<div class="flex min-h-screen flex-col bg-[var(--color-bg)]">
	<Header />

	<main id="main-content" class="flex-1">
		<!-- Hero Section -->
		<div class="bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-hover)] py-16 text-[var(--color-accent-text)]">
			<div class="mx-auto max-w-4xl px-4 text-center">
				<h1 class="mb-4 text-4xl font-bold sm:text-5xl">Hydraulic Network Analysis</h1>
				<p class="mb-8 text-lg opacity-90 sm:text-xl">
					Free, browser-based tool for steady-state pipe flow calculations. No installation, no
					account required.
				</p>
				<div class="flex flex-col justify-center gap-4 sm:flex-row">
					<a
						href="/p/"
						class="inline-flex items-center justify-center rounded-lg bg-[var(--color-surface)] px-6 py-3 font-semibold text-[var(--color-accent)] shadow-lg transition hover:opacity-90"
					>
						<svg class="mr-2 h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M12 6v6m0 0v6m0-6h6m-6 0H6"
							/>
						</svg>
						New Project
					</a>
					<a
						href={exampleUrl}
						class="inline-flex items-center justify-center rounded-lg border-2 border-current/30 px-6 py-3 font-semibold transition hover:bg-white/10"
					>
						<svg class="mr-2 h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
							/>
						</svg>
						Open Example
					</a>
				</div>
			</div>
		</div>

		<!-- Features Section -->
		<div class="mx-auto max-w-4xl px-4 py-12">
			<h2 class="mb-8 text-center text-2xl font-bold text-[var(--color-text)]">Key Features</h2>

			<div class="grid gap-6 md:grid-cols-3">
				<!-- Feature 1 -->
				<div class="rounded-lg bg-[var(--color-surface)] p-6 shadow">
					<div class="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-accent-muted)]">
						<svg class="h-6 w-6 text-[var(--color-accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M13 10V3L4 14h7v7l9-11h-7z"
							/>
						</svg>
					</div>
					<h3 class="mb-2 text-lg font-semibold text-[var(--color-text)]">Instant Results</h3>
					<p class="text-[var(--color-text-muted)]">
						Solve pump-pipe systems in seconds. Find operating points, velocities, and head losses.
					</p>
				</div>

				<!-- Feature 2 -->
				<div class="rounded-lg bg-[var(--color-surface)] p-6 shadow">
					<div class="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[rgba(34,197,94,0.15)]">
						<svg
							class="h-6 w-6 text-[var(--color-success)]"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"
							/>
						</svg>
					</div>
					<h3 class="mb-2 text-lg font-semibold text-[var(--color-text)]">Shareable via URL</h3>
					<p class="text-[var(--color-text-muted)]">
						Projects are encoded in the URL. Share designs with a simple link, no account needed.
					</p>
				</div>

				<!-- Feature 3 -->
				<div class="rounded-lg bg-[var(--color-surface)] p-6 shadow">
					<div class="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[rgba(168,85,247,0.15)]">
						<svg
							class="h-6 w-6 text-purple-500"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"
							/>
						</svg>
					</div>
					<h3 class="mb-2 text-lg font-semibold text-[var(--color-text)]">Mobile-Friendly</h3>
					<p class="text-[var(--color-text-muted)]">
						Panel navigator works great on mobile. Do hydraulic calcs in the field.
					</p>
				</div>
			</div>
		</div>

		<!-- Quick Start Section -->
		<div class="bg-[var(--color-surface-elevated)] py-12">
			<div class="mx-auto max-w-4xl px-4">
				<h2 class="mb-8 text-center text-2xl font-bold text-[var(--color-text)]">How It Works</h2>

				<div class="grid gap-4 md:grid-cols-4">
					<div class="text-center">
						<div
							class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-accent)] font-bold text-[var(--color-accent-text)]"
						>
							1
						</div>
						<h3 class="font-semibold text-[var(--color-text)]">Define System</h3>
						<p class="text-sm text-[var(--color-text-muted)]">Add components like pipes, pumps, and fittings</p>
					</div>
					<div class="text-center">
						<div
							class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-accent)] font-bold text-[var(--color-accent-text)]"
						>
							2
						</div>
						<h3 class="font-semibold text-[var(--color-text)]">Select Fluid</h3>
						<p class="text-sm text-[var(--color-text-muted)]">Water, glycols, fuels, or custom fluids</p>
					</div>
					<div class="text-center">
						<div
							class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-accent)] font-bold text-[var(--color-accent-text)]"
						>
							3
						</div>
						<h3 class="font-semibold text-[var(--color-text)]">Solve</h3>
						<p class="text-sm text-[var(--color-text-muted)]">Calculate flows, pressures, and head losses</p>
					</div>
					<div class="text-center">
						<div
							class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-accent)] font-bold text-[var(--color-accent-text)]"
						>
							4
						</div>
						<h3 class="font-semibold text-[var(--color-text)]">Share</h3>
						<p class="text-sm text-[var(--color-text-muted)]">Copy URL to share your design with others</p>
					</div>
				</div>
			</div>
		</div>
	</main>

	<!-- Footer -->
	<footer class="border-t border-[var(--color-border)] bg-[var(--color-surface)] py-6">
		<div class="mx-auto max-w-4xl px-4 text-center text-sm text-[var(--color-text-muted)]">
			<p>
				OpenSolve Pipe - Free hydraulic analysis tool.
				<a
					href="https://github.com/ccirone2/opensolve-pipe"
					class="text-[var(--color-accent)] hover:underline"
				>
					View on GitHub
				</a>
			</p>
		</div>
	</footer>
</div>
