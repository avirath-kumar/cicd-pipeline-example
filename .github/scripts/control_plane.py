#!/usr/bin/env python3
"""Client for the LangSmith Deployment control plane API.

The control plane accepts a different deployment *source* depending on how your
LangSmith instance is hosted, so the two hosting models need different payloads:

``saas``
    LangSmith Cloud. Deploys straight from a GitHub repository
    (``source: "github"``) -- the control plane builds the image for you.

``self-hosted``
    A LangSmith instance you run yourself. Deploys a Docker image that you have
    already built and pushed to a registry (``source: "external_docker"``).

Both targets share the same ``/v2`` endpoints, authentication and revision
lifecycle; only the host and the source configuration differ.

See https://docs.langchain.com/langsmith/api-ref-control-plane for the API reference.
"""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urlparse

import requests

TARGET_SAAS = "saas"
TARGET_SELF_HOSTED = "self-hosted"
TARGETS = (TARGET_SAAS, TARGET_SELF_HOSTED)

#: Control plane hosts for each LangSmith Cloud data region.
SAAS_CONTROL_PLANE_HOSTS = {
    "us": "https://api.host.langchain.com",
    "eu": "https://eu.api.host.langchain.com",
    "apac": "https://apac.api.host.langchain.com",
    "aws-us": "https://aws.api.host.langchain.com",
}

#: Revision statuses that mean the revision will never reach ``DEPLOYED``.
FAILED_REVISION_STATUSES = frozenset(
    {"CREATE_FAILED", "BUILD_FAILED", "DEPLOY_FAILED", "INTERRUPTED"}
)

#: Deployment names become DNS labels, so keep them conservative.
_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

DEFAULT_TIMEOUT = 30.0
DEFAULT_WAIT_TIMEOUT = 1800.0
DEFAULT_POLL_INTERVAL = 15.0


class ControlPlaneError(RuntimeError):
    """Raised when the control plane returns an unexpected response."""


def normalise_host(host: str, *, allow_insecure: bool = False) -> str:
    """Validate a control plane host and return it without a trailing slash.

    The host comes from CI configuration and is used to build URLs that carry a
    LangSmith API key, so reject anything that is not an absolute http(s) URL.
    Plain http is only allowed when explicitly opted into, which self-hosted
    instances on an internal network sometimes need.
    """
    if not host or not host.strip():
        raise ValueError("Control plane host is empty.")

    parsed = urlparse(host.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Control plane host must be an absolute http(s) URL, got {host!r}."
        )
    if not parsed.netloc:
        raise ValueError(f"Control plane host is missing a hostname: {host!r}.")
    if parsed.scheme == "http" and not allow_insecure:
        raise ValueError(
            f"Refusing to send an API key over plain http to {host!r}. "
            "Pass --allow-insecure-host if this is an internal self-hosted instance."
        )
    if parsed.query or parsed.fragment:
        raise ValueError(
            f"Control plane host must not contain a query or fragment: {host!r}."
        )

    # Callers sometimes paste the versioned URL; keep only the base.
    path = parsed.path.rstrip("/")
    if path.endswith("/v2"):
        path = path[: -len("/v2")]
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def validate_deployment_name(name: str) -> str:
    """Return ``name`` if it is safe to use in a URL path, else raise."""
    if not _NAME_RE.match(name):
        raise ValueError(
            f"Invalid deployment name {name!r}: expected lowercase letters, digits "
            "and dashes, starting and ending with an alphanumeric character."
        )
    return name


def collect_secrets(names: Iterable[str]) -> List[Dict[str, str]]:
    """Read deployment secrets from the environment.

    Values are read by name and never logged. A name with no value set is an
    error -- silently deploying without a required API key fails later, in a
    much more confusing place.
    """
    secrets: List[Dict[str, str]] = []
    missing: List[str] = []
    for name in names:
        value = os.environ.get(name)
        if not value:
            missing.append(name)
            continue
        secrets.append({"name": name, "value": value})
    if missing:
        raise ControlPlaneError(
            "Missing environment variables for deployment secrets: "
            + ", ".join(sorted(missing))
        )
    return secrets


class ControlPlaneClient:
    """Thin wrapper over the ``/v2`` control plane endpoints."""

    def __init__(
        self,
        host: str,
        api_key: str,
        workspace_id: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        allow_insecure: bool = False,
    ):
        if not api_key:
            raise ControlPlaneError("LANGSMITH_API_KEY is not set.")
        if not workspace_id:
            raise ControlPlaneError("LANGSMITH_WORKSPACE_ID is not set.")

        self.host = normalise_host(host, allow_insecure=allow_insecure)
        self.timeout = timeout
        self._session = requests.Session()
        # Sent on every request; never logged.
        self._session.headers.update(
            {
                "X-Api-Key": api_key,
                "X-Tenant-Id": workspace_id,
                "Content-Type": "application/json",
            }
        )

    # -- plumbing ---------------------------------------------------------

    def _url(self, *segments: str) -> str:
        path = "/".join(quote(str(segment), safe="") for segment in segments)
        return f"{self.host}/v2/{path}"

    def _request(
        self,
        method: str,
        url: str,
        *,
        expected: Iterable[int],
        **kwargs: Any,
    ) -> requests.Response:
        try:
            response = self._session.request(
                method, url, timeout=self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise ControlPlaneError(f"{method} {url} failed: {exc}") from exc

        if response.status_code not in expected:
            raise ControlPlaneError(
                f"{method} {url} returned {response.status_code}: "
                f"{response.text[:500]}"
            )
        return response

    # -- deployments ------------------------------------------------------

    def list_deployments(
        self, *, name_contains: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Return deployments in the workspace, optionally filtered by name."""
        params: Dict[str, Any] = {"limit": limit}
        if name_contains:
            params["name_contains"] = name_contains
        response = self._request(
            "GET", self._url("deployments"), params=params, expected=(200,)
        )
        return response.json().get("resources", [])

    def find_deployment(self, name: str) -> Optional[Dict[str, Any]]:
        """Return the deployment with this exact name, or ``None``."""
        validate_deployment_name(name)
        response = self._request(
            "GET", self._url("deployments"), params={"name": name}, expected=(200,)
        )
        for deployment in response.json().get("resources", []):
            if deployment.get("name") == name:
                return deployment
        return None

    def create_deployment(
        self,
        name: str,
        source: str,
        source_config: Dict[str, Any],
        source_revision_config: Dict[str, Any],
        secrets: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Create a deployment and return the created resource."""
        validate_deployment_name(name)
        body = {
            "name": name,
            "source": source,
            "source_config": source_config,
            "source_revision_config": source_revision_config,
            "secrets": secrets,
        }
        response = self._request(
            "POST", self._url("deployments"), json=body, expected=(200, 201)
        )
        return response.json()

    def patch_deployment(
        self,
        deployment_id: str,
        source_revision_config: Dict[str, Any],
        secrets: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Create a new revision of an existing deployment."""
        body: Dict[str, Any] = {"source_revision_config": source_revision_config}
        if secrets is not None:
            body["secrets"] = secrets
        response = self._request(
            "PATCH",
            self._url("deployments", deployment_id),
            json=body,
            expected=(200,),
        )
        return response.json()

    def delete_deployment(self, deployment_id: str) -> None:
        self._request(
            "DELETE", self._url("deployments", deployment_id), expected=(200, 204)
        )

    def list_revisions(self, deployment_id: str) -> List[Dict[str, Any]]:
        """Return revisions, most recent first."""
        response = self._request(
            "GET",
            self._url("deployments", deployment_id, "revisions"),
            expected=(200,),
        )
        return response.json().get("resources", [])

    def get_revision(self, deployment_id: str, revision_id: str) -> Dict[str, Any]:
        response = self._request(
            "GET",
            self._url("deployments", deployment_id, "revisions", revision_id),
            expected=(200,),
        )
        return response.json()

    def wait_for_revision(
        self,
        deployment_id: str,
        revision_id: str,
        *,
        timeout: float = DEFAULT_WAIT_TIMEOUT,
        interval: float = DEFAULT_POLL_INTERVAL,
        sleep=time.sleep,
        monotonic=time.monotonic,
    ) -> Dict[str, Any]:
        """Poll a revision until it is ``DEPLOYED``.

        Raises on a terminal failure status or when ``timeout`` elapses.
        """
        deadline = monotonic() + timeout
        revision: Dict[str, Any] = {}
        while monotonic() < deadline:
            revision = self.get_revision(deployment_id, revision_id)
            status = revision.get("status", "UNKNOWN")

            if status == "DEPLOYED":
                return revision
            if status in FAILED_REVISION_STATUSES:
                message = revision.get("status_message") or "no detail provided"
                raise ControlPlaneError(
                    f"Revision {revision_id} finished as {status}: {message}"
                )

            print(f"⏳ Revision {revision_id} is {status}...", flush=True)
            sleep(interval)

        raise ControlPlaneError(
            f"Timed out after {timeout:.0f}s waiting for revision {revision_id} "
            f"to be DEPLOYED (last status: {revision.get('status', 'UNKNOWN')})."
        )


# -- payload builders -----------------------------------------------------


def build_saas_payload(
    *,
    integration_id: str,
    repo_url: str,
    repo_ref: str,
    langgraph_config_path: str,
    deployment_type: str,
    build_on_push: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Build ``source_config``/``source_revision_config`` for LangSmith Cloud.

    Cloud deployments are built by the control plane from a GitHub repository;
    external Docker images are rejected for this hosting model.
    """
    if not integration_id:
        raise ControlPlaneError(
            "LANGSMITH_GITHUB_INTEGRATION_ID is required for SaaS deployments. "
            "Retrieve it from GET /v1/integrations/github/install."
        )
    if not repo_url:
        raise ControlPlaneError("--repo-url is required for SaaS deployments.")

    return {
        "source_config": {
            "integration_id": integration_id,
            "repo_url": repo_url,
            "deployment_type": deployment_type,
            "build_on_push": build_on_push,
        },
        "source_revision_config": {
            "repo_ref": repo_ref,
            "langgraph_config_path": langgraph_config_path,
        },
    }


def build_self_hosted_payload(
    *,
    image_uri: str,
    listener_id: Optional[str] = None,
    min_scale: int = 1,
    max_scale: int = 1,
    cpu: float = 1,
    memory_mb: int = 1024,
) -> Dict[str, Dict[str, Any]]:
    """Build ``source_config``/``source_revision_config`` for a self-hosted instance.

    Self-hosted deployments run an image you built and pushed yourself; the
    control plane never builds for this hosting model.
    """
    if not image_uri:
        raise ControlPlaneError("--image-uri is required for self-hosted deployments.")

    source_config: Dict[str, Any] = {
        "resource_spec": {
            "min_scale": min_scale,
            "max_scale": max_scale,
            "cpu": cpu,
            "memory_mb": memory_mb,
        }
    }
    if listener_id:
        source_config["listener_id"] = listener_id

    return {
        "source_config": source_config,
        "source_revision_config": {"image_uri": image_uri},
    }


def source_for_target(target: str) -> str:
    """Return the control plane ``source`` this hosting model requires."""
    if target == TARGET_SAAS:
        return "github"
    if target == TARGET_SELF_HOSTED:
        return "external_docker"
    raise ControlPlaneError(f"Unknown target {target!r}; expected one of {TARGETS}.")


def resolve_host(target: str, *, host: Optional[str], region: str) -> str:
    """Pick the control plane host for a target.

    An explicit host always wins. SaaS falls back to the region's Cloud host;
    self-hosted has no default, since only you know your instance's URL.
    """
    if host:
        return host
    if target == TARGET_SAAS:
        try:
            return SAAS_CONTROL_PLANE_HOSTS[region]
        except KeyError:
            raise ControlPlaneError(
                f"Unknown region {region!r}; expected one of "
                f"{', '.join(sorted(SAAS_CONTROL_PLANE_HOSTS))}."
            ) from None
    raise ControlPlaneError(
        "Self-hosted deployments need an explicit control plane host. Set "
        "CONTROL_PLANE_HOST (or --control-plane-host) to https://<your-langsmith-host>/api-host."
    )


def write_github_output(**values: str) -> None:
    """Expose values to later workflow steps via ``$GITHUB_OUTPUT``."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            if value:
                handle.write(f"{key}={value}\n")


def print_deployment(deployment: Dict[str, Any], *, prefix: str = "") -> None:
    """Print the non-sensitive parts of a deployment resource."""
    url = deployment.get("url") or "(not provisioned yet)"
    print(f"{prefix}📦 Deployment ID: {deployment.get('id')}")
    print(f"{prefix}🔗 URL: {url}")
    print(f"{prefix}📊 Status: {deployment.get('status', 'UNKNOWN')}")
    secret_names = [s.get("name") for s in deployment.get("secrets") or []]
    if secret_names:
        # Names only -- values must never reach CI logs.
        print(
            f"{prefix}🔐 Secrets set: {', '.join(sorted(filter(None, secret_names)))}"
        )


def die(message: str) -> "None":
    print(f"❌ {message}", file=sys.stderr)
    sys.exit(1)
