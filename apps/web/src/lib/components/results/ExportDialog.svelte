<!--
	Export results (proposal export.md §5.3-§5.4, §5.7): a workbook (.xlsx, the default) or CSV
	files in one zip, of the case shown or of all cases, in the display units or SI base units, with
	or without the project link. The dialog lists what the file holds, its row counts and what is
	left out, from the same function that makes the file (buildExport, which builds no cells), and
	the warnings of the cases it exports (did not converge, out of date, the earlier results shown
	after a failed solve). Download, with Cancel and the status lines, is in the dialog's footer,
	always in view: it has the focus when the dialog opens (so Enter, Enter gives the default
	workbook) without scrolling the body, which opens at its top, warnings first; the warnings
	describe Download, so a screen reader hears them with it. The file is made in this browser from
	the results the page holds: nothing is sent.

	Building yields to the page every 500 rows or 64 KiB (utils/export/yield.ts); after 300 ms the
	button shows a spinner, Cancel appears beside it and the status line names the sheet being
	written, at most once a second. Cancel, Close and Esc stop it ("Export cancelled; nothing was
	saved."; after Close or Esc the page's notice says it, as the dialog is gone). When Cancel goes
	(the build ends or is cancelled) while it has the focus, the focus moves to Download. One build
	at a time: while one runs the other choices are unavailable, with the reason. Lazily loaded
	(utils/export/load.ts): ResultsPanel never imports this file.
-->
<script lang="ts">
	import { onDestroy } from 'svelte';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import { saveBlob, fileSizeText } from '$lib/utils/export/download';
	import { exportInput } from '$lib/utils/export/input';
	import type { ExportChoices, ExportDialogProps } from '$lib/utils/export/load';
	import { buildExport, type ExportBundle } from '$lib/utils/export/model';
	import { writeCsvZip } from '$lib/utils/export/csv';
	import { writeXlsx } from '$lib/utils/export/xlsx';
	import { isAbortError } from '$lib/utils/export/yield';
	import { displayUnit, unitLabel } from '$lib/utils/units';

	let { choices, onchoices, initialCases, onclose }: ExportDialogProps = $props();
	const ws = useWorkspace();
	const id = $props.id();

	const hasScenarios = $derived(ws.scenarios.length > 0);
	const scenarioCount = $derived(ws.scenarios.length);
	const shownName = $derived(ws.caseName(ws.store.activeCase));
	// The Cases choice follows the tab shown when the dialog opens (export.md §2.4).
	// svelte-ignore state_referenced_locally
	let cases = $state<'shown' | 'all'>(initialCases);
	const options = $derived({
		format: choices.format,
		cases: hasScenarios ? cases : ('shown' as const),
		units: choices.units,
		link: choices.link
	});

	/** What the file holds for these choices (no cells built), or why it cannot be made. */
	const preview = $derived.by((): { bundle: ExportBundle } | { error: string } => {
		try {
			return { bundle: buildExport(exportInput(ws, options, new Date())) };
		} catch (error) {
			return { error: error instanceof Error ? error.message : String(error) };
		}
	});
	const bundle = $derived('bundle' in preview ? preview.bundle : null);

	/** "L/s, kPa(g), m": the display units the file would use. */
	const unitSummary = $derived.by(() => {
		const prefs = ws.displayUnits;
		return [
			unitLabel('flow', displayUnit('flow', prefs)),
			unitLabel('pressure', displayUnit('pressure', prefs), { gauge: true }),
			unitLabel('length', displayUnit('length', prefs))
		].join(', ');
	});

	const contents = $derived(
		bundle
			? [
					...(choices.format === 'csv' ? ['README.txt'] : []),
					...bundle.sheets.map((sheet) => {
						const name = choices.format === 'csv' ? sheet.file : sheet.title;
						return sheet.kind === 'table' ? `${name} (${sheet.rowCount})` : name;
					})
				].join(' · ')
			: ''
	);
	const hasPumps = $derived(!!bundle?.sheets.some((sheet) => sheet.id === 'pumps'));

	let downloadButton: HTMLButtonElement | undefined = $state();
	let cancelButton: HTMLButtonElement | undefined = $state();
	$effect(() => {
		downloadButton?.focus();
	});

	let controller: AbortController | null = null;
	let building = $state(false);
	/** The build has run for 300 ms: the spinner, Cancel and the progress line show. */
	let slow = $state(false);
	let status = $state('');
	let alert = $state('');
	const BUSY = 'A file is being prepared.';
	/** Download's description: the warnings (heard with it), and the reason while a build runs. */
	const downloadDescription = $derived(
		[
			...(bundle?.warnings ?? []).map((_, i) => `${id}-warning-${i}`),
			...(building ? [`${id}-busy`] : [])
		].join(' ') || undefined
	);

	function setChoice<K extends keyof ExportChoices>(key: K, value: ExportChoices[K]) {
		if (!building) onchoices({ ...choices, [key]: value });
	}

	/** A choice's control while a build runs: unavailable, with the reason. */
	function guard(event: Event) {
		if (building) event.preventDefault();
	}

	async function download() {
		if (building || !bundle) return;
		status = '';
		alert = '';
		const ownController = new AbortController();
		controller = ownController;
		building = true;
		slow = false;
		const format = options.format;
		let progress: { sheet: number; sheets: number; title: string } | null = null;
		const progressText = () =>
			progress
				? format === 'csv'
					? `Preparing the CSV files: ${progress.title} (file ${progress.sheet} of ${progress.sheets})…`
					: `Preparing the workbook: ${progress.title} (sheet ${progress.sheet} of ${progress.sheets})…`
				: format === 'csv'
					? 'Preparing the CSV files…'
					: 'Preparing the workbook…';
		// The progress line is written at most once a second, so screen readers are not flooded.
		let ticker: ReturnType<typeof setInterval> | undefined;
		const timer = setTimeout(() => {
			slow = true;
			status = progressText();
			ticker = setInterval(() => (status = progressText()), 1000);
		}, 300);
		try {
			const made = buildExport(exportInput(ws, options, new Date()));
			const write = format === 'csv' ? writeCsvZip : writeXlsx;
			const blob = await write(made, {
				signal: ownController.signal,
				onProgress: (p) => (progress = p)
			});
			ownController.signal.throwIfAborted();
			saveBlob(blob, made.fileName);
			status = `“${made.fileName}” (${fileSizeText(blob.size)}) is ready; your browser saves it to its downloads.`;
		} catch (error) {
			if (ownController.signal.aborted || isAbortError(error)) {
				status = 'Export cancelled; nothing was saved.';
			} else {
				status = '';
				alert = `The file could not be made: ${error instanceof Error ? error.message : String(error)}. Nothing was saved.`;
			}
		} finally {
			clearTimeout(timer);
			clearInterval(ticker);
			if (controller === ownController) controller = null;
			// Cancel goes with `slow`: a focused Cancel hands the focus to Download, never to <body>.
			if (cancelButton && document.activeElement === cancelButton) downloadButton?.focus();
			building = false;
			slow = false;
		}
	}

	function cancel() {
		controller?.abort();
	}

	/** Close (Esc, Close): a build in progress is cancelled, and the page's notice says so. */
	function close() {
		if (controller) {
			controller.abort();
			ws.notify('info', 'Export cancelled; nothing was saved.');
		}
		onclose();
	}

	onDestroy(() => controller?.abort());
</script>

<Dialog title="Export results" onclose={close}>
	<div class="space-y-4">
		{#if bundle?.warnings.length}
			<ul class="space-y-2">
				{#each bundle.warnings as warning, i (i)}
					<li
						class={[
							'flex items-start gap-2 rounded-md border p-3 text-sm',
							warning.kind === 'not_converged'
								? 'border-red-300 bg-red-50 text-red-900'
								: 'border-amber-300 bg-amber-50 text-amber-900'
						]}
						data-export-warning={warning.kind}
					>
						<Icon name="alert" class="mt-0.5 size-4 shrink-0" />
						<span id="{id}-warning-{i}" class="min-w-0 flex-1 break-words">{warning.text}</span>
					</li>
				{/each}
			</ul>
		{/if}

		{#if hasScenarios}
			<fieldset class="space-y-1">
				<legend class="label mb-1">Cases</legend>
				{#each [{ value: 'shown', label: `${shownName} (the case shown)` }, { value: 'all', label: `All cases (base and ${scenarioCount} scenario${scenarioCount === 1 ? '' : 's'})` }] as option (option.value)}
					<label class="flex min-h-11 items-center gap-2 text-sm break-words">
						<input
							type="radio"
							name="{id}-cases"
							value={option.value}
							checked={cases === option.value}
							aria-disabled={building ? 'true' : undefined}
							aria-describedby={building ? `${id}-busy` : undefined}
							onclick={guard}
							onchange={() => {
								if (!building) cases = option.value as 'shown' | 'all';
							}}
						/>
						<span class="min-w-0">{option.label}</span>
					</label>
				{/each}
			</fieldset>
		{/if}

		<fieldset class="space-y-1">
			<legend class="label mb-1">Format</legend>
			<label class="flex min-h-11 items-start gap-2 pt-3 text-sm">
				<input
					type="radio"
					class="mt-0.5"
					name="{id}-format"
					value="xlsx"
					checked={choices.format === 'xlsx'}
					aria-disabled={building ? 'true' : undefined}
					aria-describedby="{id}-xlsx-hint{building ? ` ${id}-busy` : ''}"
					onclick={guard}
					onchange={() => setChoice('format', 'xlsx')}
				/>
				<span class="min-w-0">
					Excel workbook (.xlsx)
					<span id="{id}-xlsx-hint" class="hint block">
						Every table on its own sheet, numbers as numbers in Excel in any language setting.
					</span>
				</span>
			</label>
			<label class="flex min-h-11 items-start gap-2 pt-3 text-sm">
				<input
					type="radio"
					class="mt-0.5"
					name="{id}-format"
					value="csv"
					checked={choices.format === 'csv'}
					aria-disabled={building ? 'true' : undefined}
					aria-describedby="{id}-csv-hint{building ? ` ${id}-busy` : ''}"
					onclick={guard}
					onchange={() => setChoice('format', 'csv')}
				/>
				<span class="min-w-0">
					CSV files (.zip)
					<span id="{id}-csv-hint" class="hint block">
						One file per table, comma-separated, UTF-8, dot decimals: for scripts. LibreOffice or
						Excel set to a language that writes decimal commas can read these values wrongly without
						a warning (101.325 as 101325); use the workbook there. The zip's README.txt says how to
						open them.
					</span>
				</span>
			</label>
		</fieldset>

		<fieldset class="space-y-1">
			<legend class="label mb-1">Units</legend>
			{#each [{ value: 'display', label: `Display units (${unitSummary}, as set in Settings)` }, { value: 'si', label: 'SI base units (m³/s, Pa, m, …)' }] as option (option.value)}
				<label class="flex min-h-11 items-center gap-2 text-sm">
					<input
						type="radio"
						name="{id}-units"
						value={option.value}
						checked={choices.units === option.value}
						aria-disabled={building ? 'true' : undefined}
						aria-describedby={building ? `${id}-busy` : undefined}
						onclick={guard}
						onchange={() => setChoice('units', option.value as 'display' | 'si')}
					/>
					<span class="min-w-0">{option.label}</span>
				</label>
			{/each}
		</fieldset>

		<div>
			<label class="flex min-h-11 items-center gap-2 text-sm">
				<input
					type="checkbox"
					class="size-4"
					checked={choices.link}
					aria-disabled={building ? 'true' : undefined}
					aria-describedby="{id}-link-hint{building ? ` ${id}-busy` : ''}"
					onclick={guard}
					onchange={(event) => setChoice('link', event.currentTarget.checked)}
				/>
				Include the project link
			</label>
			<p id="{id}-link-hint" class="hint">
				The link lets anyone open the whole project: every input of every case and scenario. Without
				it, the file still holds the exported cases' inputs (in the Trace and the tables) and every
				name and description.
			</p>
		</div>

		<section aria-labelledby="{id}-contents" class="space-y-1 text-sm">
			<h3 id="{id}-contents" class="label">In the file</h3>
			{#if bundle}
				<p class="break-words text-slate-800" data-export-contents>{contents}</p>
				{#if bundle.omitted.length}
					<p class="text-slate-700">Not in the file:</p>
					<ul class="list-disc space-y-0.5 pl-5 text-slate-700" data-export-omitted>
						{#each bundle.omitted as item, i (i)}
							<li class="break-words">{item.what}: {item.reason}</li>
						{/each}
					</ul>
				{/if}
				<p class="font-mono text-xs break-all text-slate-700" data-export-file-name>
					{bundle.fileName}
				</p>
			{:else if 'error' in preview}
				<p class="text-red-900">The file cannot be made: {preview.error}</p>
			{/if}
		</section>

		<ul class="space-y-1 text-xs text-slate-600">
			<li>Files are made in this browser; nothing is sent to the server.</li>
			<li>
				Nothing saved? Pages opened inside an app (Teams, Slack, Outlook) often cannot save files:
				open the page in your browser.
			</li>
			{#if hasPumps}
				<li>To save a pump chart as an image, use Download image under the chart (Pumps).</li>
			{/if}
		</ul>
	</div>
	{#snippet footer()}
		<!-- In the footer, always in view: focusing Download never scrolls the body (review W1). -->
		<p
			role="status"
			class="min-w-0 basis-full self-center text-sm break-words text-slate-800 empty:hidden sm:mr-auto sm:flex-1 sm:basis-auto"
		>
			{status}
		</p>
		<p
			role="alert"
			class="min-w-0 basis-full self-center text-sm break-words text-red-900 empty:hidden sm:mr-auto sm:flex-1 sm:basis-auto"
		>
			{alert}
		</p>
		{#if building}<span id="{id}-busy" class="sr-only">{BUSY}</span>{/if}
		<button type="button" class="btn" onclick={close}>Close</button>
		{#if slow}
			<button bind:this={cancelButton} type="button" class="btn" onclick={cancel}>Cancel</button>
		{/if}
		<button
			bind:this={downloadButton}
			type="button"
			class="btn btn-primary"
			data-export-download
			aria-disabled={building || !bundle}
			aria-describedby={downloadDescription}
			onclick={() => void download()}
		>
			<Icon
				name={slow ? 'spinner' : 'download'}
				class={['size-4', slow && 'motion-safe:animate-spin']}
			/>
			<!-- Both labels in one grid cell: the button keeps one width while it works. -->
			<span class="grid">
				<span class={['col-start-1 row-start-1', slow && 'invisible']} aria-hidden={slow}
					>Download</span
				>
				<span class={['col-start-1 row-start-1', !slow && 'invisible']} aria-hidden={!slow}
					>Preparing…</span
				>
			</span>
		</button>
	{/snippet}
</Dialog>
