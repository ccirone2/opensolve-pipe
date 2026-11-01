<!--
	The landing page (proposal landing-page.md): what the tool is and how to start, for someone
	arriving for the first time and for someone coming back. The start comes first (New project, the
	examples, recent projects on this device), How it works (the workflow in screenshots), then what it models, how its results are checked, its
	scope and limits, privacy, and the disclaimer and license. Plain and technical, no figures that
	could drift from the code (the owner's answers of 2026-11-01).
-->
<script lang="ts">
	import { EXAMPLES } from '$lib/utils/examples';
	import { encodeProject } from '$lib/utils/encoding';
	import RecentProjects from './RecentProjects.svelte';
	import ScreenshotCarousel from './ScreenshotCarousel.svelte';
	import Icon from './ui/Icon.svelte';
	import {
		COPYRIGHT,
		DISCLAIMER,
		NOTICES_URL,
		projectHref,
		serverSourceHref,
		SOURCE_URL
	} from './links';
	// Example links are stable: the examples have fixed ids and timestamps.
	const examples = EXAMPLES.map((e) => ({ ...e, href: projectHref(encodeProject(e.create())) }));

	/** What it models (D5's v1 scope, in an engineer's words). */
	const models: { title: string; text: string }[] = [
		{
			title: 'Networks',
			text: 'Branching and looped networks, open and closed systems, fed by gravity, by a pressurized source or by pumps in series and in parallel.'
		},
		{
			title: 'Boundaries',
			text: 'Reservoirs, reference nodes (a fixed pressure, such as an expansion tank connection) and assigned-flow nodes (a fixed demand or supply).'
		},
		{
			title: 'Pipes and fittings',
			text: 'Pipe sizes from cited tables or your own dimensions; elbows, bends, reducers, entrances, exits and inline valves, and tees and wyes, with losses from cited correlations (Crane TP-410).'
		},
		{
			title: 'Pumps',
			text: 'Fixed-speed pumps from their curves, speed-controlled pumps holding a flow, and pumps run together as a station, with NPSH available and margin.'
		},
		{
			title: 'Valves',
			text: 'Gate, ball, butterfly and globe valves, check valves, pressure-reducing, pressure-sustaining and flow-control valves, and pressure relief valves in liquid service (API 520 and 526).'
		},
		{
			title: 'Orifice plates and equipment',
			text: 'Square-edged orifice plates (ISO 5167-2) as restrictions or flow meters, and heat exchangers, coils, strainers and filters rated by a pressure drop at a flow or by a Cv or Kv.'
		},
		{
			title: 'Fluids',
			text: 'Water, ethylene and propylene glycol solutions, and fluids you define.'
		},
		{
			title: 'Analysis',
			text: 'Pump and system curves, scenarios solved and compared side by side, goal seek, opt-in design checks, a project library of pipe specs and loss coefficients with their sources, and export to a workbook, CSV files or chart images.'
		}
	];

	/** How the results are checked (D1, D6, D8, D10, D13; GOALS §4.2–§4.3). */
	const checks: { title: string; text: string }[] = [
		{
			title: 'Its own solver, one method',
			text: 'The global gradient algorithm (Todini and Pilati) with Darcy–Weisbach friction and the Colebrook equation, the same for every network.'
		},
		{
			title: 'A reference suite',
			text: 'Benchmark cases from hand calculations, Crane TP-410 and textbook worked examples, and EPANET 2.2 runs, written from the cited sources by someone who did not read the solver’s code. Every change to the solver or to a loss coefficient must keep the whole suite passing.'
		},
		{
			title: 'Compared with EPANET',
			text: 'Randomly generated networks are solved by both, so a difference outside the benchmark cases is found too.'
		},
		{
			title: 'Cited data only',
			text: 'Fluid properties from CoolProp, pipe dimensions and roughness from the fluids library, and every loss coefficient from a named source; a value you enter is labelled as yours. No number is typed from memory.'
		},
		{
			title: 'Every result shows its working',
			text: 'Each element’s inputs with their sources, the equations and correlations, the data used and why a pump or valve is in the state it is; each solve has a summary of methods and assumptions, and a value left at its default is labelled “default”.'
		},
		{
			title: 'Versioned methods',
			text: 'Each solve records the calculation methods it used, and any change that can alter a result is recorded in a changelog.'
		}
	];

	/** What it does not do (PRD §2.2; D14). */
	const limits = [
		'Steady state only: no water hammer or other transients.',
		'Single-phase liquids: no gases, steam, two-phase flow or slurries.',
		'Isothermal: one temperature throughout, no heat transfer along the network.',
		'Pressurized pipes only: no open channels.',
		'Not yet a stable release: the methods, the link format and the API may still change, and a link made today may not open, or may solve differently, after a change. Export the results you rely on.'
	];

	const link = 'text-blue-800 underline underline-offset-2';
</script>

<main class="mx-auto max-w-5xl px-4 py-10 sm:py-14">
	<div class="max-w-3xl">
		<h1 class="text-3xl font-semibold sm:text-4xl">OpenSolve Pipe</h1>
		<p class="mt-3 text-lg text-slate-800 sm:text-xl">
			Steady-state hydraulic analysis of pressurized pipe networks, in your browser.
		</p>
		<p class="mt-2 text-slate-700">
			Pumps, valves, fittings, branching and looped systems, with every result traced to its
			equations and sources. No installation and no account.
		</p>

		<div class="mt-6 flex flex-wrap gap-3">
			<a href={projectHref()} class="btn btn-primary px-5 text-base">
				<Icon name="plus" /> New project
			</a>
			<a href="#examples" class="btn px-5 text-base">Open an example</a>
		</div>

		<RecentProjects />
	</div>

	<ScreenshotCarousel />

	<section id="examples" class="mt-12 scroll-mt-6" aria-labelledby="examples-title">
		<h2 id="examples-title" class="text-xl font-semibold">Examples</h2>
		<p class="mt-1 text-sm text-slate-600">
			Illustrative projects: the dimensions and pump curves are made up to show the tool, not taken
			from a real installation.
		</p>
		<ul class="mt-4 grid gap-3 sm:grid-cols-3">
			{#each examples as example (example.slug)}
				<li>
					<a
						href={example.href}
						class="card flex h-full flex-col gap-1 p-4 hover:border-blue-400 hover:bg-blue-50"
					>
						<span class="font-medium text-blue-800">{example.title}</span>
						<span class="text-sm text-slate-600">{example.summary}</span>
					</a>
				</li>
			{/each}
		</ul>
	</section>

	<section class="mt-12" aria-labelledby="models-title">
		<h2 id="models-title" class="text-xl font-semibold">What it models</h2>
		<dl class="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
			{#each models as item (item.title)}
				<div>
					<dt class="font-medium">{item.title}</dt>
					<dd class="mt-0.5 text-slate-700">{item.text}</dd>
				</div>
			{/each}
		</dl>
	</section>

	<section class="mt-12" aria-labelledby="checks-title">
		<h2 id="checks-title" class="text-xl font-semibold">How the results are checked</h2>
		<dl class="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
			{#each checks as item (item.title)}
				<div>
					<dt class="font-medium">{item.title}</dt>
					<dd class="mt-0.5 text-slate-700">{item.text}</dd>
				</div>
			{/each}
		</dl>
	</section>

	<section class="mt-12 max-w-3xl" aria-labelledby="limits-title">
		<h2 id="limits-title" class="text-xl font-semibold">Scope and limits</h2>
		<ul class="mt-3 list-disc space-y-1.5 pl-5 text-slate-700">
			{#each limits as item (item)}<li>{item}</li>{/each}
		</ul>
	</section>

	<section id="about" class="mt-12 max-w-3xl scroll-mt-6" aria-labelledby="privacy-title">
		<h2 id="privacy-title" class="text-xl font-semibold">Your project lives in the link</h2>
		<p class="mt-3 text-slate-700">
			The whole project is compressed into the page address, after the “#”, which browsers never
			send to a server, so your project is never stored on a server. There are no accounts,
			analytics or cookies. To keep a version, keep its link.
		</p>
		<details class="mt-3">
			<summary class="cursor-pointer font-medium text-blue-800">Details</summary>
			<div class="mt-2 space-y-3 text-slate-700">
				<p>
					Every change makes a new link, and an old link still opens the project as it was. Recent
					projects are remembered in this browser only: the links of the projects you opened or
					changed here, listed on this page. They are never sent anywhere, and Forget all removes
					them.
				</p>
				<p>
					Solving sends the project to the calculation server, and so does showing a pump's system
					curve. The server works out the results and sends them back without storing the project or
					writing it to its logs. To show the calculated properties of the chosen fluid, the fluid
					settings send the fluid (its type, temperature and concentration) the same way. All of
					this travels in the body of each request, never in the address it is sent to. The server's
					log keeps neither project data nor your IP address: for each request, only its method,
					path, HTTP version and status, and for a request the server fails on, the kind of failure.
				</p>
			</div>
		</details>
	</section>

	<section class="mt-12 max-w-3xl space-y-3 border-t border-slate-200 pt-6 text-sm text-slate-600">
		<p>{DISCLAIMER}</p>
		<p>
			{COPYRIGHT}. OpenSolve Pipe is free software, licensed under the GNU Affero General Public
			License v3.0 or later (AGPL-3.0-or-later).
			<a href={SOURCE_URL} rel="external noopener noreferrer" class={link}>Source code</a>
			of this version, and the
			<a href={serverSourceHref()} rel="external noopener noreferrer" class={link}
				>calculation server's source code</a
			>. It includes open source packages under their own licenses:
			<a href={NOTICES_URL} rel="external" class={link}>third-party licenses</a>.
		</p>
	</section>
</main>
