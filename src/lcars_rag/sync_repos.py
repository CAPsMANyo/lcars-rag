"""Git repository synchronization from config.yml."""

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from lcars_rag.config import REPOS_DIR


def _ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


ICONS = {
    "INFO": "   ",
    "CLONE": "++ ",
    "UPDATE": "~~ ",
    "OK": "== ",
    "REMOVE": "-- ",
    "ERROR": "!! ",
    "WARN": "?? ",
    "DONE": "** ",
}


def log(msg, level="INFO"):
    icon = ICONS.get(level, "   ")
    print(f"[{_ts()}] {icon}{msg}", flush=True)


def run_command(command, cwd=None, env=None):
    """Run a shell command. Returns True on success, False on failure."""
    try:
        subprocess.run(command, cwd=cwd, check=True, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        return True
    except subprocess.CalledProcessError as e:
        # Strip token from logged command
        safe_cmd = ' '.join(command).replace(env.get("GITHUB_PERSONAL_ACCESS_TOKEN", "NONE"), "***") if env else ' '.join(command)
        log(f"  {safe_cmd}\n           {e.stderr.strip()}", "ERROR")
        return False
    except FileNotFoundError:
        log("git not found in PATH", "ERROR")
        return False


def get_command_output(command, cwd=None, env=None):
    """Run a command and return its stdout."""
    try:
        result = subprocess.run(
            command, cwd=cwd, check=True, text=True,
            capture_output=True, env=env,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        safe_cmd = ' '.join(command).replace(env.get("GITHUB_PERSONAL_ACCESS_TOKEN", "NONE"), "***") if env else ' '.join(command)
        log(f"  {safe_cmd}\n           {e.stderr.strip()}", "ERROR")
        return None
    except FileNotFoundError:
        log("git not found in PATH", "ERROR")
        sys.exit(1)


def is_ssh_url(url):
    """Check if the URL is an SSH Git URL."""
    return url.startswith("git@") or url.startswith("ssh://")


def get_git_env():
    """Get environment variables for Git operations."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def main():
    load_dotenv()
    log("Sync started", "INFO")

    config_file = "config.yml"
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        log(f"{config_file} not found", "ERROR")
        sys.exit(1)
    except yaml.YAMLError as e:
        log(f"Error parsing {config_file}: {e}", "ERROR")
        sys.exit(1)

    base_dir = Path(REPOS_DIR)
    sources = config.get("git_sources", [])
    git_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    base_dir.mkdir(parents=True, exist_ok=True)
    git_env = get_git_env()

    synced = 0
    skipped = 0
    cloned = 0
    failed = 0

    for repo in sources:
        repo_name = repo.get("name")
        repo_url = repo.get("url")

        if not repo_name or not repo_url:
            log(f"Skipping invalid entry: {repo}", "WARN")
            continue

        branch = repo.get("branch", "main")
        repo_dir = base_dir / repo_name

        use_ssh = is_ssh_url(repo_url)
        if use_ssh:
            authenticated_url = repo_url
        elif git_token:
            authenticated_url = repo_url.replace("https://", f"https://{git_token}@")
        else:
            authenticated_url = repo_url

        if repo_dir.is_dir():
            remote_commit_output = get_command_output(
                ["git", "ls-remote", authenticated_url, branch],
                env=git_env,
            )

            if not remote_commit_output:
                remote_commit = None
            else:
                remote_commit = remote_commit_output.split()[0]

            local_commit = get_command_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, env=git_env)

            if remote_commit and local_commit and remote_commit == local_commit:
                log(f"{repo_name}  ({local_commit[:7]})", "OK")
                skipped += 1
                continue

            log(f"{repo_name}  {(local_commit or '?')[:7]} -> {(remote_commit or '?')[:7]}", "UPDATE")
            if not run_command(["git", "fetch", "--depth=1", authenticated_url, branch], cwd=repo_dir, env=git_env):
                failed += 1
                continue
            if not run_command(["git", "reset", "--hard", "FETCH_HEAD"], cwd=repo_dir, env=git_env):
                failed += 1
                continue
            synced += 1
        else:
            log(f"{repo_name}  branch:{branch}", "CLONE")
            if not run_command([
                "git", "clone", "--depth=1", "-b", branch,
                authenticated_url, str(repo_dir),
            ], env=git_env):
                failed += 1
                continue
            cloned += 1

    # Clean up repo dirs not in current config.yml
    expected_names = {repo.get("name") for repo in sources if repo.get("name")}
    removed = 0
    for entry in base_dir.iterdir():
        if entry.is_dir() and entry.name not in expected_names:
            log(f"{entry.name}", "REMOVE")
            shutil.rmtree(entry)
            removed += 1

    # Validate local_sources paths (no cloning — just existence check so operators
    # catch typos/missing mounts before the CocoIndex run silently skips them).
    local_sources = config.get("local_sources", []) or []
    local_ok = 0
    local_missing = 0
    for local in local_sources:
        name = local.get("name")
        path = local.get("path")
        if not name or not path:
            log(f"Skipping invalid local entry: {local}", "WARN")
            local_missing += 1
            continue
        if Path(path).is_dir():
            log(f"{name}  {path}", "LOCAL")
            local_ok += 1
        else:
            log(f"{name}  path missing or not a directory: {path}", "WARN")
            local_missing += 1

    log(
        f"Done: {len(sources)} git + {len(local_sources)} local | "
        f"{skipped} ok | {synced} updated | {cloned} cloned | {removed} removed | "
        f"{failed} failed | local: {local_ok} ok, {local_missing} missing",
        "DONE",
    )


if __name__ == "__main__":
    main()
