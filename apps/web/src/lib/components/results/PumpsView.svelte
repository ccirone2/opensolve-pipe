<!--
	Pumps: status, operating point, speed, efficiency, power and NPSH per pump, then the pump and
	system curves of the pump being viewed (one at a time, chosen when there are several). Its
	system curve is computed on demand for the exact project of this solve and cached with it
	(D10; ProjectStore.loadSystemCurve), and can be cancelled while it is computed. With scenarios,
	the chart also shows the other cases' operating points (and, on request, their system curves on
	this chart's flow grid; proposal scenario-manager.md §6.13): those of every case other than the
	one shown that the chart shows, whichever case is shown. A pump the scenario of these results
	changed says so in the table (`changed`). The cases the user unticks are one choice of page
	state for this chart's list and the card's, each chart keeping the cases past its own cap, so
	the chart's list is kept when another pump is shown (proposal pumps-results-layout.md §9 S8).

	Under it, with two pumps or more, the Pumps together card (CLAUDE.md D21, proposal
	pump-groups.md §6): its members are page state (the workspace's `pumpGroup`, the same in every
	case), defaulting to the group suggested on the topology as solved for the pump viewed; its
	group curve is computed on demand for this solve and case, cached with it (ProjectStore
	loadGroupCurve), and after its answer the group system curve (slice 4b, loadGroupSystemCurve).

	Slice 4d (one pump off) with pump lineups (CLAUDE.md D24 slice L1, proposal pump-lineups.md
	§7): for a parallel station, while the base case is shown and current, the Add cases block makes
	the cases of its preset (page state: By number running, the pumps that stop first by the stop
	order switched off, or Each pump off, 4d's cases) in one undo step, and turns on "Also show the
	other cases' station duties": each other case's group curve is asked for (one request at a
	time, after the case shown's curves and while no calculation runs; at most six cases, one
	lineup of each number running first), its duty drawn as a numbered ring. "Running
	combinations" lists every case's members. The card asks again for the curves a solve, Solve
	all or goal seek cancelled, once no calculation runs; a change of members or of the case shown
	withdraws the other cases' requests (those still waiting, on a case switch), which are asked
	again after the shown case's.

	Pump lineups slice L3 (CLAUDE.md D24, proposal pump-lineups.md §9.1): each other case is
	compared with the case shown inside the station, both as solved (sameInside, its fingerprints
	kept as the rest's are), and its members switched on counted, so the card can draw a ring's own
	group curve while the shown case's is drawn; this case's count labels its own curve.

	The section nav (proposal pumps-results-layout.md §5.4, §9 S2), with the Pumps together card:
	the tab's first child, one button per section drawn. Each section registers its target here
	(section-nav.svelte.ts) with its mark: Per pump's flags, the pump chart's failed requests, and
	in the card the station's flags, the group chart's refusal and failed requests, and Running
	combinations' current cases. The nav is pinned only once the pump chart's canvas has scrolled
	out (PumpChart's `canvasArea`), in the Results pane's `scroller`, while the view is `active`.
-->
<script lang="ts">
	import { untrack } from 'svelte';
	import type {
		Project,
		PumpGroupCurveResponse,
		PumpGroupStation,
		SolvedState
	} from '$lib/api/types';
	import { useWorkspace } from '$lib/state/workspace.svelte';
	import {
		hydraulicFingerprint,
		wantsGroupSystemCurve,
		type FlowRange,
		type GroupCurveState
	} from '$lib/state/project.svelte';
	import { caseResponse } from '$lib/utils/compare';
	import type { ChartImageSource } from '$lib/utils/export/chart-image';
	import { calculatingReason, solveAllReason } from '$lib/utils/goal-seek';
	import { settingsSourceLabel } from '$lib/utils/design-checks';
	import { componentById } from '$lib/utils/graph';
	import {
		caseMarkers,
		MAX_CHART_CASES,
		pumpChartCases,
		ratedCurveRange,
		tickCase,
		untickCase,
		type CaseChart,
		type CaseChoice,
		type CaseList,
		type OtherCaseInput,
		type PumpChecksInput
	} from '$lib/utils/pump-chart';
	import {
		flagsForElement,
		Formatter,
		markChanged,
		PUMP_STATUS_TONES,
		pumpStatusParts,
		pumpTable,
		resultsProject,
		type ResultsView,
		type Row,
		type TableSort
	} from '$lib/utils/results';
	import { defaultGroup, pressureControlOnly, suggestGroups } from '$lib/utils/pump-groups';
	import {
		dutyFlow,
		namesProject,
		stationResponse,
		type GroupMemberInput
	} from '$lib/utils/pump-group-chart';
	import {
		chartKeys,
		combinationExtremes,
		MAX_GROUP_CASES,
		groupCurveDrawn,
		otherGroupCases,
		runningCombinations,
		sameInside,
		sharedRest,
		type CombinationsInput,
		type InsideComparison,
		type OtherGroupCase
	} from '$lib/utils/pump-group-one-off';
	import {
		lineupChartPriority,
		lineupPlan,
		movedStopOrder,
		pumpLineup,
		withLineupCases,
		type LineupPreset
	} from '$lib/utils/pump-lineups';
	import type { CaseId } from '$lib/utils/scenarios';
	import { flagSeverities, sectionMark } from '$lib/utils/section-nav';
	import BackToSections from './BackToSections.svelte';
	import CellValue from './CellValue.svelte';
	import PumpChart from './PumpChart.svelte';
	import PumpGroupChart from './PumpGroupChart.svelte';
	import type { LineupsBlockProps } from './PumpLineupsBlock.svelte';
	import PumpsNav from './PumpsNav.svelte';
	import ResultsTable from './ResultsTable.svelte';
	import { provideSectionNav, registerSection, type SectionTarget } from './section-nav.svelte';

	interface Props {
		solved: SolvedState;
		changed?: ReadonlySet<string>;
		/** A sort for the table (the Summary's links). */
		sortRequest?: (TableSort & { id: number }) | null;
		/** Show another Results view with the focus on its tab (the pump chart's Go to Checks). */
		onview?: (view: ResultsView) => void;
		/** The view is shown (ResultsPanel keeps visited views mounted, hidden): the nav's observers run. */
		active?: boolean;
		/** The Results pane's scroller, in which the section nav pins. */
		scroller?: HTMLElement | null;
		/** The section nav pinned (its height in px), or not (null): the scroller's scroll padding. */
		onpinned?: (height: number | null) => void;
	}

	let {
		solved,
		changed = new Set(),
		sortRequest = null,
		onview,
		active = true,
		scroller = null,
		onpinned
	}: Props = $props();
	const ws = useWorkspace();
	const uid = $props.id();
	const table = $derived(
		markChanged(pumpTable(ws.labelsProject, solved, ws.displayUnits), changed)
	);
	/** Pumps with a result, in table order. */
	const pumps = $derived(table.rows.filter((row) => solved.pumpResults[row.key]));
	let chosen = $state<string | null>(null);
	const viewed = $derived(pumps.find((row) => row.key === chosen) ?? pumps[0] ?? null);
	const result = $derived(viewed ? solved.pumpResults[viewed.key] : undefined);
	/** A pump of the solve is speed-controlled (CLAUDE.md D11). */
	const anyControlled = $derived(Object.values(solved.pumpResults).some((r) => r?.control));
	/** Another pump than the one viewed is speed-controlled and on: it regulates in its system curve. */
	const othersControlled = $derived(
		Object.entries(solved.pumpResults).some(
			([id, r]) => id !== viewed?.key && r?.control && r.control.state !== 'off'
		)
	);
	/** The solve response these results come from (a curve is only shown with its own solve). */
	const response = $derived(
		ws.store.results.response?.solvedState === solved ? ws.store.results.response : null
	);
	const system = $derived(viewed ? ws.store.systemCurve(response, viewed.key) : undefined);
	/**
	 * What an image of the chart names, and why none can be made of these results (proposal
	 * export.md §5.5): one rule with the export's (Compare's response, and its convergence).
	 */
	const image = $derived.by((): ChartImageSource | undefined => {
		if (!response) return undefined;
		const status = ws.store.caseStatus(ws.store.activeCase);
		const unavailable = !(response.success && response.solvedState.converged)
			? 'This solve did not converge: its values are not a solution, so no image is made.'
			: !caseResponse(status, ws.store.results)
				? status === 'not_reached'
					? 'Solve all stopped before it reached this case; the chart shows results from an earlier version of the project, so no image is made.'
					: 'The latest solve failed; the chart shows results from an earlier version of the project, so no image is made.'
				: calculatingReason(ws.store.calculating, 'export');
		return {
			projectName: ws.store.project.metadata.name,
			timestamp: response.solvedState.timestamp,
			methodVersion: response.solvedState.methodVersion,
			stale: ws.store.results.stale,
			unavailable,
			origin: typeof location === 'undefined' ? '' : location.origin,
			notify: (kind, text) => ws.notify(kind, text)
		};
	});
	// The curve's data range, from the project exactly as solved (the curve that was solved).
	const ratedRange = $derived(
		viewed && ws.store.solvedProject && response
			? ratedCurveRange(ws.store.solvedProject, viewed.key)
			: null
	);

	/**
	 * The design checks as solved (D19), whose limits the chart shows: the project's checks and the
	 * viewed pump's curve (manufacturer data). Neither is a scenario value, so the base sent is the
	 * case's.
	 */
	const checks = $derived.by((): PumpChecksInput | null => {
		const project = response ? ws.store.solvedProject : null;
		const settings = project?.settings.designChecks;
		if (!project || !settings || !viewed) return null;
		const pump = componentById(project, viewed.key);
		const curve =
			pump?.type === 'pump'
				? (project.pumpLibrary.find((c) => c.id === pump.curveId) ?? null)
				: null;
		return {
			checks: settings,
			curve,
			sources: {
				npshMargin: settings.npshMargin ? settingsSourceLabel(settings.npshMargin.source) : null,
				operatingRegion: settings.operatingRegion
					? settingsSourceLabel(settings.operatingRegion.source)
					: null
			}
		};
	});

	/**
	 * Why a system-curve point has no head is told with the results' names and each element's
	 * kind in the project as solved (its rule), as the curve was computed for that project.
	 */
	const curveNames = $derived({ project: ws.labelsProject, solved: ws.store.solvedProject });

	// Compute the system curve of the pump being viewed, once per solve (a new solve resets the
	// cache; a failure or cancellation waits for "Try again").
	$effect(() => {
		const id = viewed?.key;
		if (!id || !response) return;
		untrack(() => ws.store.loadSystemCurve(id));
	});

	const hasScenarios = $derived(ws.scenarios.length > 0);
	/** The flow grid of the curve shown: other cases' curves are computed on it. */
	const grid = $derived<FlowRange | null>(
		system?.status === 'ready'
			? { flowMin: system.curve.flowRange.min, flowMax: system.curve.flowRange.max }
			: null
	);
	/**
	 * The other cases' system curves are asked for (`overlay`), for the other cases the chart draws
	 * (pumpCases' `shown`), derived from the cases that are other now, so a case switch asks for the
	 * case that became another, never for the case shown.
	 */
	let overlay = $state(false);
	/** Counts the times the box was ticked: asking again computes the curves cancelled or failed. */
	let asked = $state(0);
	let retried = 0;
	const caseOf = (key: string) => (key === '' ? null : key);

	/**
	 * Other cases whose last solve converged with a result for this pump, by Compare's rule (the
	 * export's too, proposal export.md §3.4): a case whose latest solve failed, or that a stopped
	 * run did not reach, is not drawn.
	 */
	const others = $derived.by((): OtherCaseInput[] => {
		const pumpId = viewed?.key;
		if (!pumpId || !hasScenarios) return [];
		return ws.store.caseIds
			.filter((c) => c !== ws.store.activeCase)
			.flatMap((c) => {
				const r = ws.store.resultsFor(c);
				// Compare's rule: a failed or not reached case's earlier response is not drawn.
				const response = caseResponse(ws.store.caseStatus(c), r);
				const pump = response?.solvedState.pumpResults[pumpId];
				if (!response || !pump || !(response.success && response.solvedState.converged)) {
					return [];
				}
				const curve = overlay && grid ? ws.store.systemCurve(response, pumpId, grid) : undefined;
				return [
					{
						key: c ?? '',
						name: ws.caseName(c),
						result: pump,
						stale: r.stale,
						system: curve?.status === 'ready' ? curve.curve : null
					}
				];
			});
	});

	/**
	 * The other cases whose last solve converged, by Compare's rule as `others`, whatever the pump:
	 * the cases a pump's chart draws are among them, and their places are the same for every pump,
	 * though a case can give one pump no result (a pump closed off on both sides, SDD §4.10) and
	 * another one a result. caseMarkers' `all` (§9 S8 Markers; S8 second check MARK-2).
	 */
	const solvedOthers = $derived(
		hasScenarios
			? ws.store.caseIds
					.filter((c) => c !== ws.store.activeCase)
					.filter((c) => {
						const response = caseResponse(ws.store.caseStatus(c), ws.store.resultsFor(c));
						return !!response && response.success && response.solvedState.converged;
					})
					.map((c) => c ?? '')
			: []
	);

	/**
	 * One choice of cases for both charts (pumps-results-layout.md §9 S8, the owner's answer 2):
	 * the cases the user unticked under either list, and each chart's own (past its cap at an
	 * untick), page state, so the pump chart's list is kept when another pump is shown.
	 */
	const choice = $derived<CaseChoice>({
		unticked: ws.casesUnticked,
		pump: ws.pumpChartUnticked,
		group: ws.pumpGroupUnticked
	});
	/** The pump chart's cases not drawn by the choice: the user's and its own. */
	const pumpUnticked = $derived([...choice.unticked, ...choice.pump]);
	/**
	 * The pump chart's cases (§9 S8 Slots): a case in which this pump is off takes no slot while
	 * the other cases' system curves are not asked for, since it would draw nothing.
	 */
	const pumpCases = $derived(pumpChartCases(others, pumpUnticked, overlay));
	const overlayKeys = $derived(pumpCases.shown.map((o) => o.key));
	/**
	 * Their markers (§9 S8 Markers, pump-chart.ts caseMarkers): while five other cases or fewer
	 * have a converged result (solvedOthers, whatever the pump), each its place's among them, fixed
	 * by case; past five, a case keeps its marker while it stays drawn, through an untick, the other
	 * cases' system curves switched and another pump shown (the markers drawn last are page state,
	 * ws.pumpChartMarkers).
	 */
	const pumpMarkers = $derived.by(() => {
		const markers = caseMarkers(
			overlayKeys,
			pumpCases.listed.map((o) => o.key),
			ws.pumpChartMarkers,
			solvedOthers
		);
		ws.pumpChartMarkers = markers;
		return markers;
	});
	/** The keys as one value: the requests below are made again only when the cases change. */
	const overlayList = $derived(overlayKeys.join('\u0000'));

	const overlayStates = $derived(
		viewed && overlay && grid
			? overlayKeys.map((key) => {
					const response = ws.store.resultsFor(caseOf(key)).response;
					return ws.store.systemCurve(response, viewed.key, grid);
				})
			: []
	);
	const overlayProgress = $derived(
		overlayStates.some((s) => s?.status === 'loading')
			? {
					done: overlayStates.filter((s) => s && s.status !== 'loading').length,
					total: overlayStates.length
				}
			: null
	);

	// Asked for: compute each case's curve on the grid of the curve shown, once it is known.
	$effect(() => {
		const pumpId = viewed?.key;
		const range = grid;
		if (!overlay || !pumpId || !range) return;
		const keys = overlayList ? overlayList.split('\u0000') : [];
		const ask = asked;
		untrack(() => {
			// Asking again (ticking the box again) computes the ones cancelled or failed.
			const retry = ask !== retried;
			retried = ask;
			for (const key of keys) {
				ws.store.loadSystemCurve(pumpId, { caseId: caseOf(key), range, retry });
			}
		});
	});

	function setOverlay(on: boolean) {
		if (on && !overlay) asked++;
		overlay = on;
	}

	// ---- Pumps together (D21) ----------------------------------------------------------------

	/** The project the results belong to (as solved while out of date, else the labels project). */
	const groupSolvedProject = $derived(resultsProject(ws.labelsProject, solved));
	/**
	 * The pumps with a result, as the card's boxes (curves and ranges from the project as solved;
	 * names current, or as solved for a pump deleted since, as the card names everything).
	 */
	const groupPumps = $derived.by((): Omit<GroupMemberInput, 'slot'>[] => {
		const project = ws.store.solvedProject;
		return pumps.map((row) => {
			const pump = project ? componentById(project, row.key) : undefined;
			return {
				id: row.key,
				name: componentById(ws.labelsProject, row.key)
					? row.name
					: (componentById(groupSolvedProject, row.key)?.name ?? row.name),
				result: solved.pumpResults[row.key]!,
				ratedRange: project && response ? ratedCurveRange(project, row.key) : null,
				curveId: pump?.type === 'pump' ? pump.curveId : null,
				flags: flagsForElement(solved.flags, { kind: 'component', id: row.key })
			};
		});
	});
	/**
	 * The groups suggested on the case as solved (once per solve): the scenario applied to the base
	 * sent, so a PRV or PSV a scenario sets active (or not) is read as the API reads it.
	 */
	const caseSolved = $derived(response ? ws.store.caseInputs() : null);
	const suggestions = $derived(
		caseSolved && pumps.length >= 2
			? suggestGroups(
					caseSolved,
					pumps.map((row) => row.key)
				)
			: []
	);
	/** The boxes ticked by slot: the user's, else the group suggested for the pump viewed. */
	const groupSlots = $derived(ws.pumpGroup ?? defaultGroup(suggestions, viewed?.key ?? null));
	/**
	 * The pump on the pump chart, while the members are the group suggested for it (no choice of
	 * the user's yet, and a group found holds it): the card's suggestion line names it
	 * (pumps-results-layout.md §5.3 Members, F29).
	 */
	const suggestedFor = $derived(
		!ws.pumpGroup && viewed && suggestions.some((s) => s.pumpIds.includes(viewed.key))
			? (groupPumps.find((p) => p.id === viewed.key)?.name ?? viewed.name)
			: null
	);
	// Their ids are reserved while shown ticked, the default group's too (ws.reservedIds).
	$effect(() => {
		ws.pumpGroupShown = groupSlots;
	});
	/**
	 * The members with a result in this case. The station's extent is the same in every case
	 * (topology), but whether the API accepts it can differ (an active PRV or PSV inside).
	 */
	const groupMembers = $derived(
		groupSlots.filter((pumpId): pumpId is string => !!pumpId && !!solved.pumpResults[pumpId])
	);
	/**
	 * Why these results give the card no values: a solve that did not converge, or (Compare's
	 * rule) the earlier results shown after a failed solve or a stopped Solve all.
	 */
	const groupUnavailable = $derived.by(() => {
		if (!response)
			return 'These results are not the latest solve of this case: no group curve is computed for them.';
		if (!(response.success && response.solvedState.converged))
			return 'This solve did not converge: its values are not a solution, so the card shows none.';
		const status = ws.store.caseStatus(ws.store.activeCase);
		if (!caseResponse(status, ws.store.results))
			return status === 'not_reached'
				? 'Solve all stopped before it reached this case; the card shows nothing from an earlier version of the project.'
				: 'The latest solve failed; the card shows nothing from an earlier version of the project.';
		return null;
	});
	const groupState = $derived(
		groupUnavailable ? undefined : ws.store.groupCurve(response, groupMembers)
	);
	const groupSystemState = $derived(
		groupUnavailable ? undefined : ws.store.groupSystemCurve(response, groupMembers)
	);
	const groupList = $derived(groupMembers.join('\u0000'));

	// Opening the card with two members or more asks for their group curve, once per solve.
	$effect(() => {
		const ids = groupList ? groupList.split('\u0000') : [];
		if (!ws.pumpGroupOpen || ids.length < 2 || !response || groupUnavailable) return;
		untrack(() => ws.store.loadGroupCurve(ids));
	});
	// Then, once the group curve has answered (with a duty, or refused only for an active PRV or
	// PSV inside), their group system curve, once per solve (slice 4b).
	const wantsSystem = $derived(wantsGroupSystemCurve(groupState));
	$effect(() => {
		const ids = groupList ? groupList.split('\u0000') : [];
		if (!ws.pumpGroupOpen || !wantsSystem || ids.length < 2 || !response) return;
		untrack(() => ws.store.loadGroupSystemCurve(ids));
	});

	function cancelOverlay() {
		const pumpId = viewed?.key;
		if (!pumpId || !grid) return;
		for (const key of overlayKeys) {
			ws.store.cancelSystemCurve(pumpId, { caseId: caseOf(key), range: grid });
		}
	}

	// ---- Add cases (D24) and the other cases (slice 4d) ---------------------------------------

	/** The station the card shows: the group curve's answer, else the group system curve's. */
	const groupStation = $derived(
		groupUnavailable ? null : stationResponse(groupState, groupSystemState)
	);
	const groupSystemShown = $derived(
		!groupUnavailable && groupSystemState?.status === 'ready' ? groupSystemState.response : null
	);
	/** A curve a calculation (a solve, Solve all, a goal seek) cancelled: asked again after it. */
	const cancelledByCalculation = (state: GroupCurveState | undefined) =>
		state?.status === 'cancelled' && state.by !== 'user';
	/**
	 * Answered, or failed or cancelled by the user: one a calculation cancelled is still to answer,
	 * since it is asked again once the calculation ends. That is what a case not asked yet says
	 * during a calculation ("…, then for this case's curves": otherGroupCases). It does not keep
	 * the order of the requests: the first requests wait while a calculation runs, and when it
	 * ends the effect that asks again runs first in the same flush and turns such a curve to
	 * loading before the first requests' effect reads it; for the order it is only defensive.
	 */
	const settled = (state: GroupCurveState | undefined) =>
		!!state && state.status !== 'loading' && !cancelledByCalculation(state);
	/** The case shown's curves have answered: the other cases' requests come after them. */
	const shownSettled = $derived(settled(groupState) && (!wantsSystem || settled(groupSystemState)));

	/**
	 * The other cases with values by Compare's rule (a failed or not reached case's earlier
	 * response is never used), in case order, while the card shows a station.
	 */
	const valuedOthers = $derived.by(() => {
		if (!hasScenarios || !groupStation) return [];
		return ws.store.caseIds
			.filter((c) => c !== ws.store.activeCase)
			.flatMap((c) => {
				const results = ws.store.resultsFor(c);
				const response = caseResponse(ws.store.caseStatus(c), results);
				if (!response || !(response.success && response.solvedState.converged)) return [];
				return [{ key: c ?? '', caseId: c, name: ws.caseName(c), stale: results.stale, response }];
			});
	});
	/**
	 * The cases on the chart: one lineup of each number running first, most running first, then
	 * the other lineups, then case order, at most six (D24 §4.6, lineupChartPriority).
	 */
	const chartCaseKeys = $derived(
		chartKeys(valuedOthers, ws.store.project, groupMembers, [...choice.unticked, ...choice.group])
	);
	/**
	 * The other cases with values in the chart's order (D24 §4.6, unticked ones in their place):
	 * "Cases on this chart" lists them, and the rings are numbered, in that order (§7.9, §6).
	 */
	const chartOrdered = $derived.by(() => {
		const rank = new Map(
			lineupChartPriority(valuedOthers, ws.store.project, groupMembers).map((key, i) => [key, i])
		);
		return [...valuedOthers].sort((a, b) => (rank.get(a.key) ?? 0) - (rank.get(b.key) ?? 0));
	});
	/**
	 * Whether a case as solved is the same as the one shown outside the station (sharedRest),
	 * kept while both projects and the station are the same objects: the fingerprints are not
	 * computed again on every change of a curve's state.
	 */
	const restMemo: Record<
		string,
		{ shown: Project | null; other: Project | null; station: PumpGroupStation; shared: boolean }
	> = {};
	function shared(caseId: CaseId, station: PumpGroupStation): boolean {
		const shown = ws.store.caseInputs(ws.store.activeCase);
		const other = ws.store.caseInputs(caseId);
		const key = caseId ?? '';
		const known = restMemo[key];
		if (known && known.shown === shown && known.other === other && known.station === station) {
			return known.shared;
		}
		const value = sharedRest(shown, other, station, hydraulicFingerprint);
		restMemo[key] = { shown, other, station, shared: value };
		return value;
	}
	/**
	 * How a case as solved compares with the one shown inside the station (D24 §9.1 condition 4,
	 * sameInside), kept as `shared` is: the fingerprints are not computed again on every change of
	 * a curve's state.
	 */
	const insideMemo: Record<
		string,
		{
			shown: Project | null;
			other: Project | null;
			station: PumpGroupStation;
			inside: InsideComparison;
		}
	> = {};
	function inside(caseId: CaseId, station: PumpGroupStation): InsideComparison {
		const shown = ws.store.caseInputs(ws.store.activeCase);
		const other = ws.store.caseInputs(caseId);
		const key = caseId ?? '';
		const known = insideMemo[key];
		if (known && known.shown === shown && known.other === other && known.station === station) {
			return known.inside;
		}
		const value = sameInside(shown, other, station, hydraulicFingerprint);
		insideMemo[key] = { shown, other, station, inside: value };
		return value;
	}
	/** The members switched on in a case as solved (D24 §9.1's k; null without its project). */
	const runningIn = (solvedCase: Project | null) =>
		solvedCase ? pumpLineup(undefined, solvedCase, groupMembers).on.length : null;
	/** This case's members switched on as solved: its own curve's label (D24 §9.3). */
	const shownOn = $derived(runningIn(caseSolved));
	const otherCases = $derived.by((): OtherGroupCase[] => {
		if (!groupStation) return [];
		const station = groupStation.station;
		return otherGroupCases({
			valued: chartOrdered.map((v) => {
				const solvedCase = ws.store.caseInputs(v.caseId);
				const on = runningIn(solvedCase);
				return {
					key: v.key,
					caseId: v.caseId,
					name: v.name,
					stale: v.stale,
					group: ws.store.groupCurve(v.response, groupMembers),
					system: ws.store.groupSystemCurve(v.response, groupMembers),
					shared: shared(v.caseId, station),
					solved: solvedCase,
					// Its curve state (D24 §9.1): for every case with its project as solved.
					...(on !== null ? { inside: inside(v.caseId, station), on } : {})
				};
			}),
			curveDrawn: groupCurveDrawn(groupState),
			shownKeys: new Set(chartCaseKeys),
			othersOn: ws.pumpGroupOthers,
			shownSettled,
			calculating: ws.store.calculating,
			station,
			systemShown: groupSystemShown,
			memberIds: groupMembers,
			project: namesProject(ws.labelsProject, groupSolvedProject),
			boxes: groupPumps.map((p) => p.id)
		});
	});
	/**
	 * The other cases' duties being computed: the cases on the chart settled, of them all. None
	 * while a calculation runs: no other case is asked then (each says what it waits for), so
	 * nothing is computed for them and there is nothing of theirs to cancel.
	 */
	const othersProgress = $derived.by(() => {
		const onChart = otherCases.filter((o) => o.onChart);
		const pending = (o: OtherGroupCase) => o.state === 'loading' || o.state === 'waiting';
		if (!ws.pumpGroupOthers || ws.store.calculating !== null || !onChart.some(pending)) {
			return null;
		}
		return { done: onChart.filter((o) => !pending(o)).length, total: onChart.length };
	});
	/** The responses of the cases on the chart, in the chart's order (requests go in that order). */
	const chartResponses = $derived(
		chartCaseKeys.flatMap((key) => {
			const v = valuedOthers.find((x) => x.key === key);
			return v ? [{ caseId: v.caseId, response: v.response }] : [];
		})
	);

	// Once no calculation runs, ask again for every curve of the card a solve, Solve all or goal
	// seek cancelled (the shown case's first): a cancelled curve is never asked again otherwise.
	$effect(() => {
		const ids = groupList ? groupList.split('\u0000') : [];
		if (!ws.pumpGroupOpen || ws.store.calculating !== null || ids.length < 2 || groupUnavailable)
			return;
		const group = cancelledByCalculation(groupState);
		const system = wantsSystem && cancelledByCalculation(groupSystemState);
		// The other cases' after the case shown's curves, as their first requests (§2.4).
		const others =
			ws.pumpGroupOthers && shownSettled
				? chartResponses.map(({ caseId, response }) => {
						const g = ws.store.groupCurve(response, ids);
						return {
							caseId,
							group: cancelledByCalculation(g),
							system:
								g?.status === 'refused' &&
								wantsGroupSystemCurve(g) &&
								cancelledByCalculation(ws.store.groupSystemCurve(response, ids))
						};
					})
				: [];
		untrack(() => {
			if (group) ws.store.loadGroupCurve(ids, { retry: true });
			if (system) ws.store.loadGroupSystemCurve(ids, { retry: true });
			for (const other of others) {
				if (other.group) ws.store.loadGroupCurve(ids, { caseId: other.caseId, retry: true });
				if (other.system) {
					ws.store.loadGroupSystemCurve(ids, { caseId: other.caseId, retry: true });
				}
			}
		});
	});

	// Asked for (the box ticked), once the shown case's curves have answered and while no
	// calculation runs (its end may ask again for the shown case's first): each other case's
	// group curve on the chart, and for a case refused only for an active PRV or PSV inside, its
	// group system curve (its duty). One request at a time, on the store's queue.
	$effect(() => {
		const ids = groupList ? groupList.split('\u0000') : [];
		if (!ws.pumpGroupOpen || !ws.pumpGroupOthers || ids.length < 2 || groupUnavailable) return;
		if (ws.store.calculating !== null || !shownSettled) return;
		const wanted = chartResponses.map(({ caseId, response }) => ({
			caseId,
			group: ws.store.groupCurve(response, ids),
			system: ws.store.groupSystemCurve(response, ids)
		}));
		untrack(() => {
			for (const w of wanted) {
				if (w.group === undefined) ws.store.loadGroupCurve(ids, { caseId: w.caseId });
				else if (
					w.group.status === 'refused' &&
					pressureControlOnly(w.group.issues) &&
					w.system === undefined
				) {
					ws.store.loadGroupSystemCurve(ids, { caseId: w.caseId });
				}
			}
		});
	});

	/**
	 * Cancel a case's group curve and group system curve while they are computed (or wait): by
	 * the user, or withdrawn by the card (`forget`, only those still waiting with `waiting`).
	 */
	function cancelCase(
		caseId: CaseId,
		ids: readonly string[] = groupMembers,
		options: { forget?: boolean; waiting?: boolean } = {}
	) {
		ws.store.cancelGroupCurve(ids, { caseId, ...options });
		ws.store.cancelGroupSystemCurve(ids, { caseId, ...options });
	}
	// A change of members: the other cases' requests for the members before are withdrawn, never
	// cancelled by the user; they read as never asked, so going back to those members asks again.
	let membersBefore: string[] = [];
	$effect(() => {
		const ids = groupList ? groupList.split('\u0000') : [];
		const before = membersBefore;
		membersBefore = ids;
		if (before.length < 2 || before.join('\u0000') === ids.join('\u0000')) return;
		untrack(() => {
			for (const c of ws.store.caseIds) {
				if (c !== ws.store.activeCase) cancelCase(c, before, { forget: true });
			}
		});
	});
	// Another case shown, also when this view is drawn anew after it (the views visited are kept
	// per solve, so a case switched on another view draws this one anew): the other cases'
	// requests still waiting their turn are withdrawn, so the curves of the case now shown go
	// first in the one queue; the one being computed goes on. They are asked again after the
	// shown case's curves, as first requests.
	let caseBefore: CaseId | undefined;
	$effect(() => {
		const active = ws.store.activeCase;
		const before = caseBefore;
		caseBefore = active;
		if (before === active) return;
		untrack(() => {
			for (const c of ws.store.caseIds) {
				if (c !== active) cancelCase(c, groupMembers, { forget: true, waiting: true });
			}
		});
	});

	function setOthers(on: boolean) {
		ws.pumpGroupOthers = on;
		if (!on) for (const v of valuedOthers) cancelCase(v.caseId);
	}
	/**
	 * Tick or untick a case under "Cases on the chart" (`pump`) or "Cases on this chart" (`group`):
	 * one choice for both lists (§9 S8, pump-chart.ts untickCase and tickCase). Unticking leaves
	 * its place free on each chart that drew it; ticking brings it back on each chart with room.
	 * The card's list counts while its chart draws the other cases (the card open, "Also show the
	 * other cases' station duties" ticked), or while its cases are a set the user chose under
	 * "Cases on this chart" (ws.pumpGroupChosen), which it keeps as drawn: a case ticked again
	 * under "Cases on the chart" then never takes the place of one the user ticked on the card
	 * (S8 second check CHOICE-2). Otherwise a chart that draws no case keeps no place free and
	 * holds none past its cap, so its own unticks never change then (§12 answer 2: no ring the
	 * user never touched is unticked). A case leaving the card's chart has its requests
	 * cancelled, as before.
	 */
	function tickChoice(chart: CaseChart, key: string, on: boolean) {
		const lists: Partial<Record<CaseChart, CaseList>> = {
			pump: {
				listed: pumpCases.listed.map((o) => o.key),
				shown: overlayKeys,
				cap: MAX_CHART_CASES - 1
			},
			...((ws.pumpGroupOpen && ws.pumpGroupOthers) || ws.pumpGroupChosen
				? {
						group: {
							listed: valuedOthers.map((o) => o.key),
							shown: chartCaseKeys,
							cap: MAX_GROUP_CASES
						}
					}
				: {})
		};
		const onGroupChart = chartCaseKeys.includes(key);
		const next = on ? tickCase(choice, key, chart, lists) : untickCase(choice, key, lists);
		ws.casesUnticked = next.unticked;
		ws.pumpChartUnticked = next.pump;
		ws.pumpGroupUnticked = next.group;
		if (chart === 'group') ws.pumpGroupChosen = true;
		if (!on && onGroupChart) cancelCase(caseOf(key));
	}
	function cancelOthers() {
		for (const o of otherCases) if (o.onChart) cancelCase(o.caseId);
	}
	function retryOthers() {
		// Unavailable while a calculation runs (othersRetryReason): nothing is sent until it ends.
		if (ws.store.calculating !== null) return;
		for (const o of otherCases) {
			if (!o.onChart || !o.retry) continue;
			ws.store.loadGroupCurve(groupMembers, { caseId: o.caseId, retry: true });
			const v = valuedOthers.find((x) => x.key === o.key);
			const group = v ? ws.store.groupCurve(v.response, groupMembers) : undefined;
			if (group?.status === 'refused' && wantsGroupSystemCurve(group)) {
				ws.store.loadGroupSystemCurve(groupMembers, { caseId: o.caseId, retry: true });
			}
		}
	}

	/**
	 * Solve all in the Add cases block: the Scenarios menu's reasons, from the one function
	 * CaseMenu.svelte calls (a single solve named by its case).
	 */
	const toSolve = $derived(ws.store.casesToSolve());
	const caseErrors = $derived(ws.store.casesWithErrors());
	const solveAll = $derived.by(() => {
		const count = toSolve.length;
		const reason = solveAllReason({
			empty: !ws.store.project.components.length,
			calculating: ws.store.calculating,
			solvingCase: ws.store.solvingCase,
			toSolve: count,
			errors: caseErrors,
			caseName: (c) => ws.caseName(c)
		});
		return {
			count,
			canRun: !reason,
			reason,
			hint: `Solves each case whose results are missing or out of date, one after another: up to ${count} solve${count === 1 ? '' : 's'}.`,
			// solveAllReason's reasons while a solve, Solve all or a goal seek runs pass; the others
			// last, and the block shows them (pumps-results-layout.md §5.3 item 5).
			passing: !!reason && ws.store.calculating !== null
		};
	});
	/**
	 * The Add cases block (D24 §7.4): what its preset would make now, from the base case's results
	 * (Compare's rule), with the stop order derived from the one the user set (ws.pumpStopOrder,
	 * used while it holds exactly the pumps on; never written here).
	 */
	const plan = $derived.by(() => {
		if (!groupStation) return null;
		const results = ws.store.resultsFor(null);
		const response = caseResponse(ws.store.caseStatus(null), results);
		return lineupPlan({
			project: ws.store.project,
			shownCase: ws.store.activeCase,
			station: groupStation.station,
			memberIds: groupMembers,
			base: response ? { response, stale: results.stale } : null,
			preset: ws.lineupPreset,
			savedOrder: ws.pumpStopOrder
		});
	});
	/**
	 * Add the cases in one undo step, its label the preset's, its notice the plan's (said first in
	 * the step's notice); then "Also show the other cases' station duties" is ticked (4d's).
	 */
	function addLineups() {
		const now = plan;
		if (!now || now.gate || now.refusal || !now.add.length) return;
		const added = ws.updateStored(
			(draft) => withLineupCases(draft, now.add),
			now.undoLabel,
			now.notice ?? ''
		);
		if (!added) return;
		ws.pumpGroupOthers = true;
	}
	function setPreset(preset: LineupPreset) {
		ws.lineupPreset = preset;
	}
	/** A move in the stop order (page state), from the order used, which the plan derived. */
	function moveStop(pumpId: string, dir: 'up' | 'down') {
		const order = plan?.stopOrder?.order;
		if (order) ws.pumpStopOrder = movedStopOrder(order, pumpId, dir);
	}
	/** Default order: none saved, so the default is used (the last listed stops first). */
	function resetStopOrder() {
		ws.pumpStopOrder = [];
	}
	function solveAllCases() {
		if (solveAll.canRun) void ws.solveAll();
	}
	/** "Pump lineups table…" (D24 slice L2, §8.1): the manager on Pump lineups, the card's pumps. */
	function openTable() {
		ws.openManager({ pumps: groupMembers });
	}
	const lineups = $derived<LineupsBlockProps | null>(
		plan
			? {
					plan,
					solveAll,
					onpreset: setPreset,
					onmove: moveStop,
					ondefaultorder: resetStopOrder,
					onadd: addLineups,
					othersOn: ws.pumpGroupOthers,
					onsolveall: solveAllCases,
					ontable: openTable
				}
			: null
	);

	/**
	 * Running combinations' order (pumps-results-layout.md §5.3, §9 S5): the case shown, then the
	 * other cases with values in the chart's order (lineupChartPriority's, chartOrdered), then the
	 * cases without values in case order. Neither an untick under "Cases on this chart" nor "Also
	 * show …" moves a case: the chart's order holds whether a case is ticked or not.
	 */
	const combinationsOrder = $derived.by((): CaseId[] => {
		const active = ws.store.activeCase;
		const valued = new Set(chartOrdered.map((v) => v.caseId));
		return [
			active,
			...chartOrdered.map((v) => v.caseId),
			...ws.store.caseIds.filter((c) => c !== active && !valued.has(c))
		];
	});
	/** Running combinations: every case's members, in its order (slice 4d §3; §5.3). */
	const combinationsInput = $derived.by((): CombinationsInput | null => {
		if (!hasScenarios || !groupStation) return null;
		const f = new Formatter(ws.displayUnits);
		const dutyLine = (duty: { flow: number; head: number }) =>
			`Station ${f.value(dutyFlow(duty.flow), 'flow')} at a rise of ${f.value(duty.head, 'head')}`;
		const shownLine = (response: PumpGroupCurveResponse) =>
			response.duty
				? dutyLine(response.duty)
				: `No duty: ${response.message || 'the station has no duty in this case.'}`;
		const active = ws.store.activeCase;
		const nameOf = (id: string) => groupPumps.find((p) => p.id === id)?.name ?? id;
		return {
			members: groupMembers.map((id) => ({ id, name: nameOf(id), slot: groupSlots.indexOf(id) })),
			cases: combinationsOrder.map((c) => {
				const status = ws.store.caseStatus(c);
				const results = ws.store.resultsFor(c);
				const other = otherCases.find((o) => o.caseId === c);
				return {
					key: c ?? '',
					name: ws.caseName(c),
					shown: c === active,
					status,
					response: caseResponse(status, results),
					stale: results.stale,
					station:
						c === active
							? shownLine(groupStation)
							: other
								? other.state === 'ready' && other.duty
									? `${dutyLine(other.duty)}: ${other.words}`
									: other.words
								: null,
					ring: other?.number ?? null
				};
			}),
			prefs: ws.displayUnits,
			project: ws.store.project
		};
	});
	const combinations = $derived(combinationsInput ? runningCombinations(combinationsInput) : null);
	const extremes = $derived(combinationsInput ? combinationExtremes(combinationsInput) : null);

	// ---- The section nav (pumps-results-layout.md §5.4) ----------------------------------------

	/** Shown with the Pumps together card: two pumps or more with results (§5.3 item 0). */
	const navShown = $derived(pumps.length > 1);
	/** The sections drawn, in document order: one button each. */
	let sections = $state.raw<SectionTarget[]>([]);
	let nav: PumpsNav | undefined = $state();
	/**
	 * The nav's height in px (the tab's `--pumps-nav-h`), and while it is pinned the scroller's
	 * scroll padding for it (`--pumps-nav-pad`: its height and 0.5 rem, ResultsPanel's). A scroll
	 * to a target honours both the scroller's padding and the target's margin, so a target's margin
	 * is what the padding does not already hold: below the pump chart the nav's height and 0.5 rem
	 * while it is static (it pins as the target comes up), nothing more while pinned; above it (Per
	 * pump, Pump chart, where the nav unpins) 0.5 rem less the padding. Each lands 0.5 rem under
	 * the nav, or under the pane's top (§5.4 A press).
	 */
	let navHeight = $state(0);
	let navPinned = $state<number | null>(null);
	/** The pump chart's canvas, or what stands in its place: the nav pins once it is out. */
	let pumpCanvas = $state<HTMLElement | null>(null);
	let perPumpHeading: HTMLElement | undefined = $state();
	let pumpChartHeading: HTMLElement | undefined = $state();
	const inDocumentOrder = (a: SectionTarget, b: SectionTarget) =>
		a.target === b.target
			? 0
			: a.target.compareDocumentPosition(b.target) & Node.DOCUMENT_POSITION_FOLLOWING
				? -1
				: 1;
	provideSectionNav({
		get shown() {
			return navShown;
		},
		register(section) {
			sections = [...sections.filter((s) => s.key !== section.key), section].sort(inDocumentOrder);
			return () => {
				sections = sections.filter((s) => s !== section);
			};
		},
		back() {
			nav?.focusCurrent();
		},
		go(key) {
			nav?.go(key);
		}
	});
	registerSection(
		'per-pump',
		() => perPumpHeading,
		() => sectionMark(flagSeverities(table.rows.flatMap((row) => row.flags)))
	);
	registerSection(
		'pump-chart',
		() => pumpChartHeading,
		() =>
			sectionMark({
				failed:
					system?.status === 'error' || overlayStates.some((state) => state?.status === 'error')
			})
	);
</script>

<!--
	A per-pump cell (docs/proposals/pumps-nits.md item 2): Status is a pill holding the pump's state
	word, tinted by the state alone (PUMP_STATUS_TONES), any qualifier after it as plain text, so the
	cell says the label's words, word for word (pumpStatusLabel). No border, icon or glyph, so it
	never reads as a flag pill or a control; `leading-5` with no padding above or below keeps the
	row's 20 px line, and on a phone the qualifier wraps after the pill. Every other cell as
	ResultsTable draws it.
-->
{#snippet statusCell(row: Row, key: string)}
	{@const cell = row.cells[key] ?? '—'}
	{@const result = key === 'status' ? solved.pumpResults[row.key] : undefined}
	{#if result}
		{@const parts = pumpStatusParts(result, row.flags)}
		<span class="min-w-0"
			><span
				data-status-pill
				class={[
					'inline-block rounded-full px-2 align-top text-xs leading-5 font-medium whitespace-nowrap',
					PUMP_STATUS_TONES[parts.state]
				]}>{parts.word}</span
			>{parts.detail ? ` ${parts.detail}` : ''}</span
		>
	{:else if typeof cell === 'string'}{cell}{:else}<CellValue {cell} />{/if}
{/snippet}

<div
	class="space-y-4"
	style:--pumps-nav-h={navShown ? `${navHeight}px` : undefined}
	style:--pumps-nav-pad={navShown
		? navPinned === null
			? '0px'
			: `calc(${navPinned}px + 0.5rem)`
		: undefined}
>
	{#if navShown}
		<!-- The section nav (§5.4): the tab's first child, static here, pinned once the pump
			canvas has scrolled out. -->
		<PumpsNav
			bind:this={nav}
			bind:height={navHeight}
			{sections}
			{scroller}
			canvas={pumpCanvas}
			{active}
			onpinned={(height) => {
				navPinned = height;
				onpinned?.(height);
			}}
		/>
	{/if}
	<!--
		Results per pump (proposal pumps-results-layout.md §5.3 item 1): the table and its note under
		a visible heading, the title every other section has (tabindex −1, the section nav's target
		from S2); the table keeps its visually hidden caption, its name. A plain div, not a landmark.
	-->
	<div class="space-y-2" data-pump-table>
		<h3
			bind:this={perPumpHeading}
			id="{uid}-per-pump"
			class="scroll-mt-[calc(0.5rem-var(--pumps-nav-pad,0px))] text-base font-semibold"
			tabindex="-1"
		>
			Results per pump
		</h3>
		<ResultsTable
			{table}
			{sortRequest}
			caption="Results per pump"
			first="Pump"
			onselect={(row) => ws.inspect(row.element)}
			cellContent={statusCell}
		/>
	</div>
	<p class="text-xs text-slate-600">
		Head is the rise in the energy grade line across the pump; for a pump held at zero flow it is
		the head across it (its shutoff head when its discharge is closed off). NPSH available is
		computed from the absolute suction pressure and the fluid's vapor pressure; it is not shown when
		the fluid has no vapor pressure. An off pump has no speed.
		{#if anyControlled}A speed-controlled pump's speed is the one it runs at: solved to hold its
			setpoint, or its minimum or maximum speed when its drive is at a limit (its trace states the
			rule that put it there).{/if}
	</p>
	{#if viewed && result}
		<div class="card space-y-3 p-3" data-pump-chart>
			<!--
				The header row (proposal pumps-results-layout.md §5.3 item 2): the h3 and, with more
				than one pump, the select it names, beside it from a 26 rem container (the desktop
				split) and under it below, so on a phone the select has the row's whole width and
				shows a name's end, often what tells two pumps apart ("… CWP-1" to "… CWP-6"; §15
				item 17). The select's sentence stays visible: a choice starts a system curve, a cost
				(§6.4 item 8).
			-->
			<div class="@container">
				<div class="flex flex-col gap-x-3 gap-y-1 @min-[26rem]:flex-row @min-[26rem]:items-center">
					<h3
						bind:this={pumpChartHeading}
						id="{uid}-pump-chart"
						class="shrink-0 scroll-mt-[calc(0.5rem-var(--pumps-nav-pad,0px))] text-base font-semibold"
						tabindex="-1"
					>
						Pump chart
					</h3>
					{#if pumps.length > 1}
						<select
							class="input pr-8 @min-[26rem]:w-auto @min-[26rem]:flex-1"
							aria-labelledby="{uid}-pump-chart"
							aria-describedby="{uid}-pump-chart-hint"
							value={viewed.key}
							onchange={(event) => {
								// The cases' choice is kept: page state for both charts (§9 S8).
								chosen = event.currentTarget.value;
							}}
						>
							{#each pumps as row (row.key)}
								<option value={row.key}>{row.name}</option>
							{/each}
						</select>
					{/if}
				</div>
				{#if pumps.length > 1}
					<p id="{uid}-pump-chart-hint" class="hint">
						The pump and system curves of one pump at a time; each system curve is computed when its
						pump is shown.
					</p>
				{/if}
			</div>
			{#key viewed.key}
				<PumpChart
					bind:canvasArea={pumpCanvas}
					{result}
					name={viewed.name}
					prefs={ws.displayUnits}
					{ratedRange}
					names={curveNames}
					{checks}
					{system}
					onretry={response
						? () => ws.store.loadSystemCurve(viewed.key, { retry: true })
						: undefined}
					oncancel={response ? () => ws.store.cancelSystemCurve(viewed.key) : undefined}
					ontrace={() => ws.inspect(viewed.element)}
					{...onview && solved.designChecks?.length ? { onchecks: () => onview('checks') } : {}}
					{othersControlled}
					{...hasScenarios ? { caseName: ws.caseName(ws.store.activeCase) } : {}}
					{others}
					unticked={pumpUnticked}
					markers={pumpMarkers}
					ontick={(key, on) => tickChoice('pump', key, on)}
					overlayCurves={overlay}
					onoverlay={setOverlay}
					{overlayProgress}
					oncanceloverlay={cancelOverlay}
					{image}
				/>
			{/key}
			<!-- The card's last control (§5.3 item 2): the nav one Tab and a press away. -->
			<BackToSections />
		</div>
	{/if}
	{#if pumps.length > 1}
		<PumpGroupChart
			pumps={groupPumps}
			slots={groupSlots}
			onslots={(next) => (ws.pumpGroup = next)}
			{suggestions}
			{suggestedFor}
			bind:open={ws.pumpGroupOpen}
			curve={groupState}
			onretry={() => ws.store.loadGroupCurve(groupMembers, { retry: true })}
			oncancel={() => ws.store.cancelGroupCurve(groupMembers)}
			system={groupSystemState}
			onretrysystem={() => ws.store.loadGroupSystemCurve(groupMembers, { retry: true })}
			oncancelsystem={() => ws.store.cancelGroupSystemCurve(groupMembers)}
			prefs={ws.displayUnits}
			project={ws.labelsProject}
			solvedProject={groupSolvedProject}
			nodes={solved.nodeResults}
			unavailable={groupUnavailable}
			stale={ws.store.results.stale}
			{...hasScenarios ? { caseName: ws.caseName(ws.store.activeCase) } : {}}
			oninspect={(id) => ws.inspect({ kind: 'component', id })}
			flagText={(flag) => ws.flagText(flag)}
			{image}
			{lineups}
			{otherCases}
			{shownOn}
			othersOn={ws.pumpGroupOthers}
			{...hasScenarios ? { onothers: setOthers } : {}}
			onotherstick={(key, on) => tickChoice('group', key, on)}
			{othersProgress}
			oncancelothers={cancelOthers}
			onretryothers={retryOthers}
			othersRetryReason={calculatingReason(ws.store.calculating, 'solve')}
			{combinations}
			{extremes}
		/>
	{/if}
</div>
