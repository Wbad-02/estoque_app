@echo off
:: © Todos os direitos reservados – github.com/Wbad-02
title Sistema de Controle de Estoque
echo.
echo  ╔══════════════════════════════════════╗
echo  ║   Sistema de Controle de Estoque     ║
echo  ║   github.com/Wbad-02                 ║
echo  ╚══════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado.
    pause & exit /b 1
)
echo [INFO] Python detectado:
python --version

:: Verificar chave secreta JWT
if "%ESTOQUE_SECRET_KEY%"=="" (
    echo.
    echo [AVISO] Variavel ESTOQUE_SECRET_KEY nao definida.
    echo         Os tokens JWT serao invalidos ao reiniciar o servidor.
    echo         Consulte security\README_SEGURANCA.md - Passo 5.
    echo.
)

:: Instalar/atualizar dependencias
if exist ".deps_ok" del ".deps_ok"
echo [INFO] Verificando dependencias...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias.
    pause & exit /b 1
)
echo ok > .deps_ok

:: Migrar banco de dados (seguro — preserva todos os dados)
if exist estoque.db (
    echo [INFO] Verificando atualizacoes do banco de dados...
    python migrar_banco.py
)

echo.
echo [INFO] Servidor iniciando em http://localhost:8000
echo [INFO] Rede interna: http://%COMPUTERNAME%:8000
echo [INFO] Pressione CTRL+C para encerrar.
echo.
echo [SEGURANCA] Whitelist de IP e rate limiting ativos.
echo [SEGURANCA] Consulte security\README_SEGURANCA.md para configuracao completa.
echo.

:: Abrir navegador
start /b cmd /c "timeout /t 2 >nul && start http://localhost:8000"

:: Iniciar FastAPI
python -m uvicorn main:app --host 0.0.0.0 --port 8000

pause
