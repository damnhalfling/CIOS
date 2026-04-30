#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  Harmoni — Instalador de Sessão X
#  Registra "Harmoni" como opção no display manager
# ═══════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║  Harmoni — Instalação de Sessão X    ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# --- 1. Verificar dependências ---
echo "  → Verificando dependências..."

MISSING=""
if ! command -v openbox &>/dev/null; then
    MISSING="${MISSING} openbox"
fi

if [ -n "${MISSING}" ]; then
    echo ""
    echo "  ⚠ Pacotes necessários não encontrados:${MISSING}"
    echo ""
    read -p "  Instalar agora? (sudo apt install${MISSING}) [S/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "  ✗ Instalação cancelada"
        exit 1
    fi
    sudo apt install -y ${MISSING}
    echo "  ✓ Dependências instaladas"
fi

# wmctrl é opcional (pra tecla Super focar no Harmoni)
if ! command -v wmctrl &>/dev/null; then
    echo "  → Instalando wmctrl (opcional, pra tecla Super)..."
    sudo apt install -y wmctrl 2>/dev/null || echo "  ⚠ wmctrl não disponível (Super key não vai funcionar)"
fi

# --- 2. Instalar script de sessão ---
echo "  → Instalando script de sessão..."

sudo cp "${SCRIPT_DIR}/harmoni-session.sh" /usr/local/bin/harmoni-session
sudo chmod +x /usr/local/bin/harmoni-session
echo "  ✓ /usr/local/bin/harmoni-session"

# --- 3. Registrar sessão no display manager ---
echo "  → Registrando sessão X..."

sudo cp "${SCRIPT_DIR}/harmoni.desktop" /usr/share/xsessions/harmoni.desktop
echo "  ✓ /usr/share/xsessions/harmoni.desktop"

# --- 4. Configurar Openbox pra esta sessão ---
echo "  → Configurando Openbox..."

OPENBOX_CONF="${HOME}/.config/openbox-harmoni"
mkdir -p "${OPENBOX_CONF}"
cp "${SCRIPT_DIR}/rc.xml" "${OPENBOX_CONF}/rc.xml"
cp "${SCRIPT_DIR}/autostart" "${OPENBOX_CONF}/autostart"
chmod +x "${OPENBOX_CONF}/autostart"
echo "  ✓ ${OPENBOX_CONF}/"

# --- 5. Garantir que o Harmoni está instalado ---
echo "  → Verificando instalação do Harmoni..."

if [ ! -x "${HOME}/.local/bin/harmoni" ] && ! command -v harmoni &>/dev/null; then
    echo "  → Harmoni não encontrado, instalando..."
    bash "${PROJECT_DIR}/install.sh"
else
    echo "  ✓ Harmoni já instalado"
fi

# --- 6. Resumo ---
echo ""
echo "  ═══════════════════════════════════════════"
echo "  Sessão instalada com sucesso!"
echo "  ═══════════════════════════════════════════"
echo ""
echo "  Para usar:"
echo "    1. Faça logout"
echo "    2. Na tela de login, selecione 'Harmoni'"
echo "    3. Faça login normalmente"
echo ""
echo "  A sessão GNOME continua disponível como fallback."
echo ""
echo "  Atalhos na sessão Harmoni:"
echo "    Alt+Tab     → trocar janelas"
echo "    Alt+F4      → fechar janela"
echo "    Super       → focar no Harmoni"
echo "    F11         → fullscreen"
echo ""
