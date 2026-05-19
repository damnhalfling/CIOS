"""Humanizer — translates all technical output into plain human language.

This is the perception layer. Nothing technical ever reaches the user.
Every plan step, every error, every result passes through here.

Supports EN and PT-BR. Language is auto-detected from system locale.
"""

import locale
import os
import re

from cios.core.planner import PlanResult

# ── Language detection ──────────────────────────────────────────────────


def _detect_language() -> str:
    """Detect system language. Returns 'pt' or 'en'."""
    for var in ("LANG", "LC_MESSAGES", "LC_ALL", "LANGUAGE"):
        val = os.environ.get(var, "")
        if val.lower().startswith("pt"):
            return "pt"
        if val:
            # Non-empty, non-PT locale found — default to English
            return "en"
    try:
        loc = locale.getlocale()[0] or ""
        if loc.lower().startswith("pt"):
            return "pt"
    except Exception:
        pass
    return "en"


_LANG = _detect_language()


# ── PT-BR post-translations (applied after EN humanization) ────────────
_PT_MAP: dict[str, str] = {
    # Steps
    "Installing required components…": "Instalando componentes…",
    "Freeing up port…": "Liberando porta…",
    "Starting server…": "Iniciando servidor…",
    "Server running.": "Servidor rodando.",
    "Something went wrong during startup": "Algo deu errado na inicialização",
    "Detected a conflict, resolving…": "Conflito detectado, resolvendo…",
    "No project detected in this folder.": "Nenhum projeto detectado nesta pasta.",
    "No recognized project found here": "Nenhum projeto encontrado aqui",
    "Stopping the process…": "Parando o processo…",
    "is already free": "já está livre",
    "Reading system activity…": "Lendo atividade do sistema…",
    "Looking for issues…": "Procurando problemas…",
    "Checking recent activity…": "Verificando atividade recente…",
    "Found a recent issue": "Encontrei um problema recente",
    "Identified the problem": "Problema identificado",
    "Trying again…": "Tentando novamente…",
    "Reinstalling components…": "Reinstalando componentes…",
    "Scanning active services…": "Verificando serviços ativos…",
    "Running your command…": "Executando seu comando…",
    "No action specified": "Nenhuma ação especificada",
    "Which port should I check?": "Qual porta devo verificar?",
    "Scanning files…": "Escaneando arquivos…",
    "Organizing by type…": "Organizando por tipo…",
    "Checking processor…": "Verificando processador…",
    "Checking memory…": "Verificando memória…",
    "Checking storage…": "Verificando armazenamento…",
    "Finding resource-heavy apps…": "Procurando apps pesados…",
    "Opening": "Abrindo",
    "is ready": "está pronto",
    "Couldn't open": "Não consegui abrir",
    "Looking for": "Procurando",
    "Which app should I open?": "Qual app devo abrir?",
    "Shutting down…": "Desligando…",
    "Restarting…": "Reiniciando…",
    "Going to sleep…": "Entrando em modo dormir…",
    "Hibernating…": "Hibernando…",
    "Logging out…": "Encerrando sessão…",
    "Locking screen…": "Bloqueando tela…",
    "Checking connection…": "Verificando conexão…",
    "Scanning for networks…": "Procurando redes…",
    "Connecting to": "Conectando em",
    "Connected to": "Conectado em",
    "Disconnecting from": "Desconectando de",
    "Adjusting volume…": "Ajustando volume…",
    "Muting…": "Silenciando…",
    "Unmuting…": "Ativando som…",
    "Toggling mute…": "Alternando mudo…",
    # Summaries
    "Resolved the conflict — your project is running": "Conflito resolvido — seu projeto está rodando",
    "Stopped the service on port": "Serviço parado na porta",
    "is using port": "está usando a porta",
    "is available": "está disponível",
    "Everything looks good — no recent issues": "Tudo certo — sem problemas recentes",
    "Couldn't fix automatically.": "Não consegui corrigir automaticamente.",
    "Reinstalled components and restarted — running now": "Componentes reinstalados — rodando agora",
    "What would you like me to do?": "O que você quer que eu faça?",
    "Which port should I look at?": "Qual porta devo verificar?",
    "is open": "está aberto",
    "I couldn't find an app called": "Não encontrei um app chamado",
    "Which app do you want me to open?": "Qual app você quer abrir?",
    "Active services:": "Serviços ativos:",
    "No active services found": "Nenhum serviço ativo",
    "No issues found": "Nenhum problema encontrado",
    "Available networks:": "Redes disponíveis:",
    "No Wi-Fi networks found": "Nenhuma rede Wi-Fi encontrada",
    "Not connected to any network": "Não conectado a nenhuma rede",
    "No known networks found. Available:": "Nenhuma rede conhecida. Disponíveis:",
    "Already connected to": "Já conectado em",
    "Audio muted": "Silenciado ✓",
    "Audio unmuted": "Som ligado ✓",
    "Volume:": "Volume:",
    # Errors
    "Port": "Porta",
    "is busy": "está ocupada",
    "Permission needed": "Permissão necessária",
    "Missing component detected": "Componente faltando",
    "Storage is full": "Armazenamento cheio",
    "Service not reachable": "Serviço inacessível",
    "Code error detected": "Erro de código detectado",
    "Took too long — stopped": "Demorou demais — parado",
    "Blocked for safety": "Bloqueado por segurança",
    "No project detected in this folder": "Nenhum projeto detectado nesta pasta",
    "Something went wrong": "Algo deu errado",
    "Network not found": "Rede não encontrada",
    "Wrong password": "Senha incorreta",
    "Wi-Fi is disabled or not available": "Wi-Fi desativado ou indisponível",
    "Already connected": "Já conectado",
    "Connection timed out": "Conexão expirou",
    "Connection failed": "Falha na conexão",
    "Audio system not available": "Sistema de áudio indisponível",
    "Audio server not running": "Servidor de áudio não está rodando",
    "Audio operation failed": "Operação de áudio falhou",
    # System health summaries
    "Processor is very busy": "Processador muito ocupado",
    "Processor is moderately busy": "Processador moderadamente ocupado",
    "Processor is fine": "Processador está bem",
    "used,": "em uso,",
    "cores)": "núcleos)",
    "Memory is almost full": "Memória quase cheia",
    "Memory is getting full": "Memória ficando cheia",
    "Memory is fine": "Memória está bem",
    "Storage is almost full": "Armazenamento quase cheio",
    "Storage is getting full": "Armazenamento ficando cheio",
    "Storage is fine": "Armazenamento está bem",
    "free of": "livre de",
    "Most active apps:": "Apps mais ativos:",
    "processor,": "processador,",
    "memory": "memória",
    "Suggestions:": "Sugestões:",
    # Disk analysis
    "Checking disk usage…": "Verificando uso do disco…",
    "Scanning directories…": "Escaneando diretórios…",
    "Finding large files…": "Procurando arquivos grandes…",
    "Cleaning safe files…": "Limpando arquivos seguros…",
    "Total freed:": "Total liberado:",
    "Biggest space consumers:": "Maiores consumidores de espaço:",
    "Can safely free up": "Pode liberar com segurança",
    "Disk is": "Disco está",
    "full": "cheio",
    "fine": "bem",
    # Power / battery / brightness
    "Checking battery…": "Verificando bateria…",
    "Checking brightness…": "Verificando brilho…",
    "Adjusting brightness…": "Ajustando brilho…",
    "Enabling power saving…": "Ativando modo economia…",
    "Battery:": "Bateria:",
    "Charging": "Carregando",
    "remaining": "restante",
    "Battery critically low!": "Bateria criticamente baixa!",
    "Battery getting low": "Bateria ficando baixa",
    "No battery detected — running on AC power": "Sem bateria — conectado na tomada",
    "Brightness:": "Brilho:",
    "Brightness control not available": "Controle de brilho indisponível",
    "Power saving mode enabled": "Modo economia ativado",
    "brightness reduced, CPU throttled": "brilho reduzido, CPU em economia",
    # Package management
    "installed successfully": "pronto, instalado ✓",
    "is already installed": "já tá instalado",
    "removed successfully": "removido ✓",
    "is not installed": "não tá instalado",
    "Package lists updated successfully": "Listas atualizadas ✓",
    "System upgraded": "Sistema atualizado ✓",
    "packages": "pacotes",
    "Found": "Encontrados",
    "No packages found for": "Nenhum pacote encontrado para",
    # Window control
    "windows open": "janelas abertas",
    "No windows open": "Nenhuma janela aberta",
    "Focused:": "Focado:",
    "Window not found:": "Janela não encontrada:",
    "Which window?": "Qual janela?",
    "Which window should I close?": "Qual janela devo fechar?",
    "Window tiled:": "Janela posicionada:",
    "Switched to desktop": "Mudou para área de trabalho",
    # Clipboard
    "Clipboard is empty": "Área de transferência vazia",
    "No clipboard history": "Sem histórico de cópias",
    "Previous item restored to clipboard": "Item anterior restaurado",
    "Clipboard history cleared": "Histórico de cópias limpo",
    # File organize
    "files organized": "arquivos organizados",
    "Could not find folder:": "Pasta não encontrada:",
    "No files to organize": "Nenhum arquivo para organizar",
    "Created:": "Criadas:",
    # Bluetooth
    "Checking Bluetooth": "Verificando Bluetooth",
    "Scanning Bluetooth": "Escaneando Bluetooth",
    "Turning on Bluetooth": "Ligando Bluetooth",
    "Turning off Bluetooth": "Desligando Bluetooth",
    "Bluetooth on": "Bluetooth ligado",
    "Bluetooth off": "Bluetooth desligado",
    "Bluetooth already on": "Bluetooth já está ligado",
    "Bluetooth already off": "Bluetooth já está desligado",
    "Bluetooth is off": "Bluetooth está desligado",
    "Bluetooth on — no devices connected": "Bluetooth ligado — nenhum dispositivo conectado",
    "Bluetooth on — connected to": "Bluetooth ligado — conectado a",
    "Bluetooth not available on this device": "Bluetooth não disponível neste dispositivo",
    "No Bluetooth devices found nearby": "Nenhum dispositivo Bluetooth encontrado",
    "No paired Bluetooth devices": "Nenhum dispositivo Bluetooth pareado",
    "paired device(s):": "dispositivo(s) pareado(s):",
    "device(s):": "dispositivo(s):",
    "connected": "conectado",
    "paired": "pareado",
    "Which device?": "Qual dispositivo?",
    "No paired devices. Try: scan bluetooth": "Nenhum dispositivo pareado. Tente: escanear bluetooth",
    "Which device should I remove?": "Qual dispositivo devo remover?",
    "Connected to device": "Conectado a",
    "Disconnected from": "Desconectado de",
    "Removed": "Removido",
    "Trusted": "Confiável",
    "Device not found:": "Dispositivo não encontrado:",
    "Pairing failed — make sure the device is in pairing mode": "Pareamento falhou — coloque o dispositivo em modo de pareamento",
    "Connection failed — device may be out of range": "Conexão falhou — dispositivo pode estar fora de alcance",
    "Connection rejected by device": "Conexão rejeitada pelo dispositivo",
    "Bluetooth operation timed out": "Operação Bluetooth expirou",
    "Bluetooth is turned off": "Bluetooth está desligado",
    "Bluetooth not installed": "Bluetooth não instalado",
    "Bluetooth operation failed": "Operação Bluetooth falhou",
    # Graceful degradation messages
    "Wi-Fi unavailable": "Wi-Fi indisponível",
    "Audio unavailable": "Áudio indisponível",
    "Bluetooth unavailable": "Bluetooth indisponível",
    "Window control unavailable": "Controle de janelas indisponível",
    # Generic close-loop responses
    "Done": "Pronto",
    "OK": "Pronto",
    "Success": "Pronto",
    # Intent classifier
    "Classifying…": "Classificando…",
    # Explore system / capabilities
    "Listing capabilities": "Listando capacidades",
    "I can help you with:": "Posso te ajudar com:",
    "Just say what you need — no menus, no clicks.": "Diga o que precisa — sem menus, sem cliques.",
    # List apps
    "Scanning installed apps": "Escaneando aplicativos instalados",
    "installed applications:": "aplicativos instalados:",
    "No applications found.": "Nenhum aplicativo encontrado.",
    # Workflow start
    "Searching for project": "Procurando projeto",
    "Workspace ready:": "Ambiente pronto:",
    "Editor opened": "Editor aberto",
    "Editor opened.": "Editor aberto.",
    "Browser opened.": "Navegador aberto.",
    "Session saved.": "Sessão salva.",
    "Restoring project…": "Restaurando projeto…",
    "Server already running.": "Servidor já está rodando.",
    "Server stopped — starting…": "Servidor parado — iniciando…",
    "Looking for recent project…": "Procurando projeto recente…",
    "Workspace restored.": "Ambiente restaurado.",
    "Browser on localhost:": "Navegador em localhost:",
    "Available projects:": "Projetos disponíveis:",
    "not found.": "não encontrado.",
    "No project directories found.": "Nenhum diretório de projetos encontrado.",
    "Which project?": "Qual projeto?",
    # Intent media
    "Looking for music player": "Procurando player de música",
    "Looking for video player": "Procurando player de vídeo",
    "No music player found.": "Nenhum player de música encontrado.",
    "No video player found.": "Nenhum player de vídeo encontrado.",
    # Intent browse
    "Looking for browser": "Procurando navegador",
    "No browser found.": "Nenhum navegador encontrado.",
    # Intent write
    "Looking for text editor": "Procurando editor de texto",
    "No editor found.": "Nenhum editor encontrado.",
    # File search
    "Searching files": "Procurando arquivos",
    "Scanning": "Escaneando",
    "directories": "diretórios",
    "Searching file contents": "Procurando no conteúdo dos arquivos",
    "Search timed out — showing partial results": "Busca expirou — mostrando resultados parciais",
    "No files found for:": "Nenhum arquivo encontrado para:",
    "file(s) for": "arquivo(s) para",
    "File not found:": "Arquivo não encontrado:",
    "No file specified": "Nenhum arquivo especificado",
    "Which file should I open?": "Qual arquivo devo abrir?",
    "What file are you looking for?": "Qual arquivo você está procurando?",
    "opened": "aberto",
    # Unknown action fallbacks
    "I don't recognize that network action": "Não reconheço essa ação de rede",
    "I don't recognize that audio action": "Não reconheço essa ação de áudio",
    "I don't recognize that power action": "Não reconheço essa ação de energia",
    "I don't recognize that package action": "Não reconheço essa ação de pacotes",
    "I don't recognize that clipboard action": "Não reconheço essa ação de área de transferência",
    "I don't recognize that window action": "Não reconheço essa ação de janela",
    "I don't recognize that Bluetooth action": "Não reconheço essa ação de Bluetooth",
    "I don't recognize that update action": "Não reconheço essa ação de atualização",
    # Additional step translations
    "Listing Bluetooth devices…": "Listando dispositivos Bluetooth…",
    "Listing paired devices…": "Listando dispositivos pareados…",
    "Getting active window…": "Obtendo janela ativa…",
    "Checking history…": "Verificando histórico…",
    "Checking version…": "Verificando versão…",
    "Checking for updates…": "Verificando atualizações…",
    "No active window found": "Nenhuma janela ativa encontrada",
    "No previous clipboard item": "Nenhum item anterior na área de transferência",
    "No package specified": "Nenhum pacote especificado",
    "No search query": "Nenhuma busca especificada",
    # Intelligence
    "Login required for Intelligence": "Faça login para usar o Intelligence.",
    "Session expired — please log in again": "Sessão expirada. Faça login novamente.",
    "Daily limit reached": "Limite diário atingido. Renova amanhã.",
    "Intelligence service error": "Erro no serviço. Tente novamente.",
    "No connection to Intelligence": "Sem conexão com o Intelligence.",
    "Consulting CIOS Intelligence": "Consultando CIOS Intelligence",
    # Media player
    "Looking for player": "Procurando player",
    "No player found. Install with: install mpv": "Nenhum player encontrado. Instale com: instalar mpv",
}


def _translate_pt(text: str) -> str:
    """Apply PT-BR translations to humanized text."""
    if _LANG != "pt":
        return text
    result = text
    for en, pt in _PT_MAP.items():
        result = result.replace(en, pt)
    return result


# ── Plan step translations ──────────────────────────────────────────────
# Maps technical patterns in plan steps to human-readable equivalents.
_STEP_TRANSLATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Install dependencies \((.+?)\)"), "Installing required components…"),
    (re.compile(r"Port (\d+) in use — killing process"), "Freeing up port…"),
    (re.compile(r"Starting server \((.+?)\)"), "Starting server…"),
    (re.compile(r"Server running on port (\d+) \(PID \d+\)"), "Server running."),
    (re.compile(r"Server exited immediately"), "Something went wrong during startup"),
    (re.compile(r"Port conflict detected — auto-recovering"), "Detected a conflict, resolving…"),
    (re.compile(r"Could not detect project type"), "No project detected in this folder."),
    # Dev Start — editor, browser, session (must precede generic "Opening" / "is running")
    (re.compile(r"Editor opened \(.+?\)"), "Editor opened."),
    (re.compile(r"Browser opened \(.+?\)"), "Browser opened."),
    (re.compile(r"Session saved"), "Session saved."),
    # Continue project
    (re.compile(r"Restoring project: .+"), "Restoring project…"),
    (re.compile(r"Server already running on port \d+"), "Server already running."),
    (re.compile(r"Server not running — starting full Dev Start"), "Server stopped — starting…"),
    (re.compile(r"Looking for recent project"), "Looking for recent project…"),
    (re.compile(r"Check port (\d+)"), "Checking port {0}…"),
    (re.compile(r"Found (.+?) \(PID (\d+)\) on port (\d+)"), "Found {0} using port {2}"),
    (re.compile(r"Killing process"), "Stopping the process…"),
    (re.compile(r"Nothing is listening on port (\d+)"), "Port {0} is already free"),
    (re.compile(r"Read logs"), "Reading system activity…"),
    (re.compile(r"Analyze errors"), "Looking for issues…"),
    (re.compile(r"Check memory for last failure"), "Checking recent activity…"),
    (re.compile(r"Found last failure: (.+)"), "Found a recent issue"),
    (re.compile(r"Root cause: (.+)"), "Identified the problem"),
    (re.compile(r"Killing process on port (\d+)"), "Clearing port {0}…"),
    (re.compile(r"Retrying server start"), "Trying again…"),
    (re.compile(r"Reinstalling dependencies"), "Reinstalling components…"),
    (re.compile(r"Check running services"), "Scanning active services…"),
    (re.compile(r"Execute: (.+)"), "Running your command…"),
    (re.compile(r"No command provided"), "No action specified"),
    (re.compile(r"No port specified"), "Which port should I check?"),
    # File organization
    (re.compile(r"Scanning (.+)"), "Scanning files…"),
    (re.compile(r"Grouping files by type"), "Organizing by type…"),
    (re.compile(r"Moving (\d+) files"), "Moving {0} files…"),
    (re.compile(r"Created folder: (.+)"), "Created folder: {0}"),
    # System health
    (re.compile(r"Checking CPU"), "Checking processor…"),
    (re.compile(r"Checking memory"), "Checking memory…"),
    (re.compile(r"Checking disk"), "Checking storage…"),
    (re.compile(r"Checking top processes"), "Finding resource-heavy apps…"),
    # App launcher
    (re.compile(r"Opening (.+)"), "Opening {0}…"),
    (re.compile(r"(.+) is running"), "{0} is ready"),
    (re.compile(r"Failed to open (.+)"), "Couldn't open {0}"),
    (re.compile(r"Searching for (.+)"), "Looking for {0}…"),
    (re.compile(r"No app specified"), "Which app should I open?"),
    # Session control
    (re.compile(r"Desligar o computador"), "Shutting down…"),
    (re.compile(r"Reiniciar o computador"), "Restarting…"),
    (re.compile(r"Suspender \(modo dormir\)"), "Going to sleep…"),
    (re.compile(r"Hibernar"), "Hibernating…"),
    (re.compile(r"Encerrar sess[aã]o"), "Logging out…"),
    (re.compile(r"Bloquear tela"), "Locking screen…"),
    # Network
    (re.compile(r"Checking Wi-Fi"), "Checking connection…"),
    (re.compile(r"Scanning networks"), "Scanning for networks…"),
    (re.compile(r"Connecting to (.+)"), "Connecting to {0}…"),
    (re.compile(r"Connected to (.+)"), "Connected to {0}"),
    (re.compile(r"Disconnecting from (.+)"), "Disconnecting from {0}…"),
    (re.compile(r"Check Wi-Fi"), "Checking connection…"),
    # Audio
    (re.compile(r"Checking volume"), "Checking volume…"),
    (re.compile(r"Setting volume to (\d+)%"), "Setting volume to {0}%…"),
    (re.compile(r"Volume (up|down)"), "Adjusting volume…"),
    (re.compile(r"Muting audio"), "Muting…"),
    (re.compile(r"Unmuting audio"), "Unmuting…"),
    (re.compile(r"Toggling mute"), "Toggling mute…"),
    (re.compile(r"Adjusting volume"), "Adjusting volume…"),
    (re.compile(r"Switching to (.+)"), "Switching audio to {0}…"),
    # Disk analysis
    (re.compile(r"Checking disk usage"), "Checking disk usage…"),
    (re.compile(r"Scanning directories"), "Scanning directories…"),
    (re.compile(r"Finding large files"), "Finding large files…"),
    (re.compile(r"Cleaning safe directories"), "Cleaning safe files…"),
    (re.compile(r"Cleaned (.+): (.+) freed"), "Cleaned {0}: {1} freed"),
    (re.compile(r"Total freed: (.+)"), "Total freed: {0}"),
    # Power / battery / brightness
    (re.compile(r"Checking battery"), "Checking battery…"),
    (re.compile(r"Checking brightness"), "Checking brightness…"),
    (re.compile(r"Setting brightness to (\d+)%"), "Setting brightness to {0}%…"),
    (re.compile(r"Brightness (up|down)"), "Adjusting brightness…"),
    (re.compile(r"Brightness reduced to (\d+)%"), "Brightness reduced to {0}%…"),
    (re.compile(r"Enabling power saving mode"), "Enabling power saving…"),
    # Explore system
    (re.compile(r"Listing capabilities"), "Listing capabilities…"),
    # List apps
    (re.compile(r"Scanning installed apps"), "Scanning installed apps…"),
    # Workflow start
    (re.compile(r"Searching for project"), "Searching for project…"),
    (re.compile(r"Found: (.+)"), "Found: {0}"),
    (re.compile(r"Type: (.+)"), "Project type: {0}"),
    # File search
    (re.compile(r"Searching files"), "Searching files…"),
    (re.compile(r"Searching file contents"), "Searching file contents…"),
    (re.compile(r"No results"), "No results found"),
    # Bluetooth
    (re.compile(r"Listing Bluetooth devices"), "Listing Bluetooth devices…"),
    (re.compile(r"Listing paired devices"), "Listing paired devices…"),
    # Window
    (re.compile(r"Getting active window"), "Getting active window…"),
    # Clipboard
    (re.compile(r"Checking history"), "Checking history…"),
    # Self-update
    (re.compile(r"Checking version"), "Checking version…"),
    (re.compile(r"Verificando atualizações"), "Checking for updates…"),
    # Package
    (re.compile(r"No package specified"), "No package specified"),
    (re.compile(r"No search query"), "No search query"),
]


def humanize_step(step: str) -> str:
    """Convert a single plan step to human language."""
    for pattern, template in _STEP_TRANSLATIONS:
        match = pattern.search(step)
        if match:
            groups = match.groups()
            result = template
            for i, g in enumerate(groups):
                result = result.replace(f"{{{i}}}", g)
            return result
    # If no pattern matches, return as-is but strip technical noise
    cleaned = step.strip()
    # Remove PID references
    cleaned = re.sub(r"\s*\(PID \d+\)", "", cleaned)
    # Remove command references in parens
    cleaned = re.sub(r"\s*\([a-z]+ (?:run |install).+?\)", "", cleaned)
    return cleaned if cleaned else step


# ── Summary translations ────────────────────────────────────────────────
_SUMMARY_TRANSLATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Server running on port (\d+) \(PID \d+\)"), "Server running."),
    (
        re.compile(r"Fixed port conflict and (?:re)?started server \(PID \d+\)"),
        "Resolved the conflict — your project is running",
    ),
    (
        re.compile(r"Fixed port conflict and (?:re)?started server"),
        "Resolved the conflict — your project is running",
    ),
    (
        re.compile(r"Fixed port conflict and restarted server"),
        "Resolved the conflict — your project is running",
    ),
    (re.compile(r"Killed process on port (\d+)"), "Stopped the service on port {0}"),
    (re.compile(r"Failed to kill process on port (\d+)"), "Couldn't stop the service on port {0}"),
    (re.compile(r"Port (\d+): (.+?) \(PID \d+\)"), "{1} is using port {0}"),
    (re.compile(r"Port (\d+) is free"), "Port {0} is available"),
    (re.compile(r"No recent failures found"), "Everything looks good — no recent issues"),
    (re.compile(r"Applied fix: (.+)"), "Fixed: {0}"),
    (re.compile(r"Attempted fix but failed\. (.+)"), "Couldn't fix automatically. {0}"),
    (
        re.compile(r"Reinstalled deps and restarted server \(PID \d+\)"),
        "Reinstalled components and restarted — running now",
    ),
    (
        re.compile(r"Reinstalled components and restarted — running now"),
        "Reinstalled components and restarted — running now",
    ),
    (
        re.compile(r"I don't understand that request"),
        'I\'m not sure what you mean. Try something like "start my backend" or "what\'s running?"',
    ),
    (re.compile(r"What command should I run\?"), "What would you like me to do?"),
    (re.compile(r"Which port\?.*"), "Which port should I look at?"),
    # Continue project / workspace restoration
    (re.compile(r"Workspace restored: .+?\. Server already running\."), "Workspace restored."),
    (re.compile(r"Workspace restored: .+?\. Server restarted\."), "Workspace restored."),
    # App launcher
    (re.compile(r"(.+) opened"), "{0} is open"),
    (re.compile(r"Failed to open (.+)"), "Couldn't open {0}"),
    (re.compile(r"App not found: (.+)"), 'I couldn\'t find an app called "{0}"'),
    (re.compile(r"Which app should I open\?"), "Which app do you want me to open?"),
    # Session control
    (re.compile(r"Desligar o computador"), "Shutting down…"),
    (re.compile(r"Reiniciar o computador"), "Restarting…"),
    (re.compile(r"Suspender \(modo dormir\)"), "Going to sleep…"),
    (re.compile(r"Hibernar"), "Hibernating…"),
    (re.compile(r"Encerrar sess[aã]o"), "Logging out…"),
    (re.compile(r"Bloquear tela"), "Locking screen…"),
    # Package management
    (re.compile(r"Installing (.+)"), "Installing {0}…"),
    (re.compile(r"Removing (.+)"), "Removing {0}…"),
    (re.compile(r"Searching for '(.+)'"), "Searching for {0}…"),
    (re.compile(r"Updating package lists"), "Updating package lists…"),
    (re.compile(r"Upgrading system packages"), "Upgrading system…"),
    (re.compile(r"Running apt"), "Working…"),
    (re.compile(r"No package specified"), "Which package?"),
    (re.compile(r"No search query"), "What are you looking for?"),
    # Window control
    (re.compile(r"Listing windows"), "Checking open windows…"),
    (re.compile(r"No window specified"), "Which window?"),
    (re.compile(r"Focusing: (.+)"), "Focusing {0}…"),
    (re.compile(r"Closing: (.+)"), "Closing {0}…"),
    (re.compile(r"Tiling: (.+?) → (.+)"), "Positioning {0} → {1}…"),
    (re.compile(r"Moving: (.+)"), "Moving {0}…"),
    (re.compile(r"Switching to desktop (\d+)"), "Switching to desktop {0}…"),
    # Clipboard
    (re.compile(r"Checking clipboard"), "Checking clipboard…"),
    (re.compile(r"Loading clipboard history"), "Loading history…"),
    (re.compile(r"Pasting previous item"), "Restoring previous copy…"),
    (re.compile(r"Clearing clipboard history"), "Clearing history…"),
    # Resilient call fallbacks
    (re.compile(r"Verificando disponibilidade"), "Checking availability…"),
    (re.compile(r"Executando"), "Working…"),
    # Unknown action fallbacks
    (re.compile(r"Unknown network action"), "I don't recognize that network action"),
    (re.compile(r"Unknown audio action"), "I don't recognize that audio action"),
    (re.compile(r"Unknown power action"), "I don't recognize that power action"),
    (re.compile(r"Unknown package action"), "I don't recognize that package action"),
    (re.compile(r"Unknown clipboard action"), "I don't recognize that clipboard action"),
    (re.compile(r"Unknown window action"), "I don't recognize that window action"),
    (re.compile(r"Unknown Bluetooth action"), "I don't recognize that Bluetooth action"),
    (re.compile(r"Ação de atualização desconhecida"), "I don't recognize that update action"),
    # Window/clipboard edge cases
    (re.compile(r"No active window"), "No active window found"),
    (re.compile(r"No previous item"), "No previous clipboard item"),
]

# ── Error translations ──────────────────────────────────────────────────
_ERROR_TRANSLATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"EADDRINUSE.*:(\d+)", re.IGNORECASE), "Port {0} is busy"),
    (re.compile(r"Port (\d+) already in use"), "Port {0} is busy"),
    (re.compile(r"EACCES|permission denied", re.IGNORECASE), "Permission needed"),
    (
        re.compile(r"MODULE_NOT_FOUND|Cannot find module", re.IGNORECASE),
        "Missing component detected",
    ),
    (re.compile(r"ENOSPC", re.IGNORECASE), "Storage is full"),
    (re.compile(r"ECONNREFUSED", re.IGNORECASE), "Service not reachable"),
    (re.compile(r"SyntaxError|Unexpected token", re.IGNORECASE), "Code error detected"),
    (re.compile(r"Command timed out"), "Took too long — stopped"),
    (re.compile(r"BLOCKED:"), "Blocked for safety"),
    (re.compile(r"No recognized project found"), "No project detected in this folder"),
    # Intelligence errors
    (re.compile(r"not_logged_in"), "Login required for Intelligence"),
    (re.compile(r"token_expired"), "Session expired — please log in again"),
    (re.compile(r"rate_limited"), "Daily limit reached"),
    (re.compile(r"api_error"), "Intelligence service error"),
    (re.compile(r"offline"), "No connection to Intelligence"),
]


def humanize_summary(summary: str) -> str:
    """Convert a result summary to human language."""
    for pattern, template in _SUMMARY_TRANSLATIONS:
        match = pattern.search(summary)
        if match:
            groups = match.groups()
            result = template
            for i, g in enumerate(groups):
                result = result.replace(f"{{{i}}}", g)
            return result

    # For status/listening ports — reformat
    if "Listening ports:" in summary:
        return _humanize_status(summary)

    # For log analysis with Root cause
    if "Root cause:" in summary:
        return _humanize_log_analysis(summary)

    # Strip technical noise from unknown summaries
    cleaned = summary.strip()
    cleaned = re.sub(r"\(PID \d+\)", "", cleaned)
    cleaned = re.sub(r"stderr:.*", "", cleaned, flags=re.DOTALL)
    return cleaned.strip() if cleaned.strip() else summary


def humanize_error(error: str) -> str:
    """Convert a technical error to a single human-readable line."""
    if not error:
        return ""
    for pattern, template in _ERROR_TRANSLATIONS:
        match = pattern.search(error)
        if match:
            groups = match.groups()
            result = template
            for i, g in enumerate(groups):
                result = result.replace(f"{{{i}}}", g)
            return _translate_pt(result)
    # Fallback: take first line, strip paths and technical jargon
    first_line = error.split("\n")[0].strip()
    first_line = re.sub(r"/[\w/.-]+", "", first_line)  # strip file paths
    first_line = re.sub(r"\(PID \d+\)", "", first_line)
    return _translate_pt(first_line[:120] if first_line else "Something went wrong")


def _humanize_status(summary: str) -> str:
    """Convert port listing to human-friendly format."""
    lines = []
    for line in summary.splitlines():
        match = re.search(r":(\d+)\s+(\S+)(?:\s+\(PID (\d+|None)\))?", line)
        if match:
            port, name = match.group(1), match.group(2)
            if name in ("python3", "unknown"):
                lines.append(f"Port {port} — system service")
            else:
                lines.append(f"Port {port} — {name}")
    if lines:
        return "Active services:\n" + "\n".join(lines)
    return "No active services found"


def _humanize_log_analysis(summary: str) -> str:
    """Convert log analysis output to human language."""
    parts = []
    for line in summary.splitlines():
        if line.startswith("Root cause:"):
            cause = line.replace("Root cause:", "").strip()
            cause = humanize_error(cause)
            parts.append(f"Issue: {cause}")
        elif line.startswith("Suggestion:"):
            suggestion = line.replace("Suggestion:", "").strip()
            parts.append(f"Recommendation: {suggestion}")
        elif line.strip() and not line.startswith((" ", "\t")):
            # Skip raw error lines
            pass
    return "\n".join(parts) if parts else "No issues found"


def humanize_result(result: PlanResult) -> tuple[list[str], str, str, str]:
    """
    Convert an entire PlanResult into human-friendly output.

    Returns:
        (humanized_steps, humanized_summary, outcome, voice_mode)
    """
    steps = [_translate_pt(humanize_step(s)) for s in result.plan_steps]
    summary = _translate_pt(humanize_summary(result.summary))
    return steps, summary, result.outcome, result.voice_mode
