# Deployment

The web app runs on Cloudflare Pages (`https://opensolve-pipe.pages.dev`, Pages project `opensolve-pipe`), which builds production from `main`, and the API on Google Cloud Run (service `opensolve-pipe-api` in the Google Cloud project `opensolve-pipe-api`, region `us-central1`); the owner deployed both on 2026-10-25. A deployment is not a stable release: until the owner declares one, the model, the link format, the API and the methods may change, and an older link may fail to open or solve differently ([D14](decisions/D14-deployed-not-stable.md)). [`TSD.md`](TSD.md) §11 explains each setting below and cites its source, and it lists the checks to run after every deployment and the costs. Ordinary use fits within both providers' free tiers.

Every command below copies and pastes as is. Each block starts by setting the names it uses, so it also works in a new Cloud Shell session. A fork that deploys under other names changes only those first lines.

**1. The API on Cloud Run, first deployment.** You need a Google Cloud project with billing enabled and the [gcloud CLI](https://cloud.google.com/sdk/docs/install) (Cloud Shell has it).

```bash
PROJECT_ID=opensolve-pipe-api   # the Google Cloud project
REGION=us-central1
SERVICE=opensolve-pipe-api
PAGES_PROJECT=opensolve-pipe    # the Cloudflare Pages project (step 2): https://opensolve-pipe.pages.dev

gcloud auth login
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iam.googleapis.com
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

# Let Cloud Build's default service account build and push the image
gcloud projects add-iam-policy-binding "$PROJECT_ID" --role=roles/run.builder \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# An image repository that deletes every image except the 3 most recent
# (the Delete rule matches every image; the Keep rule wins where both match)
gcloud artifacts repositories create opensolve-pipe --repository-format=docker --location="$REGION"
cat > /tmp/cleanup.json <<'JSON'
[{"name": "delete-all", "action": {"type": "Delete"}, "condition": {"tagState": "any"}},
 {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 3}}]
JSON
gcloud artifacts repositories set-cleanup-policies opensolve-pipe --location="$REGION" --policy=/tmp/cleanup.json

# The API's own identity; it calls no Google API, so it has no roles
gcloud iam service-accounts create "$SERVICE"

# Build from GitHub at the commit on main (the image records it and links its source, TSD §11.2)
SHA=$(git ls-remote https://github.com/ccirone2/opensolve-pipe refs/heads/main | cut -f1)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/opensolve-pipe/api:${SHA:0:7}"
# gcloud reads --config from this machine, not from the GitHub source: fetch it at the same commit
curl -fsSL "https://raw.githubusercontent.com/ccirone2/opensolve-pipe/${SHA}/apps/api/cloudbuild.yaml" -o /tmp/cloudbuild.yaml
gcloud builds submit https://github.com/ccirone2/opensolve-pipe --git-source-revision="$SHA" \
  --git-source-dir=apps/api --config=/tmp/cloudbuild.yaml \
  --substitutions="_IMAGE=${IMAGE},_SOURCE_COMMIT=${SHA}"

# Deploy, allowing the site and its previews (TSD §11.3)
gcloud run deploy "$SERVICE" --image "$IMAGE" --region="$REGION" \
  --service-account="${SERVICE}@${PROJECT_ID}.iam.gserviceaccount.com" --allow-unauthenticated \
  --cpu=1 --memory=1Gi --concurrency=20 --timeout=60 --min-instances=0 --max-instances=1 \
  --set-env-vars="CORS_ORIGINS=https://${PAGES_PROJECT}.pages.dev,CORS_ORIGIN_REGEX=https://[a-z0-9-]+[.]${PAGES_PROJECT}[.]pages[.]dev"

# Keep Cloud Run's own request log, which records client addresses and query strings, out of storage
gcloud logging sinks update _Default \
  --add-exclusion='name=no-run-request-logs,filter=LOG_ID("run.googleapis.com/requests")'

gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)'   # the API's URL, for step 2
```

Then, in the console under Billing → Budgets & alerts, create a spend cap budget for this project and Cloud Run (TSD §11.5). Don't skip it. One instance bounds CPU and memory charges, at about $64 a month, but request fees and outbound data are charged per request and per byte, and only the spend cap bounds them.

**Redeploying the API** after a change to it is merged into `main`. The usual way is the *Deploy API* workflow (§4), which checks the new revision before it serves. By hand, this builds that commit and deploys only a new image: Cloud Run carries every other setting, the environment variables included, into the new revision. Never redeploy with `--set-env-vars`, which deletes every variable it doesn't list. After the workflow has rolled back, the traffic is pinned to the old revision: a deploy by hand then also needs `gcloud run services update-traffic "$SERVICE" --to-latest`.

```bash
PROJECT_ID=opensolve-pipe-api
REGION=us-central1
SERVICE=opensolve-pipe-api

SHA=$(git ls-remote https://github.com/ccirone2/opensolve-pipe refs/heads/main | cut -f1)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/opensolve-pipe/api:${SHA:0:7}"
# gcloud reads --config from this machine, not from the GitHub source: fetch it at the same commit
curl -fsSL "https://raw.githubusercontent.com/ccirone2/opensolve-pipe/${SHA}/apps/api/cloudbuild.yaml" -o /tmp/cloudbuild.yaml
gcloud builds submit https://github.com/ccirone2/opensolve-pipe --project="$PROJECT_ID" \
  --git-source-revision="$SHA" --git-source-dir=apps/api --config=/tmp/cloudbuild.yaml \
  --substitutions="_IMAGE=${IMAGE},_SOURCE_COMMIT=${SHA}" \
  && gcloud run deploy "$SERVICE" --image "$IMAGE" --project="$PROJECT_ID" --region="$REGION"
```

**Checking the API** after any deployment or settings change: its variables, the commit it runs, and its origins. Both origins should print `200`: the site, and a preview (any `web-*` name stands for one).

```bash
PROJECT_ID=opensolve-pipe-api
REGION=us-central1
SERVICE=opensolve-pipe-api
PAGES_PROJECT=opensolve-pipe

gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
  --format='yaml(spec.template.spec.containers[0].env)'
API=$(gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')
curl -sS "$API/api/v1/about"; echo
for ORIGIN in "https://${PAGES_PROJECT}.pages.dev" "https://web-check.${PAGES_PROJECT}.pages.dev"; do
  curl -sS -o /dev/null -w "%{http_code}  ${ORIGIN}\n" -X OPTIONS "$API/api/v1/solve" -H "Origin: ${ORIGIN}" \
    -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type'
done
```

To change a variable, use `--update-env-vars`, which keeps the others. This sets the site's origins again:

```bash
PROJECT_ID=opensolve-pipe-api
REGION=us-central1
SERVICE=opensolve-pipe-api
PAGES_PROJECT=opensolve-pipe

gcloud run services update "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
  --update-env-vars="CORS_ORIGINS=https://${PAGES_PROJECT}.pages.dev,CORS_ORIGIN_REGEX=https://[a-z0-9-]+[.]${PAGES_PROJECT}[.]pages[.]dev"
```

With a custom domain, `CORS_ORIGINS` lists both origins, comma-separated. A value that contains a comma needs another delimiter between the variables (`gcloud topic escaping`): `--update-env-vars="^;^CORS_ORIGINS=https://${PAGES_PROJECT}.pages.dev,https://example.org"`.

**2. The web app on Cloudflare Pages.** You need a Cloudflare account that can see this GitHub repository.
- In Workers & Pages → Create → Pages, connect this repository and name the project `opensolve-pipe` (step 1's `PAGES_PROJECT`).
- Use these build settings:
  - production branch `main`;
  - framework preset *None*;
  - root directory `apps/web`;
  - build command `pnpm build`;
  - build output directory `build`.
- Set these build variables, for both Production and Preview:
  - `PUBLIC_API_URL` = the API's URL that step 1 printed, without a trailing slash;
  - `NODE_VERSION` = `22.22.0`;
  - `PNPM_VERSION` = `10.28.0`.
- Under Settings → Build:
  - set *Build watch paths* to include `apps/web/*`;
  - set *Branch control → Preview branches* to *Custom branches*, including `web/*`. Web-only changes are made on `web/*` branches, and each gets a preview at `https://<branch>.opensolve-pipe.pages.dev`, the branch name lowercased, with each character that is not a letter or digit replaced by a hyphen. The alias is also cut to 28 characters, which Cloudflare's docs do not say but its previews show, so a `web/<topic>` branch previews at its full name only when `<topic>` is at most 24 characters (TSD §11.1). The API lets the previews call it through `CORS_ORIGIN_REGEX` (step 1).
- Leave Web Analytics (under Metrics) **off**: the app has no analytics, cookies or third-party requests (GOALS §4.5).
- On a custom domain whose zone is on Cloudflare, keep the zone's Web Analytics, Bot Fight Mode and Email Address Obfuscation off (TSD §11.1).

**3. Check** the deployment with TSD §11.4. This step matters most for the client-address check. Google documents neither the address its proxy connects from nor where it puts the client's address in `X-Forwarded-For`, so only this check shows that each user gets their own rate limit. Run it over IPv6 too where you can, since the API keys an IPv6 client by its /64. If it fails, TSD §11.2 shows how to find out why.

**4. Deploying from GitHub Actions** ([D25](decisions/D25-api-deploy-workflow.md)). The *Deploy API* workflow (`.github/workflows/deploy-api.yml`) builds a commit on `main` whose CI passed, signs in to Google Cloud with no stored key, deploys a candidate revision with no traffic, checks it, and only then gives it the traffic. If the service then fails its checks, the traffic goes back to the previous revision. You start it from the Actions tab. Claude starts it when you ask, through GitHub's API: it holds no Google Cloud credential. A run can do only what three grants allow: push to the image repository, deploy this one service, and run it as the API's own account, which has no roles. Google gives a run that much only when it is this file on `main`, started by hand, in the `production` environment of this repository.

Once, in Cloud Shell, after step 1:

```bash
PROJECT_ID=opensolve-pipe-api
REGION=us-central1
SERVICE=opensolve-pipe-api
REPO_ID=1132007392    # GitHub's id of ccirone2/opensolve-pipe (api.github.com/repos/ccirone2/opensolve-pipe: "id")
OWNER_ID=16159174     # GitHub's id of ccirone2 (the same page: "owner" → "id")

gcloud config set project "$PROJECT_ID"
gcloud services enable iam.googleapis.com sts.googleapis.com iamcredentials.googleapis.com cloudresourcemanager.googleapis.com
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

# Trust GitHub's tokens only from this workflow on main, started by hand, in the production environment
gcloud iam workload-identity-pools create github --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc opensolve-pipe --location=global \
  --workload-identity-pool=github --display-name="opensolve-pipe deploys" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.environment=assertion.environment,attribute.event_name=assertion.event_name,attribute.workflow_ref=assertion.workflow_ref" \
  --attribute-condition="assertion.repository_id == '${REPO_ID}' && assertion.repository_owner_id == '${OWNER_ID}' && assertion.ref == 'refs/heads/main' && assertion.environment == 'production' && assertion.event_name == 'workflow_dispatch' && assertion.workflow_ref == 'ccirone2/opensolve-pipe/.github/workflows/deploy-api.yml@refs/heads/main'"

# The deploy account: no project role, and only this repository's tokens may act as it
gcloud iam service-accounts create api-deployer --display-name="API deploys from GitHub Actions"
DEPLOYER="api-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository_id/${REPO_ID}"

# What it may do, each on one resource: push to the image repository, deploy this service,
# and run it as the API's own account (which has no roles)
gcloud artifacts repositories add-iam-policy-binding opensolve-pipe --location="$REGION" \
  --role=roles/artifactregistry.writer --member="serviceAccount:${DEPLOYER}"
gcloud run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
  --role=roles/run.developer --member="serviceAccount:${DEPLOYER}"
gcloud iam service-accounts add-iam-policy-binding "${SERVICE}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/iam.serviceAccountUser --member="serviceAccount:${DEPLOYER}"

# The value for GitHub's production environment (below)
echo "GCP_WIF_PROVIDER=projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/providers/opensolve-pipe"
```

Then, on GitHub, under the repository's Settings → Environments:
- Create the environment `production`, named exactly so: the trust condition above names it.
- Under *Deployment branches and tags*, choose *Selected branches and tags* and add the branch `main`.
- Add the environment variable `GCP_WIF_PROVIDER` with the value the last command printed. It is not a secret: it names the provider, and the workflow holds no secret at all.
- Leave *Required reviewers* off. Claude's sessions act on GitHub as you, so a reviewer rule cannot stop one (it could approve as you), and with *Prevent self-review* you could never approve a run it started. What a run can do is bounded by the grants above, whoever starts it.

Google takes up to about 5 minutes to apply new pools, providers and grants. Then run the workflow once with *Check the setup only* ticked: it signs in, reads the service and builds the image, and deploys nothing. Its log shows the deploy account signed in and the revision serving now.

**Deploying.** Actions → *Deploy API* → *Run workflow*, on `main`. Leave *commit* empty for `main`'s latest, or give an older commit of `main` whose CI passed, to go back to it. Or ask Claude. The run's summary lists the commit, the candidate revision, each check, and a rollback if one happened. Only one deploy runs at a time.

If a first deploy fails on a permission the grants above don't give (Google documents only these grants, each on its resource, for a deploy), the run's log names the permission. Add it alone, as a custom role at project level, rather than a wider role.

