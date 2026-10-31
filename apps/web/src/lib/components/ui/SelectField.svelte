<!--
	A labelled <select> that reports the chosen value. In a scenario (field-mode.ts) it is locked
	unless it is a scenario value (`change`) or `shared`: then it is drawn as a read-only text
	input showing the chosen option's label (still focusable, "Same in every scenario").

	It always shows `value`: a choice its owner does not store (an edit refused, or an option that
	starts an action, such as "New entry…") goes back to the value once the owner has answered.
-->
<script lang="ts" module>
	export interface SelectOption<V extends string> {
		value: V;
		label: string;
		disabled?: boolean;
		/** Options with the same group are shown under that heading. */
		group?: string;
	}
</script>

<script lang="ts" generics="T extends string">
	import { tick } from 'svelte';
	import ChangeNote from './ChangeNote.svelte';
	import { isLocked, useFieldMode, type FieldChange } from './field-mode';
	import Icon from './Icon.svelte';

	interface Props {
		label: string;
		value: T;
		options: readonly SelectOption<T>[];
		/** A note about its value (always shown). */
		hint?: string;
		/** Static explanation: shown while the field has focus (and with the pane's help on). */
		help?: string;
		/** Ids of other elements that describe the select (after its hint), e.g. a note about it. */
		describedby?: string;
		hideLabel?: boolean;
		disabled?: boolean;
		class?: string;
		onchange: (value: T) => void;
		/** A scenario value: what its form shows about it (editable in a scenario). */
		change?: FieldChange | null;
		/** Shared by every case: edited in a scenario too, on the base. */
		shared?: boolean;
		/** Show the change note here (false: the field's group shows one). */
		changeNote?: boolean;
		/**
		 * Its value is missing or refused (aria-invalid): the error itself is shown by the caller,
		 * which names it in `describedby`.
		 */
		invalid?: boolean;
	}

	let {
		label,
		value,
		options,
		hint,
		help,
		describedby,
		hideLabel = false,
		disabled = false,
		class: className = '',
		onchange,
		change = null,
		shared = false,
		changeNote = true,
		invalid = false
	}: Props = $props();

	const id = $props.id();
	const mode = useFieldMode();
	let select: HTMLSelectElement | undefined = $state();

	/** Report a choice; then show the value the owner holds (it may not have taken the choice). */
	async function choose(chosen: T) {
		onchange(chosen);
		await tick();
		if (select && select.value !== value) select.value = value;
	}
	const locked = $derived(isLocked(mode, change, shared));
	const changed = $derived(!!change?.inScenario && change.changed);
	const noted = $derived(
		changeNote &&
			!!change &&
			((change.inScenario && change.changed) || (!change.inScenario && change.setBy.length > 0))
	);
	const described = $derived(
		[
			noted && `${id}-change`,
			locked && `${id}-locked`,
			hint && `${id}-hint`,
			help && `${id}-help`,
			describedby
		]
			.filter(Boolean)
			.join(' ') || undefined
	);

	const groups = $derived.by(() => {
		const result: { group: string | undefined; options: SelectOption<T>[] }[] = [];
		for (const option of options) {
			const last = result[result.length - 1];
			if (last && last.group === option.group) last.options.push(option);
			else result.push({ group: option.group, options: [option] });
		}
		return result;
	});
</script>

<div class={[hideLabel ? 'min-w-0' : 'field', className]}>
	<label for={id} class={hideLabel ? 'sr-only' : 'label mb-1'}>{label}</label>
	{#if locked}
		<div class="relative">
			<input
				{id}
				class="input bg-slate-50 pr-8"
				type="text"
				readonly
				value={options.find((o) => o.value === value)?.label ?? value}
				aria-describedby={described}
			/>
			<Icon
				name="lock"
				class="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2 text-slate-500"
			/>
			<span id="{id}-locked" class="sr-only">Same in every scenario.</span>
		</div>
	{:else}
		<select
			bind:this={select}
			{id}
			class={['input pr-8', changed && 'border-2 border-teal-600']}
			{disabled}
			{value}
			aria-invalid={invalid ? 'true' : undefined}
			aria-describedby={described}
			onchange={(event) => void choose(event.currentTarget.value as T)}
		>
			{#each groups as group, g (g)}
				{#if group.group}
					<optgroup label={group.group}>
						{#each group.options as option (option.value)}
							<option value={option.value} disabled={option.disabled}>{option.label}</option>
						{/each}
					</optgroup>
				{:else}
					{#each group.options as option (option.value)}
						<option value={option.value} disabled={option.disabled}>{option.label}</option>
					{/each}
				{/if}
			{/each}
		</select>
	{/if}
	{#if noted && change}<ChangeNote {change} id="{id}-change" />{/if}
	{#if hint}<p id="{id}-hint" class="hint">{hint}</p>{/if}
	{#if help}<p id="{id}-help" class="hint help">{help}</p>{/if}
</div>
