# Solução de problemas

## SSH falha / “servidor fechou a conexão”

- Confirme IP, usuário e senha em `ssh.txt`
- Feche **todas** as janelas do WindowsVPS e espere ~1 minuto (fail2ban / limite de conexões)
- Teste no terminal: `ssh usuario@IP -p PORTA`
- Verifique se o provedor libera a porta SSH

## “Falta ssh.txt”

O arquivo precisa estar na mesma pasta do script/exe. Crie a partir do exemplo:

```bat
copy ssh.txt.example ssh.txt
```

## Timeout ao baixar a ISO

- Confira a internet do VPS (`ping 8.8.8.8`, `curl -I https://microsoft.com`)
- Ou coloque uma ISO local e aponte em `iso.txt`
- No servidor, veja `/tmp/iso-dl.log`

## VM não inicia

No Ubuntu:

```bash
virsh list --all
virsh domstate winvps
tail -n 80 /tmp/virt-winvps.log
```

Causas comuns: disco cheio, ISO incompleta, falta de KVM sem espaço/CPU suficiente.

## Console noVNC em branco

- Deixe o app **aberto** (túnel SSH)
- Veja `/tmp/novnc.log` no servidor
- Confirme se a porta 6080 está escutando: `ss -lntp | grep 6080`
- Tente a URL lite: `http://127.0.0.1:6080/vnc_lite.html?autoconnect=true`

## RDP não conecta

- Dentro do Windows da VM: ative Área de Trabalho Remota
- Firewall do Windows: permita 3389 (e 80/443 se for web)
- No Ubuntu: `ss -lntp | egrep ':(80|443|3389|13389)'`
- Teste também `IP_DO_VPS:13389`
- O IP interno da guest precisa existir (`virsh domifaddr winvps`)

## Sem KVM (muito lento)

Sem `/dev/kvm` o app usa emulação QEMU. No provedor, ative nested virtualização / CPU com VT-x/AMD-V, ou escolha um plano que permita KVM.

## Erros gravados localmente

Se a GUI mostrar erro, abra `erro.log` na pasta do app — contém o traceback completo.

## Paramiko ausente

```bat
pip install -r requirements.txt
```
