# Landing page

**Status: built (2026-11-01), web only, on `web/landing`; §5 is the as-built record.** No API, model or solver change; `METHOD_VERSION` unchanged (1.6.0). The owner set the goals in an interview (§2). Their answers are product decisions. The page's layout and wording are reversible web defaults under D14. Follows [`../ui-guide.md`](../ui-guide.md).

## 1. Scope

**The owner's request (2026-11-01).** "Make a proper landing page for the app. Interview me about the goals for the landing page first. Simple, minimal styling is good, for starters."

**Already decided, not re-opened.** Privacy (D3, GOALS §4.5): no analytics, cookies or third-party requests, and every image is served from the site itself. The legal notices on the home page (AGPL-3.0 §0 and §13, TSD §11.1): the copyright, the source of this build and of the calculation server, and the third-party licenses. The README disclaimer (GOALS §4.8). Phone and desktop equal (GOALS §4.7). The examples keep their links (GOALS §4.3).

## 2. The owner's answers (2026-11-01)

| Question | Answer |
|---|---|
| Who it is for, what it should get them to do | **Both, equally:** a short opening section with the calls to action for returning users, then sections that win over first-time visitors |
| Sections | **What it can model, how it's verified, screenshots, scope and limits** (all four offered) |
| Where it lives | **Replace the home page at `/`**; New project and the examples stay on it; project links (`/p#…`) unchanged |
| Tone | **Plain and technical**, like the docs |
| Screenshots | **Taken once by hand** and committed; replaced by hand when they go out of date |
| Privacy | **Short, with the details below** in a "Details" disclosure |
| Figures in the verification section | **Method only:** no counts, tolerance or version number that could drift from the code |
| Recent projects on this device (ui-ux-refinement.md item 14, F12) | **Yes, include it** |
| Headline | **What it does** |
| Comparisons with other tools | **None.** EPANET appears only as part of how results are verified |
| Open source (AGPL-3.0) | **Footer only**, as before |

## 3. Design

**Order.** The title, the one-line headline and a second line, then New project and Open an example. Recent projects follow when there are any. Then the screenshots, the examples, What it models, How the results are checked, Scope and limits, Your project lives in the link (short, with "Details"), and the disclaimer and license. The start comes first so a returning user needs no scrolling. The sections that answer a newcomer's questions come in the order they ask them: what is this, can it do my system, can I trust it, what can't it do, where does my data go.

**Content sources.** What it models is D5's v1 scope in an engineer's words. The fittings come from `data/fittings.json`, and tees and wyes from D9. How the results are checked comes from D1, D6, D8, D10 and D13, and the limits from PRD §2.2 and D14. Nothing on the page quotes a number from the code, so nothing goes stale when the suite grows.

**Recent projects (`utils/recent.ts`, `RecentProjects.svelte`).**
- The project page remembers each project's link in this browser's `localStorage` (`opensolve-pipe:recent-projects`). An entry is the project's id, its name, the encoded project (what the address bar already holds) and the time.
- It records a project on each new link: when a project is opened, after each edit's URL write, and when the page is left or hidden. It skips an example still as published and a project with no components, since neither is worth returning to.
- The list keeps one entry per project, the newest first, and at most 8. A project over 500,000 characters is not kept. On a full quota the oldest entries are dropped until the list fits.
- Every read and write is in try/catch: a private window or blocked storage just shows no list.
- The home page reads the list after loading, because the page is prerendered. The section exists only when the list is not empty. It shows each name and date, a Forget button per entry and Forget all, which removes the key.
- The privacy section's Details says what is kept and that it never leaves the browser.

**Screenshots.** Taken by hand on 2026-11-01 with Playwright from the dev server and the e2e API, then saved as WebP (`static/landing/`, 134 KB together):
- laptop: 1280×800, the pump transfer example solved, the pump's panel with the pump and system curves;
- phone: 390×844 at 2× density, the same project's results summary.

A phone shows only the phone shot, because the laptop's is too small to read at that width; from 640 px both show. **They go out of date when the UI changes; retake them by hand** (the owner's choice), with the same states.

## 4. Verification plan

`tests/home.e2e.ts`, at both sizes:
- **The landing page:** New project and Open an example are visible, along with each section heading. There is no recent list in a fresh browser. The right screenshot shows at each size and has loaded. The privacy details are hidden until "Details" is opened. axe-core finds no WCAG 2.2 A/AA violation with Details open.
- **Recent projects:**
  - An example opened unchanged and an empty new project are not kept; a changed example is, under its new name.
  - Its link reopens the project, and a second change updates the one entry.
  - Forget removes one entry; Forget all removes the list and the key, and a reload confirms it.
  - axe runs on the list.

`recent.test.ts` covers the store itself: order, one entry per id, the limit, a full quota, the size cap, forgetting, and unreadable or blocked storage.

## 5. As built

1. Built as designed in §3. The fittings sentence was checked against `data/fittings.json`: the fitting types are elbows, bends, reducers, entrances, exits and inline valves, and tees and wyes are separate elements. It says "losses from cited correlations (Crane TP-410)" rather than "every fitting by Crane", because one tee pattern uses Darby 3-K and is flagged (D9).
2. The caption names only the screens shown at each size ("on a laptop and on a phone" is hidden below 640 px). Both images' alt texts stand on their own.
3. Docs brought in line with recent projects: SDD §3.1.4 (Storage) and §5.2 (they said nothing is kept in browser storage), TSD §11 (the deployment check now expects only this key in `localStorage`), and `ui-guide.md` (per-browser choices).

## 6. Later

- Retake the screenshots after a visible UI change (by hand, §3).
- A recent project shows the time it was last seen here; a summary (component count, last solve) would need more stored data, so it waits for a request.
