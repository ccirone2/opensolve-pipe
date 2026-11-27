# D25. API deployment from GitHub Actions (owner, 2026-11-27)

Decision D25 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D25`.

The owner's request (2026-11-27): "Let's build a secure way for you to deploy the API without getting to much access to the server". Specs: TSD §11.2 (*Deploying from GitHub Actions*) and §11.4; the runbook: [`deployment.md`](../deployment.md) §4.

---

Designed and built in Session 17 on `claude/kind-wozniak-oui7h9`. Google Cloud's and GitHub's facts were checked against their documentation by two researchers (Workload Identity Federation, Cloud Run's roles and tags; GitHub's OIDC claims, environments and runner images), and the design then reviewed adversarially.

### What

The API is deployed by one workflow, `.github/workflows/deploy-api.yml`, started by hand: by the owner from the Actions tab, or by Claude through GitHub's REST API (`POST …/actions/workflows/deploy-api.yml/dispatches`) **when the owner asks**, as with a pull request. It deploys a commit on `main` whose CI passed, by these steps:

1. **Choose the commit.** The input commit, or `main`'s head. It must be a full 40-character hash, an ancestor of `main` (`git merge-base --is-ancestor`), and have a successful push run of `ci.yml` (`GET …/actions/workflows/ci.yml/runs?head_sha=…&event=push&status=success`). An older commit of `main` qualifies, so a deploy of it is also a rollback.
2. **Build** the image on the runner from that commit, as `cloudbuild.yaml` does: `docker build --build-arg SOURCE_COMMIT=<sha>` in `apps/api` (its `.dockerignore` applies), tagged `<repository>/api:<sha>`. The build runs before any credential exists.
3. **Sign in, keyless.** The job writes a URL-sourced external-account credential (google.aip.dev/auth/4117) to `$RUNNER_TEMP`. Each time gcloud needs a token, it fetches the job's GitHub OIDC token (audience: the provider's full name) and exchanges it with Google's STS. It then impersonates the deploy account for 15 minutes (`token_lifetime_seconds: 900`). No key is stored anywhere, and the file is deleted at the end.
4. **Read the service.** The revision serving all traffic is recorded for rollback. If none serves all traffic, the run stops and the traffic is left as it was.
5. **Push** the image, and **deploy a candidate** with no traffic and a tag (`gcloud run deploy --image … --no-traffic --tag c-<sha7>`). Only the image changes; every other setting carries over. The workflow never passes `--set-env-vars` or `--allow-unauthenticated`.
6. **Check the candidate** on its tag URL with `apps/api/scripts/check_deployment.py`, before it serves (TSD §11.4 items 1 and 2, and a solve):
   - `/health`, and `/docs` off;
   - `/api/v1/about` with the commit, the checkout's method version and the commit's source;
   - `/source`'s redirect;
   - the CORS preflight from the site and from a preview origin;
   - a two-reservoir solve that converges.
7. **Give it the traffic** (`update-traffic --to-latest --remove-tags`), only if the latest ready revision is still the candidate just checked.
8. **Check the service** on its own URL. If that fails, the traffic goes back to the recorded revision (`--to-revisions <previous>=100`, pinned until the next deploy).

`check_only: true` runs steps 1 to 4 and step 2's build, and deploys nothing. It is the first run after the one-time setup, to check the sign-in and the grants.

### The trust boundary

- **What Claude holds:** the session's GitHub access (it acts on GitHub as the owner, `ccirone2`), and no Google Cloud credential of any kind.
- **What a run can get:** a token of the deploy account `api-deployer@opensolve-pipe-api.iam.gserviceaccount.com`. Google's provider accepts a GitHub token only when every condition holds:
  - `repository_id == '1132007392'` and `repository_owner_id == '16159174'`, numeric, so they survive a rename;
  - `ref == 'refs/heads/main'`, `environment == 'production'` and `event_name == 'workflow_dispatch'`;
  - `workflow_ref == 'ccirone2/opensolve-pipe/.github/workflows/deploy-api.yml@refs/heads/main'`.

  Only that provider's identities in this repository may impersonate the account (`roles/iam.workloadIdentityUser` on `principalSet://…/attribute.repository_id/1132007392`). The workflow's own `if: github.ref == 'refs/heads/main'` and the environment's branch policy are a convenience; this condition is the control, and a copy of the file on another branch cannot change it.
- **What that token can do:** three grants, each on one resource, and no project role.
  - `roles/artifactregistry.writer` on the repository `opensolve-pipe`: push and retag images, but not delete them.
  - `roles/run.developer` on the service `opensolve-pipe-api`: deploy revisions and move traffic. It could also change the service's settings or delete the service, but not its IAM policy, so not who may call it.
  - `roles/iam.serviceAccountUser` on the runtime account `opensolve-pipe-api@…`, which has no roles, so a revision can run as nothing more.
  - That is the ceiling, whatever code runs in the workflow. It cannot reach billing, logs, other services, Cloud Build, or any secret, since the project holds none.
- **No approval gate in GitHub.** A required reviewer on the `production` environment cannot stop a session that acts as the owner: it can approve as the owner. With "Prevent self-review", the owner could never approve a run that session started. Who deploys, and when, rests on the rule above (Claude deploys only when the owner asks) and on the record: every run is visible in the Actions tab, with its commit, its checks and its log. What a run can do rests on the grants.
- **What `main` controls.** A change to the workflow takes effect only once it is on `main`, where every merge is visible. The repository has no branch protection today. Protecting `main` (and `CODEOWNERS` on `.github/workflows/`) would make a workflow change need a review, but it cannot raise the ceiling above.

### Limits

- **Not verified here:** the exchange with Google and the grants themselves. This session has no Google Cloud access. The first `check_only` run verifies the sign-in and the read. The first deploy verifies the push, the tagged deploy and `update-traffic` with `roles/run.developer` bound on the service alone. Google lists only resource-level grants for these; that gcloud needs no project-level permission (such as `run.operations.get`) is not documented either way. If a run reports one missing, a project-level custom role holding only that permission is the narrow remedy (deployment.md §4).
- **Unchanged:**
  - The manual Cloud Build path (`cloudbuild.yaml`, deployment.md *Redeploying the API*) stays the owner's fallback.
  - The first deployment's settings (deployment.md §1) are made by hand, as before.
  - The checks that need a second network or a person (TSD §11.4 items 3 to 5) stay by hand.
- **A rollback pins the traffic** to the previous revision. The next run of the workflow moves it to the new revision. A manual `gcloud run deploy` then needs `gcloud run services update-traffic --to-latest`.

### Versions

`METHOD_VERSION` unchanged (1.6.2): no solved value changes.

### Proof

- **`tests/unit/test_check_deployment.py`** (8 tests) runs the check script against the app in-process. A deployment of the commit passes every check. Each of these fails its own checks:
  - another commit, or an image without one;
  - an origin the API does not allow;
  - another method version.

  The project the script sends must validate against the model.
- **Over HTTP against a local server** started as an image would be (`SOURCE_COMMIT` and the site's CORS settings): 7 checks ok and exit 0; a wrong commit and an unknown origin fail, exit 1.
- **The workflow:**
  - **Linting:** `actionlint` (with `shellcheck` on every `run:`) reports 0 errors.
  - **The commit step, run here against the repository:**
    - accepts `main`'s head and an older `main` commit with green CI (`6891b48`);
    - refuses a commit only on a feature branch, a short hash, an unset `GCP_WIF_PROVIDER`, and a `main` commit whose CI failed (`a32f5f4`).
  - **The credential file** is written with mode 600. Google's own `google-auth` 2.63.1 loads it as an identity-pool credential with the impersonation URL and lifetime. Against a local stand-in for GitHub's token endpoint, it sent `Authorization: Bearer <request token>` to `<ACTIONS_ID_TOKEN_REQUEST_URL>&audience=https://iam.googleapis.com/<provider>` and read the token from `value`.
  - **The jq selections** of the previous revision, the candidate's revision and its tag URL were checked on a service description shaped like Cloud Run's.
