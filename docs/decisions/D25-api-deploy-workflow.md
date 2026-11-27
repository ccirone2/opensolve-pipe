# D25. API deployment from GitHub Actions (owner, 2026-11-27)

Decision D25 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D25`.

The owner's request (2026-11-27): "Let's build a secure way for you to deploy the API without getting to much access to the server". Specs: TSD §11.2 (*Deploying from GitHub Actions*) and §11.4; the runbook: [`deployment.md`](../deployment.md) §4.

---

Designed and built in Session 17 on `claude/kind-wozniak-oui7h9`:
- Google Cloud's and GitHub's facts were checked against their documentation by two researchers (Workload Identity Federation, Cloud Run's roles and tags; GitHub's OIDC claims, environments and runner images).
- An adversarial review then looked at three things: the trust and the grants, GitHub Actions security, and fail-safety. Each finding was reproduced or confirmed from documentation by a skeptic, and all 14 were taken in (*Review*, below).

### What

The API is deployed by one workflow, `.github/workflows/deploy-api.yml`, started by hand. The owner starts it from the Actions tab; Claude starts it through GitHub's REST API (`POST …/actions/workflows/deploy-api.yml/dispatches`), and **only when the owner asks**, as with a pull request. The job runs no action code: an action in it could mint the job's OIDC token. It checks out `main` with plain `git`; the repository is public.

1. **Choose the commit.** The input commit, or `main`'s head. It must:
   - be a full 40-character hash;
   - be on `main`'s first-parent history: a head `main` has had, not a commit merged in from a branch;
   - have a successful push run of `ci.yml` on `main` (`GET …/actions/workflows/ci.yml/runs?head_sha=…&branch=main&event=push&status=success`).

   An earlier head qualifies, so a deploy of it is also a rollback. A commit from before `scripts/check_deployment.py` existed borrows `main`'s copy of the script, and the summary says so.
2. **Build** the image on the runner from that commit, as `cloudbuild.yaml` does: `docker build --build-arg SOURCE_COMMIT=<sha>` in `apps/api`, with its `.dockerignore` applied, tagged `<repository>/api:<sha>`. The build runs before any credential exists.
3. **Sign in, keyless.** The job writes a URL-sourced external-account credential (google.aip.dev/auth/4117) to `$RUNNER_TEMP`. Each time gcloud needs a token, it fetches the job's GitHub OIDC token (audience: the provider's full name) and exchanges it with Google's STS. It then impersonates the deploy account for 15 minutes (`token_lifetime_seconds: 900`). No key is stored anywhere, and the file is deleted at the end.
4. **Read the service.** The revision serving all traffic is recorded for rollback, and the service's scaling and size go into the run's summary. If no revision serves all traffic, the run stops and leaves the traffic as it is.
5. **Push** the image, and **deploy a candidate** with no traffic and a tag (`gcloud run deploy --image … --no-traffic --tag c-<sha7>`). Only the image changes; every other setting carries over. The workflow never passes `--set-env-vars` or `--allow-unauthenticated`.
6. **Check the candidate** on its tag URL with `apps/api/scripts/check_deployment.py`, before it serves (TSD §11.4 items 1 and 2, plus a solve):
   - `/health`, and `/docs` off;
   - `/api/v1/about` with the commit, the checkout's method version and the commit's source;
   - `/source`'s redirect;
   - the CORS preflight from the site and from a preview origin;
   - a two-reservoir solve that converges.

   It tries up to 3 times, 15 s apart, so a dropped connection or a cold start is not a failure. A request with no answer is a failed check with its own line (status 0), never a traceback.
7. **Give it the traffic** (`update-traffic --to-latest --remove-tags`), but only if the latest ready revision is still the candidate just checked.
8. **Check the service** on its own URL, with the same retries. **Roll back** whenever the traffic may have moved and the service was not checked good: a failed or cancelled promote, or a failed or cancelled check. The traffic then goes back to the recorded revision (`--to-revisions <previous>=100`). Where the promote stopped before moving anything, the rollback changes nothing.
9. **Clean up**, always: a candidate that did not get the traffic loses its tag. The tag is looked for in the service's spec, where it is from the moment the deploy is submitted. The summary says when the traffic stays pinned (*Limits*). The credential file is deleted.

`check_only: true` runs steps 1 to 4 with the build and deploys nothing. It is the first run after the one-time setup, and it checks the trust condition and the read; the push, the deploy and the traffic change are first checked by the first real deploy.

### The trust boundary

- **What Claude holds:** the session's GitHub access (it acts on GitHub as the owner, `ccirone2`), and no Google Cloud credential of any kind.
- **What a run can get:** a token of the deploy account `api-deployer@opensolve-pipe-api.iam.gserviceaccount.com`. The provider `github` of the pool `opensolve-pipe-deploy` accepts a GitHub token only when every condition holds:
  - `repository_id == '1132007392'` and `repository_owner_id == '16159174'`, numeric, so they survive a rename;
  - `ref == 'refs/heads/main'`, `environment == 'production'` and `event_name == 'workflow_dispatch'`;
  - `run_attempt == '1'`: a re-run, which would replay the workflow file as it was at that run's commit, gets no token, so a version fixed on `main` never runs again;
  - `workflow_ref == 'ccirone2/opensolve-pipe/.github/workflows/deploy-api.yml@refs/heads/main'`.
- **Who may impersonate it:** only identities of that pool with this repository's id (`roles/iam.workloadIdentityUser` on `principalSet://…/workloadIdentityPools/opensolve-pipe-deploy/attribute.repository_id/1132007392`). The pool holds this provider alone and must stay so, since the grant names the pool, not the provider. The workflow's own `if: github.ref == 'refs/heads/main'` and the environment's branch policy are a convenience; this condition is the control, and a copy of the file on another branch cannot change it.
- **What that token can do:** three grants, each on one resource, and no project role.
  - `roles/artifactregistry.writer` on the repository `opensolve-pipe`: push and retag images, not delete them.
  - `roles/run.developer` on the service `opensolve-pipe-api`: deploy revisions and move traffic. It can also change the service's settings, including its scaling, CPU and memory and so its cost, and it can delete the service. It cannot change the service's IAM policy, so not who may call it.
  - `roles/iam.serviceAccountUser` on the runtime account `opensolve-pipe-api@…`, which has no roles, so a revision can run as nothing more.
- **The ceiling, whatever code runs in the workflow.** Within it, the cost is bounded by the project's Cloud Run quotas, which the deploy account cannot raise (deployment.md §4 suggests lowering them), and by the spend cap (TSD §11.5). It cannot reach the project's IAM, billing, logs, other services, Cloud Build, or any secret, since the project holds none.
- **No approval gate in GitHub.** A required reviewer on the `production` environment cannot stop a session that acts as the owner, which can approve as the owner. With "Prevent self-review", the owner could never approve a run that session started. Who deploys, and when, rests on the rule above: Claude deploys only when the owner asks. What a run can do rests on the grants.
- **The record.** The Actions tab shows every run, but any identity with write access can delete a run, this session included. The durable record is Google's Admin Activity audit log of the deploy account, which it cannot touch (deployment.md §4).
- **What `main` controls.** A change to the workflow takes effect once it is on `main`. `main` is protected by the ruleset *Protect-main*: a pull request is required with 0 approvals, force pushes and deletion are blocked, and there are no bypass actors. No one, the owner or a session acting as the owner included, can push to `main` directly or rewrite it, so a deployed commit stays in its history. Requiring approvals or `CODEOWNERS` would not stop a session acting as the owner, which can approve as the owner. Neither can raise the ceiling above.

### Limits

- **Verified by the first runs, not here.** This session has no Google Cloud access, so the token exchange and the grants were checked by the workflow's first runs after the merge `322db41` (2026-11-27), each a first attempt started through GitHub's API at the owner's request:
  - **Run 46054811608, `check_only`:** the sign-in as the deploy account and the read of the service passed. gcloud warns that the account cannot read the project; that is expected, since it holds no project role, and nothing needs it.
  - **Run 46057952554, the first deploy, of `322db41`:** the push, the tagged deploy and `update-traffic` passed with `roles/run.developer` bound on the service alone, so no project-level permission was needed. The candidate `opensolve-pipe-api-00020-xuq` passed all 7 checks on its tag URL (the site's and a preview's preflight among them), took all traffic in place of `opensolve-pipe-api-00017-sb9`, and passed them again on the service's URL; the rollback was skipped and the tag removed. The service then answered `/api/v1/about` with commit `322db41` and method version 1.6.2.
  - Google documents only resource-level grants for a deploy. If a later gcloud needs a project-level permission (such as `run.operations.get`), the run names it, and a project-level custom role holding only that permission is the narrow remedy (deployment.md §4).
- **A candidate not kept pins the traffic.** This covers a failed check or guard, a cancelled run, and a rollback. The traffic stays pinned to the revision that served before, and the service's template is the candidate that was not kept. The next run moves the traffic to its new revision. By hand, a deploy then needs `update-traffic --to-latest`, which deployment.md's block now ends with. A settings change by hand comes only after a deploy: built on the template, it would make a revision of the code that was not kept.
- **Unchanged:**
  - The manual Cloud Build path (`cloudbuild.yaml`, deployment.md *Redeploying the API*) stays the owner's fallback.
  - The first deployment's settings (deployment.md §1) are made by hand, as before.
  - The checks that need a second network or a person (TSD §11.4 items 3 to 5) stay by hand.

### Versions

`METHOD_VERSION` unchanged (1.6.2): no solved value changes.

### Proof

- **`tests/unit/test_check_deployment.py`** (9 tests) runs the check script against the app in-process. A deployment of the commit passes every check. Each of these fails its own checks:
  - another commit, or an image without one;
  - an origin the API does not allow;
  - another method version.

  A deployment that does not answer fails every check with its own line and exits 1 (the previous script stopped with a `URLError` traceback). The project the script sends must validate against the model.
- **Over HTTP against a local server** started as an image would be (`SOURCE_COMMIT` and the site's CORS settings): 7 checks ok and exit 0; a wrong commit and an unknown origin fail, exit 1.
- **The workflow:**
  - **Linting:** `actionlint` (with `shellcheck` on every `run:`) reports 0 errors.
  - **The checkout step,** run here, fetched `main` from GitHub (585 commits) and checked out its head.
  - **The commit step,** run here against the repository:
    - accepts `main`'s head `7f80af6` and an earlier head `6891b48`, each borrowing `main`'s check script;
    - refuses a commit merged in from a branch (`7be3a07`, green on its branch), a branch commit (`a32f5f4`), a short hash, an unset `GCP_WIF_PROVIDER`, a head with no CI run on `main`, and a head of `main` whose CI failed (`ce9bccc`).
  - **The credential file** is written with mode 600. Google's own `google-auth` 2.63.1 loads it as an identity-pool credential with the impersonation URL and lifetime. Against a local stand-in for GitHub's token endpoint, it sent `Authorization: Bearer <request token>` to `<ACTIONS_ID_TOKEN_REQUEST_URL>&audience=https://iam.googleapis.com/<provider>` and read the token from `value`.
  - **The jq selections** of the previous revision, the candidate's revision and its tag URL were checked on a service description shaped like Cloud Run's.

### Review

The adversarial review (2026-11-27) had three lenses: the trust and the grants, GitHub Actions, and fail-safety. A skeptic confirmed each of its 14 findings, by a run here or by Google's or GitHub's documentation. All were taken in.

Before the review, while re-reading the workflow, the builder found that a failed check piped into `tee` would have passed under GitHub's default shell, which runs without `pipefail`. The job now sets `shell: bash`.

The workflow:
- Only an earlier or current head of `main`, with CI on `main`, is deployed. A commit merged in from a branch, green only there, ran with the deploy credential before.
- No action runs in the job. `actions/checkout@v4`, a movable tag, ran where it could mint the OIDC token.
- Google's condition refuses a re-run (`run_attempt`).
- An old commit borrows `main`'s check script, so a rollback to it works.
- The rollback covers a failed or cancelled promote.
- The cleanup reads the tag from the spec, where a cancelled deploy leaves it before it is routed.
- A request with no answer is a failed check, not a traceback, and each check is tried up to 3 times.

The records:
- The service grant's reach into settings and cost is stated, with quotas as its bound.
- The pool holds one provider.
- The setup waits for the new service account.
- `check_only` checks the sign-in and the read only.
- The audit log is the durable record.
- `main`'s ruleset is described as it is.
- A candidate not kept leaves the traffic pinned.
