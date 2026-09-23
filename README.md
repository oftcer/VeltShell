<p align="center">
  <img src="docs/assets/banner.svg" alt="VeltShell" width="720" />
</p>

<h1 align="center">VeltShell</h1>

<p align="center">
  <strong>Windows VPS em um clique</strong><br/>
  Sobe e abre um Windows dentro do seu VPS Ubuntu — console no navegador + RDP.
</p>

<p align="center">
  <a href="https://oftcer.com"><img src="https://img.shields.io/badge/site-oftcer.com-111111?style=flat-square" alt="oftcer.com" /></a>
  <a href="#instalação-rápida"><img src="https://img.shields.io/badge/Windows-10%2F11-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows" /></a>
  <a href="#instalação-rápida"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=flat-square" alt="MIT" /></a>
  <a href="docs/ARCHITECTURE.md"><img src="https://img.shields.io/badge/Stack-QEMU%20%7C%20libvirt%20%7C%20noVNC-0ea5e9?style=flat-square" alt="Stack" /></a>
</p>

---

## O que é

Aplicativo para **Windows** que se conecta por SSH ao seu **Ubuntu**, prepara QEMU/KVM + libvirt, cria (ou reabre) uma VM Windows e mostra a tela no Edge/Chrome via **noVNC** — com túnel SSH seguro. Também encaminha **HTTP/HTTPS/RDP** do VPS para a VM.

```text
Seu PC (Windows)  ──SSH──►  VPS Ubuntu  ──►  VM Windows
       │                         │
   noVNC local              QEMU / KVM
   mstsc (RDP)              portas 80/443/3389
```

> Deixe o app **aberto** enquanto usa o console noVNC (o túnel SSH vive no processo).

---

## Recursos

- Conexão SSH automática (Paramiko, com retries)
- Instalação dos pacotes no Ubuntu se faltarem
- Download da ISO Windows Server Eval no servidor (ou upload da sua ISO)
- Uso inteligente de RAM/CPU do host (reserva o necessário para o Ubuntu)
- Console noVNC em `127.0.0.1` (não expõe VNC na internet)
- Encaminhamento 80 / 443 / 3389 / 13389 → VM
- Empacotamento em `.exe` com um clique (`gerar_exe.bat`)

---

## Requisitos

| Onde | Precisa |
|------|---------|
| **PC** | Windows 10/11, Edge ou Chrome; Python 3.10+ se rodar pelo código |
| **VPS** | Ubuntu 20.04 / 22.04 / 24.04, SSH liberado, preferência KVM |

---

## Instalação rápida

Duplo clique em **`Instalar.bat`**. Ele instala a dependência, cria o `ssh.txt` se ainda não existir e abre o app.

### 1. Clone

```bash
git clone https://github.com/oftcer/VeltShell.git
cd VeltShell
```

### 2. Credenciais SSH

```bat
copy ssh.txt.example ssh.txt
```

Edite `ssh.txt` (uma linha por campo):

```text
IP_OU_HOSTNAME
usuario
senha
22
```

A porta (4ª linha) é opcional. **Nunca envie `ssh.txt` ao GitHub.**

### 3. ISO (opcional)

```bat
copy iso.txt.example iso.txt
```

Sem ISO local, o app baixa **Windows Server 2022 Evaluation** no servidor.

### 4. Rodar

```bat
pip install -r requirements.txt
python windows_vps.py
```

### 5. Gerar `.exe` (opcional)

```bat
gerar_exe.bat
```

Coloque `ssh.txt` na **mesma pasta** do `WindowsVPS.exe`.

---

## Estrutura

```text
VeltShell/
├── windows_vps.py          # App principal (GUI + SSH + virt)
├── requirements.txt
├── gerar_exe.bat           # Build do executável
├── WindowsVPS.spec
├── ssh.txt.example         # Modelo (versionado)
├── iso.txt.example         # Modelo (versionado)
├── LICENSE · README.md · SECURITY.md · CONTRIBUTING.md
└── docs/
    ├── ARCHITECTURE.md
    ├── CONFIG.md
    ├── TROUBLESHOOTING.md
    ├── GITHUB.md
    └── assets/banner.svg
```

Arquivos **só na sua máquina** (ignorados pelo Git): `ssh.txt`, `iso.txt`, `erro.log`, `*.iso`, `build/`, `dist/`, `WindowsVPS.exe`.

---

## Portas

| No Ubuntu | Na VM | Uso |
|-----------|-------|-----|
| 80 | 80 | HTTP |
| 443 | 443 | HTTPS |
| 3389 | 3389 | RDP |
| 13389 | 3389 | RDP alternativo |

No Windows da VM, libere o firewall. O noVNC fica só no túnel local (`127.0.0.1:6080`).

---

## Documentação

| Guia | Conteúdo |
|------|----------|
| [Arquitetura](docs/ARCHITECTURE.md) | Fluxo SSH → VM → noVNC → RDP |
| [Configuração](docs/CONFIG.md) | Arquivos e constantes |
| [Problemas](docs/TROUBLESHOOTING.md) | Erros comuns |
| [Publicar no GitHub](docs/GITHUB.md) | Como versionar com segurança |
| [Contribuir](CONTRIBUTING.md) | PRs e ideias |
| [Segurança](SECURITY.md) | Relatos e boas práticas |

---

## Segurança

- `ssh.txt` **não** entra no repositório (`.gitignore`)
- Se a senha vazou, **troque imediatamente** no VPS
- Prefira fail2ban / restrição de IP no SSH em produção

---

## Autor

[oftcer](https://oftcer.com)

---

## Licença

[MIT](LICENSE) — use e modifique livremente.

A ISO do Windows é da Microsoft (Evaluation / licença própria). Este projeto só automatiza o uso no ambiente que **você** controla.
