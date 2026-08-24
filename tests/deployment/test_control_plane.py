"""Tests for the SaaS and self-hosted deployment paths.

The control plane accepts different payloads per hosting model, and a wrong
payload only surfaces as a 4xx in CI. These tests pin the host, headers and
request body that each target produces, and assert that secrets stay out of
logs.
"""

import json

import pytest
import responses

from .conftest import control_plane, langgraph_api


def _load_report_module():
    from .conftest import _load

    return _load("report_deployment")


API_KEY = "test-api-key"
WORKSPACE_ID = "11111111-2222-3333-4444-555555555555"
SAAS_HOST = "https://api.host.langchain.com"
SELF_HOSTED_HOST = "https://langsmith.internal.example.com/api-host"


def make_client(host=SAAS_HOST, **kwargs):
    return control_plane.ControlPlaneClient(host, API_KEY, WORKSPACE_ID, **kwargs)


# -- host resolution ------------------------------------------------------


@pytest.mark.deployment
@pytest.mark.parametrize(
    "region,expected",
    [
        ("us", "https://api.host.langchain.com"),
        ("eu", "https://eu.api.host.langchain.com"),
        ("apac", "https://apac.api.host.langchain.com"),
        ("aws-us", "https://aws.api.host.langchain.com"),
    ],
)
def test_saas_region_hosts(region, expected):
    assert control_plane.resolve_host("saas", host=None, region=region) == expected


@pytest.mark.deployment
def test_self_hosted_requires_explicit_host():
    with pytest.raises(
        control_plane.ControlPlaneError, match="explicit control plane host"
    ):
        control_plane.resolve_host("self-hosted", host=None, region="us")


@pytest.mark.deployment
def test_explicit_host_overrides_region():
    assert (
        control_plane.resolve_host("saas", host=SELF_HOSTED_HOST, region="eu")
        == SELF_HOSTED_HOST
    )


@pytest.mark.deployment
@pytest.mark.parametrize(
    "given,expected",
    [
        ("https://host.example.com/api-host/", "https://host.example.com/api-host"),
        ("https://host.example.com/api-host/v2", "https://host.example.com/api-host"),
        ("https://host.example.com", "https://host.example.com"),
    ],
)
def test_host_normalisation(given, expected):
    assert control_plane.normalise_host(given) == expected


@pytest.mark.deployment
@pytest.mark.parametrize(
    "bad_host",
    ["", "  ", "not-a-url", "ftp://host.example.com", "https://?q=1", "//host"],
)
def test_host_rejects_malformed_values(bad_host):
    with pytest.raises(ValueError):
        control_plane.normalise_host(bad_host)


@pytest.mark.deployment
def test_plain_http_requires_opt_in():
    """An API key must not be sent over http unless explicitly allowed."""
    with pytest.raises(ValueError, match="plain http"):
        control_plane.normalise_host("http://langsmith.internal")
    assert (
        control_plane.normalise_host("http://langsmith.internal", allow_insecure=True)
        == "http://langsmith.internal"
    )


# -- payload shape per target --------------------------------------------


@pytest.mark.deployment
def test_saas_uses_github_source():
    payload = control_plane.build_saas_payload(
        integration_id="integration-1",
        repo_url="https://github.com/org/repo",
        repo_ref="feature-branch",
        langgraph_config_path="langgraph.json",
        deployment_type="dev",
    )
    assert control_plane.source_for_target("saas") == "github"
    assert payload["source_config"]["integration_id"] == "integration-1"
    assert payload["source_config"]["repo_url"] == "https://github.com/org/repo"
    assert payload["source_config"]["deployment_type"] == "dev"
    assert payload["source_revision_config"]["repo_ref"] == "feature-branch"
    assert (
        payload["source_revision_config"]["langgraph_config_path"] == "langgraph.json"
    )
    # Cloud builds from source; an image URI would be rejected.
    assert "image_uri" not in payload["source_revision_config"]


@pytest.mark.deployment
def test_saas_requires_integration_id():
    with pytest.raises(control_plane.ControlPlaneError, match="INTEGRATION_ID"):
        control_plane.build_saas_payload(
            integration_id="",
            repo_url="https://github.com/org/repo",
            repo_ref="main",
            langgraph_config_path="langgraph.json",
            deployment_type="dev",
        )


@pytest.mark.deployment
def test_self_hosted_uses_external_docker_source():
    payload = control_plane.build_self_hosted_payload(
        image_uri="docker.io/org/agent:preview-7", listener_id="listener-9"
    )
    assert control_plane.source_for_target("self-hosted") == "external_docker"
    assert (
        payload["source_revision_config"]["image_uri"]
        == "docker.io/org/agent:preview-7"
    )
    assert payload["source_config"]["listener_id"] == "listener-9"
    assert payload["source_config"]["resource_spec"]["memory_mb"] == 1024
    # Self-hosted never builds from a repo.
    assert "repo_url" not in payload["source_config"]


@pytest.mark.deployment
def test_self_hosted_requires_image_uri():
    with pytest.raises(control_plane.ControlPlaneError, match="image-uri"):
        control_plane.build_self_hosted_payload(image_uri="")


@pytest.mark.deployment
def test_listener_id_omitted_when_unset():
    payload = control_plane.build_self_hosted_payload(image_uri="img:1")
    assert "listener_id" not in payload["source_config"]


# -- requests on the wire -------------------------------------------------


@pytest.mark.deployment
@responses.activate
def test_create_deployment_sends_auth_headers_and_body():
    responses.add(
        responses.POST,
        f"{SAAS_HOST}/v2/deployments",
        json={"id": "dep-1", "url": "https://dep-1.example.com", "status": "READY"},
        status=201,
    )
    client = make_client()
    payload = control_plane.build_saas_payload(
        integration_id="integration-1",
        repo_url="https://github.com/org/repo",
        repo_ref="main",
        langgraph_config_path="langgraph.json",
        deployment_type="prod",
    )
    result = client.create_deployment(
        "text2sql-agent-prod",
        "github",
        payload["source_config"],
        payload["source_revision_config"],
        [{"name": "OPENAI_API_KEY", "value": "secret-value"}],
    )

    assert result["id"] == "dep-1"
    request = responses.calls[0].request
    assert request.headers["X-Api-Key"] == API_KEY
    assert request.headers["X-Tenant-Id"] == WORKSPACE_ID
    body = json.loads(request.body)
    assert body["name"] == "text2sql-agent-prod"
    assert body["source"] == "github"
    assert body["secrets"] == [{"name": "OPENAI_API_KEY", "value": "secret-value"}]


@pytest.mark.deployment
@responses.activate
def test_self_hosted_requests_go_to_the_instance_host():
    responses.add(
        responses.POST,
        f"{SELF_HOSTED_HOST}/v2/deployments",
        json={"id": "dep-2", "status": "AWAITING_DATABASE"},
        status=201,
    )
    client = make_client(SELF_HOSTED_HOST)
    payload = control_plane.build_self_hosted_payload(image_uri="docker.io/org/agent:1")
    client.create_deployment(
        "text2sql-agent-pr-3",
        "external_docker",
        payload["source_config"],
        payload["source_revision_config"],
        [],
    )
    assert responses.calls[0].request.url.startswith(
        "https://langsmith.internal.example.com/api-host/v2/deployments"
    )


@pytest.mark.deployment
@responses.activate
def test_find_deployment_filters_by_exact_name():
    responses.add(
        responses.GET,
        f"{SAAS_HOST}/v2/deployments",
        json={"resources": [{"name": "text2sql-agent-pr-1", "id": "dep-1"}]},
        status=200,
    )
    client = make_client()
    assert client.find_deployment("text2sql-agent-pr-1")["id"] == "dep-1"
    assert "name=text2sql-agent-pr-1" in responses.calls[0].request.url


@pytest.mark.deployment
@responses.activate
def test_find_deployment_ignores_partial_name_matches():
    """The API filter is a prefix match, so the client must confirm exact equality."""
    responses.add(
        responses.GET,
        f"{SAAS_HOST}/v2/deployments",
        json={"resources": [{"name": "text2sql-agent-pr-11", "id": "other"}]},
        status=200,
    )
    assert make_client().find_deployment("text2sql-agent-pr-1") is None


@pytest.mark.deployment
@responses.activate
def test_patch_creates_a_new_revision():
    responses.add(
        responses.PATCH,
        f"{SAAS_HOST}/v2/deployments/dep-1",
        json={"id": "dep-1", "latest_revision_id": "rev-2"},
        status=200,
    )
    client = make_client()
    client.patch_deployment("dep-1", {"image_uri": "docker.io/org/agent:2"})
    body = json.loads(responses.calls[0].request.body)
    assert body["source_revision_config"]["image_uri"] == "docker.io/org/agent:2"


@pytest.mark.deployment
@responses.activate
def test_delete_accepts_204():
    responses.add(responses.DELETE, f"{SAAS_HOST}/v2/deployments/dep-1", status=204)
    make_client().delete_deployment("dep-1")
    assert len(responses.calls) == 1


@pytest.mark.deployment
@responses.activate
def test_error_response_raises_with_status():
    """Unexpected statuses surface the code and body so CI logs are diagnosable."""
    responses.add(
        responses.POST,
        f"{SAAS_HOST}/v2/deployments",
        json={"detail": "resource_spec.cpu must be greater than 0"},
        status=400,
    )
    with pytest.raises(control_plane.ControlPlaneError, match="400") as excinfo:
        make_client().create_deployment("x", "github", {}, {}, [])
    assert "resource_spec.cpu" in str(excinfo.value)


@pytest.mark.deployment
def test_requests_carry_a_timeout():
    """A hung control plane must not hang the CI job forever."""
    client = make_client()
    assert client.timeout > 0


# -- revision polling -----------------------------------------------------


@pytest.mark.deployment
@responses.activate
def test_wait_for_revision_returns_when_deployed():
    url = f"{SAAS_HOST}/v2/deployments/dep-1/revisions/rev-1"
    responses.add(responses.GET, url, json={"status": "BUILDING"}, status=200)
    responses.add(responses.GET, url, json={"status": "DEPLOYING"}, status=200)
    responses.add(responses.GET, url, json={"status": "DEPLOYED"}, status=200)

    revision = make_client().wait_for_revision(
        "dep-1", "rev-1", interval=0, sleep=lambda _: None
    )
    assert revision["status"] == "DEPLOYED"


@pytest.mark.deployment
@responses.activate
def test_wait_for_revision_raises_on_build_failure():
    responses.add(
        responses.GET,
        f"{SAAS_HOST}/v2/deployments/dep-1/revisions/rev-1",
        json={"status": "BUILD_FAILED", "status_message": "missing dependency"},
        status=200,
    )
    with pytest.raises(control_plane.ControlPlaneError, match="missing dependency"):
        make_client().wait_for_revision(
            "dep-1", "rev-1", interval=0, sleep=lambda _: None
        )


@pytest.mark.deployment
@responses.activate
def test_wait_for_revision_times_out():
    responses.add(
        responses.GET,
        f"{SAAS_HOST}/v2/deployments/dep-1/revisions/rev-1",
        json={"status": "BUILDING"},
        status=200,
    )
    clock = iter([0.0, 1.0, 2.0, 99.0])
    with pytest.raises(control_plane.ControlPlaneError, match="Timed out"):
        make_client().wait_for_revision(
            "dep-1",
            "rev-1",
            timeout=10,
            interval=0,
            sleep=lambda _: None,
            monotonic=lambda: next(clock),
        )


# -- naming and secrets ---------------------------------------------------


@pytest.mark.deployment
def test_preview_and_production_names():
    assert langgraph_api.preview_name("text2sql-agent", 42) == "text2sql-agent-pr-42"
    assert langgraph_api.production_name("text2sql-agent") == "text2sql-agent-prod"


@pytest.mark.deployment
@pytest.mark.parametrize(
    "bad_name",
    [
        "Text2SQL",
        "agent_underscore",
        "-leading",
        "trailing-",
        "path/traversal",
        "a" * 70,
    ],
)
def test_invalid_deployment_names_rejected(bad_name):
    with pytest.raises(ValueError):
        control_plane.validate_deployment_name(bad_name)


@pytest.mark.deployment
def test_collect_secrets_reads_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-value")
    assert control_plane.collect_secrets(["OPENAI_API_KEY"]) == [
        {"name": "OPENAI_API_KEY", "value": "test-openai-value"}
    ]


@pytest.mark.deployment
def test_collect_secrets_fails_loudly_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_MISSING_KEY", raising=False)
    with pytest.raises(control_plane.ControlPlaneError, match="SOME_MISSING_KEY"):
        control_plane.collect_secrets(["SOME_MISSING_KEY"])


@pytest.mark.deployment
def test_print_deployment_never_prints_secret_values(capsys):
    """Deployment output is echoed into CI logs and PR comments."""
    control_plane.print_deployment(
        {
            "id": "dep-1",
            "url": "https://dep-1.example.com",
            "status": "READY",
            "secrets": [{"name": "OPENAI_API_KEY", "value": "test-secret-value"}],
        }
    )
    output = capsys.readouterr().out
    assert "OPENAI_API_KEY" in output
    assert "test-secret-value" not in output


@pytest.mark.deployment
@responses.activate
def test_report_leads_with_failure_when_revision_failed(tmp_path):
    """A deployment can be READY while its newest revision failed.

    The PR comment must not show a green tick in that case -- a reviewer skims
    the heading and would otherwise read a failed deploy as a success.
    """
    report_deployment = _load_report_module()
    responses.add(
        responses.GET,
        f"{SAAS_HOST}/v2/deployments",
        json={
            "resources": [
                {"name": "text2sql-agent-pr-999", "id": "dep-1", "status": "READY"}
            ]
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{SAAS_HOST}/v2/deployments/dep-1/revisions",
        json={"resources": [{"id": "rev-1", "status": "DEPLOY_FAILED"}]},
        status=200,
    )

    report = report_deployment.build_report(
        make_client(), "text2sql-agent-pr-999", "preview", "self-hosted"
    )
    out = tmp_path / "comment.md"
    report_deployment.write_markdown_report(report, str(out))
    body = out.read_text()

    heading = next(line for line in body.splitlines() if line.startswith("### "))
    assert "❌" in heading, heading
    assert "✅" not in heading, heading
    assert "DEPLOY_FAILED" in body


@pytest.mark.deployment
@responses.activate
def test_leftover_tracing_project_gives_actionable_error():
    """Deleting a deployment leaves its tracing project, blocking the name.

    A reopened pull request whose preview was already cleaned up hits this, so
    the message has to say how to fix it rather than dumping a raw 409.
    """
    responses.add(
        responses.POST,
        f"{SAAS_HOST}/v2/deployments",
        json={
            "detail": (
                "Deployments create a tracing project in LangSmith with the same "
                "name as the deployment. There already exists a project in "
                "LangSmith named: text2sql-agent-pr-999."
            )
        },
        status=409,
    )
    with pytest.raises(control_plane.NameConflictError) as excinfo:
        make_client().create_deployment(
            "text2sql-agent-pr-999", "external_docker", {}, {}, []
        )

    message = str(excinfo.value)
    assert "tracing project" in message
    assert "Delete the tracing project" in message
    # Still a ControlPlaneError, so existing handling keeps working.
    assert isinstance(excinfo.value, control_plane.ControlPlaneError)
