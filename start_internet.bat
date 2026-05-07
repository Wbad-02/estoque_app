@echo off
:: © Todos os direitos reservados – github.com/Wbad-02
title Sistema de Estoque — Modo Internet
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║   Sistema de Controle de Estoque                ║
echo  ║   Modo Internet — estoque.upgradecontabilidade.com ║
echo  ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado. Instale em python.org
    pause & exit /b 1
)

:: Configuracoes de seguranca para internet
set DESABILITAR_WHITELIST_IP=true
set CORS_ORIGINS=https://estoque.upgradecontabilidade.com

:: Verificar chave JWT obrigatoria
if "%ESTOQUE_SECRET_KEY%"=="" (
    echo.
    echo [ERRO] Variavel ESTOQUE_SECRET_KEY nao definida!
    echo.
    echo  Gere uma chave com o comando abaixo e defina nas variaveis
    echo  de ambiente do sistema antes de rodar este arquivo:
    echo.
    echo    python -c "import secrets; print(secrets.token_hex(32))"
    echo.
    echo  Windows: Painel de Controle ^> Sistema ^> Variaveis de Ambiente
    echo           Nova variavel do sistema: ESTOQUE_SECRET_KEY = ^<chave^>
    echo.
    pause & exit /b 1
)

:: Instalar dependencias
echo [INFO] Verificando dependencias...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias.
    pause & exit /b 1
)

:: Migrar banco
if exist estoque.db (
    echo [INFO] Verificando atualizacoes do banco de dados...
    python migrar_banco.py
)

echo.
echo [INFO] Servidor iniciando em http://localhost:8000
echo [INFO] Acesso externo: https://estoque.upgradecontabilidade.com
echo [INFO] Whitelist de IP: DESATIVADA (modo internet)
echo [INFO] Pressione CTRL+C para encerrar.
echo.

:: Iniciar FastAPI
python -m uvicorn main:app --host 0.0.0.0 --port 8000

pause
