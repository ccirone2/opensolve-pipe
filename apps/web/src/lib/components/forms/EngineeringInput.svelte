<script lang="ts">
	/**
	 * Engineering Input Component
	 *
	 * A composite form control for numerical values with integrated unit selection.
	 * Designed for technical/engineering applications handling physical quantities.
	 *
	 * Features:
	 * - Numerical input with hidden spin buttons
	 * - Unit selector dropdown with keyboard navigation
	 * - Focus states with visual ring
	 * - Disabled state support
	 * - Error and hint text
	 */

	interface Props {
		/** Unique ID for the input element. */
		id: string;
		/** Label text to display above the input. */
		label: string;
		/** Current numerical value. */
		value: number | null;
		/** Currently selected unit. */
		unit: string;
		/** Available unit options. */
		units: string[];
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
		/** Whether the component is disabled. */
		disabled?: boolean;
		/** Callback when value changes. */
		onchange?: (value: number | null, unit: string) => void;
		/** Callback when unit changes. */
		onunitchange?: (oldUnit: string, newUnit: string, value: number | null) => void;
	}

	let {
		id,
		label,
		value = $bindable(null),
		unit = $bindable(''),
		units,
		min,
		max,
		step = 'any',
		required = false,
		placeholder,
		hint,
		disabled = false,
		onchange,
		onunitchange
	}: Props = $props();

	let error = $state('');
	let dropdownOpen = $state(false);
	let unitButtonRef: HTMLButtonElement | null = $state(null);

	/**
	 * Validate and handle input changes.
	 */
	function handleInput(e: Event) {
		const input = e.target as HTMLInputElement;
		const rawValue = input.value;

		// Empty input
		if (rawValue === '') {
			if (required) {
				error = 'This field is required';
			} else {
				error = '';
				value = null;
				onchange?.(null, unit);
			}
			return;
		}

		const numValue = parseFloat(rawValue);

		// Invalid number
		if (isNaN(numValue)) {
			error = 'Please enter a valid number';
			return;
		}

		// Range validation
		if (min !== undefined && numValue < min) {
			error = `Value must be at least ${min}`;
			return;
		}

		if (max !== undefined && numValue > max) {
			error = `Value must be at most ${max}`;
			return;
		}

		error = '';
		value = numValue;
		onchange?.(numValue, unit);
	}

	/**
	 * Toggle dropdown visibility.
	 */
	function toggleDropdown(e: Event) {
		e.preventDefault();
		e.stopPropagation();
		dropdownOpen = !dropdownOpen;
	}

	/**
	 * Select a unit from the dropdown.
	 */
	function selectUnit(newUnit: string) {
		if (newUnit !== unit) {
			const oldUnit = unit;
			unit = newUnit;
			onunitchange?.(oldUnit, newUnit, value);
			onchange?.(value, newUnit);
		}
		dropdownOpen = false;
		unitButtonRef?.focus();
	}

	/**
	 * Get the index of the currently selected unit.
	 */
	function getCurrentUnitIndex(): number {
		return units.indexOf(unit);
	}

	/**
	 * Cycle to the next or previous unit.
	 */
	function cycleUnit(direction: 'next' | 'prev') {
		if (units.length <= 1) return;

		const currentIndex = getCurrentUnitIndex();
		let newIndex: number;

		if (direction === 'next') {
			newIndex = (currentIndex + 1) % units.length;
		} else {
			newIndex = (currentIndex - 1 + units.length) % units.length;
		}

		selectUnit(units[newIndex]);
	}

	/**
	 * Handle keyboard navigation on unit button.
	 */
	function handleUnitKeydown(e: KeyboardEvent) {
		switch (e.key) {
			case 'ArrowDown':
			case 'ArrowRight':
				e.preventDefault();
				cycleUnit('next');
				break;
			case 'ArrowUp':
			case 'ArrowLeft':
				e.preventDefault();
				cycleUnit('prev');
				break;
			case 'Enter':
			case ' ':
				e.preventDefault();
				dropdownOpen = !dropdownOpen;
				break;
			case 'Escape':
				e.preventDefault();
				dropdownOpen = false;
				break;
		}
	}

	/**
	 * Close dropdown when clicking outside.
	 */
	function handleClickOutside(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (!target.closest('.unit-selector')) {
			dropdownOpen = false;
		}
	}

	/**
	 * Handle global keydown for Escape.
	 */
	function handleGlobalKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && dropdownOpen) {
			dropdownOpen = false;
		}
	}

	// Setup global event listeners
	$effect(() => {
		if (typeof window !== 'undefined') {
			document.addEventListener('click', handleClickOutside);
			document.addEventListener('keydown', handleGlobalKeydown);

			return () => {
				document.removeEventListener('click', handleClickOutside);
				document.removeEventListener('keydown', handleGlobalKeydown);
			};
		}
	});
</script>

<div class="engineering-input" class:disabled>
	<label for={id} class="input-label">
		{label}
		{#if required}
			<span class="text-[var(--color-error)]">*</span>
		{/if}
	</label>

	<div class="input-wrapper">
		<input
			type="number"
			{id}
			class="value-input"
			value={value ?? ''}
			{min}
			{max}
			{step}
			{placeholder}
			{disabled}
			aria-invalid={!!error}
			aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
			oninput={handleInput}
		/>

		{#if units.length > 0}
			<div class="unit-selector">
				<button
					type="button"
					class="unit-button"
					class:open={dropdownOpen}
					{disabled}
					aria-haspopup="listbox"
					aria-expanded={dropdownOpen}
					aria-label="Select unit"
					bind:this={unitButtonRef}
					onclick={toggleDropdown}
					onkeydown={handleUnitKeydown}
				>
					<span class="unit-text">{unit}</span>
					<svg class="chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"
						></path>
					</svg>
				</button>

				<div class="unit-dropdown" class:open={dropdownOpen} role="listbox" aria-label="Unit options">
					{#each units as unitOption (unitOption)}
						<button
							type="button"
							class="unit-option"
							class:selected={unitOption === unit}
							role="option"
							aria-selected={unitOption === unit}
							onclick={() => selectUnit(unitOption)}
						>
							{unitOption}
						</button>
					{/each}
				</div>
			</div>
		{/if}
	</div>

	{#if error}
		<p id="{id}-error" class="input-error">{error}</p>
	{:else if hint}
		<p id="{id}-hint" class="input-hint">{hint}</p>
	{/if}
</div>
