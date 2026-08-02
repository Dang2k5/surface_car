#!/usr/bin/env python3
"""Install AI logging support for Copilot and git push submission."""
from __future__ import annotations

import json
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
        # Submit AI logs from .ai-log/session.jsonl before git push.
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


def ensure_copilot_hook_config(repo_root: Path) -> None:
    hooks_dir = repo_root / ".github" / "hooks"
    ensure_dir(hooks_dir)
    hooks_file = hooks_dir / "hooks.json"
    copilot_config = {
        "version": 1,
        "hooks": {
            "userPromptSubmitted": [
                {
                    "type": "command",
                    "bash": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=copilot",
                    "powershell": "scripts\\_pyrun.cmd scripts\\log_hook.py --tool=copilot",
                    "timeoutSec": 10,
                }
            ],
            "sessionEnd": [
                {
                    "type": "command",
                    "bash": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=copilot",
                    "powershell": "scripts\\_pyrun.cmd scripts\\log_hook.py --tool=copilot",
                    "timeoutSec": 10,
                }
            ],
        },
    }

    if hooks_file.exists():
        try:
            existing = json.loads(hooks_file.read_text(encoding="utf-8"))
            if existing.get("hooks", {}).get("userPromptSubmitted") and existing.get("hooks", {}).get("sessionEnd"):
                print(f"[ai-log] Copilot hook config already exists: {hooks_file}")
                return
        except json.JSONDecodeError:
            pass

    hooks_file.write_text(json.dumps(copilot_config, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ai-log] Created Copilot hook config: {hooks_file}")


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
    ensure_copilot_hook_config(repo_root)
    write_pre_push_hook(repo_root)
    print("[ai-log] Setup complete. Use 'git push' to submit logs, or run 'python scripts/submit_log.py' manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
