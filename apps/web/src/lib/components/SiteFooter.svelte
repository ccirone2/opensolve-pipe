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
	Kept small and quiet: it sits at the foot of the results pane, under the user's work. The
	copyright and links share one wrapping row. Links are 24 px tall for a mouse (WCAG 2.5.8) and
	44 px on a touch screen (the app's targets).
-->
<footer class="space-y-1 border-t border-slate-200 pt-2 text-xs text-slate-500">
	<p>{DISCLAIMER}</p>
	<p class="flex flex-wrap items-center gap-x-3">
		<span>{COPYRIGHT}</span>
		<a href={aboutHref()} class={link}>About and privacy</a>
		<a href={LICENSE_URL} rel="external noopener noreferrer" class={link}
			>License: AGPL-3.0-or-later</a
		>
		<a href={SOURCE_URL} rel="external noopener noreferrer" class={link}>Source code</a>
		<a href={serverSourceHref()} rel="external noopener noreferrer" class={link}
			>Server source code</a
		>
		<a href={NOTICES_URL} rel="external" class={link}>Third-party licenses</a>
	</p>
</footer>
