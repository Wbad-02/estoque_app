# SISTEMA DE CONTROLE DE ESTOQUE — DOCUMENTAÇÃO TÉCNICA DE IMPLANTAÇÃO E OPERAÇÃO

**Responsável técnico:** Wemerson Damascena  
**Repositório privado:** https://github.com/Wbad-02/estoque_privado  
**URL de produção:** https://estoque.upgradecontabilidade.com  
**Última atualização:** 25 de maio de 2026  
**Versão do sistema:** 3.1.0  

---

## RESUMO

Este documento descreve os procedimentos técnicos de implantação, operação, atualização e resolução de problemas do Sistema de Controle de Estoque, desenvolvido em Python com o framework FastAPI e banco de dados SQLite. O sistema é exposto publicamente por meio de túnel Cloudflare, sem necessidade de IP fixo ou abertura de portas no firewall externo. Ambos os processos críticos — servidor de aplicação e agente de túnel — operam como serviços Windows gerenciados pelo NSSM, garantindo reinicialização automática após reinicialização do servidor.

**Palavras-chave:** FastAPI. Cloudflare Tunnel. NSSM. Windows Server. Controle de estoque.

---

## SUMÁRIO

1. Arquitetura do sistema  
2. Ambiente de servidor  
3. Variáveis de ambiente  
4. Serviços Windows  
   4.1 EstoqueApp  
   4.2 CloudflaredTunnel  
5. Inicialização e parada manual  
6. Atualização do sistema  
7. Verificação de saúde  
8. Infraestrutura Cloudflare  
9. Funcionalidades do sistema  
10. Resolução de problemas  
11. Referências de configuração  

---

## 1 ARQUITETURA DO SISTEMA

A Figura 1 ilustra o fluxo completo de uma requisição externa até o banco de dados.

**Figura 1 — Diagrama de fluxo da requisição**

```
Usuário (internet)
       │
       ▼ HTTPS / TLS
Cloudflare Edge (anycast — servidores globais)
       │
       ▼ QUIC / protocolo proprietário (túnel criptografado)
cloudflared.exe  ←  serviço: CloudflaredTunnel  (C:\cloudflared\)
       │
       ▼ HTTP  localhost:8000
Uvicorn + FastAPI  ←  serviço: EstoqueApp  (C:\estoque_app\)
       │
       ▼
SQLite  (C:\estoque_app\estoque.db)
```

**Fonte:** elaboração própria (2026).

O túnel Cloudflare elimina a necessidade de IP público fixo, abertura de portas no roteador ou configuração de SSL próprio, pois a terminação TLS ocorre na borda da Cloudflare.

---

## 2 AMBIENTE DE SERVIDOR

O Quadro 1 apresenta as especificações do ambiente de produção.

**Quadro 1 — Especificações do servidor de produção**

| Componente | Valor |
|---|---|
| Sistema operacional | Windows Server (Administrator) |
| Python | 3.12 — `C:\Program Files\Python312\` |
| Diretório da aplicação | `C:\estoque_app\` |
| Banco de dados | `C:\estoque_app\estoque.db` (SQLite) |
| Agente de túnel | `C:\cloudflared\cloudflared.exe` |
| Configuração do túnel | `C:\cloudflared\config.yml` |
| Gerenciador de serviços | NSSM (Non-Sucking Service Manager) |

**Fonte:** elaboração própria (2026).

---

## 3 VARIÁVEIS DE AMBIENTE

As variáveis do Quadro 2 devem estar definidas no escopo `Machine` (sistema) para que os serviços Windows as leiam corretamente.

**Quadro 2 — Variáveis de ambiente obrigatórias**

| Variável | Finalidade | Escopo |
|---|---|---|
| `ESTOQUE_SECRET_KEY` | Chave de assinatura JWT (hex 64 chars) | Machine |
| `DESABILITAR_WHITELIST_IP` | Libera acesso de qualquer origem (`true` em produção internet) | Machine |
| `CORS_ORIGINS` | Origens permitidas nas requisições CORS | Machine |

**Código 1 — Verificar variável de ambiente**
```powershell
[System.Environment]::GetEnvironmentVariable("ESTOQUE_SECRET_KEY", "Machine")
```

**Código 2 — Gerar nova chave secreta**
```powershell
& "C:\Program Files\Python312\python.exe" -c "import secrets; print(secrets.token_hex(32))"
```

**Código 3 — Definir variável permanentemente**
```powershell
[System.Environment]::SetEnvironmentVariable("ESTOQUE_SECRET_KEY", "COLE_A_CHAVE_AQUI", "Machine")
```

Após alterar variáveis de escopo `Machine`, é necessário reiniciar os serviços para que as leitura seja atualizada.

---

## 4 SERVIÇOS WINDOWS

Ambos os processos críticos são gerenciados pelo NSSM e configurados para inicialização automática (`SERVICE_AUTO_START`), de modo que uma reinicialização do servidor os retoma sem intervenção manual.

**Código 4 — Verificar status de ambos os serviços**
```powershell
Get-Service EstoqueApp, CloudflaredTunnel | Select-Object Status, StartType, DisplayName
```

Resultado esperado: `Status = Running` e `StartType = Automatic` para os dois serviços.

### 4.1 EstoqueApp

Serviço que executa o servidor FastAPI/Uvicorn na porta 8000.

**Código 5 — Instalação do serviço EstoqueApp via NSSM**
```powershell
nssm install EstoqueApp "C:\Program Files\Python312\python.exe"
nssm set EstoqueApp AppDirectory "C:\estoque_app"
nssm set EstoqueApp AppParameters "-m uvicorn main:app --host 0.0.0.0 --port 8000"
nssm set EstoqueApp DisplayName "Sistema de Estoque"
nssm set EstoqueApp Start SERVICE_AUTO_START
nssm start EstoqueApp
```

**Código 6 — Operações básicas do EstoqueApp**
```powershell
Start-Service EstoqueApp
Stop-Service EstoqueApp
Restart-Service EstoqueApp
Get-Service EstoqueApp | Select-Object Status
```

### 4.2 CloudflaredTunnel

Serviço que mantém o túnel criptografado entre o servidor e a borda da Cloudflare.

> **Atenção:** utilizar o serviço NSSM (`CloudflaredTunnel`), e não o serviço nativo instalado pelo comando `cloudflared service install`, que apresentou instabilidade na reinicialização (conexões não eram restabelecidas automaticamente).

**Código 7 — Instalação do serviço CloudflaredTunnel via NSSM**
```powershell
nssm install CloudflaredTunnel "C:\cloudflared\cloudflared.exe"
nssm set CloudflaredTunnel AppParameters "tunnel --config C:\cloudflared\config.yml run"
nssm set CloudflaredTunnel DisplayName "Cloudflare Tunnel"
nssm set CloudflaredTunnel Start SERVICE_AUTO_START
nssm start CloudflaredTunnel
```

**Código 8 — Operações básicas do CloudflaredTunnel**
```powershell
Start-Service CloudflaredTunnel
Stop-Service CloudflaredTunnel
Restart-Service CloudflaredTunnel
Get-Service CloudflaredTunnel | Select-Object Status
```

---

## 5 INICIALIZAÇÃO E PARADA MANUAL

O modo manual é indicado apenas para depuração, pois exibe os logs em tempo real no terminal.

**Código 9 — Inicialização manual para depuração**
```powershell
# Terminal 1 — Sistema de estoque
Stop-Service EstoqueApp   # para o serviço para liberar a porta
cd C:\estoque_app
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Túnel Cloudflare
Stop-Service CloudflaredTunnel
& "C:\cloudflared\cloudflared.exe" tunnel --config "C:\cloudflared\config.yml" run
```

**Código 10 — Retorno ao modo serviço após depuração**
```powershell
# Encerrar processos manuais (Ctrl+C nos terminais) e reativar serviços
Start-Service EstoqueApp
Start-Service CloudflaredTunnel
```

---

## 6 ATUALIZAÇÃO DO SISTEMA

O fluxo de atualização segue o modelo de dois repositórios: `origin` (público, referência) e `privado` (privado, usado pelo servidor).

### 6.1 Máquina de desenvolvimento

**Código 11 — Enviar alterações para o repositório privado**
```powershell
cd "i:\Meu Drive\WEMERSON\APLICATIVOS\estoque_app"
git add .
git commit -m "descricao da mudanca em ingles"
git push privado master
```

### 6.2 Servidor de produção

**Código 12 — Aplicar atualização no servidor**
```powershell
cd C:\estoque_app
git pull origin master
Restart-Service EstoqueApp
```

> **Observação:** o remote `origin` do servidor aponta para `https://github.com/Wbad-02/estoque_privado.git`. Caso o servidor exiba erro `fatal: 'privado' does not appear to be a git repository`, verificar a URL do remote com `git remote -v` e corrigir com `git remote set-url origin <url-com-token>`.

**Código 13 — Executar migrações do banco após atualização**
```powershell
cd C:\estoque_app
python migrar_banco.py
Restart-Service EstoqueApp
```

---

## 7 VERIFICAÇÃO DE SAÚDE

O Quadro 3 apresenta o checklist completo de verificação do sistema.

**Quadro 3 — Checklist de saúde do sistema**

| Verificação | Comando | Resultado esperado |
|---|---|---|
| EstoqueApp rodando | `Get-Service EstoqueApp` | `Status = Running` |
| CloudflaredTunnel rodando | `Get-Service CloudflaredTunnel` | `Status = Running` |
| Porta 8000 ativa | `netstat -ano \| findstr :8000` | `LISTENING` |
| API respondendo local | `Invoke-WebRequest http://localhost:8000` | `StatusCode 200` |
| Túnel com conexões ativas | `cloudflared tunnel list` | 1–4 conexões na coluna CONNECTIONS |
| URL externa acessível | Abrir no browser externo | Página de login carrega |

**Código 14 — Verificação completa em bloco único**
```powershell
# Serviços
Get-Service EstoqueApp, CloudflaredTunnel | Select-Object Status, DisplayName

# Porta
netstat -ano | findstr :8000

# Conexões do túnel
& "C:\cloudflared\cloudflared.exe" tunnel list

# Métricas em tempo real (número de conexões ativas deve ser 4)
Invoke-WebRequest -Uri "http://127.0.0.1:20241/metrics" -UseBasicParsing |
  Select-Object -ExpandProperty Content |
  Select-String "ha_connections"
```

---

## 8 INFRAESTRUTURA CLOUDFLARE

### 8.1 Túnel

**Quadro 4 — Dados do túnel Cloudflare**

| Campo | Valor |
|---|---|
| Tunnel ID | `86b50779-7d5a-4908-ac66-3278537a4068` |
| Nome | estoque |
| Criado em | 08 mai. 2026 |
| Config | `C:\cloudflared\config.yml` |
| Credenciais | `C:\cloudflared\86b50779-7d5a-4908-ac66-3278537a4068.json` |
| Protocolo | QUIC |

**Código 15 — Conteúdo de `C:\cloudflared\config.yml`**
```yaml
tunnel: 86b50779-7d5a-4908-ac66-3278537a4068
credentials-file: C:\cloudflared\86b50779-7d5a-4908-ac66-3278537a4068.json

ingress:
  - hostname: estoque.upgradecontabilidade.com
    service: http://localhost:8000
  - service: http_status:404
```

### 8.2 DNS

**Quadro 5 — Configuração de DNS**

| Campo | Valor |
|---|---|
| Registrador | HostGator Brasil |
| Nameserver primário | `irena.ns.cloudflare.com` |
| Nameserver secundário | `tim.ns.cloudflare.com` |
| CNAME | `estoque.upgradecontabilidade.com → 86b50779...cfargotunnel.com` |

**Nameservers originais HostGator (para reverter, se necessário):**
```
ns156.hostgator.com.br
ns157.hostgator.com.br
```

---

## 9 FUNCIONALIDADES DO SISTEMA

### 9.1 Requerimentos de compra

O módulo de requerimentos permite criar, aprovar e rejeitar pedidos de compra, com suporte a importação e exportação de planilhas Excel.

#### 9.1.1 Estrutura da planilha Excel

**Quadro 6 — Colunas da planilha de requerimento (5 colunas)**

| Coluna | Campo | Descrição |
|---|---|---|
| A | Nome | Nome do item/produto |
| B | Link (URL) | URL do produto (ex.: Mercado Livre, Amazon) — opcional |
| C | Qtd | Quantidade solicitada |
| D | Valor Unitário (R$) | Preço unitário |
| E | Subtotal (R$) | Calculado automaticamente (=C×D) |

#### 9.1.2 Fluxo de importação Excel

A importação via botão **Importar Excel** carrega os itens da planilha no formulário de criação, permitindo revisão antes de confirmar. O requerimento somente é criado ao clicar em **Criar requerimento**.

#### 9.1.3 Links nos e-mails

Os e-mails de notificação utilizam a URL de produção `https://estoque.upgradecontabilidade.com` como base. O link da notificação de **solicitação de estoque** aponta diretamente para a aba "Solicitações de Estoque" dentro da página de Requerimentos, via hash `/#requerimentos:sol`.

### 9.2 Solicitações de estoque

Notificações enviadas a administradores quando um colaborador solicita retirada de material. O botão de e-mail redireciona o aprovador para a aba correta:

```
https://estoque.upgradecontabilidade.com/#requerimentos:sol
```

---

## 10 RESOLUÇÃO DE PROBLEMAS

### 10.1 Túnel sem conexão ativa (Error 1033)

O erro 1033 da Cloudflare indica que o túnel não tem conexões ativas com a borda. Verificar se o serviço `CloudflaredTunnel` está Running. Se estiver Running mas sem conexões na coluna `CONNECTIONS` do `tunnel list`, reiniciar o serviço:

**Código 16 — Resolução do Error 1033**
```powershell
Restart-Service CloudflaredTunnel
Start-Sleep -Seconds 8
& "C:\cloudflared\cloudflared.exe" tunnel list
```

Se o serviço não responder, forçar via processo:

**Código 17 — Força reinicialização do cloudflared**
```powershell
$pid = (Get-Process -Name cloudflared -ErrorAction SilentlyContinue).Id
if ($pid) { taskkill /PID $pid /F }
Start-Service CloudflaredTunnel
```

### 10.2 Porta 8000 já em uso

**Código 18 — Liberação da porta 8000**
```powershell
netstat -ano | findstr :8000
# Anote o PID da linha LISTENING e execute:
taskkill /PID <PID> /F
Start-Service EstoqueApp
```

### 10.3 EstoqueApp não inicia após atualização

Verificar se há erro de sintaxe ou migração pendente:

**Código 19 — Diagnóstico de inicialização**
```powershell
cd C:\estoque_app
python -c "from routers import requerimentos, solicitacoes; print('OK')"
python migrar_banco.py
Restart-Service EstoqueApp
```

### 10.4 Credencial Git inválida no servidor

Caso `git pull` falhe por autenticação, atualizar a URL do remote com o token PAT do GitHub:

**Código 20 — Atualizar remote com token PAT**
```powershell
git remote set-url origin https://<USUARIO>:<TOKEN>@github.com/Wbad-02/estoque_privado.git
git pull origin master
```

> **Atenção de segurança:** após usar o token em linha de comando, regenerá-lo em **github.com → Settings → Developer settings → Personal access tokens** para invalidar a versão exposta.

### 10.5 Redefinição de senha de usuário

**Código 21 — Redefinir senha de usuário pelo banco**
```powershell
cd C:\estoque_app
& "C:\Program Files\Python312\python.exe" -c "
from database import get_db
from models import Usuario
from auth import hash_senha
db = next(get_db())
u = db.query(Usuario).filter(Usuario.email == 'EMAIL_AQUI').first()
if u:
    u.senha_hash = hash_senha('NOVA_SENHA')
    u.ativo = True
    db.commit()
    print('Senha redefinida')
"
```

---

## 11 REFERÊNCIAS DE CONFIGURAÇÃO

**Quadro 7 — Remotes Git configurados**

| Alias | URL | Uso |
|---|---|---|
| `privado` | `https://github.com/Wbad-02/estoque_privado.git` | Push da máquina de desenvolvimento |
| `origin` (servidor) | `https://github.com/Wbad-02/estoque_privado.git` | Pull no servidor de produção |
| `origin` (dev) | `https://github.com/Wbad-02/estoque_app.git` | Repositório público de referência |

**Quadro 8 — Versões de componentes em produção**

| Componente | Versão |
|---|---|
| Python | 3.12 |
| FastAPI | conforme `requirements.txt` |
| Uvicorn | conforme `requirements.txt` |
| openpyxl | 3.1.2 |
| cloudflared | 2026.3.0 (atualização recomendada: 2026.5.1) |
| SQLite | nativo do Python 3.12 |

---

*Documento elaborado conforme padrões técnicos internos. Atualização obrigatória a cada alteração de infraestrutura ou implantação de funcionalidade crítica.*
