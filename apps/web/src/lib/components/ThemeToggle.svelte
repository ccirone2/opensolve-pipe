<script lang="ts">
	/**
	 * Theme Toggle Component
	 *
	 * A toggle button for switching between light and dark themes.
	 * Displays a sun icon in light mode and moon icon in dark mode.
	 */

	import { themeStore, isDarkMode } from '$lib/stores';

	function handleToggle() {
		themeStore.toggle();
	}
</script>

<button
	type="button"
	class="theme-toggle"
	aria-label={$isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
	title={$isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
	onclick={handleToggle}
>
	<span class="theme-toggle-thumb">
		{#if $isDarkMode}
			<!-- Moon icon for dark mode -->
			<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
				></path>
			</svg>
		{:else}
			<!-- Sun icon for light mode -->
			<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
				></path>
			</svg>
		{/if}
	</span>
</button>
