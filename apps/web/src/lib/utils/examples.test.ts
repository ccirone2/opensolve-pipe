import { describe, expect, it } from 'vitest';
import type { Override } from '../api/types';
import { referentialIssues } from '../testing/helpers';
import { decodeProject, encodeProject, URL_LENGTH_WARNING, projectUrl } from './encoding';
import { EXAMPLES, exampleProject } from './examples';
import { componentKind } from './factory';
import { defaultStart, isBoundary, reachable } from './graph';
import { INCH, US_GALLON } from './units';
import { projectProblems, schemaProblems } from './validate';

describe('examples', () => {
	it('are valid against the schema, the port graph and the model rules', () => {
		for (const example of EXAMPLES) {
			const project = example.create();
			expect(schemaProblems(project), example.slug).toEqual([]);
			expect(projectProblems(project), example.slug).toEqual([]);
			expect(referentialIssues(project), example.slug).toEqual([]);
		}
	});

	it('are labeled illustrative', () => {
		for (const example of EXAMPLES) {
			expect(example.create().metadata.description).toMatch(/Illustrative example/);
		}
	});

	it('are connected networks with a fixed-pressure boundary', () => {
		for (const example of EXAMPLES) {
			const project = example.create();
			expect(project.components.some(isBoundary), example.slug).toBe(true);
			const start = defaultStart(project)!;
			expect(reachable(project, start).size, example.slug).toBe(project.components.length);
		}
	});

	it('have unique slugs and stable, fresh copies', () => {
		expect(new Set(EXAMPLES.map((e) => e.slug)).size).toBe(EXAMPLES.length);
		const a = exampleProject('pump-transfer')!;
		a.metadata.name = 'changed';
		expect(exampleProject('pump-transfer')!.metadata.name).toBe('Pump transfer between two tanks');
		expect(encodeProject(exampleProject('condenser-water')!)).toBe(
			encodeProject(exampleProject('condenser-water')!)
		);
		expect(exampleProject('nope')).toBeUndefined();
	});

	it('fit in a link well under the length warning', () => {
		for (const example of EXAMPLES) {
			const project = example.create();
			expect(projectUrl(project).length).toBeLessThan(URL_LENGTH_WARNING);
			expect(decodeProject(encodeProject(project))).toEqual(project);
		}
	});

	it('cover the three example systems', () => {
		const kinds = (slug: string) => exampleProject(slug)!.components.map(componentKind);
		// (1) reservoir → pump → gate valve → reservoir, water at 20 °C, a 4-point curve
		const transfer = exampleProject('pump-transfer')!;
		expect(kinds('pump-transfer')).toEqual(['reservoir', 'pump', 'gate', 'reservoir']);
		expect(transfer.fluid).toEqual({ kind: 'builtin', fluidId: 'water', temperature: 293.15 });
		expect(transfer.pumpLibrary[0]!.points).toHaveLength(4);
		expect(
			transfer.connections.every((c) =>
				c.piping.pipes.every((p) => p.materialId === 'carbon_steel' && p.schedule === '40')
			)
		).toBe(true);
		// (2) gravity-fed: no pump, a tee, two lower reservoirs, one branch with a globe valve
		expect(kinds('gravity-branch').sort()).toEqual(
			['globe', 'reservoir', 'reservoir', 'reservoir', 'tee'].sort()
		);
		// (3) condenser water, 90,000 gpm: six 15,000 gpm pumps on a common header, seven
		// condensers (4 × 15,000 and 3 × 10,000 gpm) each held by a flow control valve, six
		// 15,000 gpm tower cells with nozzle headers, and a tower bypass valve closed at design
		const plant = exampleProject('condenser-water')!;
		const count = (kind: string) => kinds('condenser-water').filter((k) => k === kind).length;
		expect([count('pump'), count('check'), count('fcv'), count('equipment')]).toEqual([
			6, 6, 7, 13
		]);
		const gpm = US_GALLON / 60;
		const fcvs = plant.components.filter((c) => c.type === 'valve' && c.valveType === 'fcv');
		const setpoints = fcvs.map((c) => ('setpoint' in c ? c.setpoint : 0) / gpm);
		expect(setpoints.map((q) => Math.round(q))).toEqual([
			15_000, 15_000, 15_000, 15_000, 10_000, 10_000, 10_000
		]);
		const cells = plant.components.filter((c) => /^Cell \d nozzle header$/.test(c.name));
		expect(
			cells.map(
				(c) =>
					c.type === 'equipment' && Math.round(c.rating.kind === 'point' ? c.rating.flow / gpm : 0)
			)
		).toEqual(Array(6).fill(15_000));
		expect(plant.components.find((c) => c.name === 'Tower bypass valve')).toMatchObject({
			valveType: 'butterfly',
			status: 'isolated'
		});
		expect(plant.scenarios?.map((s) => s.name)).toEqual(['Winter: tower bypassed']);
		// An open circuit: the tower basin feeds the pumps and takes the bypass; each cell sprays
		// to atmosphere.
		expect(count('reservoir')).toBe(7);
		expect(plant.connections.length).toBeGreaterThan(plant.components.length - 1);
	});
});

describe('the condenser water example on its project library', () => {
	const plant = exampleProject('condenser-water')!;
	const byId = new Map(plant.components.map((c) => [c.id, c]));
	const pipes = plant.connections.flatMap((c) => c.piping.pipes);
	/** The name of the component at the other end of the connection on `componentId`'s port. */
	const across = (componentId: string, portId: string) => {
		const c = plant.connections.find(
			(c) =>
				(c.fromComponentId === componentId && c.fromPortId === portId) ||
				(c.toComponentId === componentId && c.toPortId === portId)
		)!;
		return byId.get(c.fromComponentId === componentId ? c.toComponentId : c.fromComponentId)!.name;
	};
	/** `count` tees of a header from `first`, run_outlet to run_inlet, with their branches' names. */
	const header = (first: string, count: number) => {
		const tees = [{ id: first, branch: across(first, 'branch') }];
		while (tees.length < count) {
			const c = plant.connections.find(
				(c) => c.fromComponentId === tees.at(-1)!.id && c.fromPortId === 'run_outlet'
			)!;
			expect([byId.get(c.toComponentId)!.type, c.toPortId]).toEqual(['branch', 'run_inlet']);
			tees.push({ id: c.toComponentId, branch: across(c.toComponentId, 'branch') });
		}
		return tees;
	};

	it('has one illustrative NPS 60 pipe spec, used for every pipe the cited library lacks', () => {
		expect(plant.pipeLibrary).toEqual([
			{
				id: 'PS1',
				name: 'NPS 60 carbon steel, 0.375 in wall (illustrative)',
				source: expect.stringMatching(
					/^Illustrative example input: a 60 in OD steel pipe with a 0\.375 in wall \(59\.25 in bore\), not taken from a cited table\. Roughness: the carbon steel library’s Farshad & Rieke correlation at this bore\.$/
				),
				materialId: 'carbon_steel',
				innerDiameter: 59.25 * INCH,
				outerDiameter: 60 * INCH,
				nominalSize: 60 * INCH
			}
		]);
		// Roughness left blank: the server takes carbon steel's Farshad roughness at that bore.
		expect(plant.pipeLibrary![0]).not.toHaveProperty('roughness');
		const spec = pipes.filter((p) => p.specId === 'PS1');
		expect(spec).toHaveLength(25);
		expect(spec.every((p) => Object.keys(p).sort().join() === 'length,specId')).toBe(true);
		// Every other pipe is cited: carbon steel STD up to NPS 48, the library's largest.
		const cited = pipes.filter((p) => p.specId == null);
		for (const p of cited) {
			expect(p).toMatchObject({ materialId: 'carbon_steel', schedule: 'STD' });
			expect(p.nominalSize! / INCH).toBeLessThanOrEqual(48);
		}
	});

	it('gives its NPS 30 butterfly valves one illustrative Cv, derived as its source states', () => {
		expect(plant.resistanceLibrary).toEqual([
			{
				id: 'RS1',
				name: 'NPS 30 butterfly valve, open (illustrative)',
				source: expect.stringMatching(
					/^Illustrative example input, not a manufacturer’s value: Crane TP-410’s centric butterfly valve K for NPS 16–24, 25 f_T, extrapolated to NPS 30 .*K = 0\.274\), converted with fluids’ K_to_Cv \(48,760\) and rounded\.$/
				),
				kind: 'Cv',
				value: 48_800
			}
		]);
		// 25 f_T at the NPS 30 STD bore, D = 0.74294 m: fluids 1.3.1
		// K_butterfly_valve_Crane(0.74294, style=0) = 25 ft_Crane(D). Then fluids' K_to_Cv
		// (ISA-75.01.01), Cv = 1.1560992283536566 D² √(1.6×10⁹/K), rounded to 3 significant figures.
		const D = 0.74294;
		const K = 0.2740288404204759;
		const cv = 1.1560992283536566 * D * D * Math.sqrt(1.6e9 / K);
		expect(Math.round(cv)).toBe(48_760);
		expect(Number(cv.toPrecision(3))).toBe(plant.resistanceLibrary![0]!.value);
		// The six cell isolation valves and the six pump suction lines' butterfly valves use it.
		const cellValves = plant.components.filter((c) => /^Cell \d isolation valve$/.test(c.name));
		expect(cellValves).toHaveLength(6);
		for (const v of cellValves) {
			expect(v).toMatchObject({
				valveType: 'butterfly',
				resistance: { kind: 'library', id: 'RS1' },
				ports: [{ nominalSize: 30 * INCH }, { nominalSize: 30 * INCH }]
			});
		}
		const suction = plant.connections.filter(
			(c) => c.fromComponentId === 'B1' && c.toPortId === 'suction'
		);
		expect(suction).toHaveLength(6);
		for (const c of suction) {
			expect(c.piping.pipes.map((p) => p.nominalSize! / INCH)).toEqual([30]);
			expect(c.piping.fittings.filter((f) => f.resistanceId === 'RS1')).toEqual([
				{ type: 'butterfly_valve', quantity: 1, pipeIndex: 0, resistanceId: 'RS1' }
			]);
		}
		// Every other butterfly valve takes Crane's default, inside its table (NPS 24 at most).
		const others = plant.components.filter(
			(c) => c.type === 'valve' && c.valveType === 'butterfly' && !cellValves.includes(c)
		);
		expect(others.map((c) => c.id).sort()).toEqual(['BP', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6']);
		for (const v of others) {
			expect(v).not.toHaveProperty('resistance');
			expect(v.ports.every((p) => p.nominalSize <= 24 * INCH)).toBe(true);
		}
		expect(byId.get('BP')).toMatchObject({ name: 'Tower bypass valve', status: 'isolated' });
	});

	it('runs the water one way along its NPS 60 headers', () => {
		// Supply: CWP-1 in at the upstream end, then every other pump, then every chiller but the
		// last, which the downstream end feeds.
		const supply = header('H1', 11);
		expect(across('H1', 'run_inlet')).toBe('CWP-1 discharge valve');
		expect(supply.map((t) => t.branch)).toEqual([
			...[2, 3, 4, 5, 6].map((i) => `CWP-${i} discharge valve`),
			...[1, 2, 3, 4, 5, 6].map((i) => `CH-${i} condenser`)
		]);
		expect(across(supply.at(-1)!.id, 'run_outlet')).toBe('CH-7 condenser');
		// Return: CH-1 in at the upstream end, the other chillers, then the tower bypass and the
		// riser to the tower's distribution header, which feeds cells 1–5 and cell 6 at its end.
		const ret = header('R1', 7);
		expect(across('R1', 'run_inlet')).toBe('CH-1 flow control valve');
		expect(ret.map((t) => t.branch)).toEqual([
			...[2, 3, 4, 5, 6, 7].map((i) => `CH-${i} flow control valve`),
			'Tower bypass valve'
		]);
		const tower = header('T1', 5);
		expect(across(ret.at(-1)!.id, 'run_outlet')).toBe('Tower header tee at cell 1');
		expect(tower.map((t) => t.branch)).toEqual(
			[1, 2, 3, 4, 5].map((i) => `Cell ${i} isolation valve`)
		);
		expect(across(tower.at(-1)!.id, 'run_outlet')).toBe('Cell 6 isolation valve');
		for (const { id } of [...supply, ...ret, ...tower]) {
			expect(byId.get(id)).toMatchObject({
				branchType: 'tee',
				lossModel: 'crane',
				ports: [{ nominalSize: 60 * INCH }, { nominalSize: 60 * INCH }, {}]
			});
		}
	});

	it('has a winter scenario that names its own elements', () => {
		const overrides = plant.scenarios![0]!.overrides!;
		const status = (o: Override) =>
			o.kind === 'component' && o.field === 'status' ? [o.componentId, o.value] : [];
		expect(overrides.map(status)).toEqual([
			...[2, 3, 4, 5, 6].map((i) => [`P${i}`, 'off']),
			...[2, 3, 4, 5, 6, 7].map((i) => [`F${i}`, 'failed_closed']),
			...[1, 2, 3, 4, 5, 6].map((i) => [`IV${i}`, 'isolated']),
			['BP', 'active'],
			[]
		]);
		expect(overrides.at(-1)).toEqual({
			kind: 'component',
			componentId: 'BP',
			field: 'resistance',
			value: { kind: 'K', value: 16.5 }
		});
		for (const o of overrides) {
			expect(o.kind === 'component' && byId.has(o.componentId)).toBe(true);
		}
	});

	it('holds back pressure on the return in winter, so its riser and tower header stay full', () => {
		// Hand calculation. In winter only CH-1's flow control valve passes flow and every cell is
		// isolated, so its setpoint flows through the bypass valve to the basin, and the riser and
		// tower header are a dead end on the return. The return's EGL is at least the basin's head
		// plus the bypass valve's own loss, K v²/2g on its inlet pipe's bore (the bypass pipes, the
		// tee and the exit only add to it), and the dead end holds that EGL with no velocity. Wide
		// open (Crane's K, 25 f_T: 0.286) the return would hang 7.4 m of water below atmospheric
		// pressure at the tower header (solved: −72.1 kPa gauge), which no flag reports.
		const s1 = plant.scenarios![0]!;
		const throttle = s1.overrides!.find(
			(o) => o.kind === 'component' && o.componentId === 'BP' && o.field === 'resistance'
		);
		expect(throttle?.value).toMatchObject({ kind: 'K' });
		const K = (throttle!.value as { value: number }).value;
		const f1 = byId.get('F1')!;
		const flow = f1.type === 'valve' && 'setpoint' in f1 ? f1.setpoint : NaN;
		const inlet = plant.connections.find((c) => c.toComponentId === 'BP')!;
		expect(inlet.piping.pipes).toEqual([
			{ materialId: 'carbon_steel', schedule: 'STD', nominalSize: 24 * INCH, length: 2 }
		]);
		// NPS 24 STD (ASME B36.10M), the API's data/pipe_materials.json from fluids 1.3.1.
		const bore = 0.59094;
		const velocity = flow / ((Math.PI / 4) * bore ** 2);
		const loss = (K * velocity ** 2) / (2 * 9.80665);
		const basin = byId.get('B1')!;
		const basinHead = basin.type === 'reservoir' ? basin.elevation + basin.liquidLevel : NaN;
		const deadEnd = ['T1', 'T2', 'T3', 'T4', 'T5', 'IV1', 'IV2', 'IV3', 'IV4', 'IV5', 'IV6'];
		const top = Math.max(...deadEnd.map((id) => byId.get(id)!.elevation));
		expect([basinHead, top]).toEqual([0.6, 10]);
		expect(velocity).toBeCloseTo(3.4505, 4);
		expect(loss).toBeCloseTo(10.016, 3);
		// The valve alone keeps the highest point of the dead end above atmospheric pressure.
		expect(basinHead + loss - top).toBeGreaterThan(0.5);
		expect(s1.description).toContain(`throttled (K ${K})`);
	});
});
