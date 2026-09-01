# LangSmith Deployment CI/CD Pipeline 🚀

Agent built in [LangGraph OSS](https://docs.langchain.com/oss/python/langgraph/overview). It includes:
- unit, integration, e2e tests
- offline evaluations with [OpenEvals](https://github.com/langchain-ai/openevals) and [LangSmith](https://docs.langchain.com/langsmith/home)
- preview and prod agent deployments through the [LangSmith Deployment control plane API](https://docs.langchain.com/langsmith/api-ref-control-plane)

The pipeline supports both hosting models — **Cloud (SaaS)** and **Self-Hosted** — from
the same workflows. See [Choosing a hosting model](#-choosing-a-hosting-model).

## 🛠️ Prerequisites

- [uv](https://docs.astral.sh/uv/) - Fast Python package installer and resolver
- Python 3.11+
- A [LangSmith account](https://smith.langchain.com) (Cloud) or a self-hosted LangSmith instance

## 🚀 Quick Start

### 1. Install Dependencies

First, ensure you have `uv` installed. Then run:

```bash
uv sync
```

This will create a virtual environment and install all project dependencies.

### 2. Environment Configuration

Copy the example environment file and configure your variables:

```bash
cp .env.example .env
```

Edit the `.env` file and add your required environment variables.

### 3. Create the evaluation dataset

The offline evaluations run against a LangSmith dataset. Create it once:

```bash
uv run python helpers/create_datasets.py
```

Set `DEMO_OWNER` first if you share a workspace — see [Naming](#-naming).

### 4. Run LangGraph Studio

Start the LangGraph development server to visualize your agent:

```bash
uv run langgraph dev
```

This will start the LangGraph Studio interface where you can interact with and debug your text-to-SQL agent.

## 🤖 Choosing how to reach a model

The agent can reach a model three ways. It auto-detects in the order below, or
set `LLM_PROVIDER` to force one and `LLM_MODEL` to override the model.

| Route | Credential | Default model | Use when |
|---|---|---|---|
| `gateway` | `LANGSMITH_API_KEY` only | `anthropic/claude-haiku-4-5-20251001` | Your organisation does not issue provider keys |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-haiku-4-5-20251001` | You have an Anthropic key |
| `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` | You have an OpenAI key |

### The LLM Gateway route

The [LangSmith LLM Gateway](https://docs.langchain.com/langsmith/llm-gateway-api-formats)
is OpenAI-compatible and authenticates with a LangSmith API key, so the agent
needs **no provider key at all**:

```bash
export LLM_GATEWAY_BASE_URL="https://gateway.smith.langchain.com/v1"
export LLM_MODEL="anthropic/claude-haiku-4-5-20251001"   # provider-qualified
```

Model IDs are qualified by provider here (`anthropic/…`, `openai/…`). List what
your workspace can reach:

```bash
curl https://gateway.smith.langchain.com/v1/models \
  -H "Authorization: Bearer $LANGSMITH_API_KEY"
```

> **In a deployment**: LangSmith Cloud injects `LANGSMITH_API_KEY` for you, and
> the control plane **rejects it as a deployment secret** because the name is
> reserved. So forward only `LLM_GATEWAY_BASE_URL` and `LLM_MODEL`:
>
> ```bash
> --secret-env LLM_GATEWAY_BASE_URL --secret-env LLM_MODEL
> ```
>
> Both deployment workflows already pass these.

CI routes every job through the gateway, so no provider key is needed anywhere
in the pipeline. The e2e test pins `openai/gpt-4o` to keep its assertions on the
model they were written against.

## 📛 Naming

LangSmith object names are global to a workspace, so parallel runs of this demo
collide — on the dataset, on experiment names, and on deployment names (the
control plane returns a `409`). Set `DEMO_OWNER` to namespace all three:

| `DEMO_OWNER` | Dataset | Experiments | Deployments |
|---|---|---|---|
| unset | `text2sql-agent` | `text2sql-agent-sql` | `text2sql-pr-42`, `text2sql-prod` |
| `name` | `text2sql-agent-name` | `text2sql-agent-sql-name` | `text2sql-name-pr-42`, `text2sql-name-prod` |

Lowercase letters, digits and dashes. `DEPLOYMENT_NAME_PREFIX` overrides the
deployment half. Resolved in `agents/config.py` and in the deployment workflows.

## 📁 Project Structure

```
text2sql-agent/
├── agents/               # Agent implementation (graph, nodes, prompts, db helpers)
├── tests/
│   ├── unit/             # Individual nodes and utilities
│   ├── integrations/     # Full graph with mocked dependencies
│   ├── e2e/              # Full graph against a real model
│   ├── offline_evals/    # LangSmith + OpenEvals experiments
│   └── deployment/       # Control plane client, both hosting models
├── .github/
│   ├── scripts/          # Deployment + reporting scripts used by CI
│   └── workflows/        # Test, preview deploy, production deploy
├── examples/             # Usage examples
├── helpers/              # Dataset creation helpers
└── langgraph.json        # Agent Server configuration
```

## 🔧 Development

- **Virtual Environment**: Managed by `uv` - no need to manually activate
- **Dependencies**: All managed through `pyproject.toml` and `uv.lock`
- **Environment Variables**: Configure in `.env` file

## 🧪 Testing

Run all tests:

```bash
uv run pytest tests/
```

Run specific test categories:

- **Unit tests** (single nodes and utilities):
  ```bash
  uv run pytest -m single_node
  uv run pytest -m utils
  ```

- **Integration tests**:
  ```bash
  uv run pytest -m integration
  ```

- **Offline evaluations** (agent performance evaluation; needs the dataset from
  [step 3](#3-create-the-evaluation-dataset)):
  ```bash
  uv run pytest -m evaluator
  ```

- **Deployment client** (verifies the SaaS and self-hosted request payloads
  against a mocked control plane — no credentials required):
  ```bash
  make test-deployment
  ```

### GitHub Actions setup

Tests and evaluations run on every pull request and on pushes to `main`/`develop`.
Deployments run only for pull requests raised from this repository — a fork has
no access to these secrets, by design.

**Repository variables** (Settings → Secrets and variables → Actions → Variables):

| Variable | Purpose | Default |
|---|---|---|
| `LANGSMITH_DEPLOYMENT_TARGET` | `saas` or `self-hosted` | `saas` |
| `DEMO_OWNER` | Namespaces the dataset, experiments and deployments — see [Naming](#-naming) | unset |
| `DEPLOYMENT_NAME_PREFIX` | Prefix for deployment names. Self-hosted caps the full name at 21 chars | from `DEMO_OWNER` |
| `LANGSMITH_REGION` | Cloud region: `us`, `eu`, `apac`, `aws-us` | `us` |
| `REGISTRY` | Container registry (self-hosted only) | `docker.io` |
| `IMAGE_NAME` | Image repository (self-hosted only) | `github.repository` |
| `LANGSMITH_TRACING` | Enable tracing in test jobs | `false` |
| `LANGSMITH_ENDPOINT` | LangSmith **tracing** API URL | LangSmith default |
| `LLM_GATEWAY_BASE_URL` | Gateway URL used by every job | LangSmith Cloud gateway |
| `LLM_MODEL` | Provider-qualified model ID | `anthropic/claude-haiku-4-5-20251001` |

**Repository secrets:**

| Secret | Needed for | Purpose |
|---|---|---|
| `LANGSMITH_API_KEY` | both | Tracing, evaluations, control plane auth, and gateway auth |
| `LANGSMITH_WORKSPACE_ID` | both | Workspace to deploy into (`X-Tenant-Id`) |
| `LANGSMITH_GITHUB_INTEGRATION_ID` | SaaS | GitHub App install that grants repo access — see [GitHub App](#github-app-saas-only) |
| `CONTROL_PLANE_HOST` | self-hosted | `https://<your-langsmith-host>/api-host` |
| `LANGSMITH_LISTENER_ID` | self-hosted (optional) | Pin deployments to a listener |
| `DOCKER_USERNAME` / `DOCKER_PASSWORD` | self-hosted | Push the agent image |

### GitHub App (SaaS only)

Cloud deployments are built by the control plane from your repository, so
LangChain's `hosted-langserve` GitHub App needs access to it. **A GitHub org
owner or admin must authorize it once per workspace** — GitHub returns `404`,
not `403`, on installation settings you cannot administer, so a permissions
problem looks like a missing page.

1. Install it from [github.com/apps/hosted-langserve](https://github.com/apps/hosted-langserve),
   granting access to this repository.

2. Read the integration ID from the **control plane** host — not the tracing API:

   ```bash
   curl -sS https://api.host.langchain.com/v1/integrations/github/install \
     -H "X-Api-Key: $LANGSMITH_API_KEY" | jq -r '.[] | "\(.name)\t\(.id)"'
   ```

   One row per account, as a bare array. Use `id` as
   `LANGSMITH_GITHUB_INTEGRATION_ID` — a workspace-scoped key needs no
   `X-Tenant-Id`.

3. Confirm the install actually reaches this repo:

   ```bash
   curl -sS https://api.host.langchain.com/v1/integrations/github/<id>/repos \
     -H "X-Api-Key: $LANGSMITH_API_KEY" | jq -r '.[].url'
   ```

> Step 3 matters: a *selected repositories* install returns a perfectly valid
> integration ID, but the deploy fails because the control plane cannot read the
> repo. Add it under **Repository access** at
> `github.com/settings/installations/<installation_id>` for a personal account,
> or `github.com/organizations/<org>/settings/installations/<installation_id>`
> for an org.

## 🧭 Choosing a hosting model

LangSmith Deployment runs in one of two hosting models, and **the control plane
accepts a different deployment source for each**. This is the single most
important thing to get right — the wrong source is rejected by the API:

| | **Cloud (SaaS)** | **Self-Hosted** |
|---|---|---|
| Control plane host | `https://api.host.langchain.com` | `https://<your-langsmith-host>/api-host` |
| Deployment source | `github` — the control plane builds for you | `external_docker` — you build and push the image |
| Docker image needed? | No | Yes |
| Extra config | [GitHub integration ID](#github-app-saas-only) | Control plane host, optional listener ID |

Cloud regional hosts: `https://eu.api.host.langchain.com`,
`https://apac.api.host.langchain.com`, `https://aws.api.host.langchain.com`.

> **Note**: the control plane API and the LangSmith tracing API are different
> services on different hosts. Tracing uses `https://api.smith.langchain.com`
> (Cloud) or `https://<your-langsmith-host>/api` (self-hosted); deployments use
> the hosts in the table above.

Pick your model with the `LANGSMITH_DEPLOYMENT_TARGET` repository variable
(`saas` or `self-hosted`). Everything below follows from that one setting.

## 🚀 Deployment Options

Beyond the automated CI/CD pipeline, you can deploy this agent by hand. Both
paths start the same way.

### Prerequisites for manual deployment

1. **LangGraph graph**: your agent implementation (e.g. `./agents/simple_text2sql.py:agent`)
2. **Dependencies**: either `requirements.txt` or `pyproject.toml` with all required packages
3. **Configuration**: a `langgraph.json` specifying the graph path, dependencies,
   environment variables and Python version

Example `langgraph.json`:
```json
{
    "graphs": {
        "simple_text2sql": "./agents/simple_text2sql.py:agent"
    },
    "env": ".env",
    "python_version": "3.11",
    "dependencies": ["."],
    "image_distro": "wolfi"
}
```

### Local development & testing

Always validate locally first:

```bash
uv run langgraph dev
```

This spins up a local Agent Server with [Studio](https://docs.langchain.com/langsmith/studio),
lets you visualise and interact with the graph, and catches configuration,
dependency and logic errors before you deploy.

**💡 Tip**: if the graph runs cleanly under `langgraph dev`, deploying it to
LangSmith will very likely succeed.

![LangGraph Studio Interface](assets/studio-cli.png)

See the [LangGraph CLI documentation](https://docs.langchain.com/langsmith/cli#dev) for more.

### Cloud (SaaS)

Cloud deploys directly from your GitHub repository — no Docker involved.

**Via the UI**

1. Open your [LangSmith dashboard](https://smith.langchain.com)
2. Go to **Deployments** → **+ New Deployment**
3. Pick this repository and the branch to deploy

![Cloud Deployment UI](assets/cloud-lgp.png)

**Via the control plane API**

```bash
export LANGSMITH_API_KEY="..."             # never pass secrets as CLI arguments
export LANGSMITH_WORKSPACE_ID="..."
export LANGSMITH_GITHUB_INTEGRATION_ID="..."   # GET /v1/integrations/github/install
export OPENAI_API_KEY="..."

uv run python .github/scripts/langgraph_api.py \
  --target saas \
  --action deploy-production \
  --repo-url https://github.com/<org>/<repo> \
  --repo-ref main \
  --wait
```

### Self-Hosted

Self-hosted runs an image you build and push yourself.

```bash
# 1. Build the image
uv run langgraph build -t docker.io/<username>/text2sql-agent:latest

# 2. Push it to a registry your cluster can pull from
docker push docker.io/<username>/text2sql-agent:latest
```

Any registry works (Docker Hub, ECR, ACR, GCR, …) as long as your Kubernetes
cluster can reach it.

**Via the UI**: create a new deployment and enter the image URI in the
**Image Path** field.

![Self-Hosted Deployment UI](assets/selfhosted-lgp.png)

**Via the control plane API**

```bash
export LANGSMITH_API_KEY="..."
export LANGSMITH_WORKSPACE_ID="..."
export CONTROL_PLANE_HOST="https://langsmith.your-company.com/api-host"
export OPENAI_API_KEY="..."

uv run python .github/scripts/langgraph_api.py \
  --target self-hosted \
  --action deploy-production \
  --image-uri docker.io/<username>/text2sql-agent:latest \
  --wait
```

See the [self-hosted deployment guide](https://docs.langchain.com/langsmith/deploy-to-self-hosted-overview)
and [deploy with control plane](https://docs.langchain.com/langsmith/deploy-with-control-plane)
for cluster setup.

### Deployment flow

```mermaid
graph TD
    A[Agent Implementation] --> B[langgraph.json + dependencies]
    B --> C[Test locally with langgraph dev]
    C --> D{Errors?}
    D -->|Yes| E[Fix issues]
    E --> C
    D -->|No| F{Hosting model?}

    F -->|Cloud SaaS| G[Cloud LangSmith]
    F -->|Self-Hosted| H[Self-Hosted LangSmith]

    subgraph "Cloud SaaS — source: github"
        G --> I[Connect GitHub repo in UI]
        G --> J[Control Plane API with repo + ref]
        I --> K[Control plane builds the image]
        J --> K
    end

    subgraph "Self-Hosted — source: external_docker"
        H --> S[Build image with langgraph build]
        S --> T[Push to your container registry]
        T --> U{Deploy via?}
        U -->|UI| V[Enter image URI in the UI]
        U -->|API| W[Control Plane API with image_uri]
    end

    K --> AA[Agent ready for use]
    V --> AA
    W --> AA

    AA --> BB{Connect via?}
    BB --> CC[LangGraph SDK]
    BB --> DD[RemoteGraph]
    BB --> EE[REST API]
    BB --> FF[Studio UI]
```

### Connect to your deployed agent

- **[LangGraph SDK](https://docs.langchain.com/langsmith/deploy-reference-overview)**: programmatic integration
- **[RemoteGraph](https://docs.langchain.com/langsmith/use-remote-graph)**: use your deployed graph inside another graph
- **[REST API](https://docs.langchain.com/langsmith/agent-server-api)**: HTTP interaction with your agent
- **[Studio](https://docs.langchain.com/langsmith/studio)**: visual testing and debugging

### Environment configuration

#### Database & cache

LangSmith Deployment provisions PostgreSQL and Redis for you. To point at your own:

```bash
export POSTGRES_URI_CUSTOM="postgresql://user:pass@host:5432/db"
export REDIS_URI_CUSTOM="redis://host:6379/0"
```

See the environment variable reference for
[Cloud](https://docs.langchain.com/langsmith/env-var-cloud) and
[self-hosted](https://docs.langchain.com/langsmith/env-var-self-hosted).

#### Deployment secrets

Any API key your agent needs at runtime (here, `OPENAI_API_KEY`) is forwarded as
a deployment secret. The CI scripts read these from the environment by name and
never log their values.

### Deployment best practices

1. **Test locally first**: always validate with `langgraph dev`
2. **Version your images**: use semantic versioning for self-hosted images
3. **Monitor deployments**: use LangSmith tracing to watch agent performance
4. **Separate environments**: previews are `dev`, production is `prod`
5. **Set resource limits**: tune `--min-scale`, `--max-scale`, `--cpu`, `--memory-mb`

## 🔄 CI/CD Pipeline

Now that we have an understanding of how deployments work, let's deep dive into the specific CI/CD pipeline for this project. This automated pipeline ensures quality and reliability through multiple testing layers and evaluations, providing a robust framework for continuous integration and deployment.

The pipeline is designed to automatically handle the entire lifecycle from code changes to production deployment, incorporating comprehensive testing, evaluation, and deployment strategies that align with the deployment methods we've covered above.

### GitHub Actions Workflow

The CI/CD pipeline is implemented through GitHub Actions workflows that automatically trigger on code changes and pull requests:

#### Production deployment workflow

![Production deployment workflow](assets/new-lgp-revision.png)

When a pull request closes, this workflow deletes its preview deployment. If the pull request was merged, it then cuts a new production revision — patching the existing deployment when one exists, and creating it otherwise.

#### Testing and Evaluation Workflow

![Test with Results Workflow](assets/test-with-results.png)

In addition to the more traditional testing phases (unit tests, integration tests, end-to-end tests, etc.), we have added offline evaluations and LangGraph dev server testing because we want to test the quality of our agent. These evaluations provide comprehensive assessment of the agent's performance using real-world scenarios and data.

**Agent Server smoke test:**
- **Runs AFTER all other tests pass** (unit, integration, e2e, offline evaluations)
- Starts a local Agent Server on port 2024 via `langgraph dev`
- Tests the `/ok` health endpoint to ensure server is healthy
- Validates JSON response `{"ok": true}`
- Confirms the `simple_text2sql` graph is registered via `/assistants/search`
- Ensures the agent works in a real server environment before deployment
- **Final quality gate** before any deployment proceeds

```mermaid
graph TD
    A1[Code or Graph Change] --> B1[Trigger CI Pipeline]
    A2[Prompt Commit in PromptHub] --> B1
    A3[Online Evaluation Alert] --> B1
    A4[PR Opened] --> B1

    subgraph "Testing"
        B1 --> C1[Run Unit Tests]
        B1 --> C2[Run Integration Tests]
        B1 --> C3[Run End to End Tests]
        B1 --> C4[Run Offline Evaluations]

        C4 --> D1[Evaluate with OpenEvals or AgentEvals]
        C4 --> D2[Assertions: Hard and Soft]

        C1 --> E1[Run LangGraph Dev Server Test]
        C2 --> E1
        C3 --> E1
        D1 --> E1
        D2 --> E1
    end

    E1 --> F1[Push to Staging Deployment - Deploy to LangSmith as Development Type]

    F1 --> G1[Run Online Evaluations on Live Data]
    G1 --> H1[Attach Scores to Traces]

    H1 --> I1[If Quality Below Threshold]
    I1 --> J1[Send to Annotation Queue]
    I1 --> J2[Trigger Alert via Webhook]
    I1 --> J3[Push Trace to Golden Dataset]

    F1 --> K1[Promote to Production if All Pass - Deploy to LangSmith Production]

    J2 --> L1[Slack or PagerDuty Notification]

    subgraph Manual Review
        J1 --> M1[Human Labeling]
        M1 --> J3
    end

```

### Pipeline Stages

1. **Trigger Sources**: Code changes, graph modifications, prompt updates, or online evaluation alerts
2. **Testing Layers**: Unit tests for individual nodes, integration tests, end-to-end graph testing, deployment-client tests, and an Agent Server smoke test
3. **Evaluation**: Offline evaluations using OpenEvals/AgentEvals with hard and soft assertions
4. **Quality Gates**: Preview deployments only proceed if all tests pass successfully
5. **Staging**: Deployment to staging environment for live data testing
6. **Production**: Promotion to production if all quality thresholds are met
7. **Monitoring**: Continuous monitoring with alerts and manual review processes

### How previews stay safe and cheap

- **Tests gate deployment**: the preview workflow is invoked by the test workflow
  as a reusable workflow, so it only runs once every test job is green
- **No wasted deployments**: failing code never reaches a preview environment
- **Automatic cleanup**: closing the pull request deletes its preview
- **Fork pull requests are excluded**: previews are invoked in the pull request's
  own context rather than through `workflow_run`. A `workflow_run` trigger runs in
  the base repository *with* access to every secret, which would expose the
  deployment credentials to code from a fork
- **Secrets stay out of logs**: credentials are passed to the scripts through the
  environment, never as command-line arguments, and only secret *names* are printed

## 📚 Examples

Check out the `examples/` directory for usage examples and demonstrations of the text-to-SQL agent capabilities.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
