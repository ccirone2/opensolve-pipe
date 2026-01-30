/**
 * Theme store for managing light/dark mode.
 */

import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';

/** Available theme options. */
export type Theme = 'light' | 'dark';

/** Storage key for theme preference. */
const STORAGE_KEY = 'opensolve-pipe-theme';

/**
 * Get the initial theme from localStorage or system preference.
 */
function getInitialTheme(): Theme {
	if (!browser) return 'light';

	// Check localStorage first
	const stored = localStorage.getItem(STORAGE_KEY);
	if (stored === 'light' || stored === 'dark') {
		return stored;
	}

	// Default to light, but respect system dark preference
	if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
		return 'dark';
	}

	return 'light';
}

/**
 * Create the theme store.
 */
function createThemeStore() {
	const store = writable<Theme>(getInitialTheme());

	return {
		subscribe: store.subscribe,

		/**
		 * Set the theme.
		 */
		set(theme: Theme) {
			store.set(theme);
			if (browser) {
				localStorage.setItem(STORAGE_KEY, theme);
				document.documentElement.setAttribute('data-theme', theme);
			}
		},

		/**
		 * Toggle between light and dark themes.
		 */
		toggle() {
			store.update((current) => {
				const next = current === 'dark' ? 'light' : 'dark';
				if (browser) {
					localStorage.setItem(STORAGE_KEY, next);
					document.documentElement.setAttribute('data-theme', next);
				}
				return next;
			});
		},

		/**
		 * Initialize the theme on mount.
		 * Call this in +layout.svelte to apply the theme to the document.
		 */
		initialize() {
			if (browser) {
				const theme = getInitialTheme();
				store.set(theme);
				document.documentElement.setAttribute('data-theme', theme);
			}
		}
	};
}

/** The theme store instance. */
export const themeStore = createThemeStore();

/** Derived store that returns true if dark mode is active. */
export const isDarkMode = derived(themeStore, ($theme) => $theme === 'dark');
