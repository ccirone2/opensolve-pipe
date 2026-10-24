<!--
	A numeric input in the project's display unit for its category. It shows the stored SI value
	converted to that unit (6 significant digits), and on change (Enter or leaving the field)
	parses what was typed, converts it to SI, checks the schema bounds and calls `onchange` with
	the SI value. Text left as shown stores nothing, so a value is never rounded to its display.
	Text that is not a number, or a value out of bounds, is reported next to the field (and
	announced) and never stored, so NaN is never written. Escape reverts edited text. An `error`
	from the owner (a required value still to enter when its form is submitted) is shown the same
	way, after the field's own.
-->
<script lang="ts">
	import type { UnitPreferences } from '$lib/api/types';
	import { boundsProblem, type Bounds } from '$lib/utils/schema-bounds';
	import {
		displayUnit,
		formatNumber,
		formatValue,
		fromSI,
		parseNumber,
		toSI,
		unitLabel,
		type UnitCategory
	} from '$lib/utils/units';
	import Icon from './Icon.svelte';

	interface Props {
		label: string;
		/** Stored value, SI. */
		value: number | null | undefined;
		category: UnitCategory;
		units: UnitPreferences;
		/** A gauge pressure (label "kPa(g)", "psig"). */
		gauge?: boolean;
		/** An absolute pressure (label "kPa(a)", "psia"). */
		absolute?: boolean;
		/** Allowed range, SI (usually from the API schema). */
		bounds?: Bounds;
		/** Empty is allowed and stored as null. */
		optional?: boolean;
		integer?: boolean;
		hint?: string;
		/** Shown in the empty field, e.g. what a blank optional field means. */
		placeholder?: string;
		/** A note that does not block storing (e.g. outside a correlation's range). */
		warning?: string | null;
		/** An error the owner reports (e.g. a value it requires, not entered yet); null for none. */
		error?: string | null;
		/** Label visible only to assistive technology (compact tables). */
		hideLabel?: boolean;
		/** No unit box next to the input (the unit is in a table header); still in the label. */
		compact?: boolean;
		disabled?: boolean;
		/** Receives the SI value. Return false when it was not accepted (the text is reset). */
		onchange: (value: number | null) => boolean | void;
		/**
		 * Called on each edit of the text, before it is stored: e.g. for the owner to drop its
		 * `error` about the value that was there while the user types, not when the field stores
		 * the value on losing focus (which a press on a button below it does: anything that moves
		 * then moves the button under the pointer, and the click is lost).
		 */
		oninput?: () => void;
	}

	let {
		label,
		value,
		category,
		units,
		gauge = false,
		absolute = false,
		bounds = {},
		optional = false,
		integer = false,
		hint,
		placeholder,
		warning = null,
		error: ownerError = null,
		hideLabel = false,
		compact = false,
		disabled = false,
		onchange,
		oninput
	}: Props = $props();

	/** Significant digits shown (more would suggest precision the inputs do not have). */
	const DISPLAY_DIGITS = 6;
	const id = $props.id();
	let errorElement: HTMLElement | undefined = $state();
	const unit = $derived(displayUnit(category, units));
	const unitText = $derived(unitLabel(category, unit, { gauge, absolute }));
	const shown = $derived(
		value === null || value === undefined || !Number.isFinite(value)
			? ''
			: formatNumber(fromSI(value, unit), DISPLAY_DIGITS)
	);
	// Follows the stored value; typing overrides it until the stored value changes.
	let text = $derived(shown);
	// Cleared whenever the stored value changes.
	let inputError = $derived.by((): string | null => {
		void shown;
		return null;
	});
	/** What the field reports: its own problem with the typed text first, else the owner's. */
	const error = $derived(inputError ?? ownerError);

	const allowsNegative = $derived(
		bounds.minimum === undefined && bounds.exclusiveMinimum === undefined
			? true
			: (bounds.minimum ?? bounds.exclusiveMinimum ?? 0) < 0
	);

	function format(si: number): string {
		return formatValue(si, category, units, 6, { gauge, absolute });
	}

	// Keep a new error message in view (e.g. above a phone's bottom bar).
	$effect(() => {
		if (error) errorElement?.scrollIntoView?.({ block: 'nearest' });
	});

	function commit() {
		const trimmed = text.trim();
		if (trimmed === shown) {
			// Unchanged: the stored value stands (re-storing the display would round it).
			text = shown;
			inputError = null;
			return;
		}
		if (trimmed === '') {
			if (!optional) {
				inputError = 'Enter a value.';
				return;
			}
			inputError = null;
			if (value !== null && value !== undefined && onchange(null) === false) text = shown;
			return;
		}
		const number = parseNumber(trimmed);
		if (number === null) {
			inputError = 'Enter a number, e.g. 12.5 or 1.2e-3.';
			return;
		}
		if (integer && !Number.isInteger(number)) {
			inputError = 'Enter a whole number.';
			return;
		}
		const si = toSI(number, unit);
		const problem = boundsProblem(si, bounds, format);
		if (problem) {
			inputError = problem;
			return;
		}
		inputError = null;
		if (onchange(si) === false) text = shown;
	}

	/**
	 * The field's text as committed by Enter, until the next keystroke (plain, not reactive). The
	 * browser still reports a change for it when the field loses focus, including when the field
	 * is removed because the commit replaced it (e.g. the third point of a new pump curve creates
	 * the curve and its own table): that change is the same commit, and is ignored without
	 * reading this component's state, which may be in the middle of being destroyed.
	 */
	let enteredText: string | null = null;

	function changed(event: Event & { currentTarget: HTMLInputElement }) {
		if (event.currentTarget.value === enteredText) return;
		commit();
	}

	function keydown(event: KeyboardEvent & { currentTarget: HTMLInputElement }) {
		if (event.key === 'Enter') {
			event.preventDefault();
			commit();
			enteredText = event.currentTarget.value;
		} else if (event.key === 'Escape' && (text !== shown || inputError)) {
			// Revert only the field: preventDefault also keeps an enclosing <dialog> open (its
			// close request on Escape is skipped for a cancelled keydown).
			event.preventDefault();
			event.stopPropagation();
			text = shown;
			inputError = null;
		}
	}
</script>

<div class="min-w-0">
	<label for={id} class={hideLabel ? 'sr-only' : 'label mb-1'}>
		{label}
	</label>
	<div class="flex min-w-0 items-stretch">
		<input
			{id}
			class={['input', unitText && !compact && 'rounded-r-none']}
			type="text"
			inputmode={allowsNegative ? 'text' : 'decimal'}
			autocomplete="off"
			spellcheck="false"
			{placeholder}
			{disabled}
			aria-label={unitText ? `${label} (${unitText})` : undefined}
			value={text}
			aria-invalid={error ? 'true' : undefined}
			aria-describedby={[error && `${id}-error`, warning && `${id}-warning`, hint && `${id}-hint`]
				.filter(Boolean)
				.join(' ') || undefined}
			oninput={(event) => {
				text = event.currentTarget.value;
				enteredText = null;
				oninput?.();
			}}
			onchange={changed}
			onkeydown={keydown}
		/>
		{#if unitText && !compact}
			<span
				class="inline-flex min-h-11 shrink-0 items-center rounded-r-md border border-l-0 border-slate-300 bg-slate-50 px-2 text-sm text-slate-600"
				aria-hidden="true">{unitText}</span
			>
		{/if}
	</div>
	{#if error}
		<p
			bind:this={errorElement}
			id="{id}-error"
			role="alert"
			class="mt-1 flex scroll-mb-4 items-start gap-1 text-sm text-red-700"
		>
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span>{error}</span>
		</p>
	{/if}
	{#if warning}
		<p id="{id}-warning" class="mt-1 flex items-start gap-1 text-sm text-amber-800">
			<Icon name="alert" class="mt-0.5 size-4 shrink-0" /><span>{warning}</span>
		</p>
	{/if}
	{#if hint}
		<p id="{id}-hint" class="hint">{hint}</p>
	{/if}
</div>
