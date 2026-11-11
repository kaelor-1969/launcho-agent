"""Run the widget host and agent against the local Launcho API."""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import dotenv_values
import httpx


ROOT = Path(__file__).resolve().parents[1]
AGENT_URL = "http://127.0.0.1:8000"
HOST_URL = "http://127.0.0.1:8001"
PRICE_QUESTION = "هزینه برام زیاده، چه گزینه‌ای دارم؟"
DEMO_OFFER = "پیشنهاد آزمایشی"


def launch_server(module, port, env):
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
    )


def wait_for_server(client, url, process):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited during startup: {url}")
        try:
            response = client.get(url, timeout=1)
            response.raise_for_status()
            return response
        except httpx.TransportError:
            time.sleep(0.2)
    raise RuntimeError(f"Server did not become reachable: {url}")


def chat(client, session, message, request_id=None):
    response = client.post(
        f"{AGENT_URL}/api/chat",
        headers={"X-Session-Token": session["sessionToken"]},
        json={"sessionId": session["sessionId"], "message": message, "requestId": request_id or str(uuid4())},
    )
    response.raise_for_status()
    reply = response.json().get("reply")
    if not isinstance(reply, str) or not reply.strip():
        raise RuntimeError("The chat endpoint returned an empty reply.")
    return reply


def check_demo(client, host):
    if f'{AGENT_URL}/widget/loader.js' not in host.text:
        raise RuntimeError("The demo host did not reference the widget loader.")
    client.get(f"{AGENT_URL}/widget/loader.js").raise_for_status()
    client.get(f"{AGENT_URL}/widget/widget.html").raise_for_status()
    response = client.post(f"{AGENT_URL}/api/sessions", json={})
    response.raise_for_status()
    session = response.json()
    if session.get("adapterMode") != "local_mock" or session.get("canCreateDraft") is not False:
        raise RuntimeError("The agent session did not use the read-only local mock.")
    request_id = str(uuid4())
    first = chat(client, session, PRICE_QUESTION, request_id)
    retry = chat(client, session, PRICE_QUESTION, request_id)
    later = chat(client, session, PRICE_QUESTION)
    if DEMO_OFFER not in first or "https://launcho.ir/pricing" not in first:
        raise RuntimeError("The first price answer did not show the labeled mock offer and official link.")
    if retry != first or DEMO_OFFER in later:
        raise RuntimeError("Chat retry or offer repetition behaved unexpectedly.")
    print("PASS: widget assets, read-only mock, labeled offer, and retry")
    return session


def run_demo(args):
    env = dict(os.environ)
    if args.env_file is not None:
        if not args.env_file.is_file():
            raise RuntimeError("The specified private environment file does not exist.")
        env.update({
            key: value for key, value in dotenv_values(args.env_file).items()
            if key.startswith("AI_") and value is not None
        })
        if not all(env.get(key, "").strip() for key in ("AI_API_KEY", "AI_MODEL_NAME")):
            raise RuntimeError("Configure AI_API_KEY and AI_MODEL_NAME for the model check.")
    else:
        env.update(AI_API_KEY="demo-check", AI_MODEL_NAME="demo-check", AI_BASE_URL="https://example.invalid/v1")
    env.update(LAUNCHO_MOCK_URL=HOST_URL, LAUNCHO_API_KEY=" ", LAUNCHO_API_URL=" ")

    for url in (AGENT_URL, HOST_URL):
        port = urlsplit(url).port
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))

    with TemporaryDirectory(prefix="launcho-demo-") as temp, httpx.Client(timeout=40, trust_env=False) as client:
        env["LAUNCHO_SESSION_DB"] = str(Path(temp) / "sessions.sqlite3")
        servers = []
        try:
            servers.append(launch_server("app.mock_launcho:app", 8001, env))
            host = wait_for_server(client, HOST_URL, servers[0])
            servers.append(launch_server("app.main:app", 8000, env))
            wait_for_server(client, AGENT_URL, servers[1])
            session = check_demo(client, host)
            if args.env_file is not None:
                reply = chat(client, session, "برای فروشگاه کیف و کفش از کجا شروع کنم؟")
                print(f"Live model reply ({len(reply)} characters). Review its content in the widget.")
            if args.keep_open:
                input(f"Open {HOST_URL} on your browser. Press Enter here to stop both servers. ")
        finally:
            for process in reversed(servers):
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Use private model settings and check a real model response.")
    parser.add_argument("--keep-open", action="store_true", help="Keep the local demo running for browser checks.")
    try:
        run_demo(parser.parse_args())
    except (RuntimeError, OSError, httpx.HTTPError) as error:
        sys.exit(f"Demo check failed: {error}")
