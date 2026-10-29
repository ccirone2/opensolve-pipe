/**
 * What uses each project library entry, for the library dialog's cards (CLAUDE.md D22; proposal
 * project-library.md §6.1), at the cost of one walk of the project: the dialog shows every entry's
 * count and, on request, its users by name, and recomputes them on every change to the project.
 * Asked entry by entry (pipeSpecUsers, resistanceUsers) and named by userLabel, whose lookups are
 * linear finds, that cost grew with entries × elements and users × elements: about 0.3 s on a
 * desktop and 2 s on a phone at the schema's largest network.
 *
 * The lists and the words are those of utils/project-library.ts (the tests hold them equal).
 */
import type { Component, PipeConnection, Project } from '$lib/api/types';
import { isResistanceRef, userLabel, type LibraryUser } from '$lib/utils/project-library';

/** Each entry's users by entry id, as pipeSpecUsers and resistanceUsers list them. */
export interface LibraryUsers {
	pipe: ReadonlyMap<string, readonly LibraryUser[]>;
	resistance: ReadonlyMap<string, readonly LibraryUser[]>;
}

function add(map: Map<string, LibraryUser[]>, id: unknown, user: LibraryUser) {
	if (typeof id !== 'string') return;
	const list = map.get(id);
	if (list) list.push(user);
	else map.set(id, [user]);
}

/**
 * Every entry's users in one walk of the project, in pipeSpecUsers' and resistanceUsers' order:
 * a spec's pipes in project order, then scenarios' changes; an entry's valves in project order,
 * its fittings in connection order, then scenarios' changes (each in scenario and change order).
 */
export function libraryUsers(project: Project): LibraryUsers {
	const pipe = new Map<string, LibraryUser[]>();
	const resistance = new Map<string, LibraryUser[]>();
	for (const connection of project.connections) {
		connection.piping.pipes.forEach((p, pipeIndex) => {
			add(pipe, p.specId, { kind: 'pipe', connectionId: connection.id, pipeIndex });
		});
	}
	for (const component of project.components) {
		if (component.type === 'valve' && isResistanceRef(component.resistance)) {
			add(resistance, component.resistance.id, { kind: 'valve', componentId: component.id });
		}
	}
	for (const connection of project.connections) {
		connection.piping.fittings.forEach((fitting, fittingIndex) => {
			add(resistance, fitting.resistanceId, {
				kind: 'fitting',
				connectionId: connection.id,
				fittingIndex
			});
		});
	}
	for (const scenario of project.scenarios ?? []) {
		(scenario.overrides ?? []).forEach((override, changeIndex) => {
			const user: LibraryUser = {
				kind: 'scenario',
				scenarioId: scenario.id,
				changeIndex,
				override
			};
			// A pipe's spec change {specId} uses that spec; a valve's resistance {kind: 'library', id}
			// that entry.
			if (override.kind === 'pipe' && override.field === 'spec') {
				const value = override.value as { specId?: unknown } | null;
				if (value && typeof value === 'object') add(pipe, value.specId, user);
			} else if (
				override.kind === 'component' &&
				override.field === 'resistance' &&
				isResistanceRef(override.value)
			) {
				add(resistance, override.value.id, user);
			}
		});
	}
	return { pipe, resistance };
}

/** The first item with each id, as graph.ts's finds return it. */
function byId<T extends { id: string }>(items: readonly T[]): Map<string, T> {
	const map = new Map<string, T>();
	for (const item of items) if (!map.has(item.id)) map.set(item.id, item);
	return map;
}

/**
 * userLabel for `project`'s users at a constant cost each: "Pipe 2 of Tank → Pump", "Gate valve
 * V1", ... userLabel reads only the connection a pipe or fitting is in and that connection's two
 * ends, or the valve, each found by id (and a scenario among at most 20): it is given `project`
 * holding just those, found through maps built once, so each label reads exactly as userLabel
 * words it on the whole project.
 */
export function userLabeller(
	project: Project
): (user: LibraryUser, fittingName?: (type: string) => string) => string {
	const components = byId(project.components);
	const connections = byId(project.connections);
	const present = <T>(items: readonly (T | undefined)[]): T[] =>
		items.filter((item): item is T => item !== undefined);
	function around(user: LibraryUser): Project {
		switch (user.kind) {
			case 'valve':
				return {
					...project,
					components: present<Component>([components.get(user.componentId)]),
					connections: []
				};
			case 'pipe':
			case 'fitting': {
				const connection = connections.get(user.connectionId);
				const ends = connection
					? present<Component>([
							components.get(connection.fromComponentId),
							components.get(connection.toComponentId)
						])
					: [];
				return {
					...project,
					components: ends,
					connections: present<PipeConnection>([connection])
				};
			}
			case 'scenario':
				return project;
		}
	}
	return (user, fittingName) => userLabel(around(user), user, fittingName);
}
