---
inclusion: auto
---

# Symbiont — Padrões de Desenvolvimento

## Estrutura do Projeto

```
symbiont/
├── symbiont/
│   ├── __init__.py              # Versão
│   ├── main.py                  # Entry point (modos: gui, web, cli, daemon, etc.)
│   │
│   ├── core/                    # Núcleo do sistema (engine)
│   │   ├── __init__.py
│   │   ├── bridge.py            # Interface única UI ↔ backend
│   │   ├── intent_parser.py     # Pattern matching (90+ regex PT/EN)
│   │   ├── planner.py           # Handlers + MCO
│   │   ├── executor.py          # Shell seguro com timeout
│   │   ├── memory.py            # SQLite thread-safe
│   │   ├── mcp.py               # Estado vivo do sistema (watchers + polling)
│   │   ├── model_router.py      # LLM routing + retry + circuit breaker
│   │   ├── humanizer.py         # Técnico → humano (PT/EN)
│   │   ├── error_recovery.py    # Erro → sugestão (nunca beco sem saída)
│   │   └── config.py            # Settings persistente
│   │
│   ├── skills/                  # Módulos de ação (1 arquivo = 1 skill)
│   │   ├── __init__.py
│   │   ├── network.py           # Wi-Fi (nmcli)
│   │   ├── audio.py             # Volume (pactl)
│   │   ├── app_launcher.py      # Abrir apps (.desktop)
│   │   ├── session_control.py   # Shutdown/reboot/lock
│   │   ├── power.py             # Bateria + brilho
│   │   ├── system_health.py     # Diagnóstico
│   │   ├── disk_analysis.py     # Espaço em disco
│   │   ├── file_organize.py     # Organizar arquivos
│   │   ├── process_control.py   # Kill por porta
│   │   ├── log_analysis.py      # Análise de erros
│   │   ├── dev_start.py         # Iniciar projetos
│   │   ├── package_manager.py   # apt install/remove
│   │   ├── clipboard.py         # Clipboard cognitivo
│   │   ├── window_control.py    # EWMH (wmctrl)
│   │   └── auto_learn.py        # Auto-learning engine
│   │
│   ├── ui/                      # Interfaces (GUI, Web, CLI, overlay)
│   │   ├── __init__.py
│   │   ├── gui.py               # Tkinter nativo
│   │   ├── gui_web.py           # Web (HTTP + SSE)
│   │   ├── gui_secondary.py     # Painel multi-monitor
│   │   ├── cli.py               # Terminal (Rich)
│   │   ├── topbar.py            # Barra de status
│   │   ├── hotkey.py            # Ctrl+Space overlay
│   │   ├── splash.py            # Splash screen
│   │   └── onboarding.py        # Wizard first-run
│   │
│   ├── infra/                   # Infraestrutura (daemon, voice, monitors)
│   │   ├── __init__.py
│   │   ├── daemon.py            # Unix socket server
│   │   ├── voice.py             # STT + TTS
│   │   └── monitors.py          # Multi-monitor (xrandr)
│   │
├── tests/                       # Testes (espelha core/ e skills/)
│   ├── conftest.py
│   ├── test_bridge.py
│   ├── test_intent_parser.py
│   ├── test_planner.py
│   ├── test_executor.py
│   ├── test_memory.py
│   ├── test_mcp.py
│   ├── test_model_router.py
│   ├── test_humanizer.py
│   └── test-vm-install.sh
│
├── session/                     # Arquivos da sessão X
├── assets/                      # Imagens e branding
├── docs/                        # Documentação
└── .github/workflows/           # CI/CD
```

## Regras de Código

### 1. Cada arquivo tem UMA responsabilidade
- `bridge.py` = interface UI↔backend (nada mais)
- `planner.py` = routing de intents para handlers
- Cada skill = 1 arquivo, 1 domínio

### 2. Dependências fluem para baixo
```
UI → core/bridge → core/planner → skills/
                 → core/mcp
                 → core/memory
```
- Skills NUNCA importam de UI
- Core NUNCA importa de UI
- UI importa de core (bridge apenas)

### 3. Padrão de uma skill
```python
"""Skill: Nome — descrição curta.

O que faz:
- Item 1
- Item 2
"""

def action_name(...) -> tuple[list[str], bool, Optional[str]]:
    """Executa ação. Retorna (steps, success, error)."""
    steps = ["Doing X"]
    # ... lógica ...
    return steps, True, None
```

### 4. Padrão de um handler no planner
```python
def _handle_intent_name(self, intent: Intent) -> PlanResult:
    action = intent.params.get("action", "default")
    
    if action == "x":
        steps, ok, err = skill.do_x()
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure",
            summary="..." if ok else err)
    
    return PlanResult(plan_steps=[], results=[], outcome="failure",
                      summary="Unknown action")
```

### 5. Padrão de intent pattern
```python
(
    re.compile(r"(?:keyword1|keyword2)\s+(?:optional)?\s*(.+)?", re.IGNORECASE),
    IntentType.INTENT_NAME,
    lambda m: {"action": "x", "param": m.group(1) or ""},
    0.90,  # confidence
),
```

### 6. Testes
- Cada módulo em `core/` tem um `test_*.py` correspondente
- Skills são testadas via planner (integração)
- UI não tem testes unitários (testada manualmente)
- `pytest tests/ -q` deve passar sempre antes de commit

### 7. Commits
- `feat:` — nova funcionalidade
- `fix:` — correção de bug
- `refactor:` — reorganização sem mudar comportamento
- `docs:` — documentação
- `test:` — testes
- Tag = release (`v0.9.0`)

### 8. Nunca
- ❌ Traceback na UI (sempre `_graceful_error`)
- ❌ Erro sem sugestão (sempre `enrich_error`)
- ❌ LLM para skills de sistema (sempre pattern match direto)
- ❌ Imports circulares (respeitar hierarquia)
- ❌ `time.sleep()` no thread principal da UI
- ❌ Hardcoded paths (usar `config.py`)
