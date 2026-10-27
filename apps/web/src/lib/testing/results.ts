/**
 * Hand-built solve results for component tests. Not used by the app.
 *
 * TEST INPUTS ONLY: every number here is made up to exercise the display (unit conversion,
 * labels, flags, traces). None is computed by any method, and none is a hydraulic result of the
 * example projects whose ids they borrow for names.
 */
import type {
	ElementTrace,
	EquipmentResult,
	Flag,
	GoalSeekEvaluation,
	GoalSeekResponse,
	GoalSeekResult,
	LinkResult,
	MethodsSummary,
	NodeResult,
	PumpResult,
	SolvedState,
	SolveResponse,
	SystemCurveResponse
} from '../api/types';

/** Made-up node values at one port. */
export function node(
	componentId: string,
	portId: string,
	values: Partial<NodeResult> = {}
): NodeResult {
	return {
		componentId,
		portId,
		elevation: 0,
		velocity: 0,
		pressure: 0,
		absolutePressure: 101325,
		dynamicPressure: 0,
		totalPressure: 0,
		hgl: 0,
		egl: 0,
		...values
	};
}

/** Made-up values for a connection of one pipe segment. */
export function link(values: Partial<LinkResult> = {}): LinkResult {
	return {
		flow: 0.02,
		velocity: 2,
		headLoss: 1,
		frictionHeadLoss: 0.8,
		fittingsHeadLoss: 0.2,
		reynoldsNumber: 200000,
		frictionFactor: 0.02,
		flowRegime: 'turbulent',
		segments: [
			{
				index: 0,
				innerDiameter: 0.1,
				length: 10,
				roughness: 0.00005,
				velocity: 2,
				reynoldsNumber: 200000,
				frictionFactor: 0.02,
				flowRegime: 'turbulent',
				headLoss: 0.8
			}
		],
		fittings: [],
		...values
	};
}

export function flag(values: Partial<Flag> & Pick<Flag, 'code' | 'severity' | 'message'>): Flag {
	return { componentId: null, connectionId: null, portId: null, details: {}, ...values };
}

/** A made-up pump result: curve 0–0.03 m³/s, operating at 0.02 m³/s and 22 m. */
export function pumpResult(values: Partial<PumpResult> = {}): PumpResult {
	return {
		status: 'running',
		speed: 1,
		control: null,
		operatingFlow: 0.02,
		operatingHead: 22,
		inCurveRange: true,
		hydraulicPower: 4000,
		efficiency: 0.7,
		shaftPower: 5000,
		npshAvailable: 12,
		npshRequired: 3,
		npshMargin: 9,
		suctionAbsolutePressure: 120000,
		curve: [
			{ flow: 0, head: 30 },
			{ flow: 0.01, head: 28 },
			{ flow: 0.02, head: 22 },
			{ flow: 0.03, head: 12 }
		],
		efficiencyCurve: null,
		npshrCurve: null,
		powerCurve: null,
		// The app solves without system curves (D10); see systemCurveResponse().
		systemCurve: null,
		...values
	};
}

type SystemCurvePoint = SystemCurveResponse['points'][number];

/**
 * A system-curve point as the API sends it (POST /api/v1/system-curve): `values` over a point
 * without a head and with no reason data, which a point with a head has too (null and empty).
 */
export function systemCurvePoint(
	values: Partial<SystemCurvePoint> & { flow: number }
): SystemCurvePoint {
	return {
		head: null,
		converged: false,
		message: '',
		npshAvailable: null,
		reason: null,
		componentIds: [],
		assignedFlowNodeIds: [],
		limitFlow: null,
		passedFlow: null,
		openHead: null,
		openHeadBound: null,
		startsTried: [],
		...values
	};
}

/**
 * A made-up system curve of pump `pumpId` (POST /api/v1/system-curve): 0–0.03 m³/s, through
 * the operating point of pumpResult(). `missing` lists the indexes of points without a head
 * (their message is made up, with no reason code: the browser shows the message).
 */
export function systemCurveResponse(
	pumpId = 'P1',
	missing: readonly number[] = []
): SystemCurveResponse {
	const points = [
		{ flow: 0, head: 12 },
		{ flow: 0.01, head: 14.5 },
		{ flow: 0.02, head: 22 },
		{ flow: 0.03, head: 34.5 }
	].map((p, i) =>
		missing.includes(i)
			? systemCurvePoint({ flow: p.flow, message: 'made-up reason: not converged' })
			: systemCurvePoint({ ...p, converged: true })
	);
	return {
		pumpId,
		flowRange: { min: 0, max: 0.03, unit: 'm³/s' },
		points,
		converged: points.map((p) => p.converged),
		scenario: null
	};
}

export const SAMPLE_METHODS: MethodsSummary = {
	methodVersion: '1.0.0',
	sections: [
		{
			title: 'Pipe friction',
			items: ['Darcy–Weisbach head loss.', 'Colebrook friction factor.'],
			references: ['Colebrook, C. F. (1939).']
		}
	],
	assumptions: ['Steady, incompressible flow.'],
	libraries: { fluids: '1.3.1', scipy: '1.18.1' }
};

/** A made-up trace for connection L1 with every kind of entry. */
export const SAMPLE_TRACE: ElementTrace = {
	elementId: 'L1',
	elementType: 'pipe_connection',
	inputs: [
		{ name: 'Length', value: 5, unit: 'm', source: 'user' },
		{ name: 'Inner diameter', value: 0.1023, unit: 'm', source: 'library' },
		{ name: 'Friction method', value: 'colebrook', unit: '', source: 'default' },
		{ name: 'Flow', value: 0.02, unit: 'm³/s', source: 'computed' }
	],
	equations: ['h_f = f (L/D) v²/(2g)'],
	correlations: [{ name: 'Colebrook (1939)', citation: 'Colebrook, C. F. J. ICE 11(4), 1939.' }],
	dataSources: [{ name: 'ASME B36.10M', citation: 'ASME B36.10M-2018, Table 1.' }],
	intermediates: [
		{ name: 'Velocity', value: 2.5, unit: 'm/s' },
		{ name: 'Reynolds number', value: 250000, unit: '' },
		{ name: 'Wall shear stress', value: 3.2, unit: 'N/m²' }
	],
	notes: ['Made-up trace for tests.']
};

/** A made-up converged state for the pump transfer example (R1, P1, V1, R2; L1–L3). */
export function pumpTransferSolved(values: Partial<SolvedState> = {}): SolvedState {
	return {
		converged: true,
		methodVersion: '1.0.0',
		timestamp: '2026-10-21T00:00:00Z',
		fluid: {
			name: 'Water',
			temperature: 293.15,
			concentration: null,
			density: 998,
			dynamicViscosity: 0.001,
			kinematicViscosity: 1.002e-6,
			vaporPressure: 2339,
			sources: {
				density: { origin: 'library', citation: 'Made-up citation for tests (density).' }
			}
		},
		atmosphericPressure: 101325,
		nodeResults: {
			'R1:port_1': node('R1', 'port_1', {
				pressure: 29400,
				absolutePressure: 130725,
				hgl: 3,
				egl: 3
			}),
			'P1:suction': node('P1', 'suction', {
				pressure: 20000,
				absolutePressure: 121325,
				velocity: 2,
				hgl: 2,
				egl: 2.2
			}),
			'P1:discharge': node('P1', 'discharge', {
				pressure: 100000,
				absolutePressure: 201325,
				velocity: 4,
				hgl: 10,
				egl: 10.8
			}),
			'V1:inlet': node('V1', 'inlet', { pressure: 90000, absolutePressure: 191325, velocity: 4 }),
			'V1:outlet': node('V1', 'outlet', { pressure: 89000, absolutePressure: 190325, velocity: 4 }),
			'R2:port_1': node('R2', 'port_1', {
				elevation: 10,
				pressure: 19600,
				absolutePressure: 120925,
				hgl: 12,
				egl: 12
			})
		},
		linkResults: {
			L1: link({
				flow: 0.02,
				fittings: [
					{
						index: 0,
						type: 'entrance_sharp',
						quantity: 1,
						k: 0.5,
						referenceDiameter: 0.1,
						headLoss: 0.1,
						source: 'Made-up source for tests (entrance K).'
					}
				]
			}),
			L2: link({ flow: 0.02, velocity: 4 }),
			L3: link({ flow: 0.02, velocity: 4, headLoss: 8 })
		},
		pumpResults: { P1: pumpResult() },
		valveResults: {
			V1: {
				valveType: 'gate',
				state: 'open',
				flow: 0.02,
				headLoss: 0.1,
				pressureDrop: 1000,
				kOpen: 0.14,
				referenceDiameter: 0.078,
				kEffective: null,
				cvEffective: null,
				setpoint: null,
				setpointAchieved: null
			}
		},
		equipmentResults: {},
		branchResults: {},
		boundaryResults: {
			R1: { type: 'reservoir', egl: 3, outflow: 0.02, portOutflows: { port_1: 0.02 } },
			R2: { type: 'reservoir', egl: 12, outflow: -0.02, portOutflows: { port_1: -0.02 } }
		},
		flags: [],
		convergence: {
			innerIterations: 6,
			outerIterations: 1,
			maxContinuityResidual: { value: 0, elementId: 'P1:suction' },
			maxEnergyResidual: { value: 1e-12, elementId: 'L3' },
			oscillatingComponents: [],
			message: 'converged: 6 Newton iterations in 1 outer iteration(s)'
		},
		trace: { elements: {}, methods: SAMPLE_METHODS },
		...values
	};
}

/**
 * A made-up state for testing/helpers.ts assignedFlowProject (R1 → L1 → AF1, a demand of
 * 0.012 m³/s): AF1's port below the vapor pressure, flagged.
 */
export function assignedFlowSolved(values: Partial<SolvedState> = {}): SolvedState {
	return pumpTransferSolved({
		nodeResults: {
			'R1:port_1': node('R1', 'port_1', {
				pressure: 196000,
				absolutePressure: 297325,
				hgl: 20,
				egl: 20
			}),
			'AF1:port_1': node('AF1', 'port_1', {
				elevation: 2,
				velocity: 1.5,
				pressure: -99000,
				absolutePressure: 2325,
				hgl: -8.1,
				egl: -8
			})
		},
		linkResults: { L1: link({ flow: 0.012, velocity: 1.5 }) },
		pumpResults: {},
		valveResults: {},
		boundaryResults: {
			R1: { type: 'reservoir', egl: 20, outflow: 0.012, portOutflows: { port_1: 0.012 } },
			AF1: { type: 'assigned_flow', egl: -8, outflow: -0.012, portOutflows: { port_1: -0.012 } }
		},
		flags: [
			flag({
				code: 'BELOW_VAPOR_PRESSURE',
				severity: 'invalid',
				message:
					"absolute pressure at 'AF1:port_1' (2325 Pa) is below the vapor pressure (2339 Pa); the liquid would flash",
				componentId: 'AF1',
				portId: 'port_1',
				details: { absolutePressure: 2325, vaporPressure: 2339 }
			})
		],
		convergence: {
			innerIterations: 2,
			outerIterations: 1,
			maxContinuityResidual: { value: 0, elementId: 'AF1:port_1' },
			maxEnergyResidual: { value: 1e-12, elementId: 'L1' },
			oscillatingComponents: [],
			message: 'converged: 2 Newton iterations in 1 outer iteration(s)'
		},
		...values
	});
}

/** A made-up equipment result: 0.012 m³/s at 1.2 × the rated flow, a 36 kPa loss. */
export function equipmentResult(values: Partial<EquipmentResult> = {}): EquipmentResult {
	return {
		flow: 0.012,
		flowRatio: 1.2,
		headLoss: 3.675,
		pressureLoss: 36000,
		pressureDrop: 36500,
		rating: { kind: 'point', pressureLoss: 25000, flow: 0.01, density: 999.1 },
		...values
	};
}

/**
 * A made-up state for testing/helpers.ts equipmentProject (R1 → L1 → E1 → L2 → R2): E1 carries
 * 0.012 m³/s. `item` replaces fields of E1's result.
 */
export function equipmentSolved(
	item: Partial<EquipmentResult> = {},
	values: Partial<SolvedState> = {}
): SolvedState {
	return pumpTransferSolved({
		nodeResults: {
			'R1:port_1': node('R1', 'port_1', {
				pressure: 49000,
				absolutePressure: 150325,
				hgl: 5,
				egl: 5
			}),
			'E1:inlet': node('E1', 'inlet', {
				velocity: 1.46,
				pressure: 38000,
				absolutePressure: 139325,
				hgl: 3.88,
				egl: 3.99
			}),
			'E1:outlet': node('E1', 'outlet', {
				velocity: 1.46,
				pressure: 1500,
				absolutePressure: 102825,
				hgl: 0.15,
				egl: 0.26
			}),
			'R2:port_1': node('R2', 'port_1', { pressure: 0, absolutePressure: 101325, hgl: 0, egl: 0 })
		},
		linkResults: {
			L1: link({ flow: 0.012, velocity: 1.46 }),
			L2: link({ flow: 0.012, velocity: 1.46 })
		},
		pumpResults: {},
		valveResults: {},
		equipmentResults: { E1: equipmentResult(item) },
		boundaryResults: {
			R1: { type: 'reservoir', egl: 5, outflow: 0.012, portOutflows: { port_1: 0.012 } },
			R2: { type: 'reservoir', egl: 0, outflow: -0.012, portOutflows: { port_1: -0.012 } }
		},
		convergence: {
			innerIterations: 5,
			outerIterations: 1,
			maxContinuityResidual: { value: 0, elementId: 'E1:inlet' },
			maxEnergyResidual: { value: 1e-12, elementId: 'L2' },
			oscillatingComponents: [],
			message: 'converged: 5 Newton iterations in 1 outer iteration(s)'
		},
		...values
	});
}

export function response(
	solvedState: SolvedState,
	values: Partial<SolveResponse> = {}
): SolveResponse {
	return {
		success: solvedState.converged,
		computeTime: 0.25,
		solvedState,
		scenario: null,
		...values
	};
}

/** A made-up goal-seek evaluation of one variable and one goal (usable unless told otherwise). */
export function evaluation(
	index: number,
	x: number,
	g: number | null,
	values: Partial<GoalSeekEvaluation> = {}
): GoalSeekEvaluation {
	return {
		index,
		purpose: index === 0 ? 'start' : 'scan',
		variableValues: [x],
		outcome: g === null ? 'not_converged' : 'usable',
		goalValues: [g],
		residuals: [g === null ? null : g - 0.015],
		message: g === null ? 'made-up reason: the solve did not converge' : '',
		seconds: 0.02,
		stateChanges: [],
		...values
	};
}

/**
 * A made-up goal seek of the pump transfer example (pumpTransferSolved): Transfer pump P1's speed
 * between 20 % and 100 % to bring the flow in L2 (Transfer pump → Discharge isolation valve) to
 * 15 L/s, met at 86.1174 % after 3 evaluations. `result` replaces fields of the result.
 */
export function goalSeekResponse(
	result: Partial<GoalSeekResult> = {},
	values: Partial<GoalSeekResponse> = {}
): GoalSeekResponse {
	const speed = 0.8611744213850658;
	const base: GoalSeekResult = {
		met: true,
		stopReason: 'met',
		message: 'Every goal is met, after 3 evaluations.',
		method: 'scan_brent',
		methodVersion: '1.2.0',
		evaluationLimit: 60,
		timeBudget: 45,
		reportedEvaluation: 2,
		variables: [
			{
				index: 0,
				variable: { kind: 'component', componentId: 'P1', field: 'speed', lower: 0.2, upper: 1 },
				label: 'speed ratio of pump P1',
				unit: '',
				scale: 'linear',
				start: 1,
				startSource: 'case',
				caseValue: 1,
				baseValue: 1,
				value: speed,
				atBound: null,
				override: { kind: 'component', componentId: 'P1', field: 'speed', value: speed },
				replacedOverride: null
			}
		],
		goals: [
			{
				index: 0,
				goal: { quantity: 'link_flow', elementId: 'L2', target: 0.015 },
				label: 'flow in connection L2',
				unit: 'm³/s',
				tolerance: 7.5e-5,
				toleranceSource: 'default',
				value: 0.0150000069,
				residual: 6.9e-9,
				met: true,
				message: '',
				evaluatedMin: 0.002,
				evaluatedMax: 0.019
			}
		],
		evaluations: [
			evaluation(0, 1, 0.019),
			evaluation(1, 0.2, 0.002),
			evaluation(2, speed, 0.0150000069, { purpose: 'root' })
		],
		notes: [],
		methods: {
			title: 'Goal seek',
			items: ['Goal seek on the base case of this project: made-up methods text for tests.'],
			references: ['Made-up reference for tests.']
		},
		...result
	};
	return {
		success: base.met,
		result: base,
		solvedState: pumpTransferSolved({
			linkResults: {
				...pumpTransferSolved().linkResults,
				L2: link({ flow: 0.0150000069, velocity: 3 })
			}
		}),
		computeTime: 0.4,
		scenario: null,
		...values
	};
}
