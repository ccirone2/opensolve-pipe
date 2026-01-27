<script lang="ts">
	interface Props {
		/** Unique ID for the input element. */
		id: string;
		/** Label text to display above the input. */
		label: string;
		/** Current value of the input. */
		value: number | undefined;
		/** Unit to display (e.g., "ft", "psi", "GPM"). */
		unit?: string;
		/** Minimum allowed value. */
		min?: number;
		/** Maximum allowed value. */
		max?: number;
		/** Step increment for the input. */
		step?: number | 'any';
		/** Whether the field is required. */
		required?: boolean;
		/** Placeholder text. */
		placeholder?: string;
		/** Helper text to show below input. */
		hint?: string;
		/** Callback when value changes. */
		onchange: (value: number) => void;
	}

	let {
		id,
		label,
		value,
		unit,
		min,
		max,
		step = 'any',
		required = false,
		placeholder,
		hint,
		onchange
	}: Props = $props();

	let error = $state('');

	function handleInput(e: Event) {
		const input = e.target as HTMLInputElement;
		const numValue = parseFloat(input.value);

		// Validate
		if (input.value === '' && required) {
			error = 'This field is required';
			return;
		}

		if (isNaN(numValue) && input.value !== '') {
			error = 'Please enter a valid number';
			return;
		}

		if (min !== undefined && numValue < min) {
			error = `Value must be at least ${min}`;
			return;
		}

		if (max !== undefined && numValue > max) {
			error = `Value must be at most ${max}`;
			return;
		}

		error = '';
		if (!isNaN(numValue)) {
			onchange(numValue);
		}
	}
</script>

<div>
	<label for={id} class="block text-sm font-medium text-[var(--color-text-muted)]">
		{label}
		{#if required}
			<span class="text-[var(--color-error)]">*</span>
		{/if}
	</label>
	<div class="mt-1 flex rounded-md shadow-sm">
		<input
			type="number"
			{id}
			value={value ?? ''}
			{min}
			{max}
			{step}
			{placeholder}
			oninput={handleInput}
			class="block w-full border bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:ring-1
				{error
				? 'border-[var(--color-error)] focus:border-[var(--color-error)] focus:ring-[var(--color-error)]'
				: 'border-[var(--color-border)] focus:border-[var(--color-accent)] focus:ring-[var(--color-accent)]'}
				{unit ? 'rounded-l-md rounded-r-none' : 'rounded-md'}"
			aria-invalid={!!error}
			aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
		/>
		{#if unit}
			<span
				class="inline-flex items-center rounded-r-md border border-l-0 border-[var(--color-border)] bg-[var(--color-surface-elevated)] px-3 text-sm text-[var(--color-text-muted)]"
			>
				{unit}
			</span>
		{/if}
	</div>
	{#if error}
		<p id="{id}-error" class="mt-1 text-xs text-[var(--color-error)]">{error}</p>
	{:else if hint}
		<p id="{id}-hint" class="mt-1 text-xs text-[var(--color-text-subtle)]">{hint}</p>
	{/if}
</div>
