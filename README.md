# LGP Evals CI/CD Pipeline 🚀

Agent built in [LangGraph OSS](https://docs.langchain.com/oss/python/langgraph/overview). It includes:
- unit, integration, e2e tests
- offline evaluations with [OpenEvals](https://github.com/langchain-ai/openevals) and [LangSmith](https://docs.langchain.com/langsmith/home)
- preview and prod agent deployments using [LangGraph Platform](https://docs.langchain.com/langgraph-platform/api-ref-control-plane) control plane API

## 🛠️ Prerequisites

- [uv](https://docs.astral.sh/uv/) - Fast Python package installer and resolver

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

### 3. Run LangGraph Studio

Start the LangGraph development server to visualize your agent:

```bash
uv run langgraph dev
```

This will start the LangGraph Studio interface where you can interact with and debug your text-to-SQL agent.

## 📁 Project Structure

```
text2sql-agent/
├── agents/           # Agent implementations
├── examples/         # Usage examples
├── helpers/          # Utility functions
└── langgraph.json    # LangGraph configuration
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

- **Offline evaluations** (agent performance evaluation):
  ```bash
  uv run pytest -m evaluator
  ```

### GitHub Actions Environment Setup

If you enable the GitHub Actions workflow, make sure to set the following environment variable in your repository secrets:

- **`OPENAI_API_KEY`**: Your OpenAI API key
- **`LANGSMITH_API_KEY`**: Your LangSmith API key
- **`LANGSMITH_TRACING=true`**: Enable LangSmith tracing


The workflow will automatically run tests and evaluations on pull requests and pushes to main/develop branches

## 🚀 Deployment Options

This project supports multiple deployment methods beyond the automated GitHub Actions CI/CD pipeline. Here are the different ways you can deploy your LangGraph agent:

### Prerequisites for Manual Deployment

Before deploying your agent, ensure you have:

1. **LangGraph Graph**: Your agent implementation (e.g., `./agents/simple_text2sql.py:agent`)
2. **Dependencies**: Either `requirements.txt` or `pyproject.toml` with all required packages
3. **Configuration**: `langgraph.json` file specifying:
   - Path to your agent graph
   - Dependencies location
   - Environment variables
   - Python version

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

### Method 1: GitHub Integration from UI (Recommended for Cloud Users)

Connect your GitHub repository directly to LangGraph Platform:

1. Go to your LangGraph Platform dashboard
2. Connect your GitHub repository by providing GitHub permissions
3. The platform will automatically build and deploy your agent from your repository
4. No manual Docker image building or pushing required

**Benefits:**
- Simplest deployment method for cloud users
- Automatic build and deployment
- No manual Docker image management
- Direct integration with your GitHub repository

### Method 2: Build Docker Image with LangGraph CLI

Build a Docker image directly using the LangGraph CLI:

```bash
# Build Docker image
uv run langgraph build -t my-agent:latest

# Push to your container registry
docker push my-agent:latest
```

You can push to any container registry (Docker Hub, AWS ECR, Azure ACR, Google GCR, etc.) that your deployment environment has access to.

See the [LangGraph CLI build documentation](https://docs.langchain.com/langgraph-platform/cli#build) for more details.

### Method 3: Generate Dockerfile

Create a custom Dockerfile for more control:

```bash
# Generate Dockerfile from langgraph.json
uv run langgraph dockerfile -c langgraph.json Dockerfile

# Build and push manually
docker build -t my-agent:latest .
docker push my-agent:latest
```

See the [LangGraph CLI dockerfile documentation](https://docs.langchain.com/langgraph-platform/cli#dockerfile) for more details.

### Local Development & Testing

First, test your agent locally using LangGraph Studio:

```bash
# Start local development server with LangGraph Studio
uv run langgraph dev
```

This will:
- Spin up a local server with LangGraph Studio
- Allow you to visualize and interact with your graph
- Validate that your agent works correctly before deployment

**💡 Tip**: If your graph works in LangGraph Studio, deployment to LangGraph Platform will likely succeed.

![LangGraph Studio Interface](assets/studio-cli.png)

See the [LangGraph CLI documentation](https://docs.langchain.com/langgraph-platform/cli#dev) for more details.

### Deploy to LangGraph Platform

#### Cloud Deployment (LangSmith Cloud)

Deploy using the [LangGraph Platform Control Plane API](https://docs.langchain.com/langgraph-platform/api-ref-control-plane#langgraph-control-plane-api-reference) to create deployments from your container registry.

![Cloud Deployment UI](assets/cloud-lgp.png)

#### Self-Hosted Deployment

For [self-hosted LangSmith instances](https://docs.langchain.com/langgraph-platform/deploy-self-hosted-full-platform):

1. Ensure your Kubernetes cluster has access to your container registry
2. Create a new deployment from the LangSmith UI
3. Specify your image URI (e.g., `docker.io/username/my-agent:latest`)

**Note**: Self-hosted deployments don't distinguish between development/production types, but you can use tags to organize them.

![Self-Hosted Deployment UI](assets/selfhosted-lgp.png)

See the [self-hosted full platform deployment guide](https://docs.langchain.com/langgraph-platform/deploy-self-hosted-full-platform) for detailed setup instructions.

### Environment Configuration

#### Database & Cache Configuration

By default, LangGraph Platform creates PostgreSQL and Redis instances for you. To use external services:

```bash
# Set environment variables for external services
export POSTGRES_URI_CUSTOM="postgresql://user:pass@host:5432/db"
export REDIS_URI_CUSTOM="redis://host:6379/0"
```

See the [environment variables documentation](https://docs.langchain.com/langgraph-platform/env-var#postgres-uri-custom) for more details.

#### Required Environment Variables

Remember to add all necessary environment variables to your deployment, including any API keys required by your specific agent implementation.

### Deployment Flow

```mermaid
graph TD
    A[Agent Implementation] --> B[langgraph.json]
    B --> C[Test Locally with langgraph dev]
    C --> D{Local Test Passed?}
    D -->|No| E[Fix Issues]
    E --> C
    D -->|Yes| F[Choose Deployment Method]

    F --> G[Method 1: GitHub Integration from UI]
    F --> H[Method 2: langgraph build]
    F --> I[Method 3: langgraph dockerfile]

    G --> J[Connect GitHub Repo]
    J --> K[Auto Build & Deploy]

    H --> L[Build Docker Image]
    I --> M[Generate Dockerfile]
    M --> N[Build Docker Image Manually]

    L --> O[Push to Container Registry]
    N --> O

    K --> P[Deploy to LangGraph Platform]
    O --> P
    P --> Q{Deployment Type?}

    Q -->|Cloud| R[Use Control Plane API or GitHub]
    Q -->|Self-Hosted| S[Use LangSmith UI]

    R --> T[Production Deployment]
    S --> T

    T --> U[Monitor with LangSmith]
    U --> V[Agent Ready for Use]
```

### Deployment Best Practices

1. **Test Locally First**: Always use `langgraph dev` to validate your agent
2. **Version Your Images**: Use semantic versioning for your Docker images
3. **Monitor Deployments**: Use LangSmith tracing to monitor agent performance
4. **Environment Separation**: Use different image tags for different environments
5. **Resource Limits**: Set appropriate CPU/memory limits for your deployments

## 🔄 CI/CD Pipeline

Now that we have an understanding of how deployments work, let's deep dive into the specific CI/CD pipeline for this project. This automated pipeline ensures quality and reliability through multiple testing layers and evaluations, providing a robust framework for continuous integration and deployment.

The pipeline is designed to automatically handle the entire lifecycle from code changes to production deployment, incorporating comprehensive testing, evaluation, and deployment strategies that align with the deployment methods we've covered above.

### GitHub Actions Workflow

The CI/CD pipeline is implemented through GitHub Actions workflows that automatically trigger on code changes and pull requests:

#### New LGP Revision Workflow

![New LGP Revision Workflow](assets/new-lgp-revision.png)

If we already have an existing deployment, this workflow will run the new LangGraph Platform revision process. This ensures that any updates to the agent are properly deployed and integrated into the existing infrastructure.

#### Testing and Evaluation Workflow

![Test with Results Workflow](assets/test-with-results.png)

In addition to the more traditional testing phases (unit tests, integration tests, end-to-end tests, etc.), we have added offline evaluations because we want to test the quality of our agent. These evaluations provide comprehensive assessment of the agent's performance using real-world scenarios and data.

```mermaid
graph TD
    A1[Code or Graph Change] --> B1[Trigger CI Pipeline]
    A2[Prompt Commit in PromptHub] --> B1
    A3[Online Evaluation Alert] --> B1

    B1 --> C1[Run Unit Tests on Nodes]
    B1 --> C2[Run Integration Tests]
    B1 --> C3[Run End to End Tests on Graph]

    C1 --> D1[Run Offline Evaluations]
    C2 --> D1
    C3 --> D1

    D1 --> E1[Evaluate with OpenEvals or AgentEvals]
    D1 --> E2[Assertions: Hard and Soft]

    E1 --> F1[Push to Staging Deployment - Spin new Docker deployment in LGP as Development Type]
    E2 --> F1

    F1 --> G1[Run Online Evaluations on Live Data]
    G1 --> H1[Attach Scores to Traces]

    H1 --> I1[If Quality Below Threshold]
    I1 --> J1[Send to Annotation Queue]
    I1 --> J2[Trigger Alert via Webhook]
    I1 --> J3[Push Trace to Golden Dataset]

    F1 --> K1[Promote to Production if All Pass - Spin Production Deployment in LGP]

    J2 --> L1[Slack or PagerDuty Notification]

    subgraph Manual Review
        J1 --> M1[Human Labeling]
        M1 --> J3
    end

```

### Pipeline Stages

1. **Trigger Sources**: Code changes, graph modifications, prompt updates, or online evaluation alerts
2. **Testing Layers**: Unit tests for individual nodes, integration tests, and end-to-end graph testing
3. **Evaluation**: Offline evaluations using OpenEvals/AgentEvals with hard and soft assertions
4. **Staging**: Deployment to staging environment for live data testing
5. **Quality Gates**: Online evaluations on production-like data with trace scoring
6. **Production**: Promotion to production if all quality thresholds are met
7. **Monitoring**: Continuous monitoring with alerts and manual review processes

## 📚 Examples

Check out the `examples/` directory for usage examples and demonstrations of the text-to-SQL agent capabilities.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
