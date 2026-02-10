<script lang="ts">
	import { goto } from '$app/navigation';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import { getExampleProjectUrl } from '$lib/data/exampleProject';
	import { createNewProject } from '$lib/models';
	import { encodeProject } from '$lib/utils';

	const exampleUrl = getExampleProjectUrl();

	function handleNewProject(event: MouseEvent) {
		event.preventDefault();
		const project = createNewProject();
		const result = encodeProject(project);
		goto(`/p/${result.encoded}`);
	}
</script>

<svelte:head>
	<title>OpenSolve Pipe - Free Hydraulic Network Analysis</title>
	<meta
		name="description"
		content="Free, browser-based hydraulic network design tool for steady-state pipe flow analysis. No installation required."
	/>
</svelte:head>

<div class="flex min-h-screen flex-col bg-[var(--color-bg)]">
	<!-- Minimal Header -->
	<header class="fixed left-0 right-0 top-0 z-50 border-b border-[var(--color-border)]/50 bg-[var(--color-bg)]/80 backdrop-blur-md">
		<div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
			<div class="flex items-center gap-2">
				<svg class="h-5 w-5 text-[var(--color-accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
				</svg>
				<span class="text-sm font-semibold text-[var(--color-text)]">OpenSolve Pipe</span>
			</div>
			<div class="flex items-center gap-4">
				<a
					href="https://github.com/ccirone2/opensolve-pipe"
					class="text-xs text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)]"
				>
					GitHub
				</a>
				<ThemeToggle />
			</div>
		</div>
	</header>

	<main id="main-content" class="flex-1 pt-16">
		<!-- Hero Section -->
		<div class="relative overflow-hidden">
			<!-- Background grid pattern -->
			<div class="canvas-grid absolute inset-0 opacity-40"></div>

			<div class="relative mx-auto max-w-6xl px-6 pb-20 pt-20 sm:pt-28">
				<div class="max-w-2xl">
					<!-- Badge -->
					<div class="mb-6 inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)]/80 px-3 py-1 text-xs backdrop-blur-sm">
						<span class="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]"></span>
						<span class="text-[var(--color-text-muted)]">Free &amp; open source</span>
					</div>

					<h1 class="text-4xl font-bold tracking-tight text-[var(--color-text)] sm:text-5xl">
						Hydraulic network
						<br />
						<span class="text-[var(--color-accent)]">analysis in your browser</span>
					</h1>

					<p class="mt-5 max-w-lg text-base leading-relaxed text-[var(--color-text-muted)]">
						Professional-grade steady-state pipe flow calculations. No installation, no account.
						Share designs with a URL.
					</p>

					<div class="mt-8 flex flex-wrap gap-3">
						<a
							href="/p/"
							onclick={handleNewProject}
							class="inline-flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-5 py-2.5 text-sm font-semibold text-[var(--color-accent-text)] shadow-lg shadow-[var(--color-accent)]/20 transition hover:bg-[var(--color-accent-hover)]"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
							</svg>
							New Project
						</a>
						<a
							href={exampleUrl}
							class="inline-flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-2.5 text-sm font-medium text-[var(--color-text)] transition hover:bg-[var(--color-surface-elevated)]"
						>
							<svg class="h-4 w-4 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
							</svg>
							Open Example
						</a>
					</div>

					<!-- Keyboard hint -->
					<p class="mt-4 text-xs text-[var(--color-text-subtle)]">
						Tip: Use <span class="kbd">Ctrl</span>+<span class="kbd">K</span> in the workspace to quickly add components
					</p>
				</div>

				<!-- Right side: Workspace preview graphic -->
				<div class="pointer-events-none absolute right-0 top-16 hidden w-[480px] lg:block">
					<div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl opacity-80">
						<!-- Fake toolbar -->
						<div class="flex items-center gap-2 border-b border-[var(--color-border)] px-3 py-2">
							<div class="flex gap-1">
								<div class="h-2 w-2 rounded-full bg-[var(--color-error)]/50"></div>
								<div class="h-2 w-2 rounded-full bg-[var(--color-warning)]/50"></div>
								<div class="h-2 w-2 rounded-full bg-[var(--color-success)]/50"></div>
							</div>
							<div class="flex-1 rounded bg-[var(--color-surface-elevated)] px-2 py-0.5 text-center text-[0.5rem] text-[var(--color-text-subtle)]">
								Pump Station Design
							</div>
						</div>
						<!-- Fake workspace -->
						<div class="flex" style="height: 280px;">
							<!-- Fake sidebar -->
							<div class="w-32 border-r border-[var(--color-border)] p-2">
								<div class="mb-1 text-[0.5rem] font-semibold uppercase text-[var(--color-text-subtle)]">Components</div>
								{#each ['RSV Reservoir', 'PMP Main Pump', 'VLV Check Valve', 'JCT Branch Tee', 'SPK Sprinkler 1'] as item, i}
									<div class="mb-0.5 flex items-center gap-1 rounded px-1.5 py-0.5 text-[0.45rem] {i === 1 ? 'bg-[var(--color-tree-selected)] text-[var(--color-text)]' : 'text-[var(--color-text-muted)]'}">
										<span class="rounded bg-[var(--color-surface-elevated)] px-0.5 font-[var(--font-mono)] text-[0.4rem]">{item.split(' ')[0]}</span>
										<span class="truncate">{item.split(' ').slice(1).join(' ')}</span>
									</div>
								{/each}
							</div>
							<!-- Fake canvas -->
							<div class="flex-1 canvas-grid p-4">
								<svg class="h-full w-full" viewBox="0 0 300 240">
									<!-- Simple schematic -->
									<rect x="20" y="80" width="40" height="50" rx="4" fill="var(--color-badge-source)" stroke="var(--color-badge-source-text)" stroke-width="1" opacity="0.8" />
									<text x="40" y="108" text-anchor="middle" font-size="8" fill="var(--color-badge-source-text)">RSV</text>
									<line x1="60" y1="105" x2="95" y2="105" stroke="var(--color-text-subtle)" stroke-width="1.5" />
									<circle cx="115" cy="105" r="18" fill="var(--color-badge-equipment)" stroke="var(--color-badge-equipment-text)" stroke-width="1" opacity="0.8" />
									<text x="115" y="108" text-anchor="middle" font-size="7" fill="var(--color-badge-equipment-text)">PMP</text>
									<line x1="133" y1="105" x2="170" y2="105" stroke="var(--color-text-subtle)" stroke-width="1.5" />
									<polygon points="180,92 195,105 180,118" fill="var(--color-badge-equipment)" stroke="var(--color-badge-equipment-text)" stroke-width="1" opacity="0.8" />
									<text x="185" y="108" text-anchor="middle" font-size="6" fill="var(--color-badge-equipment-text)">CV</text>
									<line x1="195" y1="105" x2="240" y2="105" stroke="var(--color-text-subtle)" stroke-width="1.5" />
									<line x1="240" y1="105" x2="240" y2="60" stroke="var(--color-text-subtle)" stroke-width="1.5" stroke-dasharray="3,2" />
									<line x1="240" y1="105" x2="240" y2="160" stroke="var(--color-text-subtle)" stroke-width="1.5" stroke-dasharray="3,2" />
									<circle cx="240" cy="105" r="5" fill="var(--color-badge-connection)" stroke="var(--color-badge-connection-text)" stroke-width="1" opacity="0.8" />
									<circle cx="270" cy="60" r="8" fill="var(--color-surface-elevated)" stroke="var(--color-text-subtle)" stroke-width="1" />
									<text x="270" y="63" text-anchor="middle" font-size="5" fill="var(--color-text-subtle)">SPK</text>
									<line x1="240" y1="60" x2="262" y2="60" stroke="var(--color-text-subtle)" stroke-width="1" />
									<circle cx="270" cy="160" r="8" fill="var(--color-surface-elevated)" stroke="var(--color-text-subtle)" stroke-width="1" />
									<text x="270" y="163" text-anchor="middle" font-size="5" fill="var(--color-text-subtle)">SPK</text>
									<line x1="240" y1="160" x2="262" y2="160" stroke="var(--color-text-subtle)" stroke-width="1" />
								</svg>
							</div>
						</div>
						<!-- Fake statusbar -->
						<div class="flex items-center justify-between border-t border-[var(--color-border)] px-3 py-1 text-[0.45rem] text-[var(--color-text-subtle)]">
							<span class="flex items-center gap-1">
								<span class="h-1.5 w-1.5 rounded-full bg-[var(--color-success)]"></span>
								Converged (42ms)
							</span>
							<span>5 components</span>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Features Section -->
		<div class="border-t border-[var(--color-border)]">
			<div class="mx-auto max-w-6xl px-6 py-16">
				<h2 class="text-center text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
					Why OpenSolve Pipe
				</h2>

				<div class="mt-10 grid gap-8 md:grid-cols-3">
					<!-- Feature 1 -->
					<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
						<div class="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-[var(--color-accent-muted)]">
							<svg class="h-5 w-5 text-[var(--color-accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
							</svg>
						</div>
						<h3 class="text-sm font-semibold text-[var(--color-text)]">Fast Solver</h3>
						<p class="mt-1.5 text-xs leading-relaxed text-[var(--color-text-muted)]">
							Darcy-Weisbach with Colebrook iteration. EPANET-backed solver for complex looped networks. Results in under a second.
						</p>
					</div>

					<!-- Feature 2 -->
					<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
						<div class="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-[var(--color-badge-source)]">
							<svg class="h-5 w-5 text-[var(--color-badge-source-text)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
							</svg>
						</div>
						<h3 class="text-sm font-semibold text-[var(--color-text)]">URL-Encoded State</h3>
						<p class="mt-1.5 text-xs leading-relaxed text-[var(--color-text-muted)]">
							Every project state lives in the URL. Share designs with a link. No account, no database, no file transfers.
						</p>
					</div>

					<!-- Feature 3 -->
					<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
						<div class="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-[var(--color-badge-connection)]">
							<svg class="h-5 w-5 text-[var(--color-badge-connection-text)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0V12a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 12V5.25" />
							</svg>
						</div>
						<h3 class="text-sm font-semibold text-[var(--color-text)]">Engineering Workspace</h3>
						<p class="mt-1.5 text-xs leading-relaxed text-[var(--color-text-muted)]">
							IDE-like interface with live schematic, component tree, and inline results. Works on desktop and mobile.
						</p>
					</div>
				</div>
			</div>
		</div>

		<!-- How It Works -->
		<div class="border-t border-[var(--color-border)] bg-[var(--color-surface)]">
			<div class="mx-auto max-w-6xl px-6 py-16">
				<h2 class="text-center text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
					How It Works
				</h2>

				<div class="mt-10 grid gap-6 md:grid-cols-4">
					{#each [
						{ step: '1', title: 'Define System', desc: 'Add reservoirs, pumps, valves, and pipes' },
						{ step: '2', title: 'Configure', desc: 'Set fluid properties, pipe materials, pump curves' },
						{ step: '3', title: 'Solve', desc: 'Calculate flows, pressures, and head losses' },
						{ step: '4', title: 'Share', desc: 'Copy the URL to share your design' }
					] as item}
						<div class="text-center">
							<div class="mx-auto mb-3 flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-accent-muted)] font-[var(--font-mono)] text-sm font-bold text-[var(--color-accent)]">
								{item.step}
							</div>
							<h3 class="text-sm font-semibold text-[var(--color-text)]">{item.title}</h3>
							<p class="mt-1 text-xs text-[var(--color-text-muted)]">{item.desc}</p>
						</div>
					{/each}
				</div>
			</div>
		</div>

		<!-- Component Types -->
		<div class="border-t border-[var(--color-border)]">
			<div class="mx-auto max-w-6xl px-6 py-16">
				<h2 class="text-center text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
					Supported Components
				</h2>

				<div class="mt-8 flex flex-wrap justify-center gap-2">
					{#each [
						{ label: 'Reservoir', badge: 'SRC', color: 'source' },
						{ label: 'Tank', badge: 'SRC', color: 'source' },
						{ label: 'Pump', badge: 'EQP', color: 'equipment' },
						{ label: 'Gate Valve', badge: 'EQP', color: 'equipment' },
						{ label: 'Check Valve', badge: 'EQP', color: 'equipment' },
						{ label: 'PRV', badge: 'EQP', color: 'equipment' },
						{ label: 'Heat Exchanger', badge: 'EQP', color: 'equipment' },
						{ label: 'Strainer', badge: 'EQP', color: 'equipment' },
						{ label: 'Orifice', badge: 'EQP', color: 'equipment' },
						{ label: 'Sprinkler', badge: 'EQP', color: 'equipment' },
						{ label: 'Tee Branch', badge: 'CON', color: 'connection' },
						{ label: 'Wye Branch', badge: 'CON', color: 'connection' },
						{ label: 'Junction', badge: 'CON', color: 'connection' }
					] as item}
						<span
							class="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs text-[var(--color-text)]"
						>
							<span
								class="rounded px-1 py-0.5 font-[var(--font-mono)] text-[0.5rem] font-semibold
									{item.color === 'source'
									? 'bg-[var(--color-badge-source)] text-[var(--color-badge-source-text)]'
									: item.color === 'equipment'
										? 'bg-[var(--color-badge-equipment)] text-[var(--color-badge-equipment-text)]'
										: 'bg-[var(--color-badge-connection)] text-[var(--color-badge-connection-text)]'}"
							>
								{item.badge}
							</span>
							{item.label}
						</span>
					{/each}
				</div>
			</div>
		</div>
	</main>

	<!-- Footer -->
	<footer class="border-t border-[var(--color-border)] bg-[var(--color-surface)]">
		<div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
			<p class="text-xs text-[var(--color-text-subtle)]">
				OpenSolve Pipe - Free hydraulic analysis
			</p>
			<a
				href="https://github.com/ccirone2/opensolve-pipe"
				class="text-xs text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-accent)]"
			>
				View on GitHub
			</a>
		</div>
	</footer>
</div>
