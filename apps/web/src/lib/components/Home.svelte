<!-- Home page: what the tool is, how to start, privacy, disclaimer and license. -->
<script lang="ts">
	import { EXAMPLES } from '$lib/utils/examples';
	import { encodeProject } from '$lib/utils/encoding';
	import Icon from './ui/Icon.svelte';
	import { DISCLAIMER, projectHref, SOURCE_URL } from './links';
	// Example links are stable: the examples have fixed ids and timestamps.
	const examples = EXAMPLES.map((e) => ({ ...e, href: projectHref(encodeProject(e.create())) }));
</script>

<main class="mx-auto max-w-3xl px-4 py-10 sm:py-14">
	<h1 class="text-3xl font-semibold sm:text-4xl">OpenSolve Pipe</h1>
	<p class="mt-3 text-lg text-slate-700">
		Free, browser-based steady-state hydraulic analysis of pressurized pipe networks: pumps, valves,
		fittings, branching and looped systems. No installation and no account.
	</p>

	<div class="mt-6 flex flex-wrap gap-3">
		<a href={projectHref()} class="btn btn-primary px-5 text-base">
			<Icon name="plus" /> New project
		</a>
		<a href="#examples" class="btn px-5 text-base">Open an example</a>
	</div>

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

	<section id="about" class="mt-12 scroll-mt-6 space-y-3" aria-labelledby="privacy-title">
		<h2 id="privacy-title" class="text-xl font-semibold">Your project lives in the link</h2>
		<p class="text-slate-700">
			The whole project is compressed into the page address, after the “#”. Browsers never send that
			part to a server, so your project is never stored on a server. There are no accounts,
			analytics or cookies. To keep a version, keep its link: every change makes a new link, and an
			old link still opens the project as it was.
		</p>
		<p class="text-slate-700">
			Solving sends the project to the calculation server, which works it out and sends back the
			results without storing or logging it. The project settings also ask the server for the
			calculated properties of the chosen fluid; that request names only the fluid, its temperature
			and concentration, and the server logs only its path, never those values.
		</p>
	</section>

	<section class="mt-12 space-y-3 border-t border-slate-200 pt-6 text-sm text-slate-600">
		<p>{DISCLAIMER}</p>
		<p>
			OpenSolve Pipe is free software, licensed under the GNU Affero General Public License v3.0 or
			later (AGPL-3.0-or-later). <a
				href={SOURCE_URL}
				rel="external noopener noreferrer"
				class="text-blue-800 underline underline-offset-2">Source code</a
			>.
		</p>
	</section>
</main>
