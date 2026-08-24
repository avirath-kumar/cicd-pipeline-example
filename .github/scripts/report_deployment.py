#!/usr/bin/env python3
"""Render a LangSmith Deployment status report for a PR comment.

The output of this script is posted verbatim as a public pull request comment,
so it deliberately reports only non-sensitive fields: status, URL, IDs and the
*names* of configured secrets. Secret values and request headers never appear.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from control_plane import (
    TARGETS,
    ControlPlaneClient,
    ControlPlaneError,
    die,
    resolve_host,
)

DEPLOYMENT_STATUS_EMOJI = {
    "AWAITING_DATABASE": "⏳",
    "READY": "✅",
    "UNUSED": "⏸️",
    "AWAITING_DELETE": "🗑️",
    "AWAITING_FINAL_DELETE": "🗑️",
    "UNKNOWN": "❓",
}

REVISION_STATUS_EMOJI = {
    "CREATING": "🔨",
    "QUEUED": "⏳",
    "AWAITING_BUILD": "⏳",
    "BUILDING": "🔨",
    "AWAITING_DEPLOY": "⏳",
    "DEPLOYING": "🚀",
    "CREATE_FAILED": "❌",
    "BUILD_FAILED": "❌",
    "DEPLOY_FAILED": "❌",
    "DEPLOYED": "✅",
    "SKIPPED": "⏭️",
    "INTERRUPTED": "⏸️",
    "UNKNOWN": "❓",
}

IN_PROGRESS_REVISION_STATUSES = (
    "BUILDING",
    "DEPLOYING",
    "QUEUED",
    "CREATING",
    "AWAITING_BUILD",
    "AWAITING_DEPLOY",
)


def format_timestamp(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def build_report(
    client: ControlPlaneClient,
    deployment_name: str,
    deployment_type: str,
    target: str,
) -> Dict[str, Any]:
    deployment = client.find_deployment(deployment_name)
    if not deployment:
        return {
            "deployment_name": deployment_name,
            "error": f"No deployment named `{deployment_name}` was found.",
        }

    revisions = client.list_revisions(deployment["id"])
    latest = revisions[0] if revisions else {}
    revision_status = latest.get("status", "UNKNOWN")
    status = deployment.get("status", "UNKNOWN")
    revision_config = deployment.get("source_revision_config") or {}

    return {
        "deployment_name": deployment_name,
        "deployment_id": deployment.get("id"),
        "deployment_type": deployment_type,
        "target": target,
        "status": status,
        "status_emoji": DEPLOYMENT_STATUS_EMOJI.get(status, "❓"),
        "url": deployment.get("url"),
        "source": deployment.get("source"),
        "image_uri": revision_config.get("image_uri"),
        "repo_ref": revision_config.get("repo_ref"),
        "created_at": format_timestamp(deployment.get("created_at")),
        "updated_at": format_timestamp(deployment.get("updated_at")),
        "revision_id": latest.get("id"),
        "revision_status": revision_status,
        "revision_status_emoji": REVISION_STATUS_EMOJI.get(revision_status, "❓"),
        "revision_status_message": latest.get("status_message"),
        # Names only -- values must never reach a public comment.
        "secret_names": sorted(
            name
            for name in (s.get("name") for s in deployment.get("secrets") or [])
            if name
        ),
    }


def write_markdown_report(report: Dict[str, Any], output_file: str) -> None:
    lines: List[str] = ["# 🚀 LangSmith Deployment status", ""]

    if "error" in report:
        lines += ["### ❌ Deployment not found", "", report["error"], ""]
        _write(output_file, lines)
        return

    heading = report["deployment_type"].title()
    lines += [
        f"### {report['status_emoji']} {heading} deployment: `{report['deployment_name']}`",
        "",
        "| Property | Value |",
        "|----------|-------|",
        f"| **Hosting** | {report['target']} |",
        f"| **Status** | {report['status_emoji']} {report['status']} |",
    ]

    if report.get("url"):
        lines.append(f"| **URL** | [{report['url']}]({report['url']}) |")
    else:
        lines.append("| **URL** | _not provisioned yet_ |")

    lines.append(f"| **Deployment ID** | `{report['deployment_id']}` |")
    lines.append(f"| **Source** | `{report.get('source') or 'unknown'}` |")

    if report.get("image_uri"):
        lines.append(f"| **Image** | `{report['image_uri']}` |")
    if report.get("repo_ref"):
        lines.append(f"| **Git ref** | `{report['repo_ref']}` |")
    if report.get("created_at"):
        lines.append(f"| **Created** | {report['created_at']} |")
    if report.get("updated_at"):
        lines.append(f"| **Updated** | {report['updated_at']} |")

    lines.append(
        f"| **Revision** | {report['revision_status_emoji']} {report['revision_status']} |"
    )
    if report.get("secret_names"):
        lines.append(
            f"| **Secrets configured** | {', '.join(report['secret_names'])} |"
        )

    lines.append("")

    revision_status = report["revision_status"]
    if report["status"] == "READY" and revision_status == "DEPLOYED":
        lines += ["🎉 **Deployment is ready and accessible.**", ""]
    elif "FAILED" in revision_status:
        detail = report.get("revision_status_message") or "Check the deployment logs."
        lines += [f"❌ **Deployment failed.** {detail}", ""]
    elif revision_status in IN_PROGRESS_REVISION_STATUSES:
        lines += ["🚀 **Deployment is in progress...**", ""]
    elif report["status"] == "AWAITING_DATABASE":
        lines += ["⏳ **Deployment is being set up...**", ""]

    lines += [
        "---",
        f"_Report generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}_",
    ]
    _write(output_file, lines)


def _write(output_file: str, lines: List[str]) -> None:
    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"✅ Wrote deployment report to {output_file}")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment-name", required=True)
    parser.add_argument(
        "--deployment-type", choices=["preview", "production"], default="preview"
    )
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
    parser.add_argument("--output", "-o", default="deployment_comment.md")
    args = parser.parse_args(argv)

    try:
        client = ControlPlaneClient(
            resolve_host(args.target, host=args.control_plane_host, region=args.region),
            os.environ.get("LANGSMITH_API_KEY", ""),
            os.environ.get("LANGSMITH_WORKSPACE_ID", ""),
            allow_insecure=args.allow_insecure_host,
        )
        report = build_report(
            client, args.deployment_name, args.deployment_type, args.target
        )
    except (ControlPlaneError, ValueError) as exc:
        die(str(exc))

    write_markdown_report(report, args.output)
    if "error" in report:
        print(f"❌ {report['error']}", file=sys.stderr)
        return 1
    print(f"📊 Status: {report['status']} • revision {report['revision_status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
