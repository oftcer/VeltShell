# -*- coding: utf-8 -*-
"""Windows VPS — abre a tela do PC virtual no Ubuntu sem wizard."""

from __future__ import annotations

import queue
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import paramiko
except ImportError:
    paramiko = None  # type: ignore

APP_TITLE = "Windows VPS"


def _app_base() -> Path:
    """Pasta do .exe (PyInstaller) ou do script — onde ficam ssh.txt / iso.txt."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE = _app_base()
SSH_FILE = BASE / "ssh.txt"
ISO_FILE = BASE / "iso.txt"
ERR_LOG = BASE / "erro.log"

VM_NAME = "winvps"
# Alvos altos; na pratica o app detecta a maquina e usa quase tudo
RAM_MB = 112640  # ~110 GB (reserva ~8 GB para o Ubuntu)
VCPUS = 32
DISK_GB = 400
HOST_RAM_RESERVE_MB = 8192  # reserva para o sistema Ubuntu
HOST_CPU_RESERVE = 2        # reserva CPUs para o Ubuntu
VNC_PORT = 5901
NOVNC_PORT = 6080
OS_VARIANT = "win2k22"
REMOTE_ISO_DIR = "/opt/iso"
REMOTE_DISK_DIR = "/var/lib/libvirt/images"
# ISO oficial de avaliacao Windows Server 2022 (Microsoft)
WIN_ISO_URL = "https://go.microsoft.com/fwlink/p/?LinkID=2195280&clcid=0x409&culture=en-us&country=US"
WIN_ISO_NAME = "WinServer2022Eval.iso"
WIN_ISO_MIN_BYTES = 3_000_000_000  # ~3 GB (ISO real tem ~4.7 GB)


def crash(msg: str) -> None:
    try:
        ERR_LOG.write_text(msg, encoding="utf-8")
    except Exception:
        pass


def read_ssh() -> tuple[str, str, str, int]:
    if not SSH_FILE.is_file():
        raise FileNotFoundError(f"Falta {SSH_FILE}")
    lines = [x.strip() for x in SSH_FILE.read_text(encoding="utf-8", errors="ignore").splitlines() if x.strip()]
    if len(lines) < 3:
        raise ValueError("ssh.txt precisa ter 3 linhas: IP, usuario, senha\n(opcional 4a linha: porta)")
    port = 22
    if len(lines) >= 4 and lines[3].isdigit():
        port = int(lines[3])
    return lines[0], lines[1], lines[2], port


def find_local_iso() -> Path | None:
    if ISO_FILE.is_file():
        for line in ISO_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip().strip('"')
            if not s or s.startswith("#"):
                continue
            p = Path(s)
            if p.is_file() and p.suffix.lower() == ".iso":
                return p
    for p in sorted(BASE.glob("*.iso")):
        if p.is_file():
            return p
    # pastas comuns
    for folder in (
        Path.home() / "Downloads",
        Path(r"C:\Users\Public\Downloads"),
        Path(r"D:\\"),
        Path(r"E:\\"),
    ):
        try:
            if folder.is_dir():
                for p in folder.glob("*.iso"):
                    name = p.name.lower()
                    if "win" in name or "windows" in name or "server" in name:
                        return p
                for p in folder.glob("*.iso"):
                    return p
        except Exception:
            pass
    return None


def open_vps_window(url: str) -> None:
    for exe in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ):
        if Path(exe).is_file():
            subprocess.Popen(
                [exe, f"--app={url}", "--new-window", "--window-size=1280,800"],
                shell=False,
            )
            return
    webbrowser.open(url)


class Tunnel:
    def __init__(self, transport, local_port: int, remote_port: int, log):
        self.transport = transport
        self.local_port = local_port
        self.remote_port = remote_port
        self.log = log
        self._stop = threading.Event()
        self._sock = None

    def start(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", self.local_port))
        except OSError:
            # porta ocupada: tenta outra
            s.bind(("127.0.0.1", 0))
            self.local_port = s.getsockname()[1]
        s.listen(20)
        s.settimeout(1.0)
        self._sock = s
        threading.Thread(target=self._loop, daemon=True).start()
        self.log(f"Tunel 127.0.0.1:{self.local_port} -> :{self.remote_port}")

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                client, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._pipe, args=(client,), daemon=True).start()

    def _pipe(self, client: socket.socket) -> None:
        try:
            chan = self.transport.open_channel(
                "direct-tcpip",
                ("127.0.0.1", self.remote_port),
                ("127.0.0.1", 0),
            )
        except Exception as exc:
            self.log(f"Tunel erro: {exc}")
            try:
                client.close()
            except Exception:
                pass
            return

        def pump(a, b):
            try:
                while True:
                    data = a.recv(65535)
                    if not data:
                        break
                    b.sendall(data)
            except Exception:
                pass
            for x in (a, b):
                try:
                    x.close()
                except Exception:
                    pass

        threading.Thread(target=pump, args=(client, chan), daemon=True).start()
        threading.Thread(target=pump, args=(chan, client), daemon=True).start()


class SSH:
    def __init__(self, host, user, password, log, port: int = 22):
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.log = log
        self.client = None
        self.tunnels: list[Tunnel] = []

    def connect(self) -> None:
        self.log(f"SSH {self.user}@{self.host}:{self.port}")
        last_err: Exception | None = None
        for attempt in range(1, 6):
            self.log(f"Tentativa {attempt}/5...")
            try:
                self.client = self._connect_once()
                self.log("SSH OK")
                return
            except Exception as exc:
                last_err = exc
                self.log(f"Falha SSH: {type(exc).__name__}: {exc or 'conexao fechada'}")
                time.sleep(2 * attempt)

        err_name = type(last_err).__name__ if last_err else "Erro"
        err_txt = str(last_err) if last_err and str(last_err) else "servidor fechou a conexao (EOF)"
        raise RuntimeError(
            f"Nao foi possivel conectar em {self.host}:{self.port}\n"
            f"({err_name}: {err_txt})\n\n"
            "O servidor SSH esta online, mas recusou o login.\n"
            "Feche todas as janelas do WindowsVPS, espere 1 minuto\n"
            "(fail2ban/limite de conexoes) e tente de novo.\n"
            "Confira tambem usuario/senha em ssh.txt."
        )

    def _connect_once(self) -> paramiko.SSHClient:
        # Metodo 1: SSHClient padrao
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                timeout=30,
                banner_timeout=60,
                auth_timeout=60,
                allow_agent=False,
                look_for_keys=False,
                compress=False,
            )
            tr = c.get_transport()
            if tr and tr.is_active():
                return c
            c.close()
        except Exception as exc:
            self.log(f"SSHClient falhou ({exc or type(exc).__name__}), tentando Transport...")

        # Metodo 2: Transport manual (melhor com OpenSSH novo / EOF)
        sock = socket.create_connection((self.host, self.port), timeout=30)
        sock.settimeout(60)
        transport = paramiko.Transport(sock)
        transport.banner_timeout = 60
        transport.auth_timeout = 60
        try:
            transport.start_client(timeout=60)
            if not transport.is_authenticated():
                transport.auth_password(self.user, self.password)
            if not transport.is_authenticated():
                raise RuntimeError("Autenticacao SSH recusada (usuario/senha)")
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c._transport = transport  # type: ignore[attr-defined]
            return c
        except Exception:
            try:
                transport.close()
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass
            raise

    def close(self) -> None:
        for t in self.tunnels:
            t.stop()
        self.tunnels.clear()
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    def run(self, cmd: str, timeout: int = 300) -> tuple[int, str, str]:
        """Roda comando remoto com timeout real (nao trava o app)."""
        self.log(cmd[:160] + ("..." if len(cmd) > 160 else ""))
        # timeout do utilitario GNU no Ubuntu + timeout do canal SSH
        wrapped = f"timeout -k 10s {max(5, int(timeout))}s bash -lc {shlex.quote(cmd)}"
        try:
            _i, o, e = self.client.exec_command(wrapped, timeout=timeout + 30)
            # leitura com limite de tempo do canal
            chan = o.channel
            chan.settimeout(timeout + 30)
            out = o.read().decode("utf-8", errors="replace")
            err = e.read().decode("utf-8", errors="replace")
            code = chan.recv_exit_status()
        except Exception as exc:
            self.log(f"timeout/erro cmd: {exc}")
            return 124, "", str(exc)
        if out.strip():
            self.log(out.strip()[:1500])
        if err.strip() and code not in (0, 124):
            self.log(err.strip()[:800])
        if code == 124:
            self.log("(comando excedeu o tempo e foi interrompido)")
        return code, out, err

    def upload(self, local: Path, remote: str, progress) -> None:
        sftp = self.client.open_sftp()
        try:
            size = local.stat().st_size
            self.log(f"Upload ISO {size / (1024**3):.2f} GB")

            def cb(done, total):
                progress(done, total or size)

            sftp.put(str(local), remote, callback=cb)
        finally:
            sftp.close()

    def size(self, remote: str) -> int:
        _c, out, _ = self.run(f"stat -c %s -- '{remote}' 2>/dev/null || echo 0")
        try:
            return int(out.strip().splitlines()[-1])
        except Exception:
            return 0

    def tunnel(self, local_port: int, remote_port: int) -> Tunnel:
        tr = self.client.get_transport()
        t = Tunnel(tr, local_port, remote_port, self.log)
        t.start()
        self.tunnels.append(t)
        return t


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("540x280")
        self.resizable(False, False)
        self.configure(bg="#0b1220")
        self.q: queue.Queue = queue.Queue()
        self.ssh: SSH | None = None

        tk.Label(self, text="Windows VPS", fg="#f8fafc", bg="#0b1220", font=("Segoe UI", 18, "bold")).pack(
            pady=(30, 8)
        )
        self.status = tk.StringVar(value="Conectando ao servidor...")
        tk.Label(self, textvariable=self.status, fg="#7dd3fc", bg="#0b1220", font=("Segoe UI", 10)).pack()
        self.bar = ttk.Progressbar(self, length=440, mode="determinate", maximum=100)
        self.bar.pack(pady=16)
        self.detail = tk.StringVar(value="")
        tk.Label(
            self, textvariable=self.detail, fg="#94a3b8", bg="#0b1220", font=("Segoe UI", 8), wraplength=500
        ).pack(padx=16)

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._pump)
        self.after(250, lambda: threading.Thread(target=self._boot, daemon=True).start())

    def log(self, msg: str) -> None:
        self.q.put(("log", str(msg)))

    def set_status(self, msg: str, pct: int | None = None) -> None:
        self.q.put(("status", msg, pct))

    def _pump(self) -> None:
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "status":
                    self.status.set(item[1])
                    if item[2] is not None:
                        self.bar["value"] = item[2]
                elif item[0] == "log":
                    self.detail.set(item[1][:200])
                elif item[0] == "error":
                    messagebox.showerror(APP_TITLE, item[1])
                elif item[0] == "info":
                    messagebox.showinfo(APP_TITLE, item[1])
                elif item[0] == "done":
                    self.status.set("Tela do Windows aberta")
                    self.bar["value"] = 100
        except queue.Empty:
            pass
        self.after(80, self._pump)

    def _ensure_packages(self, ssh: SSH) -> None:
        """Instala so o necessario, com timeouts — nao trava em apt/systemctl."""
        self.set_status("Checando pacotes no Ubuntu...", 26)
        _c, out, _ = ssh.run(
            "command -v qemu-system-x86_64; command -v virsh; command -v virt-install; "
            "command -v websockify; echo CHECK_DONE",
            timeout=30,
        )
        need_install = not (
            "qemu-system-x86_64" in out
            and "virsh" in out
            and "virt-install" in out
        )

        if need_install:
            self.set_status("Instalando QEMU/libvirt (aguarde)...", 28)
            pkgs = (
                "qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients "
                "bridge-utils virtinst ovmf novnc websockify"
            )
            # Nao faz apt-get update sempre (muito lento). So se install falhar.
            code, _, _ = ssh.run(
                "export DEBIAN_FRONTEND=noninteractive APT_LISTCHANGES_FRONTEND=none; "
                f"apt-get install -y --no-install-recommends {pkgs}",
                timeout=600,
            )
            if code != 0:
                self.set_status("Atualizando apt e reinstalando...", 30)
                ssh.run(
                    "export DEBIAN_FRONTEND=noninteractive; apt-get update -y",
                    timeout=300,
                )
                ssh.run(
                    "export DEBIAN_FRONTEND=noninteractive APT_LISTCHANGES_FRONTEND=none; "
                    f"apt-get install -y --no-install-recommends {pkgs}",
                    timeout=600,
                )
        else:
            self.log("Pacotes ja instalados — pulando apt")

        self.set_status("Iniciando libvirt...", 33)
        # enable/start com timeout curto — se travar, segue mesmo assim
        ssh.run("systemctl enable libvirtd >/dev/null 2>&1 || true", timeout=20)
        ssh.run("systemctl start libvirtd >/dev/null 2>&1 || service libvirtd start || true", timeout=25)
        ssh.run("pgrep -a libvirtd || true", timeout=15)

        ssh.run(f"mkdir -p {REMOTE_ISO_DIR} {REMOTE_DISK_DIR}", timeout=15)
        ssh.run("virsh net-start default >/dev/null 2>&1 || true", timeout=20)
        ssh.run("virsh net-autostart default >/dev/null 2>&1 || true", timeout=15)

    def _detect_accel(self, ssh: SSH) -> tuple[str, str]:
        """Retorna (virt_type, mensagem). Usa KVM se existir; senao QEMU/TCG."""
        ssh.run("modprobe kvm 2>/dev/null || true", timeout=10)
        ssh.run("modprobe kvm_intel 2>/dev/null || true", timeout=10)
        ssh.run("modprobe kvm_amd 2>/dev/null || true", timeout=10)
        _c, out, _ = ssh.run("test -e /dev/kvm && echo KVM_OK || echo KVM_MISSING", timeout=10)
        if "KVM_OK" in out:
            return "kvm", "KVM ativo (rapido)"
        _c, out, _ = ssh.run(
            "command -v qemu-system-x86_64 >/dev/null && echo QEMU_OK || echo QEMU_MISSING",
            timeout=10,
        )
        if "QEMU_OK" not in out:
            raise RuntimeError("QEMU nao instalado no servidor.")
        return "qemu", "Sem KVM — usando QEMU (mais lento, mas funciona)"

    def _remote_iso(self, ssh: SSH) -> str | None:
        _c, out, _ = ssh.run(
            f"ls -1S {REMOTE_ISO_DIR}/*.iso 2>/dev/null | head -n 5 || true",
            timeout=20,
        )
        for line in out.splitlines():
            path = line.strip()
            if path.endswith(".iso") and ssh.size(path) >= WIN_ISO_MIN_BYTES:
                return path
        # aceita qualquer iso > 1GB se existir
        for line in out.splitlines():
            path = line.strip()
            if path.endswith(".iso") and ssh.size(path) >= 1_000_000_000:
                return path
        return None

    def _download_iso_on_server(self, ssh: SSH) -> str:
        """Baixa ISO oficial Windows Server Eval direto no Ubuntu (sem upload do PC)."""
        dest = f"{REMOTE_ISO_DIR}/{WIN_ISO_NAME}"
        ssh.run(f"mkdir -p {REMOTE_ISO_DIR}", timeout=15)
        if ssh.size(dest) >= WIN_ISO_MIN_BYTES:
            self.log("ISO ja existe no servidor")
            return dest

        self.set_status("Baixando ISO Windows no servidor (pode demorar)...", 45)
        ssh.run(
            "export DEBIAN_FRONTEND=noninteractive; "
            "apt-get install -y --no-install-recommends wget curl ca-certificates || true",
            timeout=180,
        )
        # download em background com wget -c (retomavel)
        ssh.run(f"pkill -f 'wget.*{WIN_ISO_NAME}' 2>/dev/null || true", timeout=10)
        dl = (
            f"nohup wget -c --tries=0 --read-timeout=60 --timeout=30 "
            f"-O '{dest}' '{WIN_ISO_URL}' > /tmp/iso-dl.log 2>&1 & echo DLSTART"
        )
        code, out, err = ssh.run(dl, timeout=30)
        if "DLSTART" not in out and code != 0:
            # fallback curl
            ssh.run(
                f"nohup curl -L --retry 20 --retry-all-errors -C - "
                f"-o '{dest}' '{WIN_ISO_URL}' > /tmp/iso-dl.log 2>&1 & echo DLSTART",
                timeout=30,
            )

        last = -1
        stable = 0
        for i in range(720):  # ate ~2h (10s * 720)
            time.sleep(10)
            sz = ssh.size(dest)
            gb = sz / (1024**3)
            pct = min(78, 45 + int(gb * 6))
            self.set_status(f"Baixando ISO no servidor... {gb:.2f} GB", pct)
            self.log(f"ISO size={sz}")

            if sz >= WIN_ISO_MIN_BYTES:
                if sz == last:
                    stable += 1
                else:
                    stable = 0
                last = sz
                if stable >= 3:
                    # confirma que wget/curl terminou
                    _c, ps, _ = ssh.run(
                        f"pgrep -af 'wget.*{WIN_ISO_NAME}|curl.*{WIN_ISO_NAME}' || echo DONE",
                        timeout=15,
                    )
                    if "DONE" in ps or "wget" not in ps.lower():
                        self.log("Download ISO concluido")
                        return dest
            else:
                last = sz
                stable = 0

            if i in (6, 12, 30) and sz < 1_000_000:
                ssh.run("tail -n 20 /tmp/iso-dl.log || true", timeout=15)

            if i == 12 and sz < 500_000:
                # talvez wget pegou HTML; tenta curl
                ssh.run(f"pkill -f 'wget.*{WIN_ISO_NAME}' 2>/dev/null || true", timeout=10)
                ssh.run(f"rm -f '{dest}'", timeout=15)
                ssh.run(
                    f"nohup curl -L --retry 20 --retry-all-errors "
                    f"-o '{dest}' '{WIN_ISO_URL}' > /tmp/iso-dl.log 2>&1 & echo DLSTART",
                    timeout=30,
                )

        raise RuntimeError(
            "Timeout ao baixar a ISO no servidor.\n"
            "Verifique a internet do VPS ou coloque uma ISO em iso.txt."
        )

    def _detect_host_limits(self, ssh: SSH) -> tuple[int, int]:
        """Detecta RAM/CPU do servidor e reserva um pouco para o Ubuntu."""
        _c, out, _ = ssh.run("free -m | awk '/Mem:/{print $2}'", timeout=20)
        try:
            total_ram = int(out.strip().splitlines()[-1])
        except Exception:
            total_ram = RAM_MB + HOST_RAM_RESERVE_MB

        _c, out, _ = ssh.run("nproc 2>/dev/null || echo 8", timeout=15)
        try:
            total_cpu = int(out.strip().splitlines()[-1])
        except Exception:
            total_cpu = VCPUS + HOST_CPU_RESERVE

        ram_mb = max(4096, total_ram - HOST_RAM_RESERVE_MB)
        # se o host tem ~120GB, usa o maximo util
        ram_mb = min(ram_mb, total_ram - 2048)
        vcpus = max(2, total_cpu - HOST_CPU_RESERVE)
        self.log(f"Host: {total_ram} MB RAM, {total_cpu} CPUs")
        self.log(f"VM vai usar: {ram_mb} MB RAM, {vcpus} vCPUs")
        return ram_mb, vcpus

    def _apply_full_power(self, ssh: SSH, vm: str, ram_mb: int, vcpus: int) -> None:
        """Atualiza VM existente para usar quase toda a maquina (precisa reiniciar)."""
        self.set_status(f"Aplicando desempenho total: {ram_mb//1024} GB RAM / {vcpus} CPUs...", 70)
        was_running = "running" in self._vm_state(ssh, vm)
        if was_running:
            self.log("Desligando VM para aplicar RAM/CPU...")
            ssh.run(f"virsh destroy {vm} 2>/dev/null || true", timeout=40)

        # Maximos no XML permanente
        ssh.run(f"virsh setmaxmem {vm} {ram_mb} --config || true", timeout=30)
        ssh.run(f"virsh setmem {vm} {ram_mb} --config || true", timeout=30)
        ssh.run(f"virsh setvcpus {vm} {vcpus} --config --maximum || true", timeout=30)
        ssh.run(f"virsh setvcpus {vm} {vcpus} --config || true", timeout=30)

        # Tambem tenta via edit direto do XML (mais confiavel em alguns hosts)
        ssh.run(
            f"virsh dumpxml {vm} > /tmp/{vm}.xml && "
            f"sed -i -E 's#<memory unit=.*>.*</memory>#<memory unit=\"KiB\">{ram_mb * 1024}</memory>#' /tmp/{vm}.xml && "
            f"sed -i -E 's#<currentMemory unit=.*>.*</currentMemory>#<currentMemory unit=\"KiB\">{ram_mb * 1024}</currentMemory>#' /tmp/{vm}.xml && "
            f"sed -i -E 's#<vcpu placement=.*>.*</vcpu>#<vcpu placement=\"static\">{vcpus}</vcpu>#' /tmp/{vm}.xml && "
            f"virsh define /tmp/{vm}.xml || true",
            timeout=40,
        )

        self.log("Recursos da VM atualizados")
        if was_running:
            ssh.run(f"virsh start {vm} || true", timeout=40)
            time.sleep(4)

    def _guest_ip(self, ssh: SSH, vm: str) -> str | None:
        """Descobre o IP da VM na rede libvirt."""
        cmds = [
            f"virsh domifaddr {vm} --source lease 2>/dev/null | awk '/ipv4/{{print $4}}' | cut -d/ -f1 | head -n1",
            f"virsh domifaddr {vm} --source agent 2>/dev/null | awk '/ipv4/{{print $4}}' | cut -d/ -f1 | head -n1",
            f"virsh domifaddr {vm} 2>/dev/null | awk '/ipv4/{{print $4}}' | cut -d/ -f1 | head -n1",
            "virsh net-dhcp-leases default 2>/dev/null | awk '/ipv4/ {print $5}' | cut -d/ -f1 | head -n1",
            "cat /var/lib/libvirt/dnsmasq/virbr0.status 2>/dev/null | "
            "grep -oE '192\\.168\\.122\\.[0-9]+' | head -n1",
            "arp -an 2>/dev/null | grep -oE '192\\.168\\.122\\.[0-9]+' | head -n1",
        ]
        for cmd in cmds:
            _c, out, _ = ssh.run(cmd, timeout=20)
            for line in out.splitlines():
                ip = line.strip()
                if re.match(r"^192\.168\.122\.\d+$", ip) or re.match(r"^10\.\d+\.\d+\.\d+$", ip):
                    self.log(f"IP da VM: {ip}")
                    return ip
                if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip) and not ip.startswith("127."):
                    self.log(f"IP da VM: {ip}")
                    return ip
        return None

    def _setup_rdp_forward(self, ssh: SSH, vm: str, public_host: str) -> str | None:
        """Encaminha 80/443/3389 do Ubuntu -> Windows VM."""
        self.set_status("Liberando portas 80, 443 e 3389...", 88)
        ssh.run(
            "export DEBIAN_FRONTEND=noninteractive; "
            "apt-get install -y --no-install-recommends socat iptables netcat-openbsd || true",
            timeout=180,
        )
        ssh.run("sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true", timeout=10)

        guest_ip = None
        for i in range(25):
            guest_ip = self._guest_ip(ssh, vm)
            if guest_ip:
                break
            self.log(f"Aguardando IP da VM... ({i+1}/25)")
            time.sleep(3)
        if not guest_ip:
            return (
                "Nao achei o IP interno da VM Windows.\n"
                "No noVNC abra CMD e rode: ipconfig\n"
                "Veja o IPv4 (ex.: 192.168.122.x) e me avise."
            )

        # Para web (80/443) nao exige servico rodando antes; RDP sim avisa
        _c, out, _ = ssh.run(
            f"nc -z -w 3 {guest_ip} 3389 && echo RDP_UP || echo RDP_DOWN",
            timeout=20,
        )
        rdp_note = ""
        if "RDP_UP" not in out:
            rdp_note = (
                "\n\nAviso RDP: a porta 3389 ainda nao responde DENTRO do Windows.\n"
                "Ative Remote Desktop + regra Inbound 3389 se for usar mstsc."
            )

        ports = (80, 443, 3389, 13389)
        for p in (80, 443, 3389, 13389):
            ssh.run(f"pkill -f 'socat.*TCP-LISTEN:{p}' 2>/dev/null || true", timeout=15)
        time.sleep(1)

        # 80, 443, 3389 -> guest; 13389 -> guest:3389 (alternativa RDP)
        forwards = [
            (80, 80),
            (443, 443),
            (3389, 3389),
            (13389, 3389),
        ]
        for host_port, guest_port in forwards:
            ssh.run(
                f"nohup socat TCP-LISTEN:{host_port},fork,reuseaddr,bind=0.0.0.0 "
                f"TCP:{guest_ip}:{guest_port} > /tmp/fwd-{host_port}.log 2>&1 & echo FWD{host_port}",
                timeout=20,
            )
            ssh.run(f"ufw allow {host_port}/tcp 2>/dev/null || true", timeout=15)
            ssh.run(
                f"iptables -I INPUT -p tcp --dport {host_port} -j ACCEPT 2>/dev/null || true",
                timeout=15,
            )

        time.sleep(1)
        ssh.run("ss -lntp | egrep ':(80|443|3389|13389)\\s' || true", timeout=15)

        msg = (
            f"Portas liberadas/encaminhadas para a VM {guest_ip}:\n\n"
            f"HTTP  http://{public_host}  (80)\n"
            f"HTTPS https://{public_host} (443)\n"
            f"RDP   {public_host}  ou  {public_host}:13389\n\n"
            f"No Windows da VM, libere Inbound 80, 443 e 3389 no firewall.\n"
            f"Para site: rode IIS/Apache/Nginx escutando 80/443."
            f"{rdp_note}"
        )
        self.log(f"Forward 80/443/3389/13389 -> {guest_ip}")
        return msg

    def _find_vm(self, ssh: SSH) -> str | None:
        for name in (VM_NAME, "win10", "win11", "windows", "win2k22"):
            if self._vm_exists(ssh, name):
                return name
        return None

    def _vm_exists(self, ssh: SSH, vm: str) -> bool:
        _c, out, _ = ssh.run(
            f"virsh dominfo {vm} >/dev/null 2>&1 && echo EXISTS || echo NEW",
            timeout=20,
        )
        return "EXISTS" in out

    def _vm_state(self, ssh: SSH, vm: str) -> str:
        _c, out, _ = ssh.run(
            f"virsh domstate {vm} 2>/dev/null || echo unknown",
            timeout=20,
        )
        return (out.strip().splitlines() or ["unknown"])[0].strip().lower()

    def _detect_vnc_port(self, ssh: SSH, vm: str) -> int:
        _c, out, _ = ssh.run(f"virsh vncdisplay {vm} 2>/dev/null || true", timeout=20)
        m = re.search(r":(\d+)\s*$", out.strip(), re.M)
        if m:
            return 5900 + int(m.group(1))
        # fallback: primeira porta 590x aberta no localhost
        _c, out, _ = ssh.run(
            "ss -lnt 2>/dev/null | awk '{print $4}' | egrep ':(590[0-9])$' | head -n 1 || true",
            timeout=20,
        )
        m = re.search(r":(590\d)\s*$", out.strip())
        if m:
            return int(m.group(1))
        return VNC_PORT

    def _wait_remote_port(self, ssh: SSH, port: int, label: str, tries: int = 30) -> bool:
        for i in range(tries):
            _c, out, _ = ssh.run(
                f"ss -lnt 2>/dev/null | grep -q ':{port} ' && echo UP || echo DOWN",
                timeout=15,
            )
            if "UP" in out:
                self.log(f"{label} :{port} OK")
                return True
            self.log(f"Aguardando {label} :{port} ({i+1}/{tries})")
            time.sleep(2)
        return False

    def _wait_local_port(self, port: int, tries: int = 20) -> bool:
        for i in range(tries):
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=1.5)
                s.close()
                self.log(f"Tunel local :{port} OK")
                return True
            except OSError:
                time.sleep(1)
        return False

    def _start_novnc(self, ssh: SSH, vnc_port: int) -> None:
        # limpa processos antigos na porta
        ssh.run(
            f"pkill -f 'websockify.*{NOVNC_PORT}' 2>/dev/null || true; "
            f"pkill -f 'novnc_proxy.*{NOVNC_PORT}' 2>/dev/null || true; "
            f"fuser -k {NOVNC_PORT}/tcp 2>/dev/null || true",
            timeout=20,
        )
        time.sleep(1)

        # sobe console — tenta novnc_proxy, depois websockify
        start_cmd = f"""
WEB=''
for d in /usr/share/novnc /usr/share/novnc/utils/../ /usr/share/spice-html5; do
  if [ -f \"$d/vnc.html\" ] || [ -f \"$d/vnc_lite.html\" ]; then WEB=\"$d\"; break; fi
done
if [ -z \"$WEB\" ]; then WEB=/usr/share/novnc; fi
echo WEBROOT=$WEB
if [ -x /usr/share/novnc/utils/novnc_proxy ]; then
  nohup /usr/share/novnc/utils/novnc_proxy --listen {NOVNC_PORT} --vnc 127.0.0.1:{vnc_port} > /tmp/novnc.log 2>&1 &
elif command -v novnc_proxy >/dev/null 2>&1; then
  nohup novnc_proxy --listen {NOVNC_PORT} --vnc 127.0.0.1:{vnc_port} > /tmp/novnc.log 2>&1 &
else
  nohup websockify --heartbeat=30 --web=$WEB {NOVNC_PORT} 127.0.0.1:{vnc_port} > /tmp/novnc.log 2>&1 &
fi
echo NOVNC_STARTED
sleep 1
ss -lntp | grep ':{NOVNC_PORT}' || true
tail -n 30 /tmp/novnc.log || true
"""
        ssh.run(start_cmd, timeout=40)
        if not self._wait_remote_port(ssh, NOVNC_PORT, "noVNC", tries=20):
            # ultimo recurso: websockify simples
            ssh.run(
                f"nohup python3 -m websockify --heartbeat=30 {NOVNC_PORT} 127.0.0.1:{vnc_port} "
                f"> /tmp/novnc.log 2>&1 & echo PYWS",
                timeout=30,
            )
            self._wait_remote_port(ssh, NOVNC_PORT, "noVNC-py", tries=15)

    def _pick_novnc_page(self, ssh: SSH) -> str:
        _c, out, _ = ssh.run(
            "if [ -f /usr/share/novnc/vnc.html ]; then echo vnc.html; "
            "elif [ -f /usr/share/novnc/vnc_lite.html ]; then echo vnc_lite.html; "
            "else echo vnc.html; fi",
            timeout=15,
        )
        page = (out.strip().splitlines() or ["vnc.html"])[-1].strip()
        return page if page.endswith(".html") else "vnc.html"

    def _open_console(self, ssh: SSH, vm: str) -> None:
        self.set_status("Iniciando VM...", 86)
        state = self._vm_state(ssh, vm)
        if "running" not in state:
            ssh.run(f"virsh start {vm} 2>/dev/null || true", timeout=30)

        # espera VM ficar running
        for i in range(30):
            state = self._vm_state(ssh, vm)
            self.log(f"estado VM: {state}")
            if "running" in state:
                break
            ssh.run(f"virsh start {vm} 2>/dev/null || true", timeout=20)
            time.sleep(2)
        else:
            ssh.run(f"virsh list --all; tail -n 40 /tmp/virt-{vm}.log 2>/dev/null || true", timeout=30)
            raise RuntimeError(
                f"A VM '{vm}' nao iniciou.\n"
                "Pode estar sem ISO/disco ou falhou no QEMU."
            )

        time.sleep(3)
        vnc_port = self._detect_vnc_port(ssh, vm)
        self.log(f"VNC porta {vnc_port}")
        if not self._wait_remote_port(ssh, vnc_port, "VNC", tries=25):
            # tenta detectar de novo
            vnc_port = self._detect_vnc_port(ssh, vm)
            if not self._wait_remote_port(ssh, vnc_port, "VNC", tries=10):
                raise RuntimeError(
                    f"VNC da VM nao abriu (porta {vnc_port}).\n"
                    "A VM pode ter crashado ao iniciar."
                )

        self.set_status("Ligando console noVNC...", 90)
        self._start_novnc(ssh, vnc_port)

        # Tunel SSH: noVNC web+websocket e tambem VNC cru (fallback)
        # remove tuneis antigos da mesma porta
        for t in list(ssh.tunnels):
            try:
                t.stop()
            except Exception:
                pass
        ssh.tunnels.clear()

        tun = ssh.tunnel(NOVNC_PORT, NOVNC_PORT)
        local = tun.local_port
        try:
            ssh.tunnel(vnc_port, vnc_port)
        except Exception as exc:
            self.log(f"Tunel VNC direto falhou (ok): {exc}")

        if not self._wait_local_port(local, tries=25):
            raise RuntimeError(
                "Tunel SSH do console nao subiu.\n"
                "Feche outros WindowsVPS e tente de novo."
            )

        # teste HTTP remoto via tunel
        try:
            s = socket.create_connection(("127.0.0.1", local), timeout=5)
            s.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            data = s.recv(200).decode("utf-8", errors="replace")
            s.close()
            self.log(f"HTTP noVNC: {data[:80]}")
        except Exception as exc:
            self.log(f"HTTP check: {exc}")

        page = self._pick_novnc_page(ssh)
        # encrypt=0 evita falha WSS; autoconnect liga sozinho
        url = (
            f"http://127.0.0.1:{local}/{page}"
            f"?autoconnect=true&reconnect=true&reconnect_delay=2000"
            f"&resize=scale&encryption=prefer_off"
        )
        self.set_status("Abrindo tela do Windows...", 95)
        open_vps_window(url)
        # segunda tentativa com vnc_lite se necessario
        time.sleep(2)
        if page != "vnc_lite.html":
            open_vps_window(
                f"http://127.0.0.1:{local}/vnc_lite.html"
                f"?autoconnect=true&resize=scale"
            )
        # Desbloqueia tela do Windows REMOTO (nao usa teclado do seu PC)
        time.sleep(2)
        self._send_ctrl_alt_del(ssh, vm)

        # Encaminha RDP 3389 Ubuntu -> Windows VM
        rdp_msg = self._setup_rdp_forward(ssh, vm, ssh.host)
        if rdp_msg:
            self.q.put(("info", rdp_msg))
            # abre mstsc no PC local
            try:
                subprocess.Popen(["mstsc", f"/v:{ssh.host}"], shell=False)
            except Exception as exc:
                self.log(f"mstsc: {exc}")

        self.log(url)
        self.q.put(("done",))
        self.set_status("RDP + noVNC prontos | Deixe este app ABERTO", 100)

    def _send_ctrl_alt_del(self, ssh: SSH, vm: str) -> None:
        """Envia Ctrl+Alt+Del para a VM remota (nao afeta o PC local)."""
        self.log("Enviando Ctrl+Alt+Del para a VM remota...")
        ssh.run(
            f"virsh send-key {vm} KEY_LEFTCTRL KEY_LEFTALT KEY_DELETE 2>/dev/null || "
            f"virsh send-key {vm} KEY_LEFTCTRL KEY_LEFTALT KEY_DELETE || true",
            timeout=20,
        )
        time.sleep(1)
        # segunda vez ajuda em algumas telas de lock
        ssh.run(
            f"virsh send-key {vm} KEY_LEFTCTRL KEY_LEFTALT KEY_DELETE 2>/dev/null || true",
            timeout=20,
        )

    def _boot(self) -> None:
        try:
            if paramiko is None:
                raise RuntimeError("paramiko ausente")

            self.set_status("Lendo ssh.txt...", 5)
            host, user, password, port = read_ssh()

            self.set_status("Conectando no Ubuntu...", 15)
            ssh = SSH(host, user, password, self.log, port=port)
            ssh.connect()
            self.ssh = ssh

            self.set_status("Preparando servidor...", 25)
            self._ensure_packages(ssh)

            self.set_status("Detectando virtualizacao...", 32)
            virt_type, accel_msg = self._detect_accel(ssh)
            self.log(accel_msg)

            # Usa quase toda a maquina SSH (reserva so o necessario para o Ubuntu)
            ram_mb, vcpus = self._detect_host_limits(ssh)

            vm = VM_NAME
            remote_disk = f"{REMOTE_DISK_DIR}/{vm}.qcow2"

            # 1) VM ja existe -> aplica desempenho (se preciso) e abre
            existing = self._find_vm(ssh)
            if existing:
                # so reaplica potencia se ainda estiver pequena
                _c, info, _ = ssh.run(f"virsh dominfo {existing} 2>/dev/null || true", timeout=20)
                need_power = True
                m = re.search(r"Max memory:\s+(\d+)", info)
                if m and int(m.group(1)) >= (ram_mb * 1024) - 2_000_000:
                    need_power = False
                if need_power:
                    self._apply_full_power(ssh, existing, ram_mb, vcpus)
                self.set_status(f"VM '{existing}' — abrindo console/RDP...", 85)
                self._open_console(ssh, existing)
                self.set_status("Windows VPS aberto", 100)
                return

            # 2) ISO ja no servidor OU local OU download automatico no Ubuntu
            remote_iso = self._remote_iso(ssh)
            local_iso = find_local_iso()
            if local_iso and not remote_iso:
                self.set_status("Enviando ISO para o servidor...", 45)
                remote_iso = f"{REMOTE_ISO_DIR}/{local_iso.name}"

                def prog(done, total):
                    pct = 45 + int(done * 30 / max(total, 1))
                    self.set_status(f"Enviando ISO... {pct}%", pct)

                if ssh.size(remote_iso) != local_iso.stat().st_size:
                    ssh.upload(local_iso, remote_iso, prog)
                else:
                    self.log("ISO ja enviada")
            elif local_iso and remote_iso:
                self.log(f"Usando ISO remota: {remote_iso}")

            if not remote_iso:
                self.set_status("ISO nao encontrada — baixando no servidor...", 42)
                remote_iso = self._download_iso_on_server(ssh)

            self.set_status(f"Criando Windows ({virt_type})...", 80)
            ssh.run(f"rm -f '{remote_disk}'", timeout=30)
            # os-variant: win2k22 se ISO server; win10 como fallback
            os_var = OS_VARIANT
            if "win10" in remote_iso.lower() or "windows10" in remote_iso.lower():
                os_var = "win10"
            elif "win11" in remote_iso.lower():
                os_var = "win11"
            cmd = (
                f"nohup virt-install --name {vm} "
                f"--virt-type {virt_type} "
                f"--ram {ram_mb} --vcpus {vcpus} "
                f"--disk path={remote_disk},size={DISK_GB},format=qcow2 "
                f"--cdrom '{remote_iso}' --os-variant {os_var} "
                f"--network network=default "
                f"--graphics vnc,listen=127.0.0.1,port={VNC_PORT} "
                f"--noautoconsole > /tmp/virt-{vm}.log 2>&1 & echo OK"
            )
            code, out, err = ssh.run(cmd, timeout=90)
            if "OK" not in out and code != 0:
                raise RuntimeError(err or out or "Falha ao criar VM")
            time.sleep(8)
            ssh.run(f"tail -n 40 /tmp/virt-{vm}.log || true")

            if not self._vm_exists(ssh, vm):
                # virt-install pode demorar; espera mais um pouco
                time.sleep(10)
                ssh.run(f"tail -n 60 /tmp/virt-{vm}.log || true")
                if not self._vm_exists(ssh, vm):
                    raise RuntimeError(
                        "VM nao foi criada. Veja /tmp/virt-winvps.log no servidor."
                    )

            self.set_status("Abrindo tela do Windows...", 92)
            self._open_console(ssh, vm)
            self.set_status("Windows VPS aberto", 100)
        except Exception as exc:
            crash(traceback.format_exc())
            msg = str(exc).strip() or type(exc).__name__
            self.log(msg)
            self.q.put(("error", f"{msg}\n\nDetalhes: {ERR_LOG}"))
            self.set_status("Erro — veja a mensagem", 0)

    def _close(self) -> None:
        try:
            if self.ssh:
                self.ssh.close()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    try:
        BASE.mkdir(parents=True, exist_ok=True)
        if paramiko is None:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(APP_TITLE, "Instale: pip install paramiko")
            return
        app = App()
        app.lift()
        try:
            app.attributes("-topmost", True)
            app.after(500, lambda: app.attributes("-topmost", False))
        except Exception:
            pass
        app.mainloop()
    except Exception:
        crash(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
