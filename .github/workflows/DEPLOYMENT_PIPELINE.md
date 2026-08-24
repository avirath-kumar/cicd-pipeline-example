# CI/CD pipeline

Automated testing, preview deployments and production deployments for the
text2sql agent, targeting [LangSmith Deployment](https://docs.langchain.com/langsmith/deployment).

## Hosting models

The control plane accepts a different deployment **source** per hosting model,
so this one setting determines the whole deployment path. Select it with the
`LANGSMITH_DEPLOYMENT_TARGET` repository variable.

| | `saas` | `self-hosted` |
|---|---|---|
| Control plane host | `https://api.host.langchain.com` (+ `eu.`/`apac.`/`aws.` regions) | `https://<your-langsmith-host>/api-host` |
| Source | `github` | `external_docker` |
| Docker build in CI | skipped | required |
| Extra config | `LANGSMITH_GITHUB_INTEGRATION_ID` | `CONTROL_PLANE_HOST`, optional `LANGSMITH_LISTENER_ID` |

## Workflows

### 1. `test-with-results.yml` — Comprehensive Tests

**Trigger:** pushes to `main`/`develop`, and every pull request.

| Job | What it does |
|---|---|
| `quality-checks` | ruff, black, isort, pre-commit |
| `test-coverage` | full suite with coverage |
| `deployment-tests` | control plane client for both hosting models (offline, no credentials) |
| `unit-tests` | individual nodes and utilities |
| `integration-tests` | full graph with mocked dependencies |
| `e2e-tests` | full graph against a real model |
| `evaluation-tests` | offline evaluations (pull requests only) |
| `evaluation-report` | posts the evaluation summary as a PR comment |
| `langgraph-dev-test` | boots a local Agent Server, checks `/ok` and that the graph is registered |
| `preview-deployment` | calls the preview workflow once everything above passes |

### 2. `preview-deployment.yml` — Preview Deployment

**Trigger:** `workflow_call` from the test workflow, or `workflow_dispatch`.

Builds and pushes a preview image (self-hosted only), then creates or updates
the preview deployment and comments the status on the pull request.

This is invoked as a reusable workflow rather than through `workflow_run`.
A `workflow_run` trigger executes in the base repository with access to every
secret, which would hand the deployment credentials to a fork's pull request.
Both jobs additionally skip pull requests raised from forks.

### 3. `new-lgp-revision.yml` — Production Deployment & Cleanup

**Trigger:** pull request closed against `main`.

| Job | Condition | What it does |
|---|---|---|
| `cleanup-preview` | always (non-fork) | deletes the pull request's preview deployment |
| `build-production-image` | merged **and** self-hosted | builds and pushes `:latest` and `main-<sha>` |
| `deploy-production` | merged | creates or revises the production deployment |

## Naming

- Preview deployments: `text2sql-agent-pr-<pr-number>` (deployment type `dev`)
- Production deployment: `text2sql-agent-prod` (deployment type `prod`)
- Preview images (self-hosted): `<registry>/<image>:preview-<pr-number>`
- Production images (self-hosted): `<registry>/<image>:latest`

Deployment URLs are read from the control plane's `url` field rather than being
constructed from the name — the serving hostname differs per hosting model.

## Scripts

Located in [`.github/scripts/`](.):

| Script | Purpose |
|---|---|
| `control_plane.py` | Control plane client: host resolution, auth, payload builders, revision polling |
| `langgraph_api.py` | CLI for `deploy-preview`, `deploy-production`, `cleanup-preview`, `status` |
| `report_deployment.py` | Renders the deployment status PR comment |
| `report_eval.py` | Renders the evaluation summary PR comment |
| `list_deployments.py` | Lists workspace deployments — useful for checking credentials |

All of them read credentials from the environment and print only secret *names*,
never values. Every request carries a timeout, and the control plane host is
validated as an absolute `https` URL before an API key is sent to it.

Test the client for both hosting models without any credentials:

```bash
make test-deployment
```

## Required configuration

See the [GitHub Actions setup section in the README](../../README.md#github-actions-setup)
for the full table of repository variables and secrets.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401`/`403` from the control plane | `LANGSMITH_API_KEY` or `LANGSMITH_WORKSPACE_ID` wrong for this host |
| `external_docker` rejected | You are on SaaS; Cloud requires the `github` source |
| `github` source rejected | You are self-hosted; it requires `external_docker` |
| `Self-hosted deployments need an explicit control plane host` | Set `CONTROL_PLANE_HOST` to `https://<host>/api-host` |
| `Refusing to send an API key over plain http` | Use https, or pass `--allow-insecure-host` for an internal instance |
| `LANGSMITH_GITHUB_INTEGRATION_ID is required` | Fetch it from `GET /v1/integrations/github/install` |
| Preview never deploys | The pull request is from a fork — previews are skipped by design |

Check credentials end to end with:

```bash
uv run python .github/scripts/list_deployments.py --target saas
```
