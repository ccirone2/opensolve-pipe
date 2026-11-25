<!--
	A numeric input in the project's display unit for its category. It shows the stored SI value
	converted to that unit (6 significant digits), and on change (Enter or leaving the field)
	parses what was typed, converts it to SI, checks the schema bounds and calls `onchange` with
	the SI value. What is typed may carry a unit of the field's quantity ("50 psi" in a kPa field,
	"100 ft" in a ft field; units.ts parseQuantity, proposal usability-entry.md §3): the field then
	shows the value in its own unit and says what it was converted from, until the next edit. Text left as shown stores nothing, so a value is never rounded to its display.
	A phone opens its text keyboard for every field (`inputmode="text"`), so a unit and a minus
	sign can be typed there too: the decimal keypad has no letters (the owner's answer of
	2026-11-25, proposals/open-defects.md W4). That keyboard neither corrects nor capitalizes what
	is typed (`autocorrect`, `autocapitalize` off), so a unit ("gpm") stays as typed.
	Text that is not a number, or a value out of bounds, is reported next to the field (and
	announced) and never stored, so NaN is never written. Escape reverts edited text. An `error`
	from the owner (a required value still to enter when its form is submitted) is shown the same
	way, after the field's own.

	In a scenario (field-mode.ts) the field is locked, read-only but focusable, unless it is a
	scenario value (`change`: it then shows "Changed", the base value and Reset when the scenario
	changes it) or `shared` by every case.
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import type { UnitPreferences } from '$lib/api/types';
	import { boundsProblem, type Bounds } from '$lib/utils/schema-bounds';
	import {
		displayUnit,
		formatNumber,
		formatValue,
		fromSI,
		parseQuantity,
		unitLabel,
		type UnitCategory
	} from '$lib/utils/units';
	import { afterTwoFrames } from '$lib/utils/live';
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
		/** Take only the display unit after a number (an NPS designation in inches). */
		ownUnitOnly?: boolean;
		/**
		 * Changed by the owner when it writes this field's value from elsewhere (a paste into its
		 * table): the field drops its own unstored text, its error and its note, even when the
		 * value written is the one it held.
		 */
		reset?: number;
		/**
		 * Offered the pasted text first (a table's column or rows, PointsTable): return true when
		 * it took the paste, and the field then takes nothing.
		 */
		onpaste?: (text: string) => boolean;
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
		describedby,
		onpaste,
		ownUnitOnly = false,
		reset = 0
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
	/**
	 * The text a stored value was converted from (typed in another unit), while that value is
	 * stored and shown in the unit it was converted to (not after the project's units change).
	 */
	let converted = $state<{ si: number; text: string; unit: string; shown: boolean } | null>(null);
	const convertedNote = $derived(
		converted && value === converted.si && unit === converted.unit
			? `Converted from ${converted.text}.`
			: null
	);
	// Once shown and then gone (another value stored, an undo, the units changed), it is dropped,
	// so a redo or a change of units back does not bring it back and announce it again.
	$effect.pre(() => {
		if (!converted) return;
		if (convertedNote) converted.shown = true;
		else if (converted.shown) converted = null;
	});
	// A value written from elsewhere (`reset`): the field's own edit, error and note go.
	let lastReset = untrack(() => reset);
	$effect.pre(() => {
		if (reset === lastReset) return;
		lastReset = reset;
		text = shown;
		inputError = null;
		converted = null;
		enteredText = null;
	});
	/** The polite line, drawn at the first conversion, and the words it says. */
	let speaking = $state(false);
	let spoken = $state('');
	let stopSaying: (() => void) | null = null;
	/** Say the note, or nothing: the line is emptied now and written two frames later. */
	function say(words: string) {
		stopSaying?.();
		speaking = true;
		spoken = '';
		stopSaying = words ? afterTwoFrames(() => (spoken = words)) : null;
	}
	$effect(() => {
		if (!convertedNote && spoken) say('');
	});
	$effect(() => () => stopSaying?.());
	/** What the field reports: its own problem with the typed text first, else the owner's. */
	const error = $derived(inputError ?? ownerError);

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
		const parsed = parseQuantity(trimmed, category, unit, { gauge, absolute, ownUnitOnly });
		if (!parsed) return;
		if (!parsed.ok) {
			inputError = parsed.error;
			return;
		}
		const si = parsed.si;
		if (integer && !Number.isInteger(fromSI(si, unit))) {
			inputError = 'Enter a whole number.';
			return;
		}
		const problem = boundsProblem(si, bounds, format);
		if (problem) {
			inputError = problem;
			return;
		}
		inputError = null;
		converted = parsed.converted ? { si, text: trimmed, unit, shown: false } : null;
		if (parsed.converted) say(`Converted from ${trimmed}.`);
		// Text typed with a unit is shown back in the field's own unit, even when the value it
		// stores is the one already stored (no new value to redraw the field).
		if (parsed.unit !== unit || /\D$/.test(trimmed)) text = shown;
		if (onchange(si) === false) {
			text = shown;
			converted = null;
		}
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
				inputmode="text"
				autocomplete="off"
				autocorrect="off"
				autocapitalize="off"
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
					convertedNote && `${id}-converted`,
					hint && `${id}-hint`,
					help && `${id}-help`,
					describedby
				]
					.filter(Boolean)
					.join(' ') || undefined}
				oninput={(event) => {
					text = event.currentTarget.value;
					enteredText = null;
					converted = null;
					oninput?.();
				}}
				onchange={changedText}
				onkeydown={keydown}
				onpaste={(event) => {
					const pasted = event.clipboardData?.getData('text/plain');
					if (!locked && pasted && onpaste?.(pasted)) {
						// The table took the paste: this field's own edit, unstored, is dropped, so
						// leaving the field does not store it over the pasted value.
						event.preventDefault();
						text = shown;
						inputError = null;
						converted = null;
						enteredText = null;
					}
				}}
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
	{#if convertedNote}
		<p id="{id}-converted" class="hint wrap-anywhere">{convertedNote}</p>
	{/if}
	<!-- The note said: a polite line drawn empty by the first conversion and written two frames
		later (ui-guide.md, One strip of live lines), so nothing in the form is live before the
		user converts a value. -->
	{#if speaking}<span class="sr-only" aria-live="polite">{spoken}</span>{/if}
	{#if hint}
		<p id="{id}-hint" class="hint">{hint}</p>
	{/if}
	{#if help}
		<p id="{id}-help" class="hint help">{help}</p>
	{/if}
</div>
