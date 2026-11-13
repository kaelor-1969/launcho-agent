"""Run the widget host and agent against the local Launcho API."""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import threading
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
    if session.get("adapterMode") != "local_mock" or session.get("canCreateDraft") is not True:
        raise RuntimeError("The agent session did not enable local mock drafts.")
    request_id = str(uuid4())
    first = chat(client, session, PRICE_QUESTION, request_id)
    retry = chat(client, session, PRICE_QUESTION, request_id)
    later = chat(client, session, PRICE_QUESTION)
    if DEMO_OFFER not in first or "https://launcho.ir/pricing" not in first:
        raise RuntimeError("The first price answer did not show the labeled mock offer and official link.")
    if retry != first or DEMO_OFFER in later:
        raise RuntimeError("Chat retry or offer repetition behaved unexpectedly.")
    print("PASS: widget assets, local mock drafts, labeled offer, and retry")
    return session


def run_demo(args):
    global AGENT_URL, HOST_URL
    if args.agent_port == args.mock_port or not all(1 <= p <= 65535 for p in (args.agent_port, args.mock_port)):
        raise RuntimeError('Choose distinct agent/mock ports between 1 and 65535.')
    AGENT_URL = f'http://127.0.0.1:{args.agent_port}'
    HOST_URL = f'http://127.0.0.1:{args.mock_port}'
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
        env.update(AI_API_KEY=" ", AI_MODEL_NAME=" ", AI_BASE_URL="https://example.invalid/v1")
    env.update(LAUNCHO_MOCK_URL=HOST_URL, LAUNCHO_API_KEY=" ", LAUNCHO_API_URL=" ")
    env.update(LAUNCHO_ENV='development', LAUNCHO_WIDGET_ORIGIN=AGENT_URL,
               LAUNCHO_FRAME_ANCESTORS=HOST_URL, LAUNCHO_CORS_ORIGINS=HOST_URL)

    for url in (AGENT_URL, HOST_URL):
        port = urlsplit(url).port
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise RuntimeError(f'Port {port} is unavailable. Choose --agent-port and --mock-port; existing services were not stopped.') from None

    with TemporaryDirectory(prefix="launcho-demo-") as temp, httpx.Client(timeout=40, trust_env=False) as client:
        env["LAUNCHO_SESSION_DB"] = str(Path(temp) / "sessions.sqlite3")
        env["LAUNCHO_MOCK_DRAFT_DB"] = str(Path(temp) / "drafts.sqlite3")
        servers = []
        try:
            servers.append(launch_server("app.mock_launcho:app", args.mock_port, env))
            host = wait_for_server(client, HOST_URL, servers[0])
            servers.append(launch_server("app.main:app", args.agent_port, env))
            wait_for_server(client, AGENT_URL, servers[1])
            session = check_demo(client, host)
            if args.check_core:
                subprocess.run([sys.executable, str(ROOT / 'tests' / 'check_backend_http.py'),
                                '--url', AGENT_URL], cwd=ROOT, check=True)
            if args.env_file is not None:
                # Signup starters can succeed locally even when the model is unavailable.
                reply = chat(client, session, "آیا امکان مهاجرت اطلاعات از سرویس فعلی را دارم؟")
                print(f"Live model reply ({len(reply)} characters). Review its content in the widget.")
            if args.serve:
                print(f"Main widget: {AGENT_URL}/widget/widget.html (Ctrl+C to stop)", flush=True)
                threading.Event().wait()
            elif args.keep_open:
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
    parser.add_argument('--agent-port', type=int, default=8000)
    parser.add_argument('--mock-port', type=int, default=8001)
    parser.add_argument('--check-core', action='store_true', help='Check both core signup flows over HTTP while services are running.')
    parser.add_argument("--env-file", type=Path, help="Use private model settings and check a real model response.")
    parser.add_argument("--keep-open", action="store_true", help="Keep the local demo running for browser checks.")
    parser.add_argument("--serve", action="store_true", help="Keep both services running without requiring stdin; Ctrl+C stops them.")
    try:
        run_demo(parser.parse_args())
    except KeyboardInterrupt:
        pass
    except (RuntimeError, OSError, EOFError, httpx.HTTPError) as error:
        sys.exit(f"Demo check failed: {error}")
