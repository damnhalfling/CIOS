# Implementation Plan: App Watcher

## Overview

Implementação do App Watcher — um componente reativo que monitora diretórios de `.desktop` files via inotify (ctypes) e invalida automaticamente o cache do `app_launcher` quando aplicativos são instalados ou removidos. A implementação segue o padrão dos watchers existentes no MCP (wifi, áudio) e usa debounce de 2s para agrupar eventos.

## Tasks

- [x] 1. Tornar app_launcher thread-safe com invalidação lazy
  - [x] 1.1 Adicionar threading.Lock e flag _cache_dirty ao app_launcher.py
    - Importar `threading` no módulo
    - Criar `_cache_lock = threading.Lock()` e `_cache_dirty = False` no nível do módulo
    - Reescrever `invalidate_app_cache()` para apenas setar `_cache_dirty = True` dentro do lock (sem zerar o cache imediatamente)
    - Reescrever `_ensure_cache()` para verificar `_cache_dirty` e `_cache_loaded` dentro do lock, reconstruindo o cache apenas quando necessário
    - Garantir que `find_app()`, `get_installed_apps()` e `list_installed_apps()` usem `_ensure_cache()` (já usam)
    - _Requirements: 3.2, 3.3, 5.1, 5.2, 5.3_

  - [x] 1.2 Write property test: thread safety nas leituras concorrentes
    - **Property 5: Thread safety nas leituras concorrentes durante reconstrução**
    - **Validates: Requirements 3.3, 5.1, 5.2**
    - Usar hypothesis + threading para gerar sequências concorrentes de leituras e invalidações
    - Verificar ausência de exceções e que nenhuma leitura retorna dados parciais

  - [x] 1.3 Write property test: idempotência de invalidação concorrente
    - **Property 6: Idempotência de invalidação concorrente**
    - **Validates: Requirements 5.3**
    - Gerar N invalidações concorrentes (1-50) e verificar que no máximo 1 rescan é executado na próxima consulta

- [x] 2. Checkpoint - Verificar thread safety
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implementar AppWatcher com inotify via ctypes
  - [x] 3.1 Criar cios/core/app_watcher.py com interface inotify via ctypes
    - Criar arquivo `cios/core/app_watcher.py`
    - Implementar funções de baixo nível: `_inotify_init()`, `_inotify_add_watch()`, `_parse_events()`
    - Usar `ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)` para carregar libc
    - Definir constantes: `IN_CREATE`, `IN_MODIFY`, `IN_DELETE`, `IN_MOVED_TO`, `IN_MOVED_FROM`, `WATCH_MASK`
    - Implementar parse do struct `inotify_event` (header 16 bytes + nome variável)
    - _Requirements: 6.1, 6.2_

  - [x] 3.2 Implementar classe AppWatcher com monitoramento e debounce
    - Definir `WATCHED_DIRS` (*/usr/share/applications*, *~/.local/share/applications*)
    - Definir `DEBOUNCE_SECONDS = 2.0`
    - Implementar `start()`: inicializar inotify fd, adicionar watches nos diretórios existentes (ignorar inexistentes), criar e iniciar thread daemon
    - Implementar `_monitor_loop()`: usar `select.select()` no fd do inotify, ler buffer de eventos, chamar `_on_event()` para cada arquivo
    - Implementar `_on_event(filename)`: filtrar por extensão `.desktop`, chamar `_reset_debounce()`
    - Implementar `_reset_debounce()`: cancelar timer existente, criar novo `threading.Timer(2.0, _on_debounce_expire)`
    - Implementar `_on_debounce_expire()`: chamar `invalidate_app_cache()` do app_launcher
    - Implementar `stop()`: setar `_running = False`, cancelar timer de debounce, fechar fd do inotify
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1_

  - [x] 3.3 Write property test: filtro de extensão .desktop
    - **Property 1: Filtro de extensão .desktop**
    - **Validates: Requirements 1.5**
    - Gerar nomes de arquivo aleatórios via `hypothesis.strategies.text()` e verificar que o filtro aceita sse termina em `.desktop`

  - [x] 3.4 Write property test: resiliência a diretórios inexistentes
    - **Property 2: Resiliência a diretórios inexistentes**
    - **Validates: Requirements 1.4**
    - Gerar subconjuntos aleatórios de diretórios com existência booleana, verificar que `start()` não lança exceção e monitora apenas os existentes

  - [x] 3.5 Write property test: debounce correto
    - **Property 3: Debounce correto — único rescan após período de silêncio**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    - Gerar sequências de timestamps com intervalos < 2s, verificar que exatamente 1 callback é disparado após silêncio de 2s

  - [x] 3.6 Write property test: round-trip de invalidação do cache
    - **Property 4: Round-trip de invalidação do cache**
    - **Validates: Requirements 3.2**
    - Gerar conjuntos de AppInfo aleatórios, popular cache, invalidar, verificar que próxima leitura escaneia do disco

- [x] 4. Checkpoint - Verificar AppWatcher isolado
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Integrar AppWatcher no ciclo de vida do MCP
  - [x] 5.1 Modificar mcp.py para iniciar e parar o AppWatcher
    - Importar `AppWatcher` de `cios.core.app_watcher`
    - Adicionar atributo `self._app_watcher: AppWatcher | None = None` no `__init__` de `SystemContext`
    - No `start()`, após `_warmup_parallel()`, instanciar e chamar `self._app_watcher.start()` dentro de try/except que loga warning em caso de falha
    - No `stop()`, chamar `self._app_watcher.stop()` se não for None
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.2 Write unit tests para integração MCP
    - Testar que `context.start()` funciona mesmo se AppWatcher lançar exceção no `start()`
    - Testar que `context.stop()` chama `app_watcher.stop()`
    - Testar que AppWatcher é iniciado após warmup
    - _Requirements: 4.1, 4.2, 4.4_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- A linguagem de implementação é Python (conforme já definido no design)
- Biblioteca de property-based testing: hypothesis (já disponível no projeto)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["3.1"] },
    { "id": 3, "tasks": ["3.2"] },
    { "id": 4, "tasks": ["3.3", "3.4", "3.5", "3.6"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["5.2"] }
  ]
}
```
