<script lang="ts">
	/**
	 * Wrapper component for rendering a single component in the schematic.
	 * Handles component type detection and renders the appropriate symbol.
	 */
	import type { Component, ComponentResult } from '$lib/models';
	import {
		isReservoir,
		isTank,
		isJunction,
		isPump,
		isValve,
		isHeatExchanger,
		isStrainer,
		isOrifice,
		isSprinkler,
		isPlug,
		isIdealReferenceNode,
		isNonIdealReferenceNode,
		isTeeBranch,
		isWyeBranch,
		isCrossBranch,
		type PumpComponent,
		type ValveComponent
	} from '$lib/models';
	import {
		ReservoirSymbol,
		TankSymbol,
		JunctionSymbol,
		PumpSymbol,
		ValveSymbol,
		HeatExchangerSymbol,
		StrainerSymbol,
		OrificeSymbol,
		SprinklerSymbol,
		PlugSymbol,
		ReferenceNodeSymbol,
		TeeSymbol,
		WyeSymbol,
		CrossSymbol,
		GenericSymbol
	} from './symbols';

	interface Props {
		/** The component to render. */
		component: Component;
		/** X position. */
		x: number;
		/** Y position. */
		y: number;
		/** Width. */
		width?: number;
		/** Height. */
		height?: number;
		/** Whether this component is selected. */
		selected?: boolean;
		/** Component results (for tooltip display). */
		result?: ComponentResult;
		/** Click handler. */
		onclick?: (componentId: string) => void;
		/** Selection change handler. */
		onselect?: (componentId: string) => void;
	}

	let {
		component,
		x,
		y,
		width = 60,
		height = 40,
		selected = false,
		result,
		onclick,
		onselect
	}: Props = $props();

	let hovered = $state(false);
	let showTooltip = $state(false);

	// Convert top-left position (from layout) to center position (for symbols)
	// The layout provides top-left coordinates, but SymbolBase expects center coordinates
	let centerX = $derived(x + width / 2);
	let centerY = $derived(y + height / 2);

	// Determine symbol dimensions based on component type
	let symbolDimensions = $derived.by(() => {
		if (isReservoir(component)) return { width: 60, height: 50 };
		if (isTank(component)) return { width: 50, height: 60 };
		if (isJunction(component)) return { width: 20, height: 20 };
		if (isPump(component)) return { width: 50, height: 50 };
		if (isValve(component)) return { width: 40, height: 30 };
		if (isHeatExchanger(component)) return { width: 60, height: 40 };
		if (isStrainer(component)) return { width: 50, height: 40 };
		if (isOrifice(component)) return { width: 40, height: 30 };
		if (isSprinkler(component)) return { width: 40, height: 40 };
		if (isPlug(component)) return { width: 30, height: 24 };
		if (isIdealReferenceNode(component) || isNonIdealReferenceNode(component)) return { width: 40, height: 40 };
		if (isTeeBranch(component)) return { width: 50, height: 40 };
		if (isWyeBranch(component)) return { width: 50, height: 40 };
		if (isCrossBranch(component)) return { width: 50, height: 50 };
		return { width, height };
	});

	// Get type label abbreviation for generic symbols (fallback only)
	let typeLabel = $derived.by(() => {
		// Only used for truly unknown component types
		return '?';
	});

	function handleClick(): void {
		onclick?.(component.id);
		onselect?.(component.id);
	}

	function handleMouseEnter(): void {
		hovered = true;
		showTooltip = true;
	}

	function handleMouseLeave(): void {
		hovered = false;
		showTooltip = false;
	}

	// Format result for tooltip
	let tooltipContent = $derived.by(() => {
		if (!result) return null;
		const lines: string[] = [];
		if (result.pressure !== undefined) {
			lines.push(`Pressure: ${result.pressure.toFixed(1)} psi`);
		}
		if (result.hgl !== undefined) {
			lines.push(`HGL: ${result.hgl.toFixed(1)} ft`);
		}
		return lines.length > 0 ? lines : null;
	});
</script>

<g class="schematic-component" data-component-id={component.id}>
	{#if isReservoir(component)}
		<ReservoirSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isTank(component)}
		<TankSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			level={component.initial_level ?? 0.5}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isJunction(component)}
		<JunctionSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isPump(component)}
		<PumpSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			status={(component as PumpComponent).status ?? 'running'}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isValve(component)}
		<ValveSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			valveType={(component as ValveComponent).valve_type}
			status={(component as ValveComponent).status ?? 'active'}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isHeatExchanger(component)}
		<HeatExchangerSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isStrainer(component)}
		<StrainerSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isOrifice(component)}
		<OrificeSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isSprinkler(component)}
		<SprinklerSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isPlug(component)}
		<PlugSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isIdealReferenceNode(component)}
		<ReferenceNodeSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			isIdeal={true}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isNonIdealReferenceNode(component)}
		<ReferenceNodeSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			isIdeal={false}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isTeeBranch(component)}
		<TeeSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isWyeBranch(component)}
		<WyeSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else if isCrossBranch(component)}
		<CrossSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={component.name}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{:else}
		<!-- Fallback for unknown component types -->
		<GenericSymbol
			x={centerX}
			y={centerY}
			width={symbolDimensions.width}
			height={symbolDimensions.height}
			{selected}
			{hovered}
			label={(component as Component).name}
			{typeLabel}
			onclick={handleClick}
			onmouseenter={handleMouseEnter}
			onmouseleave={handleMouseLeave}
		/>
	{/if}

	<!-- Tooltip -->
	{#if showTooltip && (tooltipContent || component.name)}
		<g transform="translate({x}, {y - symbolDimensions.height / 2 - 40})">
			<rect
				x="-60"
				y="-10"
				width="120"
				height={tooltipContent ? 40 + tooltipContent.length * 14 : 30}
				rx="4"
				class="fill-[var(--color-surface-elevated)] stroke-[var(--color-border)]"
				filter="drop-shadow(0 2px 4px rgba(0,0,0,0.1))"
			/>
			<text
				x="0"
				y="6"
				text-anchor="middle"
				class="fill-[var(--color-text)] text-xs font-medium"
			>
				{component.name}
			</text>
			{#if tooltipContent}
				{#each tooltipContent as line, i}
					<text
						x="0"
						y={22 + i * 14}
						text-anchor="middle"
						class="fill-[var(--color-text-muted)] text-[10px]"
					>
						{line}
					</text>
				{/each}
			{/if}
		</g>
	{/if}
</g>
