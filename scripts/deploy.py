"""Установка inst-trans на VPS в одно SSH-соединение.

Шаги:
1. apt update + python3 + venv + git (если нужно)
2. Создать системного пользователя inst-trans
3. Склонировать репо в /opt/inst-trans
4. Создать venv и установить пакет
5. Загрузить .env с локального .env (через SFTP)
6. Установить и запустить systemd-сервис
7. Показать статус и хвост journalctl

Использование:
    python scripts/deploy.py <host> <user> [--branch main] [--git-url https://...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import paramiko

# По умолчанию Windows-консоль шлёт stdout в cp1251 — systemctl status печатает
# bullet-точку '●', которая туда не лезет, и скрипт падает на самом безобидном
# месте (после всех настоящих шагов). Заставим stdout быть UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

INSTALL_DIR = "/opt/inst-trans"
SERVICE_NAME = "inst-trans"
SYSTEM_USER = "inst-trans"
SYSTEMD_UNIT_SOURCE = "deploy/systemd/inst-trans.service"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("user")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--git-url", default="git@github.com:russlandy/inst-trans.git")
    args = ap.parse_args()

    local_env = Path(".env")
    if not local_env.exists():
        print("error: local .env not found, abort", file=sys.stderr)
        return 2

    local_unit = Path(SYSTEMD_UNIT_SOURCE)
    if not local_unit.exists():
        print(f"error: {SYSTEMD_UNIT_SOURCE} missing", file=sys.stderr)
        return 2

    client = _connect(args.host, args.user)
    try:
        _step("системные пакеты", client, _SCRIPT_APT)
        _step(
            "системный пользователь и каталог",
            client,
            _SCRIPT_USER.format(user=SYSTEM_USER, dir=INSTALL_DIR),
        )
        _step(
            "git clone / pull",
            client,
            _SCRIPT_GIT.format(
                user=SYSTEM_USER, dir=INSTALL_DIR, url=args.git_url, branch=args.branch
            ),
        )
        _step(
            "venv и зависимости",
            client,
            _SCRIPT_VENV.format(user=SYSTEM_USER, dir=INSTALL_DIR),
        )

        _upload(client, local_env, f"{INSTALL_DIR}/.env", mode=0o600)

        local_cookies = Path("cookies.txt")
        if local_cookies.exists():
            _upload(client, local_cookies, f"{INSTALL_DIR}/cookies.txt", mode=0o600)
            cookies_chown = f"chown {SYSTEM_USER}:{SYSTEM_USER} {INSTALL_DIR}/cookies.txt && "
        else:
            print("(no local cookies.txt — skipping upload; bot will fall back to mirrors)")
            cookies_chown = ""

        _step(
            "права на .env, cookies, logs",
            client,
            f"chown {SYSTEM_USER}:{SYSTEM_USER} {INSTALL_DIR}/.env && "
            f"{cookies_chown}"
            f"mkdir -p {INSTALL_DIR}/logs && "
            f"chown -R {SYSTEM_USER}:{SYSTEM_USER} {INSTALL_DIR}/logs && "
            "echo OK",
        )

        _upload(client, local_unit, f"/etc/systemd/system/{SERVICE_NAME}.service", mode=0o644)
        _step(
            "systemd: daemon-reload + enable + restart",
            client,
            f"systemctl daemon-reload && systemctl enable {SERVICE_NAME} && "
            f"systemctl restart {SERVICE_NAME} && sleep 2 && echo OK",
        )

        print("\n=== systemctl status ===")
        _print_command(client, f"systemctl status {SERVICE_NAME} --no-pager -l | head -20")
        print("\n=== journalctl (last 30 lines) ===")
        _print_command(client, f"journalctl -u {SERVICE_NAME} -n 30 --no-pager")
    finally:
        client.close()
    return 0


# ----------------------------- helpers -----------------------------


def _connect(host: str, user: str) -> paramiko.SSHClient:
    key_path = Path.home() / ".ssh" / "id_ed25519"
    pkey = _load_key(key_path)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host, username=user, pkey=pkey, timeout=30, look_for_keys=False, allow_agent=False
    )
    return client


def _load_key(key_path: Path) -> paramiko.PKey:
    for password in (None, "", '""'):
        try:
            return paramiko.Ed25519Key.from_private_key_file(str(key_path), password=password)
        except paramiko.ssh_exception.PasswordRequiredException:
            continue
        except paramiko.ssh_exception.SSHException as exc:
            if "decrypt" in str(exc).lower() or "bad password" in str(exc).lower():
                continue
            raise
    raise SystemExit("could not decrypt SSH key")


def _step(name: str, client: paramiko.SSHClient, script: str) -> None:
    print(f"\n=== {name} ===")
    rc, out, err = _exec(client, script)
    if out:
        print(out.rstrip())
    if rc != 0:
        if err:
            print(err.rstrip(), file=sys.stderr)
        raise SystemExit(f"step failed: {name} (rc={rc})")


def _exec(client: paramiko.SSHClient, command: str) -> tuple[int, str, str]:
    full = f"bash -lc {_shell_quote(command)}"
    stdin, stdout, stderr = client.exec_command(full, get_pty=False)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def _print_command(client: paramiko.SSHClient, command: str) -> None:
    rc, out, err = _exec(client, command)
    if out:
        print(out.rstrip())
    if err:
        print(err.rstrip(), file=sys.stderr)


def _upload(client: paramiko.SSHClient, local: Path, remote: str, *, mode: int) -> None:
    print(f"=== upload {local} -> {remote} ===")
    sftp = client.open_sftp()
    try:
        sftp.put(str(local), remote)
        sftp.chmod(remote, mode)
    finally:
        sftp.close()
    print("OK")


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# ----------------------------- scripts -----------------------------

_SCRIPT_APT = """\
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
PY="python$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
# ffmpeg нужен yt-dlp на случай, когда IG отдаёт раздельные потоки видео/аудио.
NEED_PKGS="git ca-certificates ffmpeg"
if ! dpkg -s "${PY}-venv" >/dev/null 2>&1; then
  NEED_PKGS="$NEED_PKGS ${PY}-venv"
fi
apt-get install -y -qq $NEED_PKGS
echo OK
"""

_SCRIPT_USER = """\
set -e
if ! id {user} >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /home/{user} --shell /usr/sbin/nologin {user}
fi
mkdir -p {dir}
chown {user}:{user} {dir}
echo OK
"""

_SCRIPT_GIT = """\
set -e
cd {dir}
if [ -d .git ]; then
  sudo -u {user} -H git fetch --all --prune
  sudo -u {user} -H git checkout {branch}
  sudo -u {user} -H git pull --ff-only
else
  sudo -u {user} -H git clone --branch {branch} {url} .
fi
echo OK
"""

_SCRIPT_VENV = """\
set -e
cd {dir}
if [ ! -d .venv ]; then
  sudo -u {user} -H python3 -m venv .venv
fi
sudo -u {user} -H .venv/bin/pip install --upgrade pip --quiet
# Зеркало Aliyun — обычный PyPI с этого VPS часто рвёт коннект
sudo -u {user} -H .venv/bin/pip install --quiet \
  --index-url https://mirrors.aliyun.com/pypi/simple/ \
  --trusted-host mirrors.aliyun.com \
  -e .
echo OK
"""


if __name__ == "__main__":
    sys.exit(main())
