<!--
	Footer of the app pages (design §5): the README disclaimer, the copyright notice, and links to
	the privacy note, the license and the source code of this build (AGPL-3.0-or-later), and the
	third-party licenses.
-->
<script lang="ts">
	import { aboutHref, COPYRIGHT, DISCLAIMER, LICENSE_URL, NOTICES_URL, SOURCE_URL } from './links';
</script>

<footer class="space-y-1 border-t border-slate-200 pt-3 text-xs text-slate-600">
	<p>{DISCLAIMER}</p>
	<p>{COPYRIGHT}</p>
	<p class="flex flex-wrap gap-x-4">
		<a
			href={aboutHref()}
			class="inline-flex min-h-11 items-center text-blue-800 underline underline-offset-2"
			>About and privacy</a
		>
		<a
			href={LICENSE_URL}
			rel="external noopener noreferrer"
			class="inline-flex min-h-11 items-center text-blue-800 underline underline-offset-2"
			>License: AGPL-3.0-or-later</a
		>
		<a
			href={SOURCE_URL}
			rel="external noopener noreferrer"
			class="inline-flex min-h-11 items-center text-blue-800 underline underline-offset-2"
			>Source code</a
		>
		<a
			href={NOTICES_URL}
			rel="external"
			class="inline-flex min-h-11 items-center text-blue-800 underline underline-offset-2"
			>Third-party licenses</a
		>
	</p>
</footer>
