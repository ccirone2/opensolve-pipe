/**
 * The workspace's edits on a project on the project library (CLAUDE.md D22): a component or a tee
 * inserted where a pipe of a spec ends is sized to the spec's nominal size (the condenser water
 * example's NPS 60 header), so its ports match their pipes as the ports editor checks them; the
 * example ships with every port matching.
 */
import { describe, expect, it } from 'vitest';
import type { Project } from '../api/types';
import { testWorkspace } from '../testing/workspace';
import { condenserWaterExample } from '../utils/examples';
import { connectionAtPort } from '../utils/graph';
import { sameSize } from '../utils/labels';
import { pipeAtPort } from '../utils/orifice';
import { CUSTOM_MATERIAL_ID, pipeNominalSize } from '../utils/piping';

/** Every connected port whose size is not its pipe's nominal size (PortsEditor's warning). */
function mismatches(project: Project): string[] {
	const found: string[] = [];
	for (const component of project.components) {
		for (const port of component.ports) {
			const connection = connectionAtPort(project, component.id, port.id);
			if (!connection) continue;
			const { pipe } = pipeAtPort(connection, component.id, port.id);
			if (pipe.specId == null && pipe.materialId === CUSTOM_MATERIAL_ID) continue;
			const nominal = pipeNominalSize(project, pipe);
			if (nominal != null && !sameSize(nominal, port.nominalSize)) {
				found.push(`${component.id}.${port.id}`);
			}
		}
	}
	return found;
}

describe('inserting where a pipe of a spec ends', () => {
	it('sizes a component to the spec (L1 ends on PS1, NPS 60)', () => {
		const ws = testWorkspace(condenserWaterExample());
		expect(mismatches(ws.project)).toEqual([]);
		const l1 = ws.project.connections.find((c) => c.id === 'L1')!;
		expect(l1.piping.pipes.at(-1)).toMatchObject({ specId: 'PS1' });
		const id = ws.insert('L1', 'gate')!;
		const valve = ws.project.components.find((c) => c.id === id)!;
		expect(valve.ports.map((p) => p.nominalSize)).toEqual([1.524, 1.524]);
		expect(mismatches(ws.project)).toEqual([]);
	});

	it('sizes a tee to the spec, so a branch from its free port starts at NPS 60', () => {
		const ws = testWorkspace(condenserWaterExample());
		const id = ws.addBranch('L2')!;
		const tee = ws.project.components.find((c) => c.id === id)!;
		expect(tee.ports.every((p) => p.nominalSize === 1.524)).toBe(true);
		expect(mismatches(ws.project)).toEqual([]);
	});
});
