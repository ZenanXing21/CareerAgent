"""Deploy a new Career Agent release and switch Caddy after health checks.

Run interactively; the server password is read by getpass and never stored.
"""

from __future__ import annotations

import base64
import getpass
import json
from pathlib import Path
import shlex
import time
import urllib.request

import paramiko

ROOT = Path(__file__).resolve().parents[1]
HOST = "47.83.139.234"
DOMAIN = "www.zenanxing.cloud"
UPSTREAMS = ("127.0.0.1:8002", "127.0.0.1:18002")
RELEASE = time.strftime("%Y%m%d%H%M%S")
REMOTE = f"/opt/career-agent/releases/{RELEASE}"
IMAGE = f"career-agent:{RELEASE}"
CONTAINER = f"career-agent-{RELEASE}"
RESULT = ROOT / "tmp" / "deployment-result.txt"


def run(client: paramiko.SSHClient, command: str, timeout: int = 1200) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode("utf-8", "replace").strip()
    error = stderr.read().decode("utf-8", "replace").strip()
    if stdout.channel.recv_exit_status():
        raise RuntimeError(f"Remote command failed: {error[-1200:]}")
    return output


def main() -> None:
    bundle = ROOT / "tmp" / "career-agent-deploy.tar.gz"
    if not bundle.is_file():
        raise RuntimeError("Run python -m deploy.package first")
    RESULT.parent.mkdir(exist_ok=True)
    RESULT.write_text("RUNNING", encoding="utf-8")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(HOST, username="root", password=getpass.getpass("Server password: "), timeout=20)
    try:
        config = run(client, "cat /etc/caddy/Caddyfile")
        old_upstream = next((item for item in UPSTREAMS if config.count(item) == 2), None)
        if "handle_path /CareerAgent/*" not in config or old_upstream is None:
            raise RuntimeError("The live Caddy route differs from the expected version; no switch was made")
        new_upstream = next(item for item in UPSTREAMS if item != old_upstream)
        run(client, f"docker ps -q --filter publish={new_upstream.rsplit(':', 1)[1]} | xargs -r docker stop")
        run(client, f"install -d -m 700 {shlex.quote(REMOTE)}")
        with client.open_sftp() as sftp:
            sftp.put(str(bundle), f"{REMOTE}/bundle.tar.gz")
        run(client, f"cd {shlex.quote(REMOTE)} && tar -xzf bundle.tar.gz")
        print("Building new image; the current site stays online...", flush=True)
        run(client, f"cd {shlex.quote(REMOTE)} && docker build -q -t {IMAGE} -f deploy/Dockerfile .", timeout=2400)
        run(client, "test -f /opt/career-agent/shared/.env")
        run(client, f"docker run -d --name {CONTAINER} --restart unless-stopped "
            "--env-file /opt/career-agent/shared/.env "
            "-v /opt/career-agent/shared/data:/app/tmp "
            f"-p {new_upstream}:8000 {IMAGE}")
        for _ in range(30):
            try:
                status = json.loads(run(client, f"curl -fsS --max-time 5 http://{new_upstream}/api/status"))
                if status.get("ready"):
                    break
            except (RuntimeError, ValueError):
                pass
            time.sleep(2)
        else:
            raise RuntimeError("New container failed health check; current site was not changed")
        backup = f"/etc/caddy/Caddyfile.before-career-agent-{RELEASE}"
        run(client, f"cp /etc/caddy/Caddyfile {backup}")
        updated = config.replace(old_upstream, new_upstream)
        encoded = base64.b64encode(updated.encode()).decode()
        command = "import base64,pathlib; pathlib.Path('/etc/caddy/Caddyfile.pending').write_bytes(base64.b64decode('" + encoded + "'))"
        run(client, "python3 -c " + shlex.quote(command))
        run(client, "caddy validate --config /etc/caddy/Caddyfile.pending --adapter caddyfile")
        run(client, "mv /etc/caddy/Caddyfile.pending /etc/caddy/Caddyfile && systemctl reload caddy")
        try:
            for path in ("/CareerAgent", "/CareerAgent/static/app.js", "/CareerAgent/api/status"):
                with urllib.request.urlopen(f"https://{DOMAIN}{path}", timeout=20) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Public check failed: {path}")
        except Exception:
            run(client, f"cp {backup} /etc/caddy/Caddyfile && systemctl reload caddy")
            raise
        url = f"https://{DOMAIN}/CareerAgent"
        RESULT.write_text(f"SUCCESS {url} {RELEASE}", encoding="utf-8")
        print(f"Deployed: {url}", flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        RESULT.write_text(f"FAILED {type(exc).__name__}: {exc}", encoding="utf-8")
        raise
