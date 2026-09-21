# Política de segurança

## Relatar vulnerabilidades

Se encontrar um problema de segurança (vazamento de credenciais, execução remota inesperada, etc.), **não abra issue pública** com detalhes exploráveis.

Envie um relatório privado ao mantenedor do repositório (aba **Security** do GitHub, se habilitada, ou contato indicado no perfil).

## Boas práticas para quem usa

- Nunca versione `ssh.txt`
- Prefira senhas fortes e, quando possível, restrição de IP no SSH / fail2ban
- Mantenha o VPS atualizado (`apt upgrade`)
- Lembre que o app autentica por senha e usa `AutoAddPolicy` no Paramiko (aceita host key na primeira conexão) — adequado a laboratório; em produção considere pinagem de host key e autenticação por chave
