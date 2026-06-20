#!/usr/bin/env python3
"""Barebones standalone OCI list_models diagnostic client."""

from __future__ import annotations

import sys
from typing import Any

from ai_tools.oci_model_catalog_client import ModelCatalogClientError, list_active_models
from ai_tools.utils.config import get_settings


def _print_api_error(exc: ModelCatalogClientError, profile: str, compartment_id: str, endpoint: str) -> None:
    print("OCI list_models failed", file=sys.stderr)
    print(f"profile={profile}", file=sys.stderr)
    print(f"compartment_id={compartment_id}", file=sys.stderr)
    print(f"endpoint={endpoint}", file=sys.stderr)

    details: dict[str, Any] = exc.details if getattr(exc, "details", None) else {}

    status = details.get("status", "n/a")
    code = details.get("code", "n/a")
    message = details.get("message", str(exc))
    operation_name = details.get("operation_name", "list_models")
    request_endpoint = details.get("request_endpoint", "n/a")
    opc_request_id = details.get("opc_request_id", details.get("opc-request-id", "n/a"))
    timestamp = details.get("timestamp", "n/a")
    client_version = details.get("client_version", "n/a")

    print("--- error details ---", file=sys.stderr)
    print(f"status={status}", file=sys.stderr)
    print(f"code={code}", file=sys.stderr)
    print(f"message={message}", file=sys.stderr)
    print(f"operation_name={operation_name}", file=sys.stderr)
    print(f"request_endpoint={request_endpoint}", file=sys.stderr)
    print(f"opc-request-id={opc_request_id}", file=sys.stderr)
    print(f"timestamp={timestamp}", file=sys.stderr)
    print(f"client_version={client_version}", file=sys.stderr)


def main() -> int:
    try:
        settings = get_settings()
        profile = settings.oci.profile
        compartment_id = settings.oci.compartment
        endpoint = settings.oci.service_endpoint
    except Exception as exc:
        print(f"Config load error: {exc}", file=sys.stderr)
        return 2

    try:
        items = list_active_models(settings)
    except ModelCatalogClientError as exc:
        _print_api_error(exc, profile=profile, compartment_id=compartment_id, endpoint=endpoint)
        return 22
    except Exception as exc:
        print(f"OCI client bootstrap error: {exc}", file=sys.stderr)
        return 2

    print("OCI list_models success")
    print(f"profile={profile}")
    print(f"endpoint={endpoint}")
    print(f"compartment_id={compartment_id}")
    print(f"model_count={len(items)}")
    for model in items:
        model_id = model.get("id", "")
        display_name = model.get("display_name", "") or model_id
        vendor = model.get("vendor", "n/a")
        lifecycle_state = model.get("lifecycle_state", "n/a")
        print(f"{model_id} | {display_name} | {vendor} | {lifecycle_state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
