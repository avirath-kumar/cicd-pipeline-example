# GitHub Actions workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| [`test-with-results.yml`](test-with-results.yml) | push to `main`/`develop`, pull requests | Linting, coverage, unit / integration / e2e / deployment tests, offline evaluations, Agent Server smoke test |
| [`preview-deployment.yml`](preview-deployment.yml) | `workflow_call` from the test workflow, `workflow_dispatch` | Creates or updates the per-pull-request preview deployment |
| [`new-lgp-revision.yml`](new-lgp-revision.yml) | pull request closed | Deletes the preview and, if merged, cuts a production revision |

**[→ Full pipeline documentation](DEPLOYMENT_PIPELINE.md)** — hosting models,
job-by-job breakdown, required secrets and variables, and troubleshooting.

## Running the same checks locally

```bash
make lint             # ruff, black, isort
make test             # full suite with coverage
make test-deployment  # control plane client, both hosting models
make pre-commit       # pre-commit hooks
make format           # auto-fix formatting
```
