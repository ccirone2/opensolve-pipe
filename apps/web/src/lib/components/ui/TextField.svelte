<!--
	A text input that stores on change (Enter or leaving the field). A required field that is
	left empty goes back to the stored text instead of storing an empty value. In a scenario
	(field-mode.ts) it is read-only unless `shared` by every case (names, descriptions).
-->
<script lang="ts">
	import { isLocked, useFieldMode, type FieldChange } from './field-mode';
	import Icon from './Icon.svelte';

	interface Props {
		label: string;
		value: string | null | undefined;
		required?: boolean;
		maxlength?: number;
		hint?: string;
		placeholder?: string;
		hideLabel?: boolean;
		multiline?: boolean;
		class?: string;
		inputClass?: string;
		onchange: (value: string | null) => boolean | void;
		/** Shared by every case: edited in a scenario too, on the base. */
		shared?: boolean;
		/** Part of a scenario value (a custom fluid's name): editable in a scenario; its group notes it. */
		change?: FieldChange | null;
	}

	let {
		label,
		value,
		required = false,
		maxlength,
		hint,
		placeholder,
		hideLabel = false,
		multiline = false,
		class: className = '',
		inputClass = '',
		onchange,
		shared = false,
		change = null
	}: Props = $props();

	const id = $props.id();
	const mode = useFieldMode();
	const locked = $derived(isLocked(mode, change, shared));
	const described = $derived(
		[locked && `${id}-locked`, hint && `${id}-hint`].filter(Boolean).join(' ') || undefined
	);
	const shown = $derived(value ?? '');
	let text = $derived(shown);

	function commit() {
		const trimmed = text.trim();
		if (trimmed === (value ?? '').trim()) return;
		if (!trimmed) {
			if (required) {
				text = shown;
				return;
			}
			if (onchange(null) === false) text = shown;
			return;
		}
		if (onchange(trimmed) === false) text = shown;
	}
</script>

<div class={['min-w-0', className]}>
	<label for={id} class={hideLabel ? 'sr-only' : 'label mb-1'}>{label}</label>
	{#if multiline}
		<textarea
			{id}
			class={['input min-h-24 py-2', inputClass, locked && 'bg-slate-50']}
			{maxlength}
			{placeholder}
			readonly={locked}
			value={text}
			aria-describedby={described}
			oninput={(event) => (text = event.currentTarget.value)}
			onchange={commit}></textarea>
	{:else}
		<div class="relative">
			<input
				{id}
				class={['input', inputClass, locked && 'bg-slate-50 pr-8']}
				type="text"
				autocomplete="off"
				{maxlength}
				{placeholder}
				{required}
				readonly={locked}
				value={text}
				aria-describedby={described}
				oninput={(event) => (text = event.currentTarget.value)}
				onchange={commit}
				onkeydown={(event) => {
					if (event.key === 'Enter') {
						event.preventDefault();
						commit();
					}
				}}
			/>
			{#if locked}
				<Icon
					name="lock"
					class="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2 text-slate-500"
				/>
			{/if}
		</div>
	{/if}
	{#if locked}<span id="{id}-locked" class="sr-only">Same in every scenario.</span>{/if}
	{#if hint}<p id="{id}-hint" class="hint">{hint}</p>{/if}
</div>
