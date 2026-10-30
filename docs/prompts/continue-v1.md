# Prompt: continue OpenSolve Pipe

> Paste everything below the line into a fresh Claude Code session at the repository root. `CLAUDE.md` is loaded automatically; this prompt only sets the session's job.

---

You are continuing **OpenSolve Pipe**, a free, browser-based steady-state hydraulic network analysis tool. v1 is built, verified and deployed (not a stable release, D14). Your job is to harden and extend it without ever trading correctness for scope.

1. Read `docs/GOALS.md`, then `docs/history.md` (where things stand and the verified numbers) and `docs/roadmap.md` (what is open). `CLAUDE.md` holds the rules that bind every change and the index of decisions D1–D23; `docs/workflow.md` says how a slice is designed, built, proven and recorded.
2. Before changing anything, re-run every gate (`docs/workflow.md` §4) and confirm the numbers in `docs/history.md`. Report any difference before going on.
3. Work the roadmap in order, one verified slice at a time. Ask the owner only product questions; D13 settles solver questions.
4. Record what you did as `docs/workflow.md` §5 says, and end the session with the report of §7.
