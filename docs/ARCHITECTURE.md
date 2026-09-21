# Arquitetura — VeltShell / Windows VPS

## Visão geral

O cliente roda no Windows local. Ele não virtualiza nada na sua máquina: só orquestra um servidor Ubuntu remoto via SSH e abre a tela da VM através de um túnel.

```text
┌────────────────────┐         SSH + SFTP          ┌──────────────────────────┐
│  PC Windows        │ ─────────────────────────── │  VPS Ubuntu              │
│                    │                             │                          │
│  windows_vps.py    │                             │  libvirt / QEMU-KVM      │
│  (Tkinter GUI)     │                             │  VM "winvps" (Windows)   │
│        │           │                             │        │                 │
│        ▼           │   túnel 127.0.0.1:6080      │        ▼                 │
│  Edge/Chrome       │ ◄────────────────────────── │  noVNC / websockify      │
│  (noVNC)           │                             │  VNC :5901               │
│                    │                             │                          │
│  mstsc (RDP)       │ ─────── TCP 3389 ─────────► │  socat → VM:3389         │
└────────────────────┘                             └──────────────────────────┘
```

## Fluxo de boot (`App._boot`)

1. **Lê `ssh.txt`** — host, usuário, senha, porta
2. **Conecta SSH** — Paramiko, com retries e fallback via `Transport` manual
3. **Pacotes** — instala QEMU, libvirt, virtinst, OVMF, noVNC, websockify se faltarem
4. **Aceleração** — KVM se `/dev/kvm` existir; senão QEMU/TCG
5. **Limites do host** — `free -m` e `nproc`; reserva RAM/CPU para o Ubuntu
6. **VM existente?** — se achar `winvps` (ou nomes conhecidos), aplica recursos e abre console
7. **ISO** — usa ISO remota, faz upload da local, ou baixa Eval no servidor
8. **`virt-install`** — cria disco qcow2 + VM com VNC em localhost
9. **noVNC** — sobe websockify/novnc_proxy na porta 6080
10. **Túnel** — encaminha 6080 (e VNC) para `127.0.0.1` no PC
11. **RDP/HTTP** — `socat` no Ubuntu para 80/443/3389/13389 → IP da guest

## Componentes principais no código

| Classe / função      | Papel                                              |
|----------------------|----------------------------------------------------|
| `App`                | GUI Tkinter, fila de status, orquestra o boot      |
| `SSH`                | Conexão, `run`, upload SFTP, criação de túneis     |
| `Tunnel`             | Forward TCP local → canal SSH `direct-tcpip`       |
| `read_ssh`           | Parser de `ssh.txt`                                |
| `find_local_iso`     | Localiza ISO via `iso.txt` ou pastas comuns        |
| `open_vps_window`    | Abre Edge/Chrome em modo app com a URL noVNC       |

## Por que o app precisa ficar aberto

Os túneis SSH são threads do processo Python. Se fechar a janela, `_close()` encerra o cliente SSH e o console noVNC deixa de funcionar. O RDP direto no IP público do VPS (via `socat`) pode continuar se o processo `socat` ainda estiver rodando no Ubuntu.

## Logs

- Interface: linha de detalhe na GUI
- Falhas graves: `erro.log` na pasta do app
- No servidor: `/tmp/novnc.log`, `/tmp/virt-winvps.log`, `/tmp/iso-dl.log`, `/tmp/fwd-*.log`
