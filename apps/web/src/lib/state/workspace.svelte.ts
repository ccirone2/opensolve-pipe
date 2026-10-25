/**
 * The workspace of an open project: the project store, the API library, the navigator, and
 * the graph-edit actions the panels offer (add after / before, add branch, delete, plug,
 * connect). Each action is one undo step and moves the navigator to where the change is.
 *
 * Scenarios (proposal scenario-manager.md §6.6): `project` is the project of the case shown, the
 * base with the active scenario's changes (utils/scenarios.ts caseProject), so every form shows
 * and edits that case's values. `store.project` stays the stored base; names, display units and
 * topology are the same in every case, so `labelsProject`, `displayUnits` and the navigator read
 * it. In a scenario, edit() sorts an edit into the scenario's changes (allow-listed values), shared
 * labels (names, the project name and description, display units) or a refusal (anything else),
 * as one undo step.
 */
import { getContext, setContext, untrack } from 'svelte';
import type {
	Component,
	Flag,
	Override,
	PipeConnection,
	Project,
	Scenario,
	UnitPreferences
} from '../api/types';
import type { FieldChange } from '../components/ui/field-mode';
import type { CompareRow } from '../utils/compare';
import { flagText } from '../utils/flag-text';
import { fittingFallbackName } from '../utils/labels';
import {
	caseProject,
	changeStates,
	changeValueText,
	findScenario,
	makeOverride,
	overridesOf,
	scenarioEdit,
	scenariosOf,
	valueOf,
	fieldLabelFor,
	type CaseId,
	type ChangeTarget
} from '../utils/scenarios';
import {
	addBranch,
	addComponentAtPort,
	connectPorts,
	deleteComponent,
	disconnect,
	insertComponentInConnection,
	plugPort,
	updateComponent,
	updateConnection
} from '../utils/edit';
import { createComponent, type ComponentKind, type EnteredValues } from '../utils/factory';
import type { ElementRef } from '../utils/results';
import {
	componentById,
	connectionAtPort,
	connectionsOf,
	portById,
	type PortRef
} from '../utils/graph';
import { deepFreeze, structuralProblems, type ProjectStore } from './project.svelte';
import { LibraryStore } from './library.svelte';
import { NavigatorStore, pathAfterInsert } from './navigator.svelte';

export type Pane = 'build' | 'results';

export interface Notice {
	kind: 'error' | 'info';
	text: string;
	/** Increments with every notice, so the same text shown twice is announced twice. */
	id: number;
}

/** Kinds that can be inserted into a connection (separate inlet and outlet ports). */
export const INLINE_KINDS: readonly ComponentKind[] = [
	'pump',
	'gate',
	'ball',
	'butterfly',
	'globe',
	'check',
	'stop_check',
	'prv',
	'psv',
	'fcv',
	'tee',
	'wye'
];

export class Workspace {
	readonly store: ProjectStore;
	readonly library: LibraryStore;
	readonly nav: NavigatorStore;
	/** Pane shown on narrow screens (both are shown side by side on wide ones). */
	pane = $state<Pane>('build');
	notice = $state.raw<Notice | null>(null);
	/** The element whose results and trace are open in the results pane (null: none). */
	inspected = $state.raw<ElementRef | null>(null);
	/** The last case switch, said by a polite live region (empty: none yet). */
	announcement = $state('');
	/** The scenario manager is open. */
	managerOpen = $state(false);
	/** Project settings are open (from the header, or a fluid change's Show). */
	settingsOpen = $state(false);
	/** The scenario whose card the manager opens on (null: the active one). */
	managerFocus = $state<string | null>(null);
	/**
	 * The Results pane shows the Compare cases view instead of the active case's results (page
	 * state; only when the project has scenarios).
	 */
	comparing = $state(false);
	/** The rows of the Compare cases view (null: the defaults, derived from the project). Page state. */
	compareRows = $state.raw<CompareRow[] | null>(null);
	#noticeId = 0;
	/** The project of the case shown (the base, or the base with the active scenario's changes). */
	#caseProject: Project;

	/** Changes only when the display units change (not on every edit). */
	#unitsKey: string;
	/** Changes only when a name, a kind, the ports or a connection's ends change. */
	#labelsKey: string;

	/**
	 * The display units, as an object that stays the same across edits that keep them, so
	 * results derived from it are not rebuilt on every edit.
	 */
	displayUnits: UnitPreferences;

	/**
	 * The project for labelling results (names, kinds, port order, connection ends): updated
	 * only when one of those changes, so editing a value does not rebuild the result tables.
	 * Never use it for values.
	 */
	labelsProject: Project;

	constructor(store: ProjectStore, library: LibraryStore = new LibraryStore()) {
		this.store = store;
		this.library = library;
		this.nav = new NavigatorStore(store);
		this.#unitsKey = $derived(JSON.stringify(this.store.project.settings.units));
		this.#labelsKey = $derived(labelsKey(this.store.project));
		this.displayUnits = $derived.by(() => {
			void this.#unitsKey;
			return untrack(() => this.store.project.settings.units);
		});
		this.labelsProject = $derived.by(() => {
			void this.#labelsKey;
			return untrack(() => this.store.project);
		});
		this.#caseProject = $derived.by(() => {
			const project = this.store.project;
			const caseId = this.store.activeCase;
			return caseId === null ? project : deepFreeze(caseProject(project, caseId));
		});
		// Another project opened in this page: its page state starts as a reload's would.
		store.onLoad(() => this.#resetPage());
	}

	/**
	 * Forget the page state about the project shown (the trace open, Compare cases and its chosen
	 * rows, the scenario manager, Settings, the last case announcement), as a reload would: the
	 * rows and cards named elements of the project before.
	 */
	#resetPage(): void {
		this.inspected = null;
		this.comparing = false;
		this.compareRows = null;
		this.managerOpen = false;
		this.managerFocus = null;
		this.settingsOpen = false;
		this.announcement = '';
	}

	/**
	 * The project of the case shown: the base project, or in a scenario the base with its changes
	 * (carrying the base's scenarios). Forms read and edit it through edit().
	 */
	get project(): Project {
		return this.#caseProject;
	}

	/** True while a scenario is shown (its values are edited, the rest is locked). */
	get inScenario(): boolean {
		return this.store.activeCase !== null;
	}

	/** The scenario shown (undefined: the base case). */
	get activeScenario(): Scenario | undefined {
		return findScenario(this.store.project, this.store.activeCase);
	}

	/** The project's scenarios. */
	get scenarios(): readonly Scenario[] {
		return scenariosOf(this.store.project);
	}

	/** "Base case" or the scenario's name. */
	caseName(caseId: CaseId): string {
		if (caseId === null) return 'Base case';
		return findScenario(this.store.project, caseId)?.name ?? caseId;
	}

	/** "base case" or "scenario Winter", in a sentence. */
	caseWords(caseId: CaseId): string {
		return caseId === null ? 'the base case' : `scenario ${this.caseName(caseId)}`;
	}

	/** "3 changes" or "3 changes, 1 no longer applies" of a scenario. */
	changesText(scenario: Scenario): string {
		const count = overridesOf(scenario).length;
		const lapsed = changeStates(this.store.project, scenario.id).filter(
			(c) => c.state !== 'applied'
		).length;
		const changes = `${count} change${count === 1 ? '' : 's'}`;
		return lapsed ? `${changes}, ${lapsed} no longer appl${lapsed === 1 ? 'ies' : 'y'}` : changes;
	}

	/**
	 * Show another case (null: the base case), and say so in the live region. Page state: no undo
	 * step. Build keeps its place (the topology is the same); an open trace stays where the case
	 * has results, and closes otherwise.
	 */
	setCase(caseId: CaseId): void {
		this.store.setCase(caseId);
		const scenario = this.activeScenario;
		this.announcement = scenario
			? `Showing scenario ${scenario.name}, ${this.changesText(scenario)}. Your edits now change this scenario.`
			: 'Showing the base case. Your edits now change the base case and every scenario that does not set its own value.';
		if (!this.store.results.response) this.inspected = null;
	}

	/** Undo the last change; when it was made in another case, show that case and say so. */
	undo(): boolean {
		return this.#history('undo');
	}

	/** Redo the last undone change; when it was made in another case, show that case and say so. */
	redo(): boolean {
		return this.#history('redo');
	}

	#history(step: 'undo' | 'redo'): boolean {
		const before = this.store.activeCase;
		const label = step === 'undo' ? this.store.undoLabel : this.store.redoLabel;
		if (!(step === 'undo' ? this.store.undo() : this.store.redo())) return false;
		const after = this.store.activeCase;
		if (after !== before) {
			const did = step === 'undo' ? 'Undid' : 'Redid';
			this.notify('info', `${did} ${label}. Now showing ${this.caseWords(after)}.`);
		}
		return true;
	}

	/**
	 * What the form shows about `field` of `target` (FieldChange). `fields` names a value made of
	 * several changes (the fluid: the whole fluid or its temperature); the first is shown.
	 */
	fieldChange(
		target: ChangeTarget,
		fields: string | readonly string[],
		label?: string
	): FieldChange {
		const names = typeof fields === 'string' ? [fields] : fields;
		const field = names[0] as string;
		const base = this.store.project;
		const matches = (o: Override) =>
			names.includes(o.field) &&
			(target.kind === 'project'
				? o.kind === 'project'
				: target.kind === 'component'
					? o.kind === 'component' && o.componentId === target.componentId
					: o.kind === 'pipe' &&
						o.connectionId === target.connectionId &&
						o.pipeIndex === target.pipeIndex);
		const scenario = this.activeScenario;
		const component =
			target.kind === 'component'
				? base.components.find((c) => c.id === target.componentId)
				: undefined;
		const name = label ?? fieldLabelFor(component, field);
		const baseValue = valueOf(base, target, field);
		const baseText =
			baseValue === undefined
				? '—'
				: changeValueText(base, makeOverride(target, field, baseValue), baseValue, this.units, {
						materialName: (id) => this.library.material(id)?.name,
						nominalSizes: this.library.nominalSizes
					});
		const changed = !!scenario && overridesOf(scenario).some(matches);
		return {
			inScenario: !!scenario,
			changed,
			baseText,
			label: name,
			reset: () => {
				const s = this.activeScenario;
				if (!s) return;
				this.updateStored((draft) => {
					const own = draft.scenarios?.find((x) => x.id === s.id);
					if (own) own.overrides = overridesOf(own).filter((o) => !matches(o));
				}, `reset ${name.toLowerCase()} in ${s.name}`);
			},
			setBy: scenario
				? []
				: this.scenarios.filter((s) => overridesOf(s).some(matches)).map((s) => s.name)
		};
	}

	/** fieldChange() of a component's value ('liquidLevel', 'status', 'control.setpoint', ...). */
	componentChange(componentId: string, field: string): FieldChange {
		return this.fieldChange({ kind: 'component', componentId }, field);
	}

	/** fieldChange() of a pipe's value ('spec': its size and material, or 'length'). */
	pipeChange(connectionId: string, pipeIndex: number, field: 'spec' | 'length'): FieldChange {
		return this.fieldChange(
			{ kind: 'pipe', connectionId, pipeIndex },
			field,
			field === 'spec' ? 'Pipe size and material' : 'Length'
		);
	}

	/** fieldChange() of the fluid: the whole fluid, or a built-in fluid's temperature. */
	fluidChange(): FieldChange {
		return this.fieldChange({ kind: 'project' }, ['fluid', 'fluid.temperature'], 'Fluid');
	}

	/**
	 * One undo step on the stored project (the base and its scenarios: the scenario manager's
	 * actions, Reset), with a notice when it is refused.
	 */
	updateStored(change: (draft: Project) => Project | void, label: string): boolean {
		const result = this.store.update(change, label);
		if (!result.ok) {
			this.notify(
				'error',
				`Could not ${label}: ${result.problems[0] ?? 'the change is not valid.'}`
			);
			return false;
		}
		return true;
	}

	get units(): UnitPreferences {
		return this.store.project.settings.units;
	}

	/** A flag's text for display: names and display units (utils/flag-text.ts). */
	flagText(flag: Flag): string {
		const solved = this.store.solved;
		const valveTypes = solved
			? Object.fromEntries(Object.entries(solved.valveResults).map(([id, v]) => [id, v.valveType]))
			: undefined;
		return flagText(flag, {
			project: this.labelsProject,
			prefs: this.displayUnits,
			fittingName: (type) => this.library.fitting(type)?.name ?? fittingFallbackName(type),
			...(valveTypes ? { valveTypes } : {})
		});
	}

	notify(kind: Notice['kind'], text: string): void {
		this.notice = { kind, text, id: ++this.#noticeId };
	}

	dismissNotice(): void {
		this.notice = null;
	}

	/**
	 * Apply a change as one undo step. A refused change (it would make the project invalid)
	 * changes nothing and is reported as a notice. Returns true when the change was applied.
	 *
	 * In a scenario, `change` edits the case's project and the edit is sorted out (see the module
	 * comment): values become the scenario's changes, labels go to the base, and anything else
	 * refuses the whole edit ("Switch to the base case to …"). An edit that would make the case's
	 * project invalid is refused too, as one of the base is. A base edit that moved or retired
	 * scenario changes says so.
	 */
	edit(change: (draft: Project) => Project | void, label: string): boolean {
		const scenario = this.activeScenario;
		if (!scenario) {
			const result = this.store.update(change, label);
			if (!result.ok) {
				this.notify(
					'error',
					`Could not ${label}: ${result.problems[0] ?? 'the change is not valid.'}`
				);
				return false;
			}
			if (result.notes?.length) this.notify('info', result.notes.join(' '));
			return true;
		}
		const base = this.store.project;
		const edit = scenarioEdit(base, scenario.id, change);
		if (!edit.ok) {
			this.notify(
				'error',
				edit.reason === 'refused'
					? `In a scenario you can change only its values. Switch to the base case to ${label}.`
					: `Could not ${label}: ${edit.message}`
			);
			return false;
		}
		const known = structuralProblems(caseProject(base, scenario.id));
		return this.updateStored((draft) => {
			edit.apply(draft);
			const added = structuralProblems(caseProject(draft, scenario.id)).filter(
				(p) => !known.includes(p)
			);
			if (added.length) throw new Error(added[0]);
		}, `${label} in ${scenario.name}`);
	}

	/** Edit one component in place (its id and connected ports cannot change). */
	editComponent<T extends Component>(
		id: string,
		label: string,
		change: (component: T) => T | void
	): boolean {
		return this.edit(
			(p) => updateComponent(p, id, (c) => (change(c as T) ?? c) as Component),
			label
		);
	}

	/** Edit one connection in place (its id and ends cannot change). */
	editConnection(
		id: string,
		label: string,
		change: (connection: PipeConnection) => PipeConnection | void
	): boolean {
		return this.edit((p) => updateConnection(p, id, (c) => change(c) ?? c), label);
	}

	/**
	 * Add the first component of an empty project (or a separate one) and show it. `values` are
	 * what the user entered for a kind with no default (an assigned-flow node's flow).
	 */
	addStandalone(kind: ComponentKind, values: EnteredValues = {}): string | null {
		const component = createComponent(kind, this.project, values);
		const ok = this.edit(
			(p) => ({ ...p, components: [...p.components, component] }),
			`add ${component.name}`
		);
		if (!ok) return null;
		this.nav.restart(component.id);
		return component.id;
	}

	/**
	 * Add a component at a free port of `componentId`, connected with a default pipe sized to the
	 * port, and walk on to it. The new component starts at the same elevation. `values` are what
	 * the user entered for a kind with no default (an assigned-flow node's flow).
	 */
	addAfter(
		componentId: string,
		portId: string,
		kind: ComponentKind,
		values: EnteredValues = {}
	): string | null {
		const existing = componentById(this.project, componentId);
		const port = existing ? portById(existing, portId) : undefined;
		if (!existing || !port) return null;
		const component = createComponent(kind, this.project, {
			...values,
			elevation: port.elevation ?? existing.elevation,
			nominalSize: port.nominalSize
		});
		const ok = this.edit(
			(p) => addComponentAtPort(p, componentId, portId, component),
			`add ${component.name}`
		);
		if (!ok) return null;
		const connection = connectionsOf(this.project, component.id)[0];
		if (this.nav.current?.id === componentId && connection) {
			this.nav.setPath([
				...this.nav.path,
				{ componentId: component.id, viaConnectionId: connection.id }
			]);
		} else {
			this.nav.jumpTo(component.id);
		}
		return component.id;
	}

	/**
	 * Insert a component into a connection of the current component and show it: in the
	 * connection the walk arrived by it goes before the current component, in any other after.
	 */
	insert(connectionId: string, kind: ComponentKind): string | null {
		const connection = this.project.connections.find((c) => c.id === connectionId);
		if (!connection) return null;
		const component = createComponent(kind, this.project, this.#insertOptions(connection));
		const attached = this.#attachedToCurrent(connection);
		const ok = this.edit(
			(p) => insertComponentInConnection(p, connectionId, component),
			`add ${component.name}`
		);
		if (!ok) return null;
		this.#reveal(component.id, connectionId, attached);
		return component.id;
	}

	/** Insert a tee (or wye) into a connection and show its free branch port. */
	addBranch(connectionId: string, kind: 'tee' | 'wye' = 'tee'): string | null {
		const connection = this.project.connections.find((c) => c.id === connectionId);
		if (!connection) return null;
		const branch = createComponent(kind, this.project, this.#insertOptions(connection));
		const attached = this.#attachedToCurrent(connection);
		const ok = this.edit((p) => addBranch(p, connectionId, branch), `add ${branch.name}`);
		if (!ok) return null;
		this.#reveal(branch.id, connectionId, attached);
		const free = branch.ports.find((p) => !connectionAtPort(this.project, branch.id, p.id));
		if (free) this.nav.showConnection(free.id);
		return branch.id;
	}

	/** A component inserted in `connection` sits at its upstream end's elevation, sized to its last pipe. */
	#insertOptions(connection: PipeConnection): { elevation: number; nominalSize?: number } {
		const from = componentById(this.project, connection.fromComponentId);
		const size = connection.piping.pipes[connection.piping.pipes.length - 1]?.nominalSize;
		return { elevation: from?.elevation ?? 0, ...(size ? { nominalSize: size } : {}) };
	}

	#attachedToCurrent(connection: PipeConnection): boolean {
		const id = this.nav.current?.id;
		return !!id && (connection.fromComponentId === id || connection.toComponentId === id);
	}

	#reveal(insertedId: string, connectionId: string, attachedToCurrent: boolean): void {
		if (attachedToCurrent) {
			this.nav.setPath(pathAfterInsert(this.project, this.nav.path, insertedId, connectionId));
		} else {
			this.nav.jumpTo(insertedId);
		}
	}

	/**
	 * Delete a component. With `join`, its two connections become one (see canJoin). The walk
	 * goes back to the previous step, or starts at a former neighbor.
	 */
	remove(componentId: string, join: boolean): boolean {
		const component = componentById(this.project, componentId);
		if (!component) return false;
		const neighbors = connectionsOf(this.project, componentId).map((c) =>
			c.fromComponentId === componentId ? c.toComponentId : c.fromComponentId
		);
		const wasStart = this.nav.startId === componentId;
		const ok = this.edit(
			(p) => deleteComponent(p, componentId, { join }),
			`delete ${component.name}`
		);
		if (!ok) return false;
		if (wasStart) this.nav.restart(neighbors.find((id) => componentById(this.project, id)));
		return true;
	}

	/** Close a free port with a plug. */
	plug(componentId: string, portId: string): boolean {
		return this.edit((p) => plugPort(p, componentId, portId), `plug ${componentId} ${portId}`);
	}

	/** Connect a free port of the current component to a free port elsewhere (e.g. to close a loop). */
	connect(from: PortRef, to: PortRef): boolean {
		return this.edit(
			(p) => connectPorts(p, from, to),
			`connect ${from.componentId} to ${to.componentId}`
		);
	}

	/** Remove a connection, leaving both ports free. */
	disconnect(connectionId: string): boolean {
		return this.edit((p) => disconnect(p, connectionId), `remove connection ${connectionId}`);
	}

	/** Solve the case shown, and show the results pane on narrow screens. */
	async solve(): Promise<void> {
		this.pane = 'results';
		this.store.flush();
		await this.store.solve();
	}

	/** Solve every case whose results are missing or out of date, one after another. */
	async solveAll(): Promise<void> {
		this.pane = 'results';
		this.store.flush();
		await this.store.solveAll();
	}

	/**
	 * Open an element's results and trace (a row or flag in the results), and point the
	 * navigator at it (see #point). The pane does not change: on narrow screens the results stay
	 * in view, and showElement() goes to Build.
	 */
	inspect(element: ElementRef): void {
		this.inspected = element;
		this.#point(element);
	}

	closeInspector(): void {
		this.inspected = null;
	}

	/** Point the navigator at an element from the results and show it in Build. */
	showElement(element: ElementRef): void {
		this.#point(element);
		this.pane = 'build';
	}

	/**
	 * Clicking an element in the results starts the navigator's walk at it (design §5): at a
	 * component, or for a connection at its 'from' component with that connection's piping open.
	 * Elements no longer in the project leave the navigator as it is.
	 */
	#point(element: ElementRef): void {
		if (element.kind === 'component') {
			if (componentById(this.project, element.id)) this.nav.restart(element.id);
			return;
		}
		const connection = this.project.connections.find((c) => c.id === element.id);
		if (!connection) return;
		this.nav.restart(connection.fromComponentId);
		this.nav.showConnection(connection.fromPortId);
	}

	/**
	 * Show a component in the navigator (from results or issue lists); with `portId`, open the
	 * piping view on that port (e.g. a port that is not connected yet, with its actions).
	 */
	show(componentId: string, portId?: string): void {
		const component = componentById(this.project, componentId);
		if (!component) return;
		this.nav.jumpTo(componentId);
		if (portId && portById(component, portId)) this.nav.showConnection(portId);
		this.pane = 'build';
	}
}

/** What results labels depend on: names, kinds, port order and connection ends. */
export function labelsKey(project: Project): string {
	const parts: string[] = [];
	for (const c of project.components) {
		const kind = c.type === 'valve' ? c.valveType : c.type === 'branch' ? c.branchType : c.type;
		parts.push(`${c.id}\u0000${c.name}\u0000${kind}\u0000${c.ports.map((p) => p.id).join(',')}`);
	}
	for (const c of project.connections) {
		parts.push(
			`${c.id}\u0000${c.fromComponentId}:${c.fromPortId}\u0000${c.toComponentId}:${c.toPortId}\u0000${c.piping.fittings.map((f) => f.type).join(',')}`
		);
	}
	return parts.join('\n');
}

const WORKSPACE_KEY = Symbol('opensolve-pipe:workspace');

export function provideWorkspace(workspace: Workspace): Workspace {
	return setContext(WORKSPACE_KEY, workspace);
}

export function useWorkspace(): Workspace {
	const workspace = getContext<Workspace | undefined>(WORKSPACE_KEY);
	if (!workspace) throw new Error('No Workspace: call provideWorkspace in a parent component.');
	return workspace;
}
