"""Подготовка VPS для деплоя inst-trans из приватного GitHub-репо.

Что делает (idempotent):
1. Создаёт системного пользователя inst-trans (если нет).
2. Генерирует SSH-ключ /home/inst-trans/.ssh/id_ed25519 (если нет).
3. Добавляет github.com в known_hosts (если нет).
4. Печатает публичный ключ — его нужно добавить в GitHub:
   Settings -> Deploy keys -> Add deploy key (без write access).

Использование:
    python scripts/prepare_deploy_key.py <host> root
"""

from __future__ import annotations

import sys
from pathlib import Path

import paramiko

SYSTEM_USER = "inst-trans"
HOME = f"/home/{SYSTEM_USER}"

SCRIPT = f"""\
set -e

# 1. Пользователь
if ! id {SYSTEM_USER} >/dev/null 2>&1; then
  useradd --system --create-home --home-dir {HOME} --shell /usr/sbin/nologin {SYSTEM_USER}
fi

# 2. SSH-ключ для git
sudo -u {SYSTEM_USER} -H mkdir -p {HOME}/.ssh
sudo -u {SYSTEM_USER} -H chmod 700 {HOME}/.ssh
if [ ! -f {HOME}/.ssh/id_ed25519 ]; then
  sudo -u {SYSTEM_USER} -H ssh-keygen -t ed25519 -N '' -f {HOME}/.ssh/id_ed25519 -C 'inst-trans@deploy' >/dev/null
fi

# 3. known_hosts: добавить GitHub
touch {HOME}/.ssh/known_hosts
chown {SYSTEM_USER}:{SYSTEM_USER} {HOME}/.ssh/known_hosts
if ! sudo -u {SYSTEM_USER} -H ssh-keygen -F github.com -f {HOME}/.ssh/known_hosts >/dev/null 2>&1; then
  ssh-keyscan -t ed25519 github.com 2>/dev/null >> {HOME}/.ssh/known_hosts
  chown {SYSTEM_USER}:{SYSTEM_USER} {HOME}/.ssh/known_hosts
fi
chmod 600 {HOME}/.ssh/known_hosts

# 4. Распечатать публичный ключ
echo '=== DEPLOY_KEY_BEGIN ==='
cat {HOME}/.ssh/id_ed25519.pub
echo '=== DEPLOY_KEY_END ==='
"""


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: prepare_deploy_key.py <host> <user>", file=sys.stderr)
        return 2

    host, user = sys.argv[1], sys.argv[2]
    key = _load_key(Path.home() / ".ssh" / "id_ed25519")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host, username=user, pkey=key, timeout=30, look_for_keys=False, allow_agent=False
    )
    try:
        stdin, stdout, stderr = client.exec_command(f"bash -lc {_q(SCRIPT)}")
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        rc = stdout.channel.recv_exit_status()
    finally:
        client.close()

    if out:
        print(out.rstrip())
    if rc != 0:
        if err:
            print(err.rstrip(), file=sys.stderr)
        print(f"\nfailed (rc={rc})", file=sys.stderr)
        return rc
    print(
        "\nДобавь публичный ключ выше (строка ssh-ed25519 ...) в GitHub:\n"
        "  репо -> Settings -> Deploy keys -> Add deploy key\n"
        "  Title: inst-trans VPS, без галки 'Allow write access'.\n"
        "Потом запусти scripts/deploy.py."
    )
    return 0


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _load_key(key_path: Path) -> paramiko.PKey:
    """Перебираем «пустые» пароли (артефакт ssh-keygen в PowerShell)."""
    for password in (None, "", '""'):
        try:
            return paramiko.Ed25519Key.from_private_key_file(str(key_path), password=password)
        except paramiko.ssh_exception.PasswordRequiredException:
            continue
        except paramiko.ssh_exception.SSHException as exc:
            if "decrypt" in str(exc).lower() or "bad password" in str(exc).lower():
                continue
            raise
    raise SystemExit(
        f"Не удалось расшифровать {key_path}. Снять пароль: "
        "python ../teacher-helper/scripts/unlock_key.py"
    )


if __name__ == "__main__":
    sys.exit(main())
