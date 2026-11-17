<!--
	A header control's shortcut, in a pane's words that name the control (build-density.md §19): the
	words Solve's title uses, in parentheses after the control's name, drawn on a fine pointer only
	(a touch screen has no keyboard to press them on). Solve is Ctrl/⌘+Enter; Solve all, the
	Scenarios menu's, Ctrl/⌘+Shift+Enter.
-->
<script lang="ts">
	let { keys }: { keys: 'solve' | 'solveAll' } = $props();

	const KEYS: Readonly<Record<'solve' | 'solveAll', string>> = {
		solve: 'Ctrl+Enter or ⌘+Enter',
		solveAll: 'Ctrl+Shift+Enter or ⌘+Shift+Enter'
	};
</script>

<span class="hidden pointer-fine:inline">{` (${KEYS[keys]})`}</span>
