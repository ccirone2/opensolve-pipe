<!--
	A choice of two values as one row of segments (a radio group): one tap on a phone, where a
	<select> takes two (proposal build-density.md §11). It behaves as SelectField does in a scenario
	(field-mode.ts): locked, it is drawn as a read-only text input showing the chosen value's label
	(still focusable, "Same in every scenario"); a scenario value shows "Changed", the base value
	and Reset (ChangeNote), and its description names them.
-->
<script lang="ts" generics="T extends string">
	import { tick } from 'svelte';
	import ChangeNote from './ChangeNote.svelte';
	import { isLocked, useFieldMode, type FieldChange } from './field-mode';
	import Icon from './Icon.svelte';
	import type { SelectOption } from './SelectField.svelte';

	interface Props {
		label: string;
		value: T;
		options: readonly SelectOption<T>[];
		/** A note about its value (always shown). */
		hint?: string;
		/** Static explanation: shown while the field has focus (and with the pane's help on). */
		help?: string;
		onchange: (value: T) => void;
		/** A scenario value: what its form shows about it (editable in a scenario). */
		change?: FieldChange | null;
		/** Shared by every case: edited in a scenario too, on the base. */
		shared?: boolean;
	}

	let {
		label,
		value,
		options,
		hint,
		help,
		onchange,
		change = null,
		shared = false
	}: Props = $props();

	const id = $props.id();
	const mode = useFieldMode();
	const locked = $derived(isLocked(mode, change, shared));
	const changed = $derived(!!change?.inScenario && change.changed);
	const noted = $derived(
		!!change &&
			((change.inScenario && change.changed) || (!change.inScenario && change.setBy.length > 0))
	);
	let group: HTMLElement | undefined = $state();

	/** Report a choice; then show the value the owner holds (it may not have taken the choice). */
	async function choose(chosen: T) {
		onchange(chosen);
		await tick();
		for (const input of group?.querySelectorAll('input') ?? [])
			input.checked = input.value === value;
	}

	const described = $derived(
		[noted && `${id}-change`, locked && `${id}-locked`, hint && `${id}-hint`, help && `${id}-help`]
			.filter(Boolean)
			.join(' ') || undefined
	);
</script>

<div class="field">
	{#if locked}
		<label for={id} class="label">{label}</label>
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
		<span id="{id}-label" class="label">{label}</span>
		<div
			bind:this={group}
			role="radiogroup"
			aria-labelledby="{id}-label"
			aria-describedby={described}
			class={[
				'flex min-h-ctl overflow-hidden rounded-md border border-slate-300',
				changed && 'border-2 border-teal-600'
			]}
		>
			{#each options as option, i (option.value)}
				<label
					class={[
						'relative flex min-w-0 flex-1 cursor-pointer items-center justify-center px-2 text-center text-sm leading-tight',
						'has-[:focus-visible]:outline-2 has-[:focus-visible]:-outline-offset-2 has-[:focus-visible]:outline-blue-600',
						i > 0 && 'border-l border-slate-300',
						option.value === value
							? 'bg-blue-700 font-medium text-white'
							: 'bg-white text-slate-800 hover:bg-slate-50'
					]}
				>
					<input
						type="radio"
						class="absolute inset-0 cursor-pointer appearance-none opacity-0"
						name="{id}-choice"
						value={option.value}
						checked={option.value === value}
						disabled={option.disabled}
						onchange={() => void choose(option.value)}
					/>
					<!-- The radio covers its segment: the whole segment is its target. -->
					{option.label}
				</label>
			{/each}
		</div>
	{/if}
	{#if noted && change}<ChangeNote {change} id="{id}-change" />{/if}
	{#if hint}<p id="{id}-hint" class="hint">{hint}</p>{/if}
	{#if help}<p id="{id}-help" class="hint help">{help}</p>{/if}
</div>
