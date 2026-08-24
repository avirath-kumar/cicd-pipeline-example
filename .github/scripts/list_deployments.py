#!/usr/bin/env python3
"""List the deployments in a workspace. Handy for verifying CI credentials."""

from __future__ import annotations

import argparse
import os
import sys
from typing import List

from control_plane import (
    TARGETS,
    ControlPlaneClient,
    ControlPlaneError,
    die,
    resolve_host,
)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default=os.environ.get("LANGSMITH_DEPLOYMENT_TARGET", "saas"),
    )
    parser.add_argument(
        "--control-plane-host", default=os.environ.get("CONTROL_PLANE_HOST")
    )
    parser.add_argument("--region", default=os.environ.get("LANGSMITH_REGION", "us"))
    parser.add_argument("--allow-insecure-host", action="store_true")
    parser.add_argument("--name-contains", default=None)
    args = parser.parse_args(argv)

    try:
        client = ControlPlaneClient(
            resolve_host(args.target, host=args.control_plane_host, region=args.region),
            os.environ.get("LANGSMITH_API_KEY", ""),
            os.environ.get("LANGSMITH_WORKSPACE_ID", ""),
            allow_insecure=args.allow_insecure_host,
        )
        deployments = client.list_deployments(
            name_contains=args.name_contains, limit=100
        )
    except (ControlPlaneError, ValueError) as exc:
        die(str(exc))

    print(f"📋 {len(deployments)} deployment(s) at {client.host}:\n")
    for deployment in deployments:
        print(f"🔗 {deployment.get('name')}")
        print(f"   ID:      {deployment.get('id')}")
        print(f"   Status:  {deployment.get('status')}")
        print(f"   Source:  {deployment.get('source')}")
        print(f"   URL:     {deployment.get('url') or '-'}")
        print(f"   Created: {deployment.get('created_at')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
