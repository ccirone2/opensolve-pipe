<!-- A labelled <select> that reports the chosen value. -->
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
	interface Props {
		label: string;
		value: T;
		options: readonly SelectOption<T>[];
		hint?: string;
		/** Ids of other elements that describe the select (after its hint), e.g. a note about it. */
		describedby?: string;
		hideLabel?: boolean;
		disabled?: boolean;
		class?: string;
		onchange: (value: T) => void;
	}

	let {
		label,
		value,
		options,
		hint,
		describedby,
		hideLabel = false,
		disabled = false,
		class: className = '',
		onchange
	}: Props = $props();

	const id = $props.id();

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

<div class={['min-w-0', className]}>
	<label for={id} class={hideLabel ? 'sr-only' : 'label mb-1'}>{label}</label>
	<select
		{id}
		class="input pr-8"
		{disabled}
		{value}
		aria-describedby={[hint && `${id}-hint`, describedby].filter(Boolean).join(' ') || undefined}
		onchange={(event) => onchange(event.currentTarget.value as T)}
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
	{#if hint}<p id="{id}-hint" class="hint">{hint}</p>{/if}
</div>
