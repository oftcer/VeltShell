# Contribuindo

Obrigado por contribuir com o VeltShell.

## Antes de abrir um PR

1. Não inclua `ssh.txt`, senhas, IPs reais de produção, ISOs ou logs sensíveis
2. Teste no Windows com um VPS de laboratório
3. Mantenha o estilo do código existente (Python 3.10+, type hints leves, UI simples)

## Como contribuir

1. Faça um fork
2. Crie uma branch: `git checkout -b feature/minha-ideia`
3. Commit com mensagem clara
4. Abra um Pull Request descrevendo o problema e a solução

## Ideias úteis

- Autenticação SSH por chave (sem senha em arquivo)
- Interface para editar RAM/CPU/disco sem alterar o código
- Detecção e recriação limpa de VM corrompida
- Suporte a mais variantes de ISO (Windows 11, Server 2025, etc.)
- Testes automatizados das funções de parsing (`read_ssh`, `find_local_iso`)

## Reportar bugs

Inclua:

- Sistema do PC e versão do Python
- Distro/versão do Ubuntu no VPS
- Trecho relevante de `erro.log` (sem senhas)
- Se usa KVM ou QEMU
