# D3. Sharing: URL fragment only in v1

Decision D3 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D3`.

---

- The encoded project goes in the URL fragment: `https://opensolve-pipe.app/p#<encoded>`. The fragment is never sent to the server, so project data is never logged.
- Encoding: canonical JSON → gzip (pako) → base64url, no padding.
- v1 has no accounts, no database and no server-side storage. History is in-browser undo/redo plus the URLs a user keeps.
- Warn when the encoded URL exceeds 8,000 characters; some chat and email clients truncate long links.
- Deferred: short links, accounts, branch and merge (PRD §4.4–4.5, SDD §3.2.3).
