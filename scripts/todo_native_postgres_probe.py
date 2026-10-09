"""Exercise the immutable TODO gateway against disposable PostgreSQL, never Notion."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit

SOURCE_SHA = "28fc1eb58b6c8163e8c4fa63a6bb0adbd1376f59"
DATABASE = "todo_native_ci"
PORT = 18080


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def guarded_dsn(env: dict[str, str]) -> str:
    require(env.get("TODO_NATIVE_E2E_DISPOSABLE") == "1", "disposable opt-in required")
    dsn = env.get("TODO_NATIVE_E2E_DSN", "")
    try:
        p = urlsplit(dsn)
        valid = (p.scheme == "postgresql" and p.hostname == "127.0.0.1"
                 and p.port == 5432 and p.path == "/" + DATABASE
                 and p.username == "todo_ci" and bool(p.password)
                 and not p.query and not p.fragment
                 and not any(c.isspace() or ord(c) < 32 for c in dsn))
    except ValueError:
        valid = False
    require(valid, "only the fixed disposable loopback database is allowed")
    return dsn


def git_sha(root: Path) -> str:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            check=True, text=True, capture_output=True, timeout=10)
    return result.stdout.strip()


def connect(dsn: str):
    import psycopg
    return psycopg.connect(dsn, connect_timeout=3,
                           options="-c statement_timeout=5000 -c lock_timeout=3000")


def db_snapshot(dsn: str) -> dict:
    with connect(dsn) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        database, started = conn.execute(
            "SELECT current_database(), pg_postmaster_start_time()").fetchone()
        require(database == DATABASE, "database identity mismatch")
        rows = conn.execute(
            "SELECT event_id, idempotency_key, payload->'todo'->>'status', "
            "state, attempts FROM todo_bus.queue_events ORDER BY event_id").fetchall()
    return {"started": started.isoformat(), "rows": [list(row) for row in rows]}


def check_rows(snapshot: dict, expected: list[list]) -> None:
    require(snapshot["rows"] == sorted(expected), "independent database readback mismatch")


@contextlib.contextmanager
def gateway(source: Path, dsn: str):
    import httpx
    token = secrets.token_urlsafe(32)
    env = {k: v for k, v in os.environ.items() if not k.startswith("NOTION_")}
    env.update(DATABASE_URL=dsn, TODO_GATEWAY_TOKEN=token, PORT=str(PORT),
               PYTHONDONTWRITEBYTECODE="1")
    with socket.socket() as s:
        s.bind(("127.0.0.1", PORT))
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "services.todo_gateway.service_main"],
            cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=5,
                              trust_env=False) as client:
                deadline = time.monotonic() + 35
                while True:
                    require(process.poll() is None, "gateway exited before readiness")
                    try:
                        if client.get("/readyz").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    require(time.monotonic() < deadline, "gateway readiness timeout")
                    time.sleep(0.25)
                yield client, {"Authorization": "Bearer " + token}, process.pid
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)


def event(key: str, status: str, correlation: str) -> dict:
    todo = {"title": "Disposable native TODO validation", "type": "Validação",
            "status": status, "next_action": "read back the fixture"}
    if status == "BLOQUEADO":
        todo["blocker"] = "Controlled validation fixture"
    return {"schema_version": "1.0", "event_id": "evt-" + secrets.token_hex(12),
            "event_type": "todo.updated",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation, "idempotency_key": key,
            "project": "Native TODO validation", "producer": "e2e-platform",
            "todo": todo}


def list_check(client, headers: dict, expected: dict[str, str]) -> None:
    response = client.get("/v1/todos", headers=headers)
    require(response.status_code == 200, "authenticated list failed")
    body = response.json()
    actual = {item["idempotency_key"]: item["todo"]["status"]
              for item in body["items"]}
    require(body["count"] == len(expected) and actual == expected,
            "native TODO listing does not match persisted state")
    require(all(item["queue_state"] == "PENDING" and item["attempts"] == 0
                for item in body["items"]), "unexpected projection processing")


def run(source: Path, report: Path, phase: str) -> None:
    dsn = guarded_dsn(dict(os.environ))
    require(git_sha(source) == SOURCE_SHA, "immutable source SHA mismatch")
    harness_sha = git_sha(Path(__file__).resolve().parents[1])
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    require(bool(run_id), "GitHub run identity required")
    if phase == "exercise":
        require(not report.exists(), "evidence file already exists")
        with connect(dsn) as conn:
            database, namespace = conn.execute(
                "SELECT current_database(), to_regnamespace('todo_bus')").fetchone()
            require(database == DATABASE and namespace is None,
                    "refusing nonempty or unrelated database")
        correlation = "todo-native-" + secrets.token_hex(12)
        key = hashlib.sha256(correlation.encode()).hexdigest()
        other_key = hashlib.sha256((correlation + "-concurrent").encode()).hexdigest()
        first = event(key, "PENDENTE", correlation)
        expected_rows: list[list] = []
        with gateway(source, dsn) as (client, headers, first_pid):
            require(client.get("/v1/todos").status_code == 401, "read auth bypass")
            require(client.post("/v1/events", json=first).status_code == 401,
                    "write auth bypass")
            invalid = event(key, "CONCLUÍDO", correlation)
            require(client.post("/v1/events", json=invalid, headers=headers).status_code
                    == 422, "unsupported completion accepted")
            check_rows(db_snapshot(dsn), [])
            created = client.post("/v1/events", json=first, headers=headers)
            require(created.status_code == 202 and not created.json()["duplicate"],
                    "initial native event not accepted")
            expected_rows.append([first["event_id"], key, "PENDENTE", "PENDING", 0])
            check_rows(db_snapshot(dsn), expected_rows)
            replay = client.post("/v1/events", json=first, headers=headers)
            require(replay.status_code == 202 and replay.json()["duplicate"],
                    "event replay was not deduplicated")
            check_rows(db_snapshot(dsn), expected_rows)
            update = event(key, "BLOQUEADO", correlation)
            changed = client.post("/v1/events", json=update, headers=headers)
            require(changed.status_code == 202 and not changed.json()["duplicate"],
                    "native task update failed")
            expected_rows.append([update["event_id"], key, "BLOQUEADO", "PENDING", 0])
            list_check(client, headers, {key: "BLOQUEADO"})
            race = event(other_key, "PENDENTE", correlation)
            def send(_):
                response = client.post("/v1/events", json=race, headers=headers)
                require(response.status_code == 202, "concurrent event failed")
                return response.json()["duplicate"]
            with ThreadPoolExecutor(max_workers=4) as pool:
                duplicates = list(pool.map(send, range(4)))
            require(duplicates.count(False) == 1 and duplicates.count(True) == 3,
                    "concurrent replay was not idempotent")
            expected_rows.append([race["event_id"], other_key, "PENDENTE", "PENDING", 0])
            before = db_snapshot(dsn)
            check_rows(before, expected_rows)
        expected_todos = {key: "BLOQUEADO", other_key: "PENDENTE"}
        with gateway(source, dsn) as (client, headers, second_pid):
            require(second_pid != first_pid, "gateway was not restarted")
            list_check(client, headers, expected_todos)
            check_rows(db_snapshot(dsn), expected_rows)
        result = {"status": "AWAITING_DATABASE_RESTART", "source_sha": SOURCE_SHA,
                  "harness_sha": harness_sha, "run_id": run_id,
                  "correlation_id": correlation, "database_started": before["started"],
                  "expected_rows": expected_rows, "expected_todos": expected_todos,
                  "notion_configured": False, "projection_attempts": 0,
                  "cases": ["unauthorized_read", "unauthorized_write",
                            "invalid_completion", "native_write", "native_read",
                            "task_update", "replay", "concurrent_replay",
                            "independent_sql_readback", "gateway_restart"]}
    else:
        result = json.loads(report.read_text(encoding="utf-8"))
        require(result["status"] == "AWAITING_DATABASE_RESTART"
                and result["source_sha"] == SOURCE_SHA
                and result["harness_sha"] == harness_sha
                and result["run_id"] == run_id, "stale or unrelated evidence")
        deadline = time.monotonic() + 35
        while True:
            try:
                after = db_snapshot(dsn)
                break
            except Exception:
                require(time.monotonic() < deadline, "database restart timeout")
                time.sleep(0.25)
        require(after["started"] != result["database_started"],
                "database process was not restarted")
        check_rows(after, result["expected_rows"])
        with gateway(source, dsn) as (client, headers, _):
            list_check(client, headers, result["expected_todos"])
            check_rows(db_snapshot(dsn), result["expected_rows"])
        result["cases"].append("database_restart_and_http_readback")
        result["database_restarted"] = after["started"]
        result["status"] = "PASS"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"status": result["status"], "source_sha": SOURCE_SHA,
                      "harness_sha": harness_sha, "run_id": run_id,
                      "cases": result["cases"], "notion_configured": False,
                      "event_count": len(result["expected_rows"]),
                      "logical_task_count": len(result["expected_todos"])}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--phase", choices=("exercise", "readback"), required=True)
    args = parser.parse_args()
    try:
        run(args.source.resolve(), args.report.resolve(), args.phase)
    except Exception as error:
        # Only test-generated diagnostics reach logs; never echo a connection string.
        print("TODO_NATIVE_POSTGRES_FAILED " + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
