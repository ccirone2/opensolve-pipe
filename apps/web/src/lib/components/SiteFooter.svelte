<!--
	Footer of the app pages (design §5): the README disclaimer, and links to the privacy note, the
	license and the source code (AGPL-3.0-or-later).
-->
<script lang="ts">
	import { aboutHref, DISCLAIMER, LICENSE_URL, SOURCE_URL } from './links';
</script>

<footer class="space-y-1 border-t border-slate-200 pt-3 text-xs text-slate-600">
	<p>{DISCLAIMER}</p>
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
	</p>
</footer>
