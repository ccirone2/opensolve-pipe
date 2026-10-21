/**
 * Results tables: element names, flags per row, and display units. Expected values are computed
 * here from the unit definitions (NIST SP 811), not taken from units.ts. The solved states are
 * made-up test inputs (testing/results.ts).
 */
import { describe, expect, it } from 'vitest';
import type { BranchResult, SolvedState } from '../api/types';
import { flag, link, node, pumpResult, pumpTransferSolved } from '../testing/results';
import { gravityBranchExample, pumpTransferExample } from './examples';
import {
	availableViews,
	boundaryTable,
	branchBases,
	branchTable,
	branchVelocityBasis,
	cellLines,
	compareVersions,
	connectionName,
	elementName,
	fastestLink,
	fittingFlags,
	fittingTable,
	flagElement,
	flagsForElement,
	formatResultNumber,
	groupFlags,
	linkTable,
	lowestPressureNode,
	nodeTable,
	pumpStatusLabel,
	pumpTable,
	rowsForElement,
	segmentFlags,
	segmentTable,
	setpointText,
	siText,
	valveTable,
	versionsBetween
} from './results';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

// Definitions (exact): 1 in = 0.0254 m, 1 ft = 0.3048 m, 1 lb = 0.45359237 kg, g_n = 9.80665,
// US gallon = 231 in³.
const IN = 0.0254;
const FT = 0.3048;
const PSI = (0.45359237 * 9.80665) / (IN * IN); // Pa
const GPM = (231 * IN ** 3) / 60; // m³/s
const sig4 = (v: number) => String(Number(v.toPrecision(4)));

const project = pumpTransferExample();

describe('flags', () => {
	const flags = [
		flag({ code: 'TRANSITIONAL_FLOW', severity: 'info', message: 'i1', connectionId: 'L2' }),
		flag({
			code: 'CAVITATION',
			severity: 'invalid',
			message: 'x1',
			componentId: 'P1',
			portId: 'suction'
		}),
		flag({ code: 'PUMP_OUTSIDE_CURVE', severity: 'warning', message: 'w1', componentId: 'P1' }),
		flag({ code: 'NOT_CONVERGED', severity: 'invalid', message: 'x2' })
	];

	it('groups by severity, invalid first, keeping the order within a group', () => {
		expect(groupFlags(flags).map((g) => [g.severity, g.flags.map((f) => f.message)])).toEqual([
			['invalid', ['x1', 'x2']],
			['warning', ['w1']],
			['info', ['i1']]
		]);
		expect(groupFlags(flags.filter((f) => f.severity === 'info')).map((g) => g.severity)).toEqual([
			'info'
		]);
		expect(groupFlags([])).toEqual([]);
	});

	it('finds the element a flag is about', () => {
		expect(flags.map(flagElement)).toEqual([
			{ kind: 'connection', id: 'L2' },
			{ kind: 'component', id: 'P1' },
			{ kind: 'component', id: 'P1' },
			null
		]);
		expect(flagsForElement(flags, { kind: 'component', id: 'P1' }).map((f) => f.message)).toEqual([
			'x1',
			'w1'
		]);
		expect(flagsForElement(flags, { kind: 'connection', id: 'L2' }).map((f) => f.message)).toEqual([
			'i1'
		]);
	});
});

describe('names', () => {
	it('names components and connections, falling back to ids', () => {
		expect(elementName(project, { kind: 'component', id: 'P1' })).toBe('Transfer pump');
		expect(elementName(project, { kind: 'component', id: 'GONE' })).toBe('GONE');
		expect(connectionName(project, 'L1')).toBe('Suction tank → Transfer pump');
		expect(elementName(project, { kind: 'connection', id: 'L9' })).toBe('L9');
	});
});

describe('node table', () => {
	const solved = pumpTransferSolved({
		flags: [
			flag({
				code: 'CAVITATION',
				severity: 'invalid',
				message: 'cav',
				componentId: 'P1',
				portId: 'suction'
			}),
			flag({ code: 'PUMP_OUTSIDE_CURVE', severity: 'warning', message: 'curve', componentId: 'P1' })
		]
	});

	it('lists ports in project order, with names and port labels', () => {
		const table = nodeTable(project, solved, SI_UNITS);
		expect(table.rows.map((r) => [r.name, r.detail])).toEqual([
			['Suction tank', 'Port 1'],
			['Transfer pump', 'Suction'],
			['Transfer pump', 'Discharge'],
			['Discharge isolation valve', 'Inlet'],
			['Discharge isolation valve', 'Outlet'],
			['Discharge tank', 'Port 1']
		]);
	});

	it('marks gauge and absolute pressure in the unit labels (SI and US units)', () => {
		const si = nodeTable(project, solved, SI_UNITS).columns;
		expect(si.find((c) => c.key === 'pressure')?.unit).toBe('kPa(g)');
		expect(si.find((c) => c.key === 'absolutePressure')?.unit).toBe('kPa(a)');
		// PRD §3.2.1: static, dynamic and total pressure per node.
		expect(si.map((c) => c.label)).toEqual([
			'Elevation',
			'Pressure',
			'Dynamic pressure',
			'Total pressure',
			'Absolute pressure',
			'Velocity',
			'HGL',
			'EGL'
		]);
		expect(si.find((c) => c.key === 'dynamicPressure')?.unit).toBe('kPa');
		expect(si.find((c) => c.key === 'totalPressure')?.unit).toBe('kPa(g)');
		const us = nodeTable(project, solved, IMPERIAL_UNITS).columns;
		expect(us.find((c) => c.key === 'dynamicPressure')?.unit).toBe('psi');
		expect(us.find((c) => c.key === 'totalPressure')?.unit).toBe('psig');
		expect(us.find((c) => c.key === 'pressure')?.unit).toBe('psig');
		expect(us.find((c) => c.key === 'absolutePressure')?.unit).toBe('psia');
		expect(us.find((c) => c.key === 'hgl')?.unit).toBe('ft');
	});

	it('converts SI values to the display units', () => {
		const discharge = nodeTable(project, solved, IMPERIAL_UNITS).rows[2]!;
		expect(discharge.cells.pressure).toBe(sig4(100000 / PSI));
		expect(discharge.cells.absolutePressure).toBe(sig4(201325 / PSI));
		expect(discharge.cells.velocity).toBe(sig4(4 / FT));
		expect(discharge.cells.egl).toBe(sig4(10.8 / FT));
		const kpa = nodeTable(project, solved, SI_UNITS).rows[2]!;
		expect(kpa.cells.pressure).toBe('100');
		const moving = nodeTable(
			project,
			{
				...solved,
				nodeResults: {
					'P1:discharge': {
						...solved.nodeResults['P1:discharge']!,
						dynamicPressure: 7987.2,
						totalPressure: 107987.2
					}
				}
			},
			IMPERIAL_UNITS
		).rows[0]!;
		expect(moving.cells.dynamicPressure).toBe(sig4(7987.2 / PSI));
		expect(moving.cells.totalPressure).toBe(sig4(107987.2 / PSI));
	});

	it('shows a flag on the row of the port it names only', () => {
		const rows = nodeTable(project, solved, SI_UNITS).rows;
		expect(rows.map((r) => r.flags.map((f) => f.message))).toEqual([[], ['cav'], [], [], [], []]);
	});
});

describe('link table', () => {
	const solved = pumpTransferSolved();

	it('names connections from → to and converts flow to gpm', () => {
		const table = linkTable(project, solved, IMPERIAL_UNITS);
		expect(table.columns.find((c) => c.key === 'flow')?.unit).toBe('gpm');
		expect(table.rows.map((r) => r.name)).toEqual([
			'Suction tank → Transfer pump',
			'Transfer pump → Discharge isolation valve',
			'Discharge isolation valve → Discharge tank'
		]);
		expect(table.rows[0]!.cells.flow).toBe(sig4(0.02 / GPM));
		expect(table.rows[0]!.cells.reynoldsNumber).toBe('200000');
		expect(table.rows[0]!.cells.flowRegime).toBe('Turbulent');
	});

	it('lists segments and fittings with K and its source', () => {
		const link = solved.linkResults.L1!;
		const segments = segmentTable('L1', link, IMPERIAL_UNITS);
		expect(segments.columns.find((c) => c.key === 'innerDiameter')?.unit).toBe('in');
		expect(segments.rows[0]!.cells.innerDiameter).toBe(sig4(0.1 / IN));
		const fittings = fittingTable('L1', link, SI_UNITS);
		expect(fittings.rows[0]!.name).toBe('Entrance, sharp-edged');
		expect(fittings.rows[0]!.cells.k).toBe('0.5');
		expect(fittings.rows[0]!.cells.source).toBe('Made-up source for tests (entrance K).');
		const named = fittingTable('L1', link, SI_UNITS, () => 'Library name');
		expect(named.rows[0]!.name).toBe('Library name');
	});

	it('keeps results of connections that no longer exist, by id', () => {
		const edited = { ...project, connections: project.connections.filter((c) => c.id !== 'L2') };
		expect(linkTable(edited, solved, SI_UNITS).rows.map((r) => r.name)).toEqual([
			'Suction tank → Transfer pump',
			'Discharge isolation valve → Discharge tank',
			'L2'
		]);
	});
});

describe('pump, valve, branch and boundary tables', () => {
	it('shows pump speed and efficiency as percentages and power in kW or hp', () => {
		const solved = pumpTransferSolved();
		const si = pumpTable(project, solved, SI_UNITS);
		const row = si.rows[0]!;
		expect(row.name).toBe('Transfer pump');
		expect(row.detail).toBe('Pump · P1');
		expect(row.cells).toMatchObject({
			status: 'Running',
			speed: '100',
			efficiency: '70',
			hydraulicPower: '4',
			npshMargin: '9'
		});
		expect(si.columns.find((c) => c.key === 'hydraulicPower')?.unit).toBe('kW');
		const us = pumpTable(project, solved, IMPERIAL_UNITS);
		expect(us.columns.find((c) => c.key === 'hydraulicPower')?.unit).toBe('hp');
		expect(us.rows[0]!.cells.hydraulicPower).toBe(sig4(4000 / (550 * FT * 0.45359237 * 9.80665)));
	});

	it('shows a control valve setpoint in pressure (gauge) or flow units', () => {
		const solved = pumpTransferSolved();
		const valve = solved.valveResults.V1!;
		expect(valveTable(project, solved, SI_UNITS).rows[0]!.cells).toMatchObject({
			type: 'Gate',
			state: 'Open',
			setpoint: '—',
			setpointAchieved: '—'
		});
		expect(setpointText({ ...valve, valveType: 'prv', setpoint: 200000 }, IMPERIAL_UNITS)).toBe(
			`${sig4(200000 / PSI)} psig`
		);
		expect(setpointText({ ...valve, valveType: 'fcv', setpoint: 0.01 }, SI_UNITS)).toBe('10 L/s');
	});

	it('lists a tee’s port flows, K and losses per port in port order', () => {
		const gravity = gravityBranchExample();
		const solved: SolvedState = pumpTransferSolved({
			branchResults: {
				T1: {
					branchType: 'tee',
					lossModel: 'crane',
					pattern: 'diverging from run_inlet',
					combinedPortId: 'run_inlet',
					portFlows: { branch: -0.01, run_inlet: 0.03, run_outlet: -0.02 },
					kFactors: { branch: 1.2, run_outlet: 0.1 },
					pathHeadLosses: { run_outlet: 0.05, branch: 0.6 },
					referenceVelocity: 3,
					correlation: 'Made-up correlation text',
					inCorrelationRange: false
				}
			}
		});
		const row = branchTable(gravity, solved, SI_UNITS).rows[0]!;
		expect(row.name).toBe('Distribution tee');
		expect(cellLines(row.cells.portFlows!)).toEqual([
			'Run inlet: 30',
			'Run outlet: -20',
			'Branch: -10'
		]);
		expect(cellLines(row.cells.kFactors!)).toEqual(['Run outlet: 0.1', 'Branch: 1.2']);
		expect(cellLines(row.cells.correlation!)).toEqual([
			'Made-up correlation text',
			'Outside the correlation’s range.'
		]);
	});

	it('shows boundary heads and outflows', () => {
		const rows = boundaryTable(project, pumpTransferSolved(), SI_UNITS).rows;
		expect(rows.map((r) => [r.name, r.cells.egl, r.cells.outflow])).toEqual([
			['Suction tank', '3', '20'],
			['Discharge tank', '12', '-20']
		]);
	});
});

describe('views and summaries', () => {
	it('offers views that have results', () => {
		expect(availableViews(pumpTransferSolved())).toEqual([
			'summary',
			'nodes',
			'links',
			'pumps',
			'valves',
			'boundaries',
			'methods'
		]);
		expect(availableViews(pumpTransferSolved({ pumpResults: {}, valveResults: {} }))).toEqual([
			'summary',
			'nodes',
			'links',
			'boundaries',
			'methods'
		]);
	});

	it('collects the rows of one element', () => {
		const groups = rowsForElement(project, pumpTransferSolved(), SI_UNITS, {
			kind: 'component',
			id: 'P1'
		});
		expect(groups.map((g) => [g.title, g.rows.map((r) => r.detail)])).toEqual([
			['Pump', ['Pump · P1']],
			['Ports', ['Suction', 'Discharge']]
		]);
	});

	it('finds the lowest pressure and the highest velocity', () => {
		const solved = pumpTransferSolved();
		expect(lowestPressureNode(solved)?.componentId).toBe('R2');
		expect(fastestLink(solved)).toEqual({ id: 'L2', velocity: 4 });
	});
});

describe('method versions', () => {
	it('compares dotted versions numerically', () => {
		expect(compareVersions('1.10.0', '1.9.2')).toBe(1);
		expect(compareVersions('1.0', '1.0.0')).toBe(0);
		expect(compareVersions('0.9.0', '1.0.0')).toBe(-1);
	});

	it('lists the versions after the older one up to the newer one, oldest first', () => {
		const versions = [
			{ version: '1.2.0' },
			{ version: '1.0.0' },
			{ version: '1.1.0' },
			{ version: '2.0.0' }
		];
		expect(versionsBetween(versions, '1.0.0', '1.2.0').map((v) => v.version)).toEqual([
			'1.1.0',
			'1.2.0'
		]);
		expect(versionsBetween(versions, '1.2.0', '1.0.0').map((v) => v.version)).toEqual([
			'1.1.0',
			'1.2.0'
		]);
		expect(versionsBetween(versions, '2.0.0', '2.0.0')).toEqual([]);
	});
});

describe('number display', () => {
	it('writes small and large numbers as ×10ⁿ, not e-notation', () => {
		expect(formatResultNumber(2.555e-6)).toBe('2.555×10⁻⁶');
		expect(formatResultNumber(-3.211e-24)).toBe('-3.211×10⁻²⁴');
		expect(formatResultNumber(1.5e12)).toBe('1.5×10¹²');
		expect(formatResultNumber(0.1154)).toBe('0.1154');
		expect(formatResultNumber(0)).toBe('0');
	});

	it('resolves heads and elevations to 0.01 m (or 4 significant figures where finer)', () => {
		// Made-up test input: a valve 1000 m above the datum, 0.1154 m of loss across it and a
		// velocity head of 0.33 m (the 4-significant-figure display showed all four as "1004").
		const solved = pumpTransferSolved({
			nodeResults: {
				'V1:inlet': node('V1', 'inlet', { elevation: 1000, hgl: 1003.7, egl: 1004.03 }),
				'V1:outlet': node('V1', 'outlet', { elevation: 1000, hgl: 1003.5846, egl: 1003.9146 })
			}
		});
		const si = nodeTable(project, solved, SI_UNITS).rows.map((r) => [r.cells.hgl, r.cells.egl]);
		expect(si).toEqual([
			['1003.7', '1004.03'],
			['1003.58', '1003.91']
		]);
		// In feet, 0.01 ft (finer than 0.01 m) is shown.
		const us = nodeTable(project, solved, IMPERIAL_UNITS).rows[0]!.cells;
		expect(us.egl).toBe(String(Number((1004.03 / FT).toFixed(2))));
		expect(us.elevation).toBe(String(Number((1000 / FT).toFixed(2))));
		// Small heads keep 4 significant figures.
		const small = pumpTransferSolved({
			nodeResults: { 'V1:inlet': node('V1', 'inlet', { hgl: 0.012345, egl: 0.012345 }) }
		});
		expect(nodeTable(project, small, SI_UNITS).rows[0]!.cells.hgl).toBe('0.01235');
	});

	it('shows round-off below the solver resolution as "≈ 0", with the exact value as a note', () => {
		// Made-up test input: a connection without flow whose head loss is round-off.
		const solved = pumpTransferSolved({
			linkResults: { L1: link({ flow: 0, headLoss: 8.686e-13 }) }
		});
		const cell = linkTable(project, solved, SI_UNITS).rows[0]!.cells.headLoss!;
		expect(cell).toEqual({
			text: '≈ 0',
			title: "8.686×10⁻¹³ m: round-off, below the solver's resolution"
		});
		expect(cellLines(cell)).toEqual(['≈ 0']);
		// A real small loss (above the solver's 1e-7 m) is shown.
		const real = pumpTransferSolved({ linkResults: { L1: link({ headLoss: 2.555e-6 }) } });
		expect(linkTable(project, real, SI_UNITS).rows[0]!.cells.headLoss).toBe('2.555×10⁻⁶');
	});
});

describe('connections of several pipes', () => {
	// Made-up test input: a 102.3 mm pipe then a 52.5 mm pipe; the second is transitional.
	const solved = pumpTransferSolved({
		linkResults: {
			...pumpTransferSolved().linkResults,
			L1: link({
				fittings: pumpTransferSolved().linkResults.L1!.fittings,
				velocity: 0.9,
				reynoldsNumber: 1493,
				frictionFactor: 0.0429,
				flowRegime: 'laminar',
				segments: [
					{
						index: 0,
						innerDiameter: 0.1023,
						length: 5,
						roughness: 4.6e-5,
						velocity: 0.9,
						reynoldsNumber: 1493,
						frictionFactor: 0.0429,
						flowRegime: 'laminar',
						headLoss: 0.01
					},
					{
						index: 1,
						innerDiameter: 0.0525,
						length: 5,
						roughness: 4.6e-5,
						velocity: 3.42,
						reynoldsNumber: 2909,
						frictionFactor: 0.045,
						flowRegime: 'transitional',
						headLoss: 0.5
					}
				]
			})
		},
		flags: [
			flag({
				code: 'TRANSITIONAL_FLOW',
				severity: 'warning',
				message: "connection 'L1' segment 1: Re = 2909 is in the transition range",
				connectionId: 'L1',
				details: { segmentIndex: 1, reynoldsNumber: 2909 }
			}),
			flag({
				code: 'CORRELATION_OUT_OF_RANGE',
				severity: 'warning',
				message: "connection 'L1' fitting 0 (entrance_sharp): made-up reason",
				connectionId: 'L1',
				details: { fittingIndex: 0 }
			})
		]
	});

	it('shows velocity, Re, f and regime for each pipe, numbered from 1', () => {
		const row = linkTable(project, solved, SI_UNITS).rows[0]!;
		expect(row.detail).toBe('L1 · 2 pipes');
		expect(cellLines(row.cells.velocity!)).toEqual(['Pipe 1: 0.9', 'Pipe 2: 3.42']);
		expect(cellLines(row.cells.reynoldsNumber!)).toEqual(['Pipe 1: 1493', 'Pipe 2: 2909']);
		expect(cellLines(row.cells.flowRegime!)).toEqual(['Pipe 1: Laminar', 'Pipe 2: Transitional']);
		// A connection of one pipe keeps single values.
		expect(linkTable(project, solved, SI_UNITS).rows[1]!.cells.velocity).toBe('4');
	});

	it('attaches flags to the pipe and fitting they are about', () => {
		const link = solved.linkResults.L1!;
		const segments = segmentTable('L1', link, SI_UNITS, solved.flags);
		expect(segments.rows.map((r) => [r.name, r.flags.map((f) => f.code)])).toEqual([
			['Pipe 1', []],
			['Pipe 2', ['TRANSITIONAL_FLOW']]
		]);
		const fittings = fittingTable('L1', link, SI_UNITS, undefined, solved.flags);
		expect(fittings.rows[0]!.detail).toBe('Fitting 1');
		expect(fittings.rows[0]!.flags.map((f) => f.code)).toEqual(['CORRELATION_OUT_OF_RANGE']);
		expect(segmentFlags(solved.flags, 'L1', 0)).toEqual([]);
		expect(fittingFlags(solved.flags, 'L2', 0)).toEqual([]);
	});
});

describe('pump status', () => {
	const reversal = (headRise: number, shutoffHead: number) =>
		flag({
			code: 'PUMP_FLOW_REVERSAL',
			severity: 'invalid',
			message: 'made-up',
			componentId: 'P1',
			details: { headRise, shutoffHead }
		});

	it('tells a dead-headed pump from one the system head stops, and stays neutral otherwise', () => {
		const held = pumpResult({ status: 'no_flow', operatingFlow: 0, operatingHead: 30 });
		expect(pumpStatusLabel(held, [reversal(30, 30)])).toBe(
			'No flow (discharge closed off: dead-headed at shutoff head)'
		);
		expect(pumpStatusLabel(held, [reversal(35, 30)])).toBe('No flow (system head above shutoff)');
		expect(pumpStatusLabel(held)).toBe('No flow (held at zero by its check)');
		expect(pumpStatusLabel(pumpResult())).toBe('Running');
	});

	it('shows no speed for an off pump', () => {
		const solved = pumpTransferSolved({
			pumpResults: { P1: pumpResult({ status: 'off', operatingFlow: 0, hydraulicPower: 0 }) }
		});
		expect(pumpTable(project, solved, SI_UNITS).rows[0]!.cells).toMatchObject({
			status: 'Off',
			speed: '—'
		});
	});
});

describe('branch velocity basis', () => {
	const gravity = gravityBranchExample();
	// Made-up test inputs for tee T1.
	const crane: BranchResult = {
		branchType: 'tee',
		lossModel: 'crane',
		pattern: 'diverging from run_inlet',
		combinedPortId: 'run_inlet',
		portFlows: { branch: -0.01, run_inlet: 0.03, run_outlet: -0.02 },
		kFactors: { branch: 1.2, run_outlet: 3e-24 },
		pathHeadLosses: { run_outlet: 0.05, branch: 0.6 },
		referenceVelocity: 4.233,
		correlation: 'Made-up correlation text',
		inCorrelationRange: true
	};

	it('gives the combined-flow velocity for Crane, and labels the pattern', () => {
		const solved = pumpTransferSolved({ branchResults: { T1: crane } });
		const row = branchTable(gravity, solved, SI_UNITS).rows[0]!;
		expect(row.cells.pattern).toBe('Diverging from run inlet');
		expect(cellLines(row.cells.kVelocity!)).toEqual(['Combined flow: 4.233']);
		expect(cellLines(row.cells.kFactors!)).toEqual(['Run outlet: ≈ 0', 'Branch: 1.2']);
		expect([...branchBases(solved)]).toEqual(['combined']);
	});

	it('gives each leg’s own velocity for the flagged Darby fallback', () => {
		const darby: BranchResult = {
			...crane,
			pattern: 'diverging from branch',
			combinedPortId: 'branch',
			portFlows: { run_inlet: -0.017, run_outlet: -0.018, branch: 0.035 },
			kFactors: { run_inlet: 1.088, run_outlet: 1.088 },
			pathHeadLosses: { run_inlet: 0.719, run_outlet: 0.76 }
		};
		const solved = pumpTransferSolved({
			branchResults: { T1: darby },
			nodeResults: {
				'T1:run_inlet': node('T1', 'run_inlet', { velocity: 3.6 }),
				'T1:run_outlet': node('T1', 'run_outlet', { velocity: 3.7 }),
				'T1:branch': node('T1', 'branch', { velocity: 4.233 })
			},
			flags: [
				flag({
					code: 'TEE_PATTERN_FALLBACK',
					severity: 'warning',
					message: 'made-up',
					componentId: 'T1'
				})
			]
		});
		const row = branchTable(gravity, solved, SI_UNITS).rows[0]!;
		expect(row.cells.pattern).toBe('Diverging from branch');
		expect(cellLines(row.cells.kVelocity!)).toEqual(['Run inlet: 3.6', 'Run outlet: 3.7']);
		expect(branchVelocityBasis('T1', darby, solved.flags)).toBe('own');
		expect(branchVelocityBasis('T1', { ...crane, lossModel: 'ideal' }, [])).toBe('none');
	});
});

describe('valve flow direction', () => {
	it('states the sign of the flow in the column heading', () => {
		const columns = valveTable(project, pumpTransferSolved(), SI_UNITS).columns;
		expect(columns.find((c) => c.key === 'flow')?.label).toBe('Flow (+ inlet → outlet)');
	});
});

describe('SI quantities in API text', () => {
	it('shows them in display units, diameters in the diameter unit', () => {
		const text =
			'Crane (D_run = 0.1023 m, D_branch = 0.0779 m, angle 90°); 0.02 m³/s at 5 m, -52340.5 Pa';
		expect(siText(text, IMPERIAL_UNITS)).toBe(
			`Crane (D_run = ${sig4(0.1023 / IN)} in, D_branch = ${sig4(0.0779 / IN)} in, angle 90°); ${sig4(0.02 / GPM)} gpm at ${String(Number((5 / FT).toFixed(2)))} ft, ${sig4(-52340.5 / PSI)} psi`
		);
		expect(siText('Re = 2909, no units here', SI_UNITS)).toBe('Re = 2909, no units here');
	});

	it('converts the units in a branch’s correlation text', () => {
		const solved = pumpTransferSolved({
			branchResults: {
				T1: {
					branchType: 'tee',
					lossModel: 'crane',
					pattern: 'diverging from run_inlet',
					combinedPortId: 'run_inlet',
					portFlows: { run_inlet: 0.03, run_outlet: -0.02, branch: -0.01 },
					kFactors: { run_outlet: 0.1, branch: 1.2 },
					pathHeadLosses: { run_outlet: 0.05, branch: 0.6 },
					referenceVelocity: 3,
					correlation: 'Made-up correlation (D_run = 0.1023 m)',
					inCorrelationRange: true
				}
			}
		});
		const row = branchTable(gravityBranchExample(), solved, SI_UNITS).rows[0]!;
		expect(cellLines(row.cells.correlation!)).toEqual(['Made-up correlation (D_run = 102.3 mm)']);
	});
});
