/**
 * Example projects for the home page ("Open example").
 *
 * They are illustrative: elevations, pipe lengths and sizes, and pump curves are made-up user
 * inputs chosen to show the tool, not data for a real installation or a real pump. Pipe
 * dimensions and roughness, fitting K values and fluid properties are not set here; the
 * solver takes them from its cited library (carbon steel by schedule and nominal size, Crane
 * TP-410 K values). The one exception is the condenser water example's project library, which
 * gives what the cited library lacks (an NPS 60 pipe and an NPS 30 butterfly valve's Cv) as
 * illustrative inputs, labelled so in their sources.
 */
import type {
	Component,
	Fitting,
	Override,
	PipeConnection,
	PipeDefinition,
	Port,
	Project
} from '../api/types';
import { createEmptyProject } from './factory';
import { FOOT, INCH, POUND_FORCE, US_GALLON } from './units';

const ILLUSTRATIVE =
	'Illustrative example: the elevations, pipe lengths and sizes and the pump curve are ' +
	'made-up inputs to show the tool, not data for a real installation or pump.';

/** Fixed timestamp, so example links are stable. */
const EXAMPLE_DATE = '2026-10-21T00:00:00Z';

const NPS3 = 3 * INCH;
const NPS4 = 4 * INCH;

function pipe(
	id: string,
	from: [string, string],
	to: [string, string],
	nominalSize: number,
	length: number,
	fittings: Fitting[] = []
): PipeConnection {
	return {
		id,
		fromComponentId: from[0],
		fromPortId: from[1],
		toComponentId: to[0],
		toPortId: to[1],
		piping: {
			pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize, length }],
			fittings
		}
	};
}

function fitting(type: Fitting['type'], quantity = 1, pipeIndex = 0): Fitting {
	return { type, quantity, pipeIndex };
}

function ports(...spec: [string, number, Port['direction']][]): Port[] {
	return spec.map(([id, nominalSize, direction]) => ({ id, nominalSize, direction }));
}

function base(id: string, name: string, description: string): Project {
	const project = createEmptyProject({ id, name, now: EXAMPLE_DATE });
	project.metadata.description = `${description} ${ILLUSTRATIVE}`;
	return project;
}

/** (1) Pump transfer between two tanks: R1 → pipe → P1 → pipe → gate valve → pipe → R2. */
export function pumpTransferExample(): Project {
	const project = base(
		'example-pump-transfer',
		'Pump transfer between two tanks',
		'Water at 20 °C pumped from a suction tank to a discharge tank 10 m higher.'
	);
	const components: Component[] = [
		{
			type: 'reservoir',
			id: 'R1',
			name: 'Suction tank',
			elevation: 0,
			liquidLevel: 3,
			surfacePressure: 0,
			ports: ports(['port_1', NPS4, 'bidirectional'])
		},
		{
			type: 'pump',
			id: 'P1',
			name: 'Transfer pump',
			elevation: 0,
			curveId: 'C1',
			speed: 1,
			status: 'on',
			ports: ports(['suction', NPS4, 'inlet'], ['discharge', NPS3, 'outlet'])
		},
		{
			type: 'valve',
			valveType: 'gate',
			id: 'V1',
			name: 'Discharge isolation valve',
			elevation: 0,
			status: 'active',
			ports: ports(['inlet', NPS3, 'inlet'], ['outlet', NPS3, 'outlet'])
		},
		{
			type: 'reservoir',
			id: 'R2',
			name: 'Discharge tank',
			elevation: 10,
			liquidLevel: 2,
			surfacePressure: 0,
			ports: ports(['port_1', NPS3, 'bidirectional'])
		}
	];
	return {
		...project,
		components,
		connections: [
			pipe('L1', ['R1', 'port_1'], ['P1', 'suction'], NPS4, 5, [fitting('entrance_sharp')]),
			pipe('L2', ['P1', 'discharge'], ['V1', 'inlet'], NPS3, 3),
			pipe('L3', ['V1', 'outlet'], ['R2', 'port_1'], NPS3, 60, [
				fitting('elbow_90_lr', 4),
				fitting('exit')
			])
		],
		pumpLibrary: [
			{
				id: 'C1',
				name: 'Example transfer pump curve (illustrative)',
				points: [
					{ flow: 0, head: 30 },
					{ flow: 0.01, head: 28 },
					{ flow: 0.02, head: 22 },
					{ flow: 0.03, head: 12 }
				],
				efficiencyCurve: [
					{ flow: 0.005, efficiency: 0.45 },
					{ flow: 0.015, efficiency: 0.7 },
					{ flow: 0.025, efficiency: 0.6 }
				],
				npshrCurve: [
					{ flow: 0.005, npshr: 1.5 },
					{ flow: 0.015, npshr: 2.5 },
					{ flow: 0.03, npshr: 5 }
				]
			}
		]
	};
}

/**
 * (2) Gravity-fed branched network: an elevated tank feeds a tee; one branch runs through a
 * globe valve to tank A, the other to tank B. No pump. The tee's run is NPS 4 on both sides (the
 * Crane tee correlations assume equal run diameters, so the example solves without a range
 * flag), reducing to NPS 3 one metre after the tee.
 */
export function gravityBranchExample(): Project {
	const project = base(
		'example-gravity-branch',
		'Gravity-fed branched network',
		'An elevated tank supplies two lower tanks through a tee; the run reduces from NPS 4 to ' +
			'NPS 3 just after the tee. No pump.'
	);
	const components: Component[] = [
		{
			type: 'reservoir',
			id: 'R1',
			name: 'Elevated tank',
			elevation: 40,
			liquidLevel: 3,
			surfacePressure: 0,
			ports: ports(['port_1', NPS4, 'bidirectional'])
		},
		{
			type: 'branch',
			branchType: 'tee',
			id: 'T1',
			name: 'Distribution tee',
			elevation: 10,
			lossModel: 'crane',
			ports: ports(
				['run_inlet', NPS4, 'bidirectional'],
				['run_outlet', NPS4, 'bidirectional'],
				['branch', NPS3, 'bidirectional']
			)
		},
		{
			type: 'valve',
			valveType: 'globe',
			id: 'V1',
			name: 'Branch A globe valve',
			elevation: 5,
			status: 'active',
			ports: ports(['inlet', NPS3, 'inlet'], ['outlet', NPS3, 'outlet'])
		},
		{
			type: 'reservoir',
			id: 'R2',
			name: 'Lower tank A',
			elevation: 5,
			liquidLevel: 2,
			surfacePressure: 0,
			ports: ports(['port_1', NPS3, 'bidirectional'])
		},
		{
			type: 'reservoir',
			id: 'R3',
			name: 'Lower tank B',
			elevation: 0,
			liquidLevel: 2,
			surfacePressure: 0,
			ports: ports(['port_1', NPS3, 'bidirectional'])
		}
	];
	return {
		...project,
		components,
		connections: [
			pipe('L1', ['R1', 'port_1'], ['T1', 'run_inlet'], NPS4, 50, [
				fitting('entrance_sharp'),
				fitting('elbow_90_lr', 2)
			]),
			{
				...pipe('L2', ['T1', 'run_outlet'], ['V1', 'inlet'], NPS4, 1),
				piping: {
					pipes: [
						{ materialId: 'carbon_steel', schedule: '40', nominalSize: NPS4, length: 1 },
						{ materialId: 'carbon_steel', schedule: '40', nominalSize: NPS3, length: 79 }
					],
					fittings: [fitting('reducer_sudden')]
				}
			},
			pipe('L3', ['V1', 'outlet'], ['R2', 'port_1'], NPS3, 20, [fitting('exit')]),
			pipe('L4', ['T1', 'branch'], ['R3', 'port_1'], NPS3, 120, [
				fitting('elbow_90_lr', 3),
				fitting('exit')
			])
		]
	};
}

/** US gallon per minute, m³/s, and pound-force per square inch, Pa (both exact). */
const GPM = US_GALLON / 60;
const PSI = POUND_FORCE / (INCH * INCH);

/**
 * Ids of the condenser water example's project library entries: its NPS 60 pipe spec and its
 * NPS 30 butterfly valve's Cv (both illustrative inputs, sourced as such).
 */
const NPS60_SPEC = 'PS1';
const BUTTERFLY30_CV = 'RS1';

/**
 * The condenser water example's tower bypass valve's K in the winter scenario, throttled on its
 * NPS 24 bore to hold back pressure on the return (an illustrative input, as a modulating bypass
 * valve's position is): at 15,000 gpm its loss, 10.0 m, exceeds the 9.4 m from the basin's water
 * up to the tower header.
 */
const WINTER_BYPASS_K = 16.5;

/**
 * A pipe of `nps` inches and `length` m: NPS 60 refers to the project library's pipe spec, every
 * other size is standard-wall (STD, ASME B36.10M) carbon steel from the cited library.
 */
function stdPipe(nps: number, length: number): PipeDefinition {
	return nps === 60
		? { specId: NPS60_SPEC, length }
		: { materialId: 'carbon_steel', schedule: 'STD', nominalSize: nps * INCH, length };
}

/**
 * A connection of pipes in series (`stdPipe`), ordered from → to, each `[nominal size in inches,
 * length in m]`.
 */
function stdLine(
	id: string,
	from: [string, string],
	to: [string, string],
	segments: [number, number][],
	fittings: Fitting[] = []
): PipeConnection {
	return {
		id,
		fromComponentId: from[0],
		fromPortId: from[1],
		toComponentId: to[0],
		toPortId: to[1],
		piping: { pipes: segments.map(([nps, length]) => stdPipe(nps, length)), fittings }
	};
}

/** A concentric (conical, 30° included angle) reducer between pipes `pipeIndex` and the next. */
function reducer(pipeIndex = 0): Fitting {
	return { type: 'reducer_conical', quantity: 1, pipeIndex, angle: 30 };
}

/**
 * (3) Condenser water system of a 90,000 gpm chiller plant (an open circuit).
 *
 * Six 15,000 gpm condenser water pumps each take suction from the cooling tower basin's sump
 * through an NPS 30 butterfly valve and discharge through a check valve and an NPS 24 butterfly
 * valve into one NPS 60 common supply header: CWP-1 into its upstream end, CWP-2 to CWP-6 through
 * a tee each. The header then feeds seven water-cooled chiller condensers, CH-1 to CH-6 through a
 * tee each and CH-7 from its downstream end, so the water runs one way along the whole header,
 * 90,000 gpm at most (about 3.2 m/s). Four condensers are rated 15,000 gpm and three 10,000 gpm
 * (each by its pressure drop at that flow), and a flow control valve on each leaving side holds
 * its design flow. The NPS 60 common return header takes CH-1 at its upstream end and CH-2 to CH-7
 * through a tee each, passes the tower bypass tee and rises in one NPS 60 riser to the tower's
 * NPS 60 distribution header, which feeds cells 1 to 5 through a tee each and cell 6 from its end.
 * Each 15,000 gpm cell has an NPS 30 line with an isolation butterfly valve and a nozzle header
 * (rated by its pressure drop), which sprays into the open cell, modelled as a reservoir at
 * atmospheric pressure at the nozzles' elevation; the water falls to the basin the pumps draw from.
 * The NPS 24 tower bypass valve, from the return header to the basin, is closed at design; the
 * winter scenario opens it for one pump's 15,000 gpm (about 3.45 m/s), throttled to K 16.5 on its
 * bore (`WINTER_BYPASS_K`, an illustrative input) so that it holds back pressure on the return:
 * its own loss, 10.0 m, keeps the return above the tower header's 10 m, so the dead-ended riser and
 * tower header stay full above atmospheric pressure. Wide open (Crane's K 0.286), the tower header
 * would sit 7.4 m of water below atmospheric pressure, which no flag reports (only pressures below
 * the vapour pressure are flagged) but which a real riser does not hold: its vents admit air.
 *
 * The project library holds what the cited library lacks, both illustrative inputs labelled as
 * such in their sources: the NPS 60 pipe (steel STD stops at NPS 48 in the cited library), a
 * 59.25 in bore with carbon steel's Farshad roughness at that bore; and the NPS 30 butterfly
 * valves' Cv (Crane's butterfly valve table stops at NPS 24), Crane's NPS 16–24 K of 25 f_T
 * extrapolated to the NPS 30 STD bore (K = 0.274) and converted with fluids' K_to_Cv, 48,760,
 * rounded to 48,800. All twelve NPS 30 butterfly valves, the six cell valves and the six pump
 * suction valves (inline fittings), refer to that one entry.
 *
 * Datum: the basin floor. Rated drops are on water at 85 °F (995.8 kg/m³, IAPWS-95 at 1 atm),
 * the condenser entering water temperature of AHRI 550/590's standard rating conditions.
 */
export function condenserWaterExample(): Project {
	const project = base(
		'example-condenser-water',
		'Chiller plant condenser water system',
		'A 90,000 gpm condenser water system: six parallel 15,000 gpm pumps into an NPS 60 common ' +
			'header, seven chiller condensers (4 × 15,000 and 3 × 10,000 gpm) each with a flow ' +
			'control valve, and a six-cell cooling tower with a nozzle header per cell and a tower ' +
			'bypass valve, closed at design (the winter scenario opens it). Water at 85 °F. The NPS 60 ' +
			'pipe and the NPS 30 butterfly valves’ Cv are illustrative project library entries.'
	);
	project.fluid = { kind: 'builtin', fluidId: 'water', temperature: ((85 - 32) * 5) / 9 + 273.15 };
	const RATED_DENSITY = 995.8; // kg/m³, water at 85 °F
	const BASIN_LEVEL = 0.6; // m of water above the basin floor (the datum)
	const PLANT = 0.5; // m, pump and chiller nozzle centrelines
	const RETURN = 5; // m, the overhead return header
	const DISTRIBUTION = 10; // m, the tower's distribution header and cell valves
	const NOZZLES = 11; // m, the cells' nozzle headers
	const components: Component[] = [];
	const connections: PipeConnection[] = [];
	const connect = (
		from: [string, string],
		to: [string, string],
		segments: [number, number][],
		fittings: Fitting[] = []
	) => connections.push(stdLine(`L${connections.length + 1}`, from, to, segments, fittings));
	const tee = (id: string, name: string, elevation: number, branch: number) =>
		components.push({
			type: 'branch',
			branchType: 'tee',
			id,
			name,
			elevation,
			lossModel: 'crane',
			ports: ports(
				['run_inlet', 60 * INCH, 'bidirectional'],
				['run_outlet', 60 * INCH, 'bidirectional'],
				['branch', branch * INCH, 'bidirectional']
			)
		});
	/**
	 * Tees `ids[k]` named `names[k]` with NPS `branch[k]` branches along a header, joined run to
	 * run by NPS 60 pipes, `spacing[k - 1]` m from tee k − 1 to tee k.
	 */
	const header = (
		ids: string[],
		names: string[],
		elevation: number,
		branch: number[],
		spacing: number[]
	) =>
		ids.forEach((id, k) => {
			tee(id, names[k]!, elevation, branch[k]!);
			if (k > 0) connect([ids[k - 1]!, 'run_outlet'], [id, 'run_inlet'], [[60, spacing[k - 1]!]]);
		});
	const reservoir = (id: string, name: string, elevation: number, level: number, sizes: number[]) =>
		components.push({
			type: 'reservoir',
			id,
			name,
			elevation,
			liquidLevel: level,
			surfacePressure: 0,
			ports: sizes.map((nps, k) => ({
				id: `port_${k + 1}`,
				nominalSize: nps * INCH,
				direction: 'bidirectional'
			}))
		});
	const twoPort = (nps: number) =>
		ports(['inlet', nps * INCH, 'inlet'], ['outlet', nps * INCH, 'outlet']);
	const butterfly = (
		id: string,
		name: string,
		elevation: number,
		nps: number,
		{ open = true, cv }: { open?: boolean; cv?: string } = {}
	) =>
		components.push({
			type: 'valve',
			valveType: 'butterfly',
			id,
			name,
			elevation,
			status: open ? 'active' : 'isolated',
			...(cv ? { resistance: { kind: 'library' as const, id: cv } } : {}),
			ports: twoPort(nps)
		});
	const ratedDrop = (
		id: string,
		name: string,
		elevation: number,
		nps: number,
		psi: number,
		gpm: number
	) =>
		components.push({
			type: 'equipment',
			id,
			name,
			elevation,
			rating: { kind: 'point', pressureLoss: psi * PSI, flow: gpm * GPM, density: RATED_DENSITY },
			ports: twoPort(nps)
		});

	// The tower basin's sump: a suction line per pump (ports 1–6) and the bypass return (7).
	reservoir('B1', 'Cooling tower basin', 0, BASIN_LEVEL, [30, 30, 30, 30, 30, 30, 24]);

	// Chillers: CH-1 to CH-4 rated 15,000 gpm on NPS 24, CH-5 to CH-7 10,000 gpm on NPS 20.
	const chillers = [1, 2, 3, 4, 5, 6, 7].map((i) =>
		i <= 4 ? { i, gpm: 15_000, nps: 24, psi: 10 } : { i, gpm: 10_000, nps: 20, psi: 8 }
	);

	// Supply header (NPS 60): CWP-1 into its upstream end, a tee for each of CWP-2 to CWP-6 and
	// for each of CH-1 to CH-6, CH-7 from its downstream end.
	const supply = [
		'CWP-2',
		'CWP-3',
		'CWP-4',
		'CWP-5',
		'CWP-6',
		...[1, 2, 3, 4, 5, 6].map((i) => `CH-${i}`)
	];
	const supplyTee = (tag: string) => `H${supply.indexOf(tag) + 1}`;
	header(
		supply.map(supplyTee),
		supply.map((tag) => `Supply header tee at ${tag}`),
		PLANT,
		supply.map((tag) => chillers.find((c) => `CH-${c.i}` === tag)?.nps ?? 24),
		supply.slice(1).map((tag) => (tag.startsWith('CWP') ? 6 : 10))
	);

	// Pumps: suction line with a butterfly valve, pump, check valve, discharge butterfly valve.
	for (let i = 1; i <= 6; i++) {
		components.push({
			type: 'pump',
			id: `P${i}`,
			name: `Condenser water pump CWP-${i}`,
			elevation: PLANT,
			curveId: 'C1',
			speed: 1,
			status: 'on',
			ports: ports(['suction', 30 * INCH, 'inlet'], ['discharge', 24 * INCH, 'outlet'])
		});
		components.push({
			type: 'valve',
			valveType: 'check',
			id: `K${i}`,
			name: `CWP-${i} check valve`,
			elevation: PLANT,
			status: 'active',
			crackingPressure: 0,
			ports: twoPort(24)
		});
		butterfly(`D${i}`, `CWP-${i} discharge valve`, PLANT, 24);
		connect(
			['B1', `port_${i}`],
			[`P${i}`, 'suction'],
			[[30, 8]],
			[
				fitting('entrance_sharp'),
				{ ...fitting('butterfly_valve'), resistanceId: BUTTERFLY30_CV },
				fitting('elbow_90_lr')
			]
		);
		connect([`P${i}`, 'discharge'], [`K${i}`, 'inlet'], [[24, 1]]);
		connect([`K${i}`, 'outlet'], [`D${i}`, 'inlet'], [[24, 1]]);
		if (i === 1) {
			connect(
				['D1', 'outlet'],
				['H1', 'run_inlet'],
				[
					[24, 4],
					[60, 1]
				],
				[fitting('elbow_90_lr'), reducer()]
			);
		} else {
			connect(
				[`D${i}`, 'outlet'],
				[supplyTee(`CWP-${i}`), 'branch'],
				[[24, 4]],
				[fitting('elbow_90_lr')]
			);
		}
	}

	// Return header (NPS 60, overhead): CH-1 into its upstream end, a tee for each of CH-2 to
	// CH-7, then the tower bypass tee, whose run goes on up the riser.
	const returns = [2, 3, 4, 5, 6, 7].map((i) => `CH-${i}`);
	const returnTee = (tag: string) => `R${returns.indexOf(tag) + 1}`;
	header(
		[...returns.map(returnTee), 'R7'],
		[
			...returns.map((tag) => `Return header tee at ${tag}`),
			'Return header tee at the tower bypass'
		],
		RETURN,
		[...returns.map((tag) => chillers.find((c) => `CH-${c.i}` === tag)!.nps), 24],
		[...returns.slice(1).map(() => 10), 6]
	);

	// Chillers: condenser, then its flow control valve, then up to the return header.
	for (const { i, gpm, nps, psi } of chillers) {
		ratedDrop(`E${i}`, `CH-${i} condenser`, PLANT, nps, psi, gpm);
		components.push({
			type: 'valve',
			valveType: 'fcv',
			id: `F${i}`,
			name: `CH-${i} flow control valve`,
			elevation: PLANT,
			status: 'active',
			setpoint: gpm * GPM,
			ports: twoPort(nps)
		});
		if (i === 7) {
			connect(
				[supplyTee('CH-6'), 'run_outlet'],
				['E7', 'inlet'],
				[
					[60, 1],
					[nps, 6]
				],
				[reducer(), fitting('elbow_90_lr', 1, 1)]
			);
		} else {
			connect(
				[supplyTee(`CH-${i}`), 'branch'],
				[`E${i}`, 'inlet'],
				[[nps, 6]],
				[fitting('elbow_90_lr')]
			);
		}
		connect([`E${i}`, 'outlet'], [`F${i}`, 'inlet'], [[nps, 2]]);
		if (i === 1) {
			connect(
				['F1', 'outlet'],
				['R1', 'run_inlet'],
				[
					[nps, 6],
					[60, 1]
				],
				[fitting('elbow_90_lr', 2), reducer()]
			);
		} else {
			connect(
				[`F${i}`, 'outlet'],
				[returnTee(`CH-${i}`), 'branch'],
				[[nps, 6]],
				[fitting('elbow_90_lr', 2)]
			);
		}
	}

	// Tower bypass, closed at design: from the return header down to the basin.
	butterfly('BP', 'Tower bypass valve', RETURN, 24, { open: false });
	connect(['R7', 'branch'], ['BP', 'inlet'], [[24, 2]]);
	connect(
		['BP', 'outlet'],
		['B1', 'port_7'],
		[[24, 25]],
		[fitting('elbow_90_lr', 3), fitting('exit')]
	);

	// The riser to the tower's distribution header (NPS 60), then per cell an isolation valve and
	// the nozzle header, spraying into the open cell.
	connect(['R7', 'run_outlet'], ['T1', 'run_inlet'], [[60, 60]], [fitting('elbow_90_lr', 4)]);
	const cells = [1, 2, 3, 4, 5].map((i) => `T${i}`);
	header(
		cells,
		cells.map((_, k) => `Tower header tee at cell ${k + 1}`),
		DISTRIBUTION,
		cells.map(() => 30),
		cells.slice(1).map(() => 12)
	);
	const cellFeeds: [string, string][] = [
		...cells.map((t): [string, string] => [t, 'branch']),
		['T5', 'run_outlet']
	];
	cellFeeds.forEach((feed, k) => {
		const i = k + 1;
		butterfly(`IV${i}`, `Cell ${i} isolation valve`, DISTRIBUTION, 30, { cv: BUTTERFLY30_CV });
		ratedDrop(`N${i}`, `Cell ${i} nozzle header`, NOZZLES, 30, 5, 15_000);
		reservoir(`A${i}`, `Cell ${i} spray (open to atmosphere)`, NOZZLES, 0, [30]);
		const end = feed[1] === 'run_outlet';
		connect(
			feed,
			[`IV${i}`, 'inlet'],
			end
				? [
						[60, 1],
						[30, 2]
					]
				: [[30, 2]],
			end ? [reducer()] : []
		);
		connect([`IV${i}`, 'outlet'], [`N${i}`, 'inlet'], [[30, 1]]);
		connect([`N${i}`, 'outlet'], [`A${i}`, 'port_1'], [[30, 0.5]]);
	});

	// Winter: one chiller on one pump, every cell isolated and the tower bypassed through the
	// bypass valve, throttled to hold back pressure on the return (wide open, the dead-ended riser
	// and tower header would hang below atmospheric pressure).
	const status = (componentId: string, value: string): Override => ({
		kind: 'component',
		componentId,
		field: 'status',
		value
	});
	const winter: Override[] = [
		...[2, 3, 4, 5, 6].map((i) => status(`P${i}`, 'off')),
		...[2, 3, 4, 5, 6, 7].map((i) => status(`F${i}`, 'failed_closed')),
		...cellFeeds.map((_, k) => status(`IV${k + 1}`, 'isolated')),
		status('BP', 'active'),
		{
			kind: 'component',
			componentId: 'BP',
			field: 'resistance',
			value: { kind: 'K', value: WINTER_BYPASS_K }
		}
	];

	return {
		...project,
		components,
		connections,
		scenarios: [
			{
				id: 'S1',
				name: 'Winter: tower bypassed',
				description:
					'CH-1 on CWP-1; the other pumps off, the other chillers’ flow control valves ' +
					'closed, every cell isolated and the tower bypass valve open, throttled (K 16.5) ' +
					'to hold the return header, riser and tower header above atmospheric pressure.',
				overrides: winter
			}
		],
		pumpLibrary: [
			{
				id: 'C1',
				name: 'Example 15,000 gpm condenser water pump curve (illustrative)',
				points: [
					[0, 135],
					[5_000, 132],
					[10_000, 124],
					[15_000, 110],
					[18_000, 98],
					[21_000, 83]
				].map(([gpm, ft]) => ({ flow: gpm! * GPM, head: ft! * FOOT })),
				efficiencyCurve: [
					[6_000, 0.62],
					[10_000, 0.8],
					[15_000, 0.88],
					[19_000, 0.84]
				].map(([gpm, efficiency]) => ({ flow: gpm! * GPM, efficiency: efficiency! })),
				npshrCurve: [
					[5_000, 14],
					[10_000, 18],
					[15_000, 25],
					[20_000, 34]
				].map(([gpm, ft]) => ({ flow: gpm! * GPM, npshr: ft! * FOOT }))
			}
		],
		pipeLibrary: [
			{
				id: NPS60_SPEC,
				name: 'NPS 60 carbon steel, 0.375 in wall (illustrative)',
				source:
					'Illustrative example input: a 60 in OD steel pipe with a 0.375 in wall (59.25 in ' +
					'bore), not taken from a cited table. Roughness: the carbon steel library’s Farshad ' +
					'& Rieke correlation at this bore.',
				materialId: 'carbon_steel',
				innerDiameter: 59.25 * INCH,
				outerDiameter: 60 * INCH,
				nominalSize: 60 * INCH
			}
		],
		resistanceLibrary: [
			{
				id: BUTTERFLY30_CV,
				name: 'NPS 30 butterfly valve, open (illustrative)',
				source:
					'Illustrative example input, not a manufacturer’s value: Crane TP-410’s centric ' +
					'butterfly valve K for NPS 16–24, 25 f_T, extrapolated to NPS 30 (fluids 1.3.1 ' +
					'K_butterfly_valve_Crane at the STD bore 0.74294 m: K = 0.274), converted with ' +
					'fluids’ K_to_Cv (48,760) and rounded.',
				kind: 'Cv',
				value: 48_800
			}
		]
	};
}

export interface ExampleProject {
	slug: string;
	title: string;
	summary: string;
	create: () => Project;
}

export const EXAMPLES: readonly ExampleProject[] = [
	{
		slug: 'pump-transfer',
		title: 'Pump transfer between two tanks',
		summary: 'Reservoir, pump, gate valve and reservoir in series.',
		create: pumpTransferExample
	},
	{
		slug: 'gravity-branch',
		title: 'Gravity-fed branched network',
		summary: 'An elevated tank feeding two tanks through a tee, no pump.',
		create: gravityBranchExample
	},
	{
		slug: 'condenser-water',
		title: 'Chiller plant condenser water system',
		summary:
			'90,000 gpm: six parallel pumps, seven chiller condensers with flow control valves, a ' +
			'six-cell cooling tower and a tower bypass.',
		create: condenserWaterExample
	}
];

export function exampleProject(slug: string): Project | undefined {
	return EXAMPLES.find((e) => e.slug === slug)?.create();
}
