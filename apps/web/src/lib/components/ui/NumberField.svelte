<!--
	A numeric input in the project's display unit for its category. It shows the stored SI value
	converted to that unit (6 significant digits), and on change (Enter or leaving the field)
	parses what was typed, converts it to SI, checks the schema bounds and calls `onchange` with
	the SI value. Text left as shown stores nothing, so a value is never rounded to its display.
	Text that is not a number, or a value out of bounds, is reported next to the field (and
	announced) and never stored, so NaN is never written. Escape reverts edited text. An `error`
	from the owner (a required value still to enter when its form is submitted) is shown the same
	way, after the field's own.

	In a scenario (field-mode.ts) the field is locked, read-only but focusable, unless it is a
	scenario value (`change`: it then shows "Changed", the base value and Reset when the scenario
	changes it) or `shared` by every case.
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
	import ChangeNote from './ChangeNote.svelte';
	import { isLocked, useFieldMode, type FieldChange } from './field-mode';
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
		/** A note about its value (always shown): what applies, what a blank means. */
		hint?: string;
		/** Static explanation: shown while the field has focus (and with the pane's help on). */
		help?: string;
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
		/** A scenario value: what its form shows about it (editable in a scenario). */
		change?: FieldChange | null;
		/** Shared by every case: edited in a scenario too, on the base. */
		shared?: boolean;
		/** Show the change note here (false: the field's group shows one). */
		changeNote?: boolean;
		/** Ids of other elements that describe the input (after its own), e.g. its group's note. */
		describedby?: string;
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
		help,
		placeholder,
		warning = null,
		error: ownerError = null,
		hideLabel = false,
		compact = false,
		disabled = false,
		onchange,
		oninput,
		change = null,
		shared = false,
		changeNote = true,
		describedby
	}: Props = $props();

	const mode = useFieldMode();
	const locked = $derived(isLocked(mode, change, shared));
	const changed = $derived(!!change?.inScenario && change.changed);
	const noted = $derived(
		changeNote &&
			!!change &&
			((change.inScenario && change.changed) || (!change.inScenario && change.setBy.length > 0))
	);

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

	function changedText(event: Event & { currentTarget: HTMLInputElement }) {
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

<div class={hideLabel ? 'min-w-0' : 'field'}>
	<label for={id} class={hideLabel ? 'sr-only' : 'label mb-1'}>
		{label}
	</label>
	<div class="flex min-w-0 items-stretch">
		<div class="relative min-w-0 flex-1">
			<input
				{id}
				class={[
					'input',
					unitText && !compact && 'rounded-r-none',
					locked && 'bg-slate-50 pr-8',
					changed && 'border-2 border-teal-600'
				]}
				type="text"
				inputmode={allowsNegative ? 'text' : 'decimal'}
				autocomplete="off"
				spellcheck="false"
				{placeholder}
				{disabled}
				readonly={locked}
				aria-label={unitText ? `${label} (${unitText})` : undefined}
				value={text}
				aria-invalid={error ? 'true' : undefined}
				aria-describedby={[
					noted && `${id}-change`,
					locked && `${id}-locked`,
					error && `${id}-error`,
					warning && `${id}-warning`,
					hint && `${id}-hint`,
					help && `${id}-help`,
					describedby
				]
					.filter(Boolean)
					.join(' ') || undefined}
				oninput={(event) => {
					text = event.currentTarget.value;
					enteredText = null;
					oninput?.();
				}}
				onchange={changedText}
				onkeydown={keydown}
			/>
			{#if locked}
				<Icon
					name="lock"
					class="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2 text-slate-500"
				/>
				<span id="{id}-locked" class="sr-only">Same in every scenario.</span>
			{/if}
		</div>
		{#if unitText && !compact}
			<span
				class="inline-flex min-h-ctl shrink-0 items-center rounded-r-md border border-l-0 border-slate-300 bg-slate-50 px-2 text-sm text-slate-600"
				aria-hidden="true">{unitText}</span
			>
		{/if}
	</div>
	{#if noted && change}<ChangeNote {change} id="{id}-change" />{/if}
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
	{#if help}
		<p id="{id}-help" class="hint help">{help}</p>
	{/if}
</div>
