<!--
	Share: copies the current link (the whole project is in it) and shows it, with a warning
	when it is longer than 8,000 characters (D3), since some email and chat apps cut long links.
	Without clipboard access the link is shown selected, to copy by hand.
-->
<script lang="ts">
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { URL_LENGTH_WARNING } from '$lib/utils/encoding';
	import { useWorkspace } from '$lib/state/workspace.svelte';

	let { compact = false }: { compact?: boolean } = $props();
	const ws = useWorkspace();
	const id = $props.id();

	let open = $state(false);
	let link = $state('');
	let status = $state<'copied' | 'manual'>('manual');
	let field: HTMLInputElement | undefined = $state();

	async function copy(): Promise<boolean> {
		try {
			if (!navigator.clipboard?.writeText) return false;
			await navigator.clipboard.writeText(link);
			return true;
		} catch {
			return false;
		}
	}

	async function share() {
		link = ws.store.shareLink();
		status = (await copy()) ? 'copied' : 'manual';
		open = true;
	}

	async function copyAgain() {
		status = (await copy()) ? 'copied' : 'manual';
		if (status === 'manual') selectLink();
	}

	function selectLink() {
		field?.focus();
		field?.select();
	}

	$effect(() => {
		if (open && status === 'manual' && field) selectLink();
	});

	const length = $derived(link.length);
	const tooLong = $derived(length > URL_LENGTH_WARNING);
	const count = $derived(ws.scenarios.length);
</script>

<button
	type="button"
	class={['btn', compact && 'btn-icon sm:w-auto sm:px-3']}
	aria-label={compact ? 'Share' : undefined}
	onclick={share}
>
	<Icon name="share" /><span class={compact ? 'hidden sm:inline' : ''}>Share</span>
</button>

{#if open}
	<Dialog title="Share this project" onclose={() => (open = false)}>
		<div class="space-y-3">
			<p role="status" class="flex items-start gap-2 text-sm">
				{#if status === 'copied'}
					<Icon name="check" class="mt-0.5 size-4 shrink-0 text-green-700" />
					<span>Link copied to the clipboard.</span>
				{:else}
					<span>Copy the link below.</span>
				{/if}
			</p>
			<div>
				<label for="{id}-link" class="label mb-1">Link to this version of the project</label>
				<div class="flex gap-2">
					<input
						bind:this={field}
						id="{id}-link"
						class="input font-mono text-sm"
						type="text"
						readonly
						value={link}
						onfocus={(event) => event.currentTarget.select()}
					/>
					<button type="button" class="btn shrink-0" onclick={copyAgain}>
						<Icon name="copy" class="size-4" /> Copy
					</button>
				</div>
				<p class="hint">{length.toLocaleString('en-US')} characters</p>
			</div>
			{#if tooLong}
				<p
					class="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
				>
					<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
					<span>
						This link is longer than {URL_LENGTH_WARNING.toLocaleString('en-US')} characters. Some email
						and chat apps cut long links short, and a cut link cannot be opened. Check that the whole
						link arrives, or send it as a file or a note.
					</span>
				</p>
			{/if}
			{#if count}
				<p class="text-sm text-slate-700">
					This link holds the base case and its {count === 1 ? 'scenario' : `${count} scenarios`}.
					It opens on the base case.{#if ws.activeScenario}
						You are looking at «{ws.activeScenario.name}»: the person you send it to can choose it
						from the Case menu.{/if}
				</p>
			{/if}
			<p class="text-sm text-slate-700">
				The whole project is in the link, after the “#”, which browsers do not send to any server.
				Anyone with the link can open it; their edits make a new link, and this one keeps opening
				this version.
			</p>
		</div>
	</Dialog>
{/if}
