<!--
	Small line icons (24×24, stroke = currentColor). Decorative: buttons carry their own text or
	aria-label.
-->
<script lang="ts" module>
	export type IconName =
		| 'undo'
		| 'redo'
		| 'play'
		| 'share'
		| 'settings'
		| 'left'
		| 'right'
		| 'plus'
		| 'close'
		| 'trash'
		| 'list'
		| 'alert'
		| 'check'
		| 'home'
		| 'branch'
		| 'insert'
		| 'copy'
		| 'flag'
		| 'info'
		| 'down'
		| 'external'
		| 'spinner'
		| 'layers'
		| 'lock'
		| 'target'
		| 'download'
		| 'droplet'
		| 'up';
</script>

<script lang="ts">
	import type { ClassValue } from 'svelte/elements';

	let { name, class: className = 'size-5' }: { name: IconName; class?: ClassValue } = $props();
</script>

<svg
	class={className}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="2"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
	focusable="false"
>
	{#if name === 'undo'}
		<path d="M9 14 4 9l5-5" />
		<path d="M4 9h10a6 6 0 0 1 0 12h-3" />
	{:else if name === 'redo'}
		<path d="m15 14 5-5-5-5" />
		<path d="M20 9H10a6 6 0 0 0 0 12h3" />
	{:else if name === 'play'}
		<path d="M7 4v16l13-8z" />
	{:else if name === 'share'}
		<path d="M12 3v12" />
		<path d="m7 8 5-5 5 5" />
		<path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" />
	{:else if name === 'settings'}
		<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1" />
		<circle cx="15" cy="6" r="2" />
		<circle cx="9" cy="12" r="2" />
		<circle cx="17" cy="18" r="2" />
	{:else if name === 'left'}
		<path d="m15 18-6-6 6-6" />
	{:else if name === 'right'}
		<path d="m9 18 6-6-6-6" />
	{:else if name === 'plus'}
		<path d="M12 5v14M5 12h14" />
	{:else if name === 'close'}
		<path d="M6 6l12 12M18 6 6 18" />
	{:else if name === 'trash'}
		<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
	{:else if name === 'list'}
		<path d="M9 6h11M9 12h11M9 18h11" />
		<path d="M4 6h.01M4 12h.01M4 18h.01" />
	{:else if name === 'alert'}
		<path d="M12 3 2 20h20z" />
		<path d="M12 10v4M12 17h.01" />
	{:else if name === 'check'}
		<path d="m5 12 5 5 9-10" />
	{:else if name === 'home'}
		<path d="m3 11 9-8 9 8" />
		<path d="M5 10v10h14V10" />
	{:else if name === 'branch'}
		<path d="M4 12h16M12 12v8" />
		<path d="m17 9 3 3-3 3" />
	{:else if name === 'insert'}
		<path d="M3 12h4M17 12h4" />
		<rect x="7" y="8" width="10" height="8" rx="1" />
	{:else if name === 'copy'}
		<rect x="9" y="9" width="11" height="11" rx="2" />
		<path d="M5 15V5a2 2 0 0 1 2-2h8" />
	{:else if name === 'flag'}
		<path d="M5 21V4M5 4h11l-2 4 2 4H5" />
	{:else if name === 'info'}
		<circle cx="12" cy="12" r="9" />
		<path d="M12 11v5M12 8h.01" />
	{:else if name === 'down'}
		<path d="m6 9 6 6 6-6" />
	{:else if name === 'external'}
		<path d="M14 4h6v6M20 4l-9 9" />
		<path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
	{:else if name === 'layers'}
		<path d="m12 3 9 5-9 5-9-5z" />
		<path d="m3 13 9 5 9-5" />
	{:else if name === 'lock'}
		<rect x="5" y="11" width="14" height="10" rx="2" />
		<path d="M8 11V7a4 4 0 0 1 8 0v4" />
	{:else if name === 'droplet'}
		<!-- A drop of liquid: the project fluid. -->
		<path d="M12 3c3.5 4.2 6 7.6 6 10.5a6 6 0 0 1-12 0C6 10.6 8.5 7.2 12 3z" />
	{:else if name === 'target'}
		<!-- A crosshair: goal seek. -->
		<circle cx="12" cy="12" r="8" />
		<circle cx="12" cy="12" r="3" />
		<path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
	{:else if name === 'download'}
		<!-- An arrow down into a tray: export a file. -->
		<path d="M12 3v12" />
		<path d="m7 10 5 5 5-5" />
		<path d="M5 15v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />
	{:else if name === 'up'}
		<path d="m6 15 6-6 6 6" />
	{:else if name === 'spinner'}
		<!-- Three quarters of a circle; spun with motion-safe:animate-spin where used. -->
		<path d="M12 3a9 9 0 1 0 9 9" />
	{/if}
</svg>
