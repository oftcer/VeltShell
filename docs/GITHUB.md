# Publicar no GitHub

Passo a passo para colocar este projeto no GitHub **sem vazar senha**.

## 1. Segurança antes de tudo

1. Confirme que `ssh.txt` **não** será commitado (já está no `.gitignore`)
2. Se a senha do VPS já ficou em algum lugar inseguro, **troque a senha agora**
3. Não suba `*.iso`, `erro.log`, `WindowsVPS.exe`, pastas `build/` ou `dist/`

Checklist rápido:

```bat
dir ssh.txt
```

Esse arquivo deve existir só na sua máquina. No GitHub deve aparecer apenas `ssh.txt.example`.

## 2. Inicializar o Git (se ainda não tiver)

No PowerShell, dentro da pasta do projeto:

```powershell
cd C:\xampp\htdocs\VeltShell
git init
git add .
git status
```

Revise o `git status`: **não** pode listar `ssh.txt`, `iso.txt` com dados reais, nem ISOs.

## 3. Primeiro commit

```powershell
git commit -m "Initial commit: VeltShell Windows VPS client and docs"
```

## 4. Criar o repositório no GitHub

1. Acesse https://github.com/new
2. Nome sugerido: `VeltShell`
3. Deixe **público** ou **privado** (privado se ainda for só seu)
4. **Não** marque “Add a README” (você já tem um)
5. Crie o repositório

## 5. Enviar

Substitua `SEU_USUARIO` pelo seu usuário GitHub:

```powershell
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/VeltShell.git
git push -u origin main
```

Com a CLI `gh`:

```powershell
gh repo create VeltShell --public --source=. --remote=origin --push
```

## 6. Depois do push

- No GitHub, abra o README e confira se a documentação aparece
- Em **About**, adicione descrição curta: *Cliente Windows para subir VM Windows em VPS Ubuntu via SSH/noVNC*
- Topics sugeridos: `qemu`, `libvirt`, `novnc`, `vps`, `windows`, `python`, `tkinter`

## 7. Releases (opcional)

Para publicar o `.exe` sem versionar no Git:

1. Rode `gerar_exe.bat`
2. GitHub → **Releases** → **Draft a new release**
3. Anexe `WindowsVPS.exe`
4. No texto do release, lembre: o usuário precisa criar `ssh.txt` ao lado do exe
