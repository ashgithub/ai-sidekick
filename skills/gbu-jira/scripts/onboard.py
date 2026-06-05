#!/usr/bin/env python3
"""Create or repair the gbu-jira skill's private config/.env file."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = SKILL_DIR / "config"
EXAMPLE_ENV_PATH = CONFIG_DIR / ".env.example"
ENV_PATH = CONFIG_DIR / ".env"
NETRC_PATH = Path.home() / ".netrc"
DEFAULT_JIRA_MACHINE = "gbujira.oraclecorp.com"

FIELD_HELP = {
    "JIRA_CONFIG": "Path to the existing Jira CLI config file.",
    "JIRA_API_TOKEN": "Current Jira PAT token. Used to update ~/.netrc and kept as a fallback.",
    "JIRA_PAT_EXPIRES_ON": "Jira PAT expiry date in YYYY-MM-DD format.",
}


def parse_env(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    order: list[str] = []
    if not path.exists():
        return values, order

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = unquote(value.strip())
        if not key:
            continue
        if key not in values:
            order.append(key)
        values[key] = value

    return values, order


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def quote_env_value(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def parse_jira_cli_config(raw_config: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in raw_config.splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"login", "server"}:
            values[key] = unquote(value.strip())
    return values


def machine_from_server(server: str) -> str:
    parsed = urlparse(server)
    return parsed.hostname or server.removeprefix("https://").removeprefix("http://")


def upsert_netrc_entry(existing: str, machine: str, login: str, password: str) -> str:
    lines = existing.splitlines()
    kept_blocks: list[list[str]] = []
    index = 0

    while index < len(lines):
        block = [lines[index]]
        stripped = lines[index].strip().split()
        index += 1
        while index < len(lines) and not lines[index].strip().startswith("machine "):
            block.append(lines[index])
            index += 1

        if len(stripped) >= 2 and stripped[0] == "machine" and stripped[1] == machine:
            continue
        kept_blocks.append(block)

    new_block = [
        f"machine {machine}",
        f"  login {login}",
        f"  password {password}",
    ]
    kept_blocks.append(new_block)

    return "\n".join("\n".join(block).rstrip() for block in kept_blocks if block) + "\n"


def write_netrc_entry(path: Path, machine: str, login: str, password: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(
        upsert_netrc_entry(existing, machine, login, password),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def sync_netrc(values: dict[str, str]) -> bool:
    token = values.get("JIRA_API_TOKEN", "")
    if not token:
        return False

    config_path = Path(
        os.path.expandvars(os.path.expanduser(values.get("JIRA_CONFIG", "")))
    )
    if not config_path.exists():
        raise RuntimeError(f"Cannot update {NETRC_PATH}: Jira config not found at {config_path}")

    jira_config = parse_jira_cli_config(config_path.read_text(encoding="utf-8"))
    login = jira_config.get("login")
    if not login:
        raise RuntimeError(f"Cannot update {NETRC_PATH}: login missing from {config_path}")

    machine = machine_from_server(jira_config.get("server", DEFAULT_JIRA_MACHINE))
    write_netrc_entry(NETRC_PATH, machine, login, token)
    return True


def can_prompt() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def prompt_for_value(key: str, current: str | None, default: str | None) -> str:
    if help_text := FIELD_HELP.get(key):
        print(f"\n{key}: {help_text}")

    fallback = current if current not in {None, ""} else default
    suffix = f" [{fallback}]" if fallback else ""
    answer = input(f"{key}{suffix}: ").strip()
    return answer or fallback or ""


def parse_overrides(raw_overrides: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in raw_overrides:
        if "=" not in item:
            raise ValueError(f"Expected --set KEY=VALUE, got: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Expected --set KEY=VALUE, got: {item}")
        overrides[key] = value.strip()
    return overrides


def write_env(values: dict[str, str], order: list[str]) -> None:
    lines = [
        "# Local config for the gbu-jira skill.",
        "# Generated by scripts/onboard.py. This file is ignored by Git.",
        "",
    ]
    for key in order:
        lines.append(f"{key}={quote_env_value(values.get(key, ''))}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(ENV_PATH, 0o600)


def build_config(repair: bool, overrides: dict[str, str]) -> tuple[dict[str, str], list[str], bool]:
    defaults, order = parse_env(EXAMPLE_ENV_PATH)
    existing, existing_order = parse_env(ENV_PATH)
    if not order:
        raise RuntimeError(f"No config keys found in {EXAMPLE_ENV_PATH}")

    for key in existing_order:
        if key not in order:
            order.append(key)
    for key in overrides:
        if key not in order:
            order.append(key)

    values = {**defaults, **existing, **overrides}
    if repair:
        prompt_keys = [key for key in order if key not in overrides]
    elif ENV_PATH.exists():
        prompt_keys = [key for key in order if not existing.get(key) and key not in overrides]
    else:
        prompt_keys = [key for key in order if key not in overrides]

    if not prompt_keys:
        return values, order, bool(overrides) or not ENV_PATH.exists()

    if not can_prompt():
        missing = ", ".join(prompt_keys)
        raise RuntimeError(
            f"Cannot prompt for config values in this shell. Edit {ENV_PATH} "
            f"or rerun this script in a terminal. Missing: {missing}"
        )

    print("GBU Jira skill onboarding")
    print(f"Config file: {ENV_PATH}")
    if repair:
        print("Repair mode: press Enter to keep each current/default value.")
    else:
        print("Press Enter to accept defaults from config/.env.example.")

    changed = False
    for key in prompt_keys:
        new_value = prompt_for_value(key, existing.get(key), defaults.get(key))
        if values.get(key) != new_value:
            changed = True
        values[key] = new_value

    return values, order, changed or not ENV_PATH.exists()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or repair config/.env for the gbu-jira skill."
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Prompt for every supported key instead of only missing keys.",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set or replace one config value without prompting. Can be repeated.",
    )
    args = parser.parse_args()

    try:
        values, order, should_write = build_config(
            repair=args.repair,
            overrides=parse_overrides(args.set),
        )
        if should_write:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            write_env(values, order)
            print(f"Wrote {ENV_PATH}")
        else:
            print(f"{ENV_PATH} already exists and has all supported keys.")
        if sync_netrc(values):
            print(f"Updated {NETRC_PATH} for Jira CLI authentication.")
        return 0
    except KeyboardInterrupt:
        print("\nOnboarding cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
