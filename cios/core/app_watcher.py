"""App Watcher — monitoramento reativo de diretórios .desktop via inotify.

Usa inotify do Linux diretamente via ctypes (sem dependências externas) para
detectar criação, modificação e remoção de arquivos .desktop nos diretórios
monitorados. Quando mudanças são detectadas, invalida o cache do app_launcher
após debounce de 2 segundos.

Requirements: 6.1, 6.2 — Implementação sem dependências externas adicionais.
"""

import ctypes
import ctypes.util
import logging
import os
import select
import struct
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# libc via ctypes
# ---------------------------------------------------------------------------

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

# ---------------------------------------------------------------------------
# Constantes inotify
# ---------------------------------------------------------------------------

IN_CREATE: int = 0x00000100
IN_MODIFY: int = 0x00000002
IN_DELETE: int = 0x00000200
IN_MOVED_TO: int = 0x00000080
IN_MOVED_FROM: int = 0x00000040

WATCH_MASK: int = IN_CREATE | IN_MODIFY | IN_DELETE | IN_MOVED_TO | IN_MOVED_FROM

# Tamanho do header do struct inotify_event (wd + mask + cookie + len = 16 bytes)
EVENT_HEADER_SIZE: int = 16  # struct.calcsize("iIII")

# ---------------------------------------------------------------------------
# Funções de baixo nível inotify
# ---------------------------------------------------------------------------


def _inotify_init() -> int:
    """Cria um file descriptor inotify.

    Returns:
        O file descriptor do inotify.

    Raises:
        OSError: Se a chamada inotify_init() falhar.
    """
    fd: int = _libc.inotify_init()
    if fd < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    return fd


def _inotify_add_watch(fd: int, path: str, mask: int) -> int:
    """Adiciona um watch em um diretório.

    Args:
        fd: File descriptor do inotify (retornado por _inotify_init).
        path: Caminho do diretório a monitorar.
        mask: Máscara de eventos a observar (use WATCH_MASK).

    Returns:
        O watch descriptor associado ao diretório.

    Raises:
        OSError: Se a chamada inotify_add_watch() falhar.
    """
    wd: int = _libc.inotify_add_watch(fd, path.encode(), mask)
    if wd < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    return wd


def _parse_events(buffer: bytes) -> list[tuple[int, int, str]]:
    """Faz parse de um buffer de eventos inotify.

    O buffer contém zero ou mais structs inotify_event consecutivos.
    Cada struct tem um header de 16 bytes seguido de um campo name variável
    (null-padded).

    Args:
        buffer: Bytes lidos do file descriptor inotify.

    Returns:
        Lista de tuplas (wd, mask, filename) para cada evento com nome.
    """
    events: list[tuple[int, int, str]] = []
    offset = 0

    while offset < len(buffer):
        wd, mask, cookie, length = struct.unpack_from("iIII", buffer, offset)
        offset += EVENT_HEADER_SIZE

        if length > 0:
            name = (
                buffer[offset : offset + length].rstrip(b"\x00").decode("utf-8", errors="replace")
            )
            events.append((wd, mask, name))

        offset += length

    return events


# ---------------------------------------------------------------------------
# AppWatcher — monitoramento de alto nível com debounce
# ---------------------------------------------------------------------------


class AppWatcher:
    """Monitora diretórios de .desktop files via inotify e invalida o cache do app_launcher.

    Observa os diretórios padrão de aplicativos do Linux, detecta criação/modificação/
    remoção de arquivos .desktop e, após debounce de 2 segundos sem novos eventos,
    chama invalidate_app_cache() para forçar rescan na próxima consulta.

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1
    """

    WATCHED_DIRS: list[Path] = [
        Path("/usr/share/applications"),
        Path.home() / ".local" / "share" / "applications",
    ]
    DEBOUNCE_SECONDS: float = 2.0

    def __init__(self) -> None:
        self._inotify_fd: int = -1
        self._watch_descriptors: dict[int, Path] = {}  # wd → dir path
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._debounce_timer: threading.Timer | None = None
        self._debounce_lock: threading.Lock = threading.Lock()

    def start(self) -> None:
        """Inicializa inotify e inicia a thread de monitoramento.

        Cria o file descriptor inotify, adiciona watches nos diretórios existentes
        (diretórios inexistentes são ignorados silenciosamente) e inicia uma thread
        daemon para monitorar eventos.

        Raises:
            OSError: Se inotify_init() falhar (capturado pelo MCP).
        """
        self._inotify_fd = _inotify_init()
        self._running = True

        for dir_path in self.WATCHED_DIRS:
            if not dir_path.is_dir():
                logger.debug("Diretório não existe, ignorando: %s", dir_path)
                continue
            try:
                wd = _inotify_add_watch(self._inotify_fd, str(dir_path), WATCH_MASK)
                self._watch_descriptors[wd] = dir_path
                logger.debug("Watch adicionado: %s (wd=%d)", dir_path, wd)
            except OSError as e:
                logger.warning("Falha ao adicionar watch em %s: %s", dir_path, e)

        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="app-watcher",
            daemon=True,
        )
        self._thread.start()
        logger.debug("AppWatcher iniciado com %d watches", len(self._watch_descriptors))

    def stop(self) -> None:
        """Encerra monitoramento, cancela timers e fecha o fd do inotify.

        Seta _running = False para sinalizar a thread, cancela qualquer timer de
        debounce pendente, fecha o fd do inotify (o que também desbloqueia select)
        e aguarda a thread finalizar.
        """
        self._running = False

        # Cancela timer de debounce pendente
        with self._debounce_lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None

        # Fecha o fd do inotify (desbloqueia select na thread)
        if self._inotify_fd >= 0:
            try:
                os.close(self._inotify_fd)
            except OSError:
                pass
            self._inotify_fd = -1

        # Aguarda a thread finalizar
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        self._watch_descriptors.clear()
        logger.debug("AppWatcher encerrado")

    def _monitor_loop(self) -> None:
        """Loop principal: select() no fd do inotify, lê eventos, filtra e faz debounce.

        Usa select com timeout de 1s para permitir verificação periódica de _running
        e saída limpa da thread.
        """
        while self._running:
            try:
                readable, _, _ = select.select([self._inotify_fd], [], [], 1.0)
            except (OSError, ValueError):
                # fd foi fechado (stop() chamado) ou inválido
                break

            if not readable:
                continue

            try:
                buffer = os.read(self._inotify_fd, 4096)
            except OSError:
                # fd foi fechado ou erro de leitura
                break

            if not buffer:
                continue

            events = _parse_events(buffer)
            for _wd, _mask, filename in events:
                self._on_event(filename)

    def _on_event(self, filename: str) -> None:
        """Chamado para cada evento. Filtra por .desktop e aciona debounce.

        Apenas arquivos com extensão .desktop disparam o mecanismo de debounce.
        Outros tipos de arquivo são ignorados silenciosamente.

        Args:
            filename: Nome do arquivo que gerou o evento inotify.
        """
        if not filename.endswith(".desktop"):
            return
        logger.debug("Evento .desktop detectado: %s", filename)
        self._reset_debounce()

    def _reset_debounce(self) -> None:
        """Cancela timer existente e cria novo timer de 2s.

        Usa _debounce_lock para sincronizar cancelamento e criação do timer,
        garantindo que apenas um timer esteja ativo por vez.
        """
        with self._debounce_lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(self.DEBOUNCE_SECONDS, self._on_debounce_expire)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _on_debounce_expire(self) -> None:
        """Callback do timer — chama invalidate_app_cache().

        Executado após DEBOUNCE_SECONDS sem novos eventos .desktop.
        Importa e chama invalidate_app_cache() do módulo app_launcher.
        """
        logger.debug("Debounce expirou — invalidando cache de apps")
        from cios.skills.app_launcher import invalidate_app_cache

        invalidate_app_cache()
