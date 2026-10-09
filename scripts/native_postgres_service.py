"""Manage only a disposable PostgreSQL 16 cluster on a standard hosted Linux runner."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

BIN = Path("/usr/lib/postgresql/16/bin")
TEMP = Path("/home/runner/work/_temp")
PASSWORD = "ci_fixture_only"


def cluster_root(env: dict[str, str]) -> Path:
    if (env.get("GITHUB_ACTIONS") != "true"
            or env.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or env.get("RUNNER_OS") != "Linux"
            or env.get("GITHUB_REPOSITORY") != "ericson-j-santos/e2e-platform"
            or env.get("TODO_NATIVE_E2E_DISPOSABLE") != "1"):
        raise ValueError("only the authorized disposable hosted runner is allowed")
    run_id, attempt = env.get("GITHUB_RUN_ID", ""), env.get("GITHUB_RUN_ATTEMPT", "")
    if not re.fullmatch(r"[1-9][0-9]*", run_id) or not re.fullmatch(r"[1-9][0-9]*", attempt):
        raise ValueError("invalid run identity")
    if Path(env.get("RUNNER_TEMP", "")) != TEMP:
        raise ValueError("unexpected runner temporary directory")
    return TEMP / f"todo-native-{run_id}-{attempt}"


def call(binary: str, args: list[str], *, env: dict[str, str] | None = None) -> None:
    if binary not in {"initdb", "pg_ctl", "createdb"}:
        raise ValueError("binary not allowed")
    subprocess.run([str(BIN / binary), *args], check=True, timeout=40,
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def manage(action: str) -> None:
    env = dict(os.environ)
    root = cluster_root(env)
    if os.geteuid() == 0 or root.is_symlink():
        raise ValueError("privileged execution or symlink refused")
    if any(not (BIN / name).is_file() for name in ("initdb", "pg_ctl", "createdb", "postgres")):
        raise ValueError("native PostgreSQL 16 is not installed")
    data, marker = root / "data", root / "owner.json"
    identity = {"run_id": env["GITHUB_RUN_ID"], "attempt": env["GITHUB_RUN_ATTEMPT"]}
    if action == "start":
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 5432))
        root.mkdir(mode=0o700, exist_ok=False)
        marker.write_text(json.dumps(identity), encoding="utf-8")
        password_file = root / "password.fixture"
        fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(PASSWORD + "\n")
            call("initdb", ["-D", str(data), "-U", "todo_ci", "--auth-local=reject",
                           "--auth-host=scram-sha-256", "--pwfile=" + str(password_file)])
        finally:
            password_file.unlink(missing_ok=True)
        call("pg_ctl", ["-D", str(data), "-l", str(root / "postgres.log"),
                       "-o", f"-h 127.0.0.1 -p 5432 -k {root}", "-w", "-t", "20", "start"])
        call("createdb", ["-h", "127.0.0.1", "-p", "5432", "-U", "todo_ci", "todo_native_ci"],
             env={**env, "PGPASSWORD": PASSWORD, "PGCONNECT_TIMEOUT": "5"})
    else:
        if action == "stop" and not marker.exists():
            return
        if (data.is_symlink() or not marker.is_file()
                or json.loads(marker.read_text(encoding="utf-8")) != identity):
            raise ValueError("disposable cluster ownership not proved")
        if action == "stop" and not (data / "postmaster.pid").exists():
            return
        if action not in {"restart", "stop"}:
            raise ValueError("action not allowed")
        call("pg_ctl", ["-D", str(data), "-m", "fast", "-w", "-t", "20", action])
    print("DISPOSABLE_NATIVE_POSTGRES_" + action.upper())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "restart", "stop"))
    args = parser.parse_args()
    try:
        manage(args.action)
    except Exception as exc:
        print("NATIVE_POSTGRES_FAILED " + type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
