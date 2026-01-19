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
	<label for={id} class="block text-sm font-medium text-gray-700">
		{label}
		{#if required}
			<span class="text-red-500">*</span>
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
			class="block w-full rounded-{unit ? 'l' : ''}md border px-3 py-2 text-sm focus:outline-none focus:ring-1
				{error
				? 'border-red-300 focus:border-red-500 focus:ring-red-500'
				: 'border-gray-300 focus:border-blue-500 focus:ring-blue-500'}
				{unit ? 'rounded-r-none' : ''}"
			aria-invalid={!!error}
			aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
		/>
		{#if unit}
			<span
				class="inline-flex items-center rounded-r-md border border-l-0 border-gray-300 bg-gray-50 px-3 text-sm text-gray-500"
			>
				{unit}
			</span>
		{/if}
	</div>
	{#if error}
		<p id="{id}-error" class="mt-1 text-xs text-red-600">{error}</p>
	{:else if hint}
		<p id="{id}-hint" class="mt-1 text-xs text-gray-500">{hint}</p>
	{/if}
</div>
