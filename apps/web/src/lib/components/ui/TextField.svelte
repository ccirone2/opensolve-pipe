<!--
	A text input that stores on change (Enter or leaving the field). A required field that is
	left empty goes back to the stored text instead of storing an empty value.
-->
<script lang="ts">
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
		onchange
	}: Props = $props();

	const id = $props.id();
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
			class={['input min-h-24 py-2', inputClass]}
			{maxlength}
			{placeholder}
			value={text}
			aria-describedby={hint ? `${id}-hint` : undefined}
			oninput={(event) => (text = event.currentTarget.value)}
			onchange={commit}></textarea>
	{:else}
		<input
			{id}
			class={['input', inputClass]}
			type="text"
			autocomplete="off"
			{maxlength}
			{placeholder}
			{required}
			value={text}
			aria-describedby={hint ? `${id}-hint` : undefined}
			oninput={(event) => (text = event.currentTarget.value)}
			onchange={commit}
			onkeydown={(event) => {
				if (event.key === 'Enter') {
					event.preventDefault();
					commit();
				}
			}}
		/>
	{/if}
	{#if hint}<p id="{id}-hint" class="hint">{hint}</p>{/if}
</div>
