# Configuração

## Arquivos locais

### `ssh.txt` (obrigatório)

Copie de `ssh.txt.example`.

```text
208.x.x.x
root
senha_secreta
22
```

| Linha | Campo    | Obrigatório | Descrição                |
|-------|----------|-------------|--------------------------|
| 1     | Host     | Sim         | IP ou hostname do Ubuntu |
| 2     | Usuário  | Sim         | Ex.: `root`              |
| 3     | Senha    | Sim         | Senha SSH                |
| 4     | Porta    | Não         | Padrão `22`              |

O arquivo deve ficar na **mesma pasta** do `windows_vps.py` ou do `WindowsVPS.exe`.

### `iso.txt` (opcional)

Copie de `iso.txt.example`.

```text
C:\Users\SeuUsuario\Downloads\WinServer2022Eval.iso
```

- Linhas vazias e linhas começando com `#` são ignoradas
- Se inválido/ausente, o app procura `*.iso` na pasta do projeto e em Downloads
- Se ainda não achar, baixa a Eval oficial no servidor (`WIN_ISO_URL` no código)

## Constantes no código (`windows_vps.py`)

Você pode editar estes valores no topo do arquivo:

| Constante             | Padrão     | Significado                                      |
|-----------------------|------------|--------------------------------------------------|
| `VM_NAME`             | `winvps`   | Nome da VM no libvirt                            |
| `DISK_GB`             | `400`      | Tamanho do disco qcow2 na criação                |
| `HOST_RAM_RESERVE_MB` | `8192`     | RAM reservada para o Ubuntu                      |
| `HOST_CPU_RESERVE`    | `2`        | CPUs reservadas para o Ubuntu                    |
| `VNC_PORT`            | `5901`     | Porta VNC preferida na criação                   |
| `NOVNC_PORT`          | `6080`     | Porta do console web                             |
| `OS_VARIANT`          | `win2k22`  | Variante libosinfo (`win10` / `win11` auto)      |
| `REMOTE_ISO_DIR`      | `/opt/iso` | Pasta remota das ISOs                            |
| `REMOTE_DISK_DIR`     | `/var/lib/libvirt/images` | Pasta dos discos virtuais          |

RAM e vCPUs efetivos são calculados automaticamente a partir do host (`_detect_host_limits`).

## Dependências Python

Arquivo `requirements.txt`:

```text
paramiko>=3.4.0
pyinstaller>=6.0.0
```

- **paramiko** — SSH/SFTP/túneis
- **pyinstaller** — só para gerar o `.exe`
- **tkinter** — vem com o Python no Windows (não está no pip)

## Gerar executável

```bat
gerar_exe.bat
```

Equivalente manual:

```bat
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "WindowsVPS" --hidden-import=paramiko --collect-all paramiko windows_vps.py
```

O `.exe` final fica em `dist\WindowsVPS.exe` e é copiado para a raiz como `WindowsVPS.exe`.

## Firewall / provedor do VPS

Libere no painel do provedor (além do SSH):

- **3389** (e/ou **13389**) — RDP
- **80** / **443** — se for hospedar site na VM Windows

O noVNC **não** precisa ficar exposto na internet: o acesso é pelo túnel local `127.0.0.1:6080`.
