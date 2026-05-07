"""Skill: explore_system — show what CIOS can do.

Lists all capabilities grouped by category. Designed to answer
"o que posso fazer?", "me ajuda", "what can you do?".

No LLM. Pure static knowledge about the system's own skills.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from cios.skills.app_launcher import get_installed_apps

logger = logging.getLogger(__name__)


@dataclass
class Capability:
    """A single thing CIOS can do."""
    category: str       # "sistema", "apps", "arquivos", etc.
    icon: str           # emoji
    examples_pt: list[str]
    examples_en: list[str]
    description_pt: str
    description_en: str


# All capabilities — static, no LLM needed
_CAPABILITIES: list[Capability] = [
    Capability(
        category="apps",
        icon="🚀",
        examples_pt=["abrir chrome", "abrir terminal", "abrir spotify"],
        examples_en=["open chrome", "open terminal", "open spotify"],
        description_pt="Abrir qualquer aplicativo instalado",
        description_en="Open any installed application",
    ),
    Capability(
        category="rede",
        icon="📶",
        examples_pt=["conectar wifi", "listar redes", "qual minha rede?"],
        examples_en=["connect wifi", "list networks", "what's my network?"],
        description_pt="Gerenciar Wi-Fi: conectar, desconectar, listar redes",
        description_en="Manage Wi-Fi: connect, disconnect, list networks",
    ),
    Capability(
        category="áudio",
        icon="🔊",
        examples_pt=["aumentar volume", "silenciar", "volume 50%"],
        examples_en=["volume up", "mute", "volume 50%"],
        description_pt="Controlar volume: aumentar, diminuir, silenciar",
        description_en="Control volume: up, down, mute",
    ),
    Capability(
        category="bluetooth",
        icon="🔵",
        examples_pt=["conectar bluetooth", "escanear bluetooth", "listar dispositivos"],
        examples_en=["connect bluetooth", "scan bluetooth", "list devices"],
        description_pt="Gerenciar Bluetooth: conectar, parear, escanear",
        description_en="Manage Bluetooth: connect, pair, scan",
    ),
    Capability(
        category="energia",
        icon="🔋",
        examples_pt=["quanta bateria?", "aumentar brilho", "modo economia"],
        examples_en=["battery status", "brightness up", "power saving"],
        description_pt="Bateria, brilho e modo economia de energia",
        description_en="Battery, brightness and power saving mode",
    ),
    Capability(
        category="janelas",
        icon="🪟",
        examples_pt=["janelas abertas", "fechar chrome", "janela para esquerda"],
        examples_en=["open windows", "close chrome", "tile window left"],
        description_pt="Controlar janelas: listar, focar, fechar, posicionar",
        description_en="Control windows: list, focus, close, tile",
    ),
    Capability(
        category="sessão",
        icon="⚡",
        examples_pt=["desligar", "reiniciar", "bloquear tela", "suspender"],
        examples_en=["shutdown", "reboot", "lock screen", "suspend"],
        description_pt="Desligar, reiniciar, suspender, bloquear, sair",
        description_en="Shutdown, reboot, suspend, lock, logout",
    ),
    Capability(
        category="pacotes",
        icon="📦",
        examples_pt=["instalar vlc", "remover gimp", "atualizar sistema"],
        examples_en=["install vlc", "remove gimp", "update system"],
        description_pt="Instalar, remover e atualizar pacotes (apt)",
        description_en="Install, remove and update packages (apt)",
    ),
    Capability(
        category="arquivos",
        icon="📁",
        examples_pt=["organizar downloads", "onde está o contrato?", "abrir arquivo relatório"],
        examples_en=["organize downloads", "where is the contract?", "open file report"],
        description_pt="Organizar arquivos, buscar e abrir documentos",
        description_en="Organize files, search and open documents",
    ),
    Capability(
        category="disco",
        icon="💾",
        examples_pt=["liberar espaço", "limpar cache", "quanto espaço tenho?"],
        examples_en=["free space", "clean cache", "how much space?"],
        description_pt="Analisar disco, encontrar arquivos grandes, limpar cache",
        description_en="Analyze disk, find large files, clean cache",
    ),
    Capability(
        category="sistema",
        icon="🖥️",
        examples_pt=["tá lento", "verificar sistema", "o que tá usando memória?"],
        examples_en=["it's slow", "check system", "what's using memory?"],
        description_pt="Diagnóstico de saúde: CPU, memória, disco, processos",
        description_en="Health check: CPU, memory, disk, processes",
    ),
    Capability(
        category="desenvolvimento",
        icon="💻",
        examples_pt=["quero trabalhar no projeto X", "iniciar backend", "matar porta 3000"],
        examples_en=["work on project X", "start backend", "kill port 3000"],
        description_pt="Iniciar projetos, gerenciar servidores, resolver conflitos",
        description_en="Start projects, manage servers, resolve conflicts",
    ),
    Capability(
        category="clipboard",
        icon="📋",
        examples_pt=["o que copiei?", "histórico de cópias", "colar anterior"],
        examples_en=["what did I copy?", "clipboard history", "paste previous"],
        description_pt="Área de transferência: ver, histórico, colar anterior",
        description_en="Clipboard: view, history, paste previous",
    ),
    Capability(
        category="voz",
        icon="🎤",
        examples_pt=["(falar com o microfone)"],
        examples_en=["(speak into microphone)"],
        description_pt="Controle por voz: fale e o CIOS executa",
        description_en="Voice control: speak and CIOS executes",
    ),
]


def get_capabilities(lang: str = "pt") -> list[Capability]:
    """Return all system capabilities."""
    return list(_CAPABILITIES)


def format_capabilities(lang: str = "pt") -> tuple[list[str], str]:
    """Format capabilities for display.

    Returns:
        (plan_steps, summary)
    """
    plan_steps = ["Listing capabilities"]
    lines = []

    for cap in _CAPABILITIES:
        desc = cap.description_pt if lang == "pt" else cap.description_en
        examples = cap.examples_pt if lang == "pt" else cap.examples_en
        ex_str = ", ".join(f'"{e}"' for e in examples[:2])
        lines.append(f"  {cap.icon} {desc}")
        lines.append(f"     Ex: {ex_str}")

    header = "Posso te ajudar com:" if lang == "pt" else "I can help you with:"
    footer = (
        "\nDiga o que precisa — sem menus, sem cliques."
        if lang == "pt"
        else "\nJust say what you need — no menus, no clicks."
    )

    summary = header + "\n\n" + "\n".join(lines) + footer
    return plan_steps, summary


def list_installed_apps_grouped(lang: str = "pt") -> tuple[list[str], str]:
    """List installed apps grouped by category.

    Returns:
        (plan_steps, summary)
    """
    plan_steps = ["Scanning installed apps"]
    apps = get_installed_apps()

    if not apps:
        msg = "Nenhum aplicativo encontrado." if lang == "pt" else "No applications found."
        return plan_steps, msg

    # Group by rough category based on keywords
    categories: dict[str, list[str]] = {
        "🌐 Internet": [],
        "💻 Desenvolvimento": [] if lang == "pt" else [],
        "📝 Escritório": [] if lang == "pt" else [],
        "🎵 Mídia": [] if lang == "pt" else [],
        "🔧 Sistema": [] if lang == "pt" else [],
        "🎮 Jogos": [] if lang == "pt" else [],
        "📁 Arquivos": [] if lang == "pt" else [],
        "📦 Outros": [] if lang == "pt" else [],
    }

    # Category labels for EN
    if lang != "pt":
        categories = {
            "🌐 Internet": [],
            "💻 Development": [],
            "📝 Office": [],
            "🎵 Media": [],
            "🔧 System": [],
            "🎮 Games": [],
            "📁 Files": [],
            "📦 Other": [],
        }

    _INTERNET_KW = {"browser", "chrome", "firefox", "chromium", "thunderbird", "telegram", "discord", "slack", "web"}
    _DEV_KW = {"code", "editor", "terminal", "git", "vim", "emacs", "ide", "studio", "konsole", "alacritty", "kitty"}
    _OFFICE_KW = {"libreoffice", "writer", "calc", "impress", "draw", "office", "evince", "pdf", "okular"}
    _MEDIA_KW = {"vlc", "spotify", "rhythmbox", "audacious", "totem", "mpv", "gimp", "inkscape", "shotwell", "cheese"}
    _SYSTEM_KW = {"settings", "monitor", "task", "disk", "update", "software", "synaptic", "gparted"}
    _GAMES_KW = {"game", "steam", "lutris", "wine"}
    _FILES_KW = {"nautilus", "thunar", "nemo", "dolphin", "pcmanfm", "file", "archive", "compress"}

    cat_keys = list(categories.keys())

    for app in apps:
        name_lower = app.name.lower()
        kw_lower = " ".join(app.keywords).lower() if app.keywords else ""
        combined = name_lower + " " + kw_lower

        if any(k in combined for k in _INTERNET_KW):
            categories[cat_keys[0]].append(app.name)
        elif any(k in combined for k in _DEV_KW):
            categories[cat_keys[1]].append(app.name)
        elif any(k in combined for k in _OFFICE_KW):
            categories[cat_keys[2]].append(app.name)
        elif any(k in combined for k in _MEDIA_KW):
            categories[cat_keys[3]].append(app.name)
        elif any(k in combined for k in _SYSTEM_KW):
            categories[cat_keys[4]].append(app.name)
        elif any(k in combined for k in _GAMES_KW):
            categories[cat_keys[5]].append(app.name)
        elif any(k in combined for k in _FILES_KW):
            categories[cat_keys[6]].append(app.name)
        else:
            categories[cat_keys[7]].append(app.name)

    lines = []
    total = 0
    for cat_name, app_names in categories.items():
        if not app_names:
            continue
        total += len(app_names)
        lines.append(f"\n{cat_name}")
        for name in sorted(app_names)[:10]:
            lines.append(f"  {name}")
        if len(app_names) > 10:
            extra = len(app_names) - 10
            more = f"mais {extra}" if lang == "pt" else f"{extra} more"
            lines.append(f"  ...{more}")

    header = f"{total} aplicativos instalados:" if lang == "pt" else f"{total} installed applications:"
    tip = (
        '\nDiga "abrir [nome]" para abrir qualquer um.'
        if lang == "pt"
        else '\nSay "open [name]" to launch any of them.'
    )

    summary = header + "\n".join(lines) + tip
    return plan_steps, summary
