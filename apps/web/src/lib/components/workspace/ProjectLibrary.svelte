<!--
	The project library (CLAUDE.md D22; proposal project-library.md §6.1): pipe specs and loss
	coefficients from the user's own sources, each defined once with its source and referred to by
	any pipe, valve or fitting, so an edit to an entry reaches every element that uses it. Two
	lists, Pipe specs and Resistances (tabs); each entry shows its name, its values in display
	units, its source and what uses it. Its form opens in place of the lists, Save and Cancel in
	the footer; a new entry takes an id from newId (PS1, RS1, ...), never one in use. Every save
	and delete is one undo step. Delete is refused while anything uses the entry (an element, or a
	scenario's change), naming the first user, as a pump curve's is; the refusal is scrolled into
	view (on a phone it would be under the footer), the focus staying on Delete. A list holds at
	most 100 entries (the schema's limit, library/limits.ts): when it is full, New is unavailable
	and the list says why, before any form is filled in.

	Opened from the header (its lists), from a picker that can use an entry (an entry's form, or a
	new entry's form whose entry is then used there in the same undo step: `use`), and from a
	trace's mention of an entry (that entry, in view). A form opened that way closes the dialog when
	it is saved or cancelled, so the focus goes back where the user was; one opened here returns
	the focus to its button, or to the entry saved.

	The library is base data, the same in every case: in a scenario it is shown read-only, saying
	so (a pipe's spec and a valve's resistance stay scenario values, chosen in their forms).
-->
<script lang="ts">
	import { tick, untrack } from 'svelte';
	import type { PipeSpec, ResistanceSpec } from '$lib/api/types';
	import Dialog from '$lib/components/ui/Dialog.svelte';
	import Icon from '$lib/components/ui/Icon.svelte';
	import { npsLabel } from '$lib/utils/labels';
	import { CUSTOM_MATERIAL_ID } from '$lib/utils/piping';
	import {
		entryValueText,
		newPipeSpecId,
		newResistanceId,
		pipeSpecs,
		pipeSpecUsers,
		removePipeSpec,
		removeResistanceSpec,
		resistanceEntries,
		resistanceUsers,
		setPipeSpec,
		setResistanceSpec,
		userLabel,
		type LibraryUser
	} from '$lib/utils/project-library';
	import { formatValue } from '$lib/utils/units';
	import { pipeSpecProblems, resistanceSpecProblems } from '$lib/utils/validate';
	import { useWorkspace, type LibraryFocus } from '$lib/state/workspace.svelte';
	import {
		pipeSpecMissing,
		pipeSpecOf,
		resistanceMissing,
		resistanceOf,
		type FieldErrors,
		type PipeSpecDraft,
		type ResistanceDraft
	} from './library/drafts';
	import { libraryFull, libraryLimitText } from './library/limits';
	import PipeSpecFields from './library/PipeSpecFields.svelte';
	import ResistanceEntryFields from './library/ResistanceEntryFields.svelte';

	let { onclose }: { onclose: () => void } = $props();
	const ws = useWorkspace();
	const store = ws.store;
	const id = $props.id();

	type List = LibraryFocus['list'];
	interface FormBase {
		/** A new entry (else the edit of the entry with the draft's id). */
		isNew: boolean;
		/** Opened by the dialog's focus (a picker or a trace): closing it closes the dialog. */
		fromFocus: boolean;
		use?: LibraryFocus['use'];
	}
	type Form =
		| (FormBase & { list: 'pipe'; draft: PipeSpecDraft })
		| (FormBase & { list: 'resistance'; draft: ResistanceDraft });

	/** The library is base data: read-only in a scenario. */
	const readOnly = $derived(ws.inScenario);
	const specs = $derived(pipeSpecs(store.project));
	const entries = $derived(resistanceEntries(store.project));
	const LISTS: readonly { value: List; label: string }[] = [
		{ value: 'pipe', label: 'Pipe specs' },
		{ value: 'resistance', label: 'Resistances' }
	];

	const initial = untrack(() => ws.libraryFocus);
	let list = $state<List>(initial?.list ?? 'pipe');
	/** The list shown holds as many entries as a project may: New is unavailable. */
	const full = $derived(libraryFull(store.project, list));
	let form = $state<Form | null>(untrack(() => initialForm(initial)));
	let errors = $state<FieldErrors>({});
	/** Problems the API's rules find in a complete draft (or a refused save), under the form. */
	let problems = $state<string[]>([]);
	/** Why an entry could not be deleted, by entry id (shown on its card until the next delete). */
	let refusals = $state<Record<string, string>>({});
	/** What the last delete did, said by a polite live region. */
	let status = $state('');

	function newDraft(which: List): Form['draft'] {
		const reserved = ws.reservedIds;
		if (which === 'pipe') {
			const first = ws.library.materials[0]?.id ?? CUSTOM_MATERIAL_ID;
			return { id: newPipeSpecId(store.project, reserved), materialId: first };
		}
		return { id: newResistanceId(store.project, reserved), kind: 'Cv' };
	}

	function initialForm(focus: LibraryFocus | null): Form | null {
		if (!focus || ws.inScenario) return null;
		if (focus.create) {
			// A full list: shown, saying why, rather than a form that cannot be saved.
			if (libraryFull(store.project, focus.list)) return null;
			return focus.list === 'pipe'
				? {
						list: 'pipe',
						draft: newDraft('pipe') as PipeSpecDraft,
						isNew: true,
						fromFocus: true,
						...(focus.use ? { use: focus.use } : {})
					}
				: {
						list: 'resistance',
						draft: newDraft('resistance') as ResistanceDraft,
						isNew: true,
						fromFocus: true,
						...(focus.use ? { use: focus.use } : {})
					};
		}
		return focus.edit ? editForm(focus.list, focus.edit, true) : null;
	}

	function editForm(which: List, entryId: string, fromFocus: boolean): Form | null {
		if (which === 'pipe') {
			const spec = pipeSpecs(store.project).find((s) => s.id === entryId);
			return spec ? { list: 'pipe', draft: { ...spec }, isNew: false, fromFocus } : null;
		}
		const entry = resistanceEntries(store.project).find((e) => e.id === entryId);
		return entry ? { list: 'resistance', draft: { ...entry }, isNew: false, fromFocus } : null;
	}

	// Opened on an entry or a form: after the dialog has placed the focus, move it there.
	$effect(() => {
		const focus = untrack(() => ws.libraryFocus);
		if (!focus) return;
		void tick().then(() => {
			if (form) focusForm();
			else if (focus.edit ?? focus.show) focusEntry(focus.edit ?? focus.show ?? '');
		});
	});

	function focusForm() {
		const input = document.querySelector<HTMLElement>(
			`#${id}-form input, #${id}-form select, #${id}-form textarea`
		);
		input?.focus();
	}

	function focusEntry(entryId: string) {
		const heading = document.querySelector<HTMLElement>(`[data-entry-heading="${entryId}"]`);
		heading?.scrollIntoView?.({ block: 'nearest' });
		heading?.focus();
	}

	function openForm(next: Form) {
		form = next;
		errors = {};
		problems = [];
		void tick().then(focusForm);
	}

	/** Close the form: the dialog too when the focus opened it, else back to its button or entry. */
	async function closeForm(saved: string | null) {
		const closing = form;
		form = null;
		errors = {};
		problems = [];
		if (!closing || closing.fromFocus) {
			onclose();
			return;
		}
		list = closing.list;
		await tick();
		if (saved) focusEntry(saved);
		else if (!closing.isNew) {
			document.querySelector<HTMLElement>(`[data-entry-edit="${closing.draft.id}"]`)?.focus();
		} else document.getElementById(`${id}-new`)?.focus();
	}

	async function focusFirstError(found: FieldErrors) {
		await tick();
		const field = Object.keys(found)[0];
		document
			.querySelector<HTMLElement>(
				`#${id}-form [data-field="${field}"] input, #${id}-form [data-field="${field}"] textarea`
			)
			?.focus();
	}

	function save() {
		const current = form;
		if (!current || readOnly) return;
		if (current.isNew && libraryFull(store.project, current.list)) {
			problems = [libraryLimitText(current.list)];
			return;
		}
		const missing =
			current.list === 'pipe' ? pipeSpecMissing(current.draft) : resistanceMissing(current.draft);
		if (Object.keys(missing).length) {
			errors = missing;
			void focusFirstError(missing);
			return;
		}
		const entry: PipeSpec | ResistanceSpec =
			current.list === 'pipe' ? pipeSpecOf(current.draft) : resistanceOf(current.draft);
		const found = current.list === 'pipe' ? pipeSpecProblems(entry) : resistanceSpecProblems(entry);
		if (found.length) {
			problems = found;
			return;
		}
		const what = current.list === 'pipe' ? 'pipe spec' : 'resistance entry';
		const use = current.use;
		const label = !current.isNew
			? `edit ${what} ${entry.name}`
			: use
				? `add ${what} ${entry.name} for ${use.label}`
				: `add ${what} ${entry.name}`;
		const result = store.update((p) => {
			const next =
				current.list === 'pipe'
					? setPipeSpec(p, entry as PipeSpec)
					: setResistanceSpec(p, entry as ResistanceSpec);
			return use ? use.apply(next, entry.id) : next;
		}, label);
		if (!result.ok) {
			problems = [result.problems[0] ?? 'The entry is not valid.'];
			return;
		}
		if (result.notes?.length) ws.notify('info', result.notes.join(' '));
		void closeForm(entry.id);
	}

	async function remove(which: List, entry: PipeSpec | ResistanceSpec) {
		const what = which === 'pipe' ? 'pipe spec' : 'resistance entry';
		const result = store.update(
			(p) => (which === 'pipe' ? removePipeSpec(p, entry.id) : removeResistanceSpec(p, entry.id)),
			`delete ${what} ${entry.name}`
		);
		if (!result.ok) {
			refusals = {
				[entry.id]: `Not deleted: ${result.problems[0] ?? 'it is in use.'} An entry can be deleted once nothing uses it.`
			};
			status = '';
			// The refusal is drawn below Delete: in view in full (on a phone it would be under the
			// footer), the focus staying on Delete.
			await tick();
			document.getElementById(`${id}-refusal-${entry.id}`)?.scrollIntoView?.({ block: 'nearest' });
			return;
		}
		refusals = {};
		status = `Deleted ${what} ${entry.name}. Undo brings it back.`;
		await tick();
		document.getElementById(`${id}-${which}-heading`)?.focus();
	}

	function selectList(next: List) {
		list = next;
		refusals = {};
	}

	function tabKeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
			event.preventDefault();
			const next = list === 'pipe' ? 'resistance' : 'pipe';
			selectList(next);
			document.getElementById(`${id}-tab-${next}`)?.focus();
		}
	}

	/** A rule's clause as a sentence: "Its inner diameter must be below its outer diameter." */
	const sentence = (text: string) =>
		`${text.charAt(0).toUpperCase()}${text.slice(1)}${/[.!?]$/.test(text) ? '' : '.'}`;
	const fittingName = (type: string) => ws.library.fitting(type)?.name;
	const usersOf = (which: List, entryId: string): LibraryUser[] =>
		which === 'pipe'
			? pipeSpecUsers(store.project, entryId)
			: resistanceUsers(store.project, entryId);
	const label = (user: LibraryUser) =>
		userLabel(store.project, user, (type) => fittingName(type) ?? type);
	const fmt = (si: number) => formatValue(si, 'diameter', ws.units, 4);
	const materialName = (materialId: string) =>
		materialId === CUSTOM_MATERIAL_ID
			? 'Custom'
			: (ws.library.material(materialId)?.name ?? materialId);
	/** What a blank roughness is on a library material: its cited one at the spec's bore. */
	function roughnessText(spec: PipeSpec): string {
		if (spec.roughness != null) return fmt(spec.roughness);
		const material = ws.library.material(spec.materialId);
		for (const schedule of material?.schedules ?? []) {
			const size = schedule.sizes.find((s) => s.innerDiameter === spec.innerDiameter);
			if (size) return `${fmt(size.roughness)}, the material's at this bore`;
		}
		return "the material's at this bore (Farshad & Rieke 2006), computed when solving";
	}

	const formTitle = $derived(
		!form
			? ''
			: form.isNew
				? form.list === 'pipe'
					? 'New pipe spec'
					: 'New resistance entry'
				: `Edit ${form.list === 'pipe' ? 'pipe spec' : 'resistance entry'} ${form.draft.id}`
	);
	const saveLabel = $derived(
		form?.use ? `Save and use for ${form.use.label}` : form?.isNew ? 'Add' : 'Save'
	);
</script>

{#snippet users(which: List, entryId: string)}
	{@const found = usersOf(which, entryId)}
	{#if found.length}
		<details class="group">
			<summary
				class="flex min-h-11 cursor-pointer list-none items-center gap-1 text-sm font-medium text-blue-800 [&::-webkit-details-marker]:hidden"
			>
				<Icon name="right" class="size-4 shrink-0 transition-transform group-open:rotate-90" />
				Used by {found.length}
			</summary>
			<ul class="list-disc space-y-0.5 pb-1 pl-9 text-sm text-slate-700">
				{#each found as user, i (i)}
					<li class="break-words">{label(user)}</li>
				{/each}
			</ul>
		</details>
	{:else}
		<p class="py-2 text-sm text-slate-600">Not used.</p>
	{/if}
{/snippet}

{#snippet actions(which: List, entry: PipeSpec | ResistanceSpec)}
	{#if !readOnly}
		<div class="flex flex-wrap gap-2">
			<button
				type="button"
				class="btn"
				data-entry-edit={entry.id}
				aria-label="Edit {entry.name}"
				onclick={() => {
					const next = editForm(which, entry.id, false);
					if (next) openForm(next);
				}}
			>
				Edit
			</button>
			<button
				type="button"
				class="btn btn-quiet text-red-800"
				aria-label="Delete {entry.name}"
				onclick={() => remove(which, entry)}
			>
				<Icon name="trash" class="size-4" /> Delete
			</button>
		</div>
	{/if}
	{#if refusals[entry.id]}
		<!-- Its scroll margin: scrolled into view with a gap above the footer, never a sliver under
			it (a fraction of a pixel at 320 px). -->
		<p
			id="{id}-refusal-{entry.id}"
			role="alert"
			class="flex scroll-mb-3 items-start gap-1 text-sm text-red-700"
		>
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span>{refusals[entry.id]}</span>
		</p>
	{/if}
{/snippet}

<Dialog title="Project library" wide {onclose}>
	{#if form}
		<section id="{id}-form" class="space-y-4 text-sm" aria-labelledby="{id}-form-title">
			<h3 id="{id}-form-title" class="font-semibold">{formTitle}</h3>
			{#if !form.isNew}
				{@const count = usersOf(form.list, form.draft.id).length}
				{#if count}
					<p class="text-slate-700">
						Used by {count}: saving changes every one of them.
					</p>
				{/if}
			{/if}
			{#if form.list === 'pipe'}
				<PipeSpecFields bind:draft={form.draft} bind:errors units={ws.units} />
			{:else}
				<ResistanceEntryFields bind:draft={form.draft} bind:errors units={ws.units} />
			{/if}
			{#if problems.length}
				<div role="alert" class="rounded-md border border-red-300 bg-red-50 p-3 text-red-900">
					<p class="font-medium">Not saved:</p>
					<ul class="list-disc pl-5">
						{#each problems as problem, i (i)}<li class="break-words">
								{sentence(problem)}
							</li>{/each}
					</ul>
				</div>
			{/if}
		</section>
	{:else}
		<div class="space-y-4 text-sm">
			<p class="text-slate-700">
				Pipe sizes and loss coefficients from your own sources (a datasheet, a standard the pipe
				library does not hold, a measurement), each defined once with its source and used by any
				pipe, valve or fitting. Editing an entry changes every element that uses it, and every
				result that uses it cites its source.
			</p>
			{#if readOnly}
				<p
					class="flex items-start gap-2 rounded-md border border-slate-300 bg-slate-50 p-3 text-slate-800"
				>
					<Icon name="lock" class="mt-0.5 size-4 shrink-0" />
					<span>
						The library is the same in every case: switch to the base case to change it. In this
						scenario a pipe's spec and a valve's resistance are still chosen in their forms.
					</span>
				</p>
			{/if}
			<div
				role="tablist"
				aria-label="Library lists"
				class="flex border-b border-slate-200"
				tabindex="-1"
				onkeydown={tabKeydown}
			>
				{#each LISTS as tab (tab.value)}
					<button
						type="button"
						role="tab"
						id="{id}-tab-{tab.value}"
						aria-selected={list === tab.value}
						aria-controls="{id}-panel"
						tabindex={list === tab.value ? 0 : -1}
						class={[
							'-mb-px min-h-11 border-b-2 px-4 text-sm font-medium',
							list === tab.value
								? 'border-blue-700 text-blue-800'
								: 'border-transparent text-slate-600 hover:text-slate-900'
						]}
						onclick={() => selectList(tab.value)}
					>
						{tab.label} ({tab.value === 'pipe' ? specs.length : entries.length})
					</button>
				{/each}
			</div>
			<div id="{id}-panel" role="tabpanel" aria-labelledby="{id}-tab-{list}" class="space-y-3">
				<h3 id="{id}-{list}-heading" tabindex="-1" class="sr-only">
					{list === 'pipe' ? 'Pipe specs' : 'Resistances'}
				</h3>
				{#if full && !readOnly}
					<p id="{id}-limit" class="text-slate-700">
						{libraryLimitText(list)} Delete one that nothing uses to add another.
					</p>
				{/if}
				{#if list === 'pipe'}
					{#if !specs.length}
						<p class="text-slate-700">
							No pipe specs yet. A spec holds a pipe size the pipe library does not have (or a bore
							you measured): its material, inner diameter and roughness, with their source. Pipes
							use it from their Material list.
						</p>
					{/if}
					{#each specs as spec (spec.id)}
						<section class="card space-y-2 p-3" aria-labelledby="{id}-entry-{spec.id}">
							<h4
								id="{id}-entry-{spec.id}"
								tabindex="-1"
								data-entry-heading={spec.id}
								class="font-semibold break-words"
							>
								{spec.name}
								<span class="font-mono text-xs font-normal text-slate-600">{spec.id}</span>
							</h4>
							<dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-slate-700">
								<dt class="text-slate-600">Material</dt>
								<dd class="break-words">{materialName(spec.materialId)}</dd>
								{#if spec.nominalSize != null}
									<dt class="text-slate-600">Nominal size</dt>
									<dd>{npsLabel(spec.nominalSize, ws.library.nominalSizes)}</dd>
								{/if}
								<dt class="text-slate-600">Inner diameter</dt>
								<dd>{fmt(spec.innerDiameter)}</dd>
								<dt class="text-slate-600">Roughness</dt>
								<dd class="break-words">{roughnessText(spec)}</dd>
								{#if spec.outerDiameter != null}
									<dt class="text-slate-600">Outer diameter</dt>
									<dd>{fmt(spec.outerDiameter)}</dd>
								{/if}
							</dl>
							<p class="text-xs break-words text-slate-700">Source: {spec.source}</p>
							{@render users('pipe', spec.id)}
							{@render actions('pipe', spec)}
						</section>
					{/each}
				{:else}
					{#if !entries.length}
						<p class="text-slate-700">
							No resistances yet. An entry holds a valve's or fitting's loss coefficient from its
							datasheet (a K with the bore it is stated at, a Cv or a Kv), with its source. Valves
							and fittings use it from their resistance list.
						</p>
					{/if}
					{#each entries as entry (entry.id)}
						<section class="card space-y-2 p-3" aria-labelledby="{id}-entry-{entry.id}">
							<h4
								id="{id}-entry-{entry.id}"
								tabindex="-1"
								data-entry-heading={entry.id}
								class="font-semibold break-words"
							>
								{entry.name}
								<span class="font-mono text-xs font-normal text-slate-600">{entry.id}</span>
							</h4>
							<p class="text-slate-700">{entryValueText(entry, ws.units)}</p>
							<p class="text-xs break-words text-slate-700">Source: {entry.source}</p>
							{@render users('resistance', entry.id)}
							{@render actions('resistance', entry)}
						</section>
					{/each}
				{/if}
				<p class="sr-only" role="status">{status}</p>
			</div>
		</div>
	{/if}
	{#snippet footer()}
		{#if form}
			<button type="button" class="btn" onclick={() => closeForm(null)}>Cancel</button>
			<!-- Wraps: "Save and use for pipe 1 of A → B" is wider than a phone's sheet, whose
				right-aligned footer would cut its start off (the footer wraps it onto a row of its own). -->
			<button
				type="button"
				class="btn btn-primary py-1.5 text-left wrap-anywhere whitespace-normal"
				onclick={save}>{saveLabel}</button
			>
		{:else}
			{#if !readOnly}
				<button
					type="button"
					id="{id}-new"
					class="btn"
					aria-disabled={full}
					aria-describedby={full ? `${id}-limit` : undefined}
					title={full ? libraryLimitText(list) : undefined}
					onclick={() => {
						if (full) return;
						openForm(
							list === 'pipe'
								? {
										list: 'pipe',
										draft: newDraft('pipe') as PipeSpecDraft,
										isNew: true,
										fromFocus: false
									}
								: {
										list: 'resistance',
										draft: newDraft('resistance') as ResistanceDraft,
										isNew: true,
										fromFocus: false
									}
						);
					}}
				>
					<Icon name="plus" class="size-4" />
					{list === 'pipe' ? 'New pipe spec' : 'New resistance entry'}
				</button>
			{/if}
			<button type="button" class="btn btn-primary" onclick={onclose}>Done</button>
		{/if}
	{/snippet}
</Dialog>
