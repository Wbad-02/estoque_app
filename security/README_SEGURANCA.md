# 🔒 Guia de Segurança — Sistema de Controle de Estoque
**© Todos os direitos reservados – github.com/Wbad-02**

---

## Camadas de segurança implementadas

### 1. Aplicação (Python/FastAPI)
| Mecanismo | Onde | O que faz |
|---|---|---|
| Whitelist de IP/CIDR | `middleware_seguranca.py` | Bloqueia qualquer IP fora da rede interna |
| Rate limiting geral | `middleware_seguranca.py` | Máx. 60 req/min por IP |
| Rate limiting login | `middleware_seguranca.py` | Máx. 10 tentativas/5min por IP |
| Security headers HTTP | `middleware_seguranca.py` | XSS, Clickjacking, MIME sniff, CSP |
| bcrypt cost 12 | `auth.py` | Senhas resistentes a brute-force |
| JWT com expiração 8h | `auth.py` | Sessões limitadas no tempo |
| Chave JWT via env var | `auth.py` | Segredo não fica no código-fonte |
| RBAC (3 níveis) | routers | Admin / Editor / Viewer |
| Log de auditoria | `models.py` | Toda ação sensível é registrada |
| Docs API desativados | `main.py` | /docs e /openapi.json desabilitados |

### 2. Rede / Windows Server
| Script | O que faz |
|---|---|
| `configurar_firewall_windows.ps1` | Cria regras no Windows Firewall bloqueando acesso externo à porta 8000 |
| `configurar_rede_windows.ps1` | Define IP estático e máscara de rede no servidor |
| `monitorar_acessos.ps1` | Monitor em tempo real das conexões ativas |
| `backup_automatico.ps1` | Backup diário do banco SQLite com retenção de 30 dias |

---

## Passo a passo de instalação segura

### Passo 1 — Descobrir sua sub-rede
Abra o CMD e execute:
```
ipconfig
```
Anote o valor de **Endereço IPv4** e **Máscara de Sub-rede**.
Exemplo: IP `192.168.1.50`, Máscara `255.255.255.0` → Sub-rede: `192.168.1.0/24`

### Passo 2 — Configurar IP estático no servidor
```powershell
# Execute como Administrador:
.\security\configurar_rede_windows.ps1
# (sem parâmetros primeiro — ele lista os adaptadores disponíveis)

# Depois execute com seus valores:
.\security\configurar_rede_windows.ps1 `
    -Adaptador "Ethernet" `
    -IPServidor "192.168.1.10" `
    -MascaraRede "255.255.255.0" `
    -Gateway "192.168.1.1"
```

### Passo 3 — Atualizar a whitelist de IP na aplicação
Abra o arquivo `middleware_seguranca.py` e ajuste:
```python
REDES_PERMITIDAS: list[str] = [
    "127.0.0.1/32",       # localhost — obrigatório
    "::1/128",            # localhost IPv6
    "192.168.1.0/24",     # ← coloque AQUI sua sub-rede real
]
```

### Passo 4 — Configurar o Firewall do Windows
```powershell
# Execute como Administrador:
.\security\configurar_firewall_windows.ps1 -SubRede "192.168.1.0/24" -Porta 8000
```

### Passo 5 — Definir a chave secreta JWT
Abra o PowerShell e execute:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Copie o resultado e defina como variável de ambiente **permanente**:
```powershell
# Como Administrador:
[System.Environment]::SetEnvironmentVariable(
    "ESTOQUE_SECRET_KEY",
    "cole_aqui_o_valor_gerado",
    "Machine"   # Machine = permanente para todos os usuários
)
```
Reinicie o servidor após isso.

### Passo 6 — Agendar backup automático
1. Abra o **Agendador de Tarefas** do Windows
2. Clique em **Criar Tarefa**
3. Nome: `Backup Estoque`
4. Gatilho: Diariamente às 23:00
5. Ação: `powershell.exe -File "C:\caminho\estoque_app\security\backup_automatico.ps1"`
6. Executar como: conta do sistema ou administrador

---

## O que cada sub-rede significa

| CIDR | Faixa de IPs | Hosts | Quando usar |
|---|---|---|---|
| `192.168.1.0/24` | .1 até .254 | 254 | Escritório pequeno (recomendado) |
| `192.168.0.0/16` | .0.1 até .255.254 | 65534 | Vários andares/departamentos |
| `10.0.0.0/8` | 10.x.x.x | 16M | Corporativo amplo (evitar se possível) |

**Regra de ouro:** use sempre a faixa mais restrita possível.

---

## Checklist de segurança pós-instalação

- [ ] IP estático configurado no servidor
- [ ] Sub-rede real inserida em `REDES_PERMITIDAS`
- [ ] Firewall do Windows configurado com o script
- [ ] Variável `ESTOQUE_SECRET_KEY` definida no sistema
- [ ] Senha do admin padrão trocada (`admin@estoque.local` / `admin123`)
- [ ] Backup automático agendado
- [ ] Testado acesso de outro PC da rede: `http://IP_SERVIDOR:8000`
- [ ] Testado bloqueio de acesso de fora da rede (usar hotspot do celular)
