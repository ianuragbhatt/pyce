"""Auto-configure MCP for Claude Code, GitHub Copilot, and Opencode."""

from __future__ import annotations

import json
from pathlib import Path


def configure_editors(project_root: Path) -> list[str]:
    configured: list[str] = []

    if _configure_claude_code(project_root):
        configured.append("Claude Code")
    if _configure_copilot(project_root):
        configured.append("GitHub Copilot")
    if _configure_opencode(project_root):
        configured.append("Opencode")

    return configured


def _configure_claude_code(project_root: Path) -> bool:
    config_path = project_root / ".mcp.json"
    config = {"mcpServers": {"pyce": {"command": "pyce", "args": ["serve"]}}}
    try:
        if config_path.exists():
            with open(config_path) as f:
                existing = json.load(f)
            existing.setdefault("mcpServers", {})["pyce"] = config["mcpServers"]["pyce"]
            config = existing
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError:
        return False


def _configure_copilot(project_root: Path) -> bool:
    vscode_dir = project_root / ".vscode"
    config_path = vscode_dir / "mcp.json"
    config = {"servers": {"pyce": {"command": "pyce", "args": ["serve"]}}}
    try:
        vscode_dir.mkdir(exist_ok=True)
        if config_path.exists():
            with open(config_path) as f:
                existing = json.load(f)
            existing.setdefault("servers", {})["pyce"] = config["servers"]["pyce"]
            config = existing
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError:
        return False


def _configure_opencode(project_root: Path) -> bool:
    config_path = project_root / "opencode.json"
    config = {"mcpServers": {"pyce": {"command": "pyce", "args": ["serve"]}}}
    try:
        if config_path.exists():
            with open(config_path) as f:
                existing = json.load(f)
            existing.setdefault("mcpServers", {})["pyce"] = config["mcpServers"]["pyce"]
            config = existing
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError:
        return False
