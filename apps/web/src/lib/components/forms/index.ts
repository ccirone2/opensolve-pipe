/**
 * Component Property Forms
 *
 * Dedicated forms for editing properties of each component type.
 * Each form includes validation, unit display, and mobile-friendly inputs.
 */

import type { ComponentType } from '$lib/models';
import type { Component as SvelteComponent } from 'svelte';

// Base components
export { default as NumberInput } from './NumberInput.svelte';
export { default as EngineeringInput } from './EngineeringInput.svelte';

// Node components
export { default as ReservoirForm } from './ReservoirForm.svelte';
export { default as TankForm } from './TankForm.svelte';
export { default as JunctionForm } from './JunctionForm.svelte';
export { default as SprinklerForm } from './SprinklerForm.svelte';
export { default as OrificeForm } from './OrificeForm.svelte';

// Link components
export { default as PumpForm } from './PumpForm.svelte';
export { default as ValveForm } from './ValveForm.svelte';
export { default as HeatExchangerForm } from './HeatExchangerForm.svelte';
export { default as StrainerForm } from './StrainerForm.svelte';

// Boundary components
export { default as ReferenceNodeForm } from './ReferenceNodeForm.svelte';
export { default as PlugForm } from './PlugForm.svelte';

// Branch components
export { default as TeeBranchForm } from './TeeBranchForm.svelte';
export { default as WyeBranchForm } from './WyeBranchForm.svelte';
export { default as CrossBranchForm } from './CrossBranchForm.svelte';

// Piping components
export { default as PipeForm } from './PipeForm.svelte';
export { default as FittingsTable } from './FittingsTable.svelte';

// --- Form Registry ---
// Maps ComponentType → form component for dynamic rendering.
// ReferenceNodeForm handles both ideal and non-ideal types.

import ReservoirForm from './ReservoirForm.svelte';
import TankForm from './TankForm.svelte';
import JunctionForm from './JunctionForm.svelte';
import PumpForm from './PumpForm.svelte';
import ValveForm from './ValveForm.svelte';
import HeatExchangerForm from './HeatExchangerForm.svelte';
import StrainerForm from './StrainerForm.svelte';
import OrificeForm from './OrificeForm.svelte';
import SprinklerForm from './SprinklerForm.svelte';
import ReferenceNodeForm from './ReferenceNodeForm.svelte';
import PlugForm from './PlugForm.svelte';
import TeeBranchForm from './TeeBranchForm.svelte';
import WyeBranchForm from './WyeBranchForm.svelte';
import CrossBranchForm from './CrossBranchForm.svelte';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const FORM_REGISTRY: Record<ComponentType, SvelteComponent<any>> = {
	reservoir: ReservoirForm,
	tank: TankForm,
	junction: JunctionForm,
	pump: PumpForm,
	valve: ValveForm,
	heat_exchanger: HeatExchangerForm,
	strainer: StrainerForm,
	orifice: OrificeForm,
	sprinkler: SprinklerForm,
	ideal_reference_node: ReferenceNodeForm,
	non_ideal_reference_node: ReferenceNodeForm,
	plug: PlugForm,
	tee_branch: TeeBranchForm,
	wye_branch: WyeBranchForm,
	cross_branch: CrossBranchForm
};
