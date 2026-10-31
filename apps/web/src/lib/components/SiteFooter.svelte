<!--
	Footer of the app pages (design §5): the README disclaimer, the copyright notice, and links to
	the privacy note, the license, the source code of this build and of the calculation server
	(AGPL-3.0-or-later), and the third-party licenses.
-->
<script lang="ts">
	import {
		aboutHref,
		COPYRIGHT,
		DISCLAIMER,
		LICENSE_URL,
		NOTICES_URL,
		serverSourceHref,
		SOURCE_URL
	} from './links';

	const link =
		'inline-flex min-h-6 items-center text-slate-600 underline underline-offset-2 hover:text-blue-800 pointer-coarse:min-h-11';
</script>

<!--
	Kept small and quiet: it sits at the foot of the results pane, under the user's work. Links have
	short labels inside their full accessible names and tooltips (WCAG 2.5.3), and are 24 px tall
	for a mouse (WCAG 2.5.8) and 44 px on a touch screen (the app's targets).
-->
<footer class="space-y-1 border-t border-slate-200 pt-2 text-xs text-slate-500">
	<p>{DISCLAIMER}</p>
	<!-- The links stay together on one line: after the copyright where they fit, else all on the
		next line (build-density.md §13). -->
	<p class="flex flex-wrap items-center gap-x-1.5 tracking-tight">
		<span>{COPYRIGHT}</span>
		<!-- Below 360 px the five cannot share one line: only there do they wrap. -->
		<span class="flex flex-nowrap items-center gap-x-1.5 whitespace-nowrap max-[22.5rem]:flex-wrap">
			<a href={aboutHref()} class={link} aria-label="About and privacy" title="About and privacy"
				>About</a
			>
			<a
				href={LICENSE_URL}
				rel="external noopener noreferrer"
				class={link}
				aria-label="License: AGPL-3.0-or-later"
				title="License: AGPL-3.0-or-later">AGPL-3.0</a
			>
			<a
				href={SOURCE_URL}
				rel="external noopener noreferrer"
				class={link}
				aria-label="Source code"
				title="Source code of this app">Source</a
			>
			<a
				href={serverSourceHref()}
				rel="external noopener noreferrer"
				class={link}
				aria-label="Server source code"
				title="Source code of the calculation server">Server source</a
			>
			<a
				href={NOTICES_URL}
				rel="external"
				class={link}
				aria-label="Third-party licenses"
				title="Third-party licenses">Third-party</a
			>
		</span>
	</p>
</footer>
