<!-- This page should never render: +page.ts redirects to /p/{encoded}. -->
<!-- Fallback UI in case the redirect doesn't fire (e.g., JS disabled). -->
<div class="flex h-screen items-center justify-center bg-[var(--color-bg)]">
	<div class="flex flex-col items-center gap-3">
		<svg class="h-8 w-8 animate-spin text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24">
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" />
			<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
		</svg>
		<p class="text-xs text-[var(--color-text-muted)]">Creating new project...</p>
	</div>
</div>
