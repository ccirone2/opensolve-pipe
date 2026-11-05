/**
 * Names that follow their pumps, in the workspace (CLAUDE.md D24, proposal pump-lineups.md §4.5,
 * §10.1 "L1a, workspace"): Build's edit in a case and in the base renames an app-made name in the
 * same undo step, with the notice; Undo restores both; the undo label names the case after the
 * step; a name the user typed, or a 4d name on a base edit, stays; a base PRV status edit (the
 * frame) and a pump's rename follow; a pipe removed with its change gives the carry note, then the
 * rename. The projects are made-up test inputs (testing/lineups.ts); nothing is solved.
 */
import { describe, expect, it } from 'vitest';
import type { Component, Override, Project, Scenario } from '../api/types';
import { prvStation, station } from '../testing/lineups';
import { testWorkspace } from '../testing/workspace';
import { updateConnection } from '../utils/edit';
import { addPipe, removePipe } from '../utils/piping';
import { scenariosOf, withScenarios } from '../utils/scenarios';

const off = (...ids: string[]): Override[] =>
	ids.map((componentId) => ({ kind: 'component', componentId, field: 'status', value: 'off' }));
const named = (id: string, name: string, overrides: Override[]): Scenario => ({
	id,
	name,
	overrides
});
const names = (ws: ReturnType<typeof testWorkspace>) => ws.scenarios.map((s) => s.name);

/** Build's status segment: the same edit RegistryField makes (field-registry's label). */
const setStatus = (ws: ReturnType<typeof testWorkspace>, id: string, value: string) =>
	ws.editComponent(id, 'change pump status', (c) => {
		(c as unknown as Record<string, unknown>).status = value;
	});

describe('names that follow, in the workspace', () => {
	const project = () =>
		withScenarios(station(4), [
			named('S1', '2 of 4 running (Pump P3, Pump P4 off)', off('P3', 'P4')),
			named('S2', 'Pump P1 off', off('P1'))
		]);

	it('renames a shown case on Build’s P2 Off, in the same step, with the notice', () => {
		const ws = testWorkspace(project());
		ws.setCase('S1');
		const depth = ws.store.undoDepth;
		expect(setStatus(ws, 'P2', 'off')).toBe(true);
		expect(ws.store.undoDepth).toBe(depth + 1);
		expect(ws.activeScenario?.overrides).toEqual(off('P3', 'P4', 'P2'));
		expect(names(ws)).toEqual(['1 of 4 running (Pump P2, Pump P3, Pump P4 off)', 'Pump P1 off']);
		expect(ws.notice).toMatchObject({
			kind: 'info',
			text: '«2 of 4 running (Pump P3, Pump P4 off)» is now «1 of 4 running (Pump P2, Pump P3, Pump P4 off)»: a name the app made follows its pumps until you rename it.'
		});
	});

	it('Undo restores the status and the name; the undo label names the case after the step', () => {
		const ws = testWorkspace(project());
		ws.setCase('S1');
		setStatus(ws, 'P2', 'off');
		expect(ws.store.undoLabel).toBe(
			'change pump status in 1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
		);
		expect(ws.undo()).toBe(true);
		expect(ws.store.project).toEqual(project());
		expect(ws.store.redoLabel).toBe(
			'change pump status in 1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
		);
		// A reset in the case: its undo label names it as the reset leaves it.
		setStatus(ws, 'P2', 'off');
		ws.componentChange('P3', 'status').reset();
		expect(names(ws)[0]).toBe('2 of 4 running (Pump P2, Pump P4 off)');
		expect(ws.store.undoLabel).toBe('reset status in 2 of 4 running (Pump P2, Pump P4 off)');
	});

	it('does not follow a case the user renamed', () => {
		const ws = testWorkspace(project());
		ws.updateStored(
			(p) =>
				withScenarios(
					p,
					scenariosOf(p).map((s) => (s.id === 'S1' ? { ...s, name: 'Night' } : s))
				),
			'rename scenario'
		);
		ws.setCase('S1');
		ws.dismissNotice();
		setStatus(ws, 'P2', 'off');
		expect(names(ws)).toEqual(['Night', 'Pump P1 off']);
		expect(ws.store.undoLabel).toBe('change pump status in Night');
		expect(ws.notice).toBeNull();
	});

	it('renames a template name on a base status edit, and not a 4d name', () => {
		const ws = testWorkspace(project());
		expect(setStatus(ws, 'P2', 'off')).toBe(true);
		expect(names(ws)).toEqual(['1 of 4 running (Pump P2, Pump P3, Pump P4 off)', 'Pump P1 off']);
		expect(ws.store.undoLabel).toBe('change pump status');
		expect(ws.notice?.text).toBe(
			'«2 of 4 running (Pump P3, Pump P4 off)» is now «1 of 4 running (Pump P2, Pump P3, Pump P4 off)»: a name the app made follows its pumps until you rename it.'
		);
	});

	it('renames a template name on a base PRV status edit: the frame changed', () => {
		const ws = testWorkspace(
			withScenarios(prvStation('failed_open'), [
				named('S1', '1 of 2 running (Pump PB off)', off('PB'))
			])
		);
		expect(
			ws.editComponent('V1', 'change valve status', (c) => {
				(c as unknown as Record<string, unknown>).status = 'active';
			})
		).toBe(true);
		expect(names(ws)).toEqual(['Pump PB off']);
		expect(ws.notice?.text).toBe(
			'«1 of 2 running (Pump PB off)» is now «Pump PB off»: a name the app made follows its pumps until you rename it.'
		);
	});

	it('follows a pump’s rename, three cases in one notice', () => {
		const ws = testWorkspace(
			withScenarios(station(4), [
				named('S1', '3 of 4 running (Pump P4 off)', off('P4')),
				named('S2', '2 of 4 running (Pump P3, Pump P4 off)', off('P3', 'P4')),
				named('S3', 'Pump P4 off', off('P4')),
				named('S4', 'Night', off('P4'))
			])
		);
		ws.editComponent('P4', 'rename', (c: Component) => {
			c.name = 'Standby';
		});
		expect(names(ws)).toEqual([
			'3 of 4 running (Standby off)',
			'2 of 4 running (Pump P3, Standby off)',
			'Standby off',
			'Night'
		]);
		expect(ws.notice?.text).toBe(
			'Renamed 3 scenarios to match their pumps, for example «3 of 4 running (Pump P4 off)» is now «3 of 4 running (Standby off)». A name the app made follows its pumps until you rename it.'
		);
		// One step: Undo brings back every name.
		ws.undo();
		expect(names(ws)).toEqual([
			'3 of 4 running (Pump P4 off)',
			'2 of 4 running (Pump P3, Pump P4 off)',
			'Pump P4 off',
			'Night'
		]);
	});

	it('says the carry notes, then the rename, after a base edit that removes a changed pipe', () => {
		// A second pipe on P4's suction connection, which S1 also lengthens: one other change.
		const twoPipes: Project = updateConnection(station(4), 'SP4', (c) => ({
			...c,
			piping: addPipe(c.piping, { ...c.piping.pipes[0]!, length: 7 })
		}));
		const length: Override = {
			kind: 'pipe',
			connectionId: 'SP4',
			pipeIndex: 1,
			field: 'length',
			value: 25
		};
		const ws = testWorkspace(
			withScenarios(twoPipes, [
				named('S1', '3 of 4 running (Pump P4 off) + 1 other change', [...off('P4'), length])
			])
		);
		expect(
			ws.edit(
				(p) => updateConnection(p, 'SP4', (c) => ({ ...c, piping: removePipe(c.piping, 1) })),
				'remove pipe'
			)
		).toBe(true);
		expect(ws.scenarios[0]).toMatchObject({
			name: '3 of 4 running (Pump P4 off)',
			overrides: off('P4')
		});
		expect(ws.notice?.text).toBe(
			'Pipe 2 of connection SP4 removed, with its changes in 3 of 4 running (Pump P4 off) + 1 other change. Undo restores both. «3 of 4 running (Pump P4 off) + 1 other change» is now «3 of 4 running (Pump P4 off)»: a name the app made follows its pumps until you rename it.'
		);
	});

	it('names a case by the changes the edit carried: a setpoint change removed no longer counts', () => {
		// PB's PRV, inactive, made an FCV: the scenario's pressure setpoint goes (carryChanges),
		// though as a value it would still apply to an FCV.
		const setpoint: Override = {
			kind: 'component',
			componentId: 'V1',
			field: 'setpoint',
			value: 200000
		};
		const ws = testWorkspace(
			withScenarios(prvStation('failed_open'), [
				named('S1', '1 of 2 running (Pump PB off) + 1 other change', [...off('PB'), setpoint])
			])
		);
		ws.editComponent('V1', 'change valve type', (c) => {
			Object.assign(c, { valveType: 'fcv', setpoint: 0 });
		});
		expect(ws.scenarios[0]).toMatchObject({
			name: '1 of 2 running (Pump PB off)',
			overrides: off('PB')
		});
		expect(ws.notice?.text).toBe(
			"The setpoint changes of PRV V1 in 1 of 2 running (Pump PB off) + 1 other change were removed: a PRV or PSV setpoint is a pressure, an FCV's a flow. «1 of 2 running (Pump PB off) + 1 other change» is now «1 of 2 running (Pump PB off)»: a name the app made follows its pumps until you rename it."
		);
	});
});
