#!/usr/bin/env python3
"""Install AI logging support for Antigravity IDE and git push submission."""
from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent
from typing import Dict


def load_env(env_path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_pre_push_hook(repo_root: Path) -> None:
    hook_dir = repo_root / ".git" / "hooks"
    ensure_dir(hook_dir)
    hook_file = hook_dir / "pre-push"
    hook_text = dedent(
        """\
        #!/usr/bin/env bash
        # Pre-push: sweep recent Antigravity / Gemini prompts, then submit AI logs.
        bash scripts/_pyrun.sh scripts/log_antigravity.py --auto || true
        bash scripts/_pyrun.sh scripts/submit_log.py || true
        exit 0
        """
    )
    hook_file.write_text(hook_text, encoding="utf-8")
    try:
        hook_file.chmod(0o755)
    except OSError:
        pass
    print(f"[ai-log] Installed git pre-push hook: {hook_file}")


def cleanup_copilot_hook_config(repo_root: Path) -> None:
    copilot_file = repo_root / ".github" / "hooks" / "hooks.json"
    if copilot_file.exists():
        try:
            copilot_file.unlink()
            print(f"[ai-log] Removed legacy Copilot hook config: {copilot_file}")
            hooks_dir = copilot_file.parent
            if hooks_dir.exists() and not any(hooks_dir.iterdir()):
                hooks_dir.rmdir()
        except OSError:
            pass


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / ".env"
    env = load_env(env_path)
    if not env:
        print("[ai-log] Warning: .env file not found or empty. Create .env from .env.example and set AI_LOG_SERVER.")
    if not env.get("AI_LOG_SERVER"):
        print("[ai-log] Warning: AI_LOG_SERVER is not set in .env. The submit step will be skipped until this is configured.")
    log_dir = repo_root / env.get("AI_LOG_DIR", ".ai-log")
    ensure_dir(log_dir)
    keep_path = log_dir / ".gitkeep"
    if not keep_path.exists():
        keep_path.write_text("", encoding="utf-8")
    print(f"[ai-log] Ensured AI log directory exists: {log_dir}")
    cleanup_copilot_hook_config(repo_root)
    write_pre_push_hook(repo_root)
    print("[ai-log] Antigravity AI log setup complete. Use 'git push' to sweep and submit logs, or run 'python scripts/submit_log.py' manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

