# Harmoni OS — Roadmap de Desenvolvimento

> De app standalone a distro Linux AI-First
> Atualizado: Maio 2026 — v0.12.0

---

## Visão Geral

**Posicionamento:** "Substituindo apps por intenção." — rumo a distro própria base Debian.

O MVP é: **`dpkg -i harmoni.deb` → reboot → tela de login bonita → Harmoni fullscreen → funciona.**

Zero configuração manual. Tudo vem pronto no pacote. Testado em hardware real (máquina 2014).

| Fase | Objetivo | Status |
|------|----------|--------|
| **1** | Sessão X funcional + skills core | ✅ Concluído |
| **2** | Pacote .deb + login customizado | ✅ Concluído |
| **3** | Camada cognitiva (MCP/MCO) + desktop completo | ✅ Concluído |
| **4** | Desktop features (daemon, topbar, hotkey, EWMH, clipboard) | ✅ Concluído |
| **5** | Polimento: boot, latência, confiabilidade, UX conversacional | ✅ Concluído |
| **5.5** | Intenção > App: intent abstrato, workflow, file search, explore | ✅ Concluído |
| **5.6** | Intent híbrido: regex + cache LLM + stemming + aprendizado | ✅ Concluído |
| **6** | Harmoni Intelligence integration (optional cloud AI) | 🟡 Pendente |
| **7** | Demo 100% voz + script matador | 🟡 Pendente |
| **8** | Distribuição: 1-liner, AppImage, distro própria | 🟡 Pendente |

---

## Números do projeto (v0.12.0)

| Métrica | Valor |
|---------|-------|
| Versão | v0.12.0 |
| Arquivos fonte | 42+ (.py) |
| Skills | 21 |
| Intent patterns | 148+ (PT/EN) |
| Traduções humanizer | 185+ (PT/EN) |
| Tipos de erro classificados | 19 |
| Testes | 323 (9 arquivos) |
| Modos de execução | 6 |
| LLM provider | Ollama (local, padrão) |
| Itens concluídos | 131 |

---

## Regra #0: Latência + Previsibilidade

> Se Wi-Fi falhar 1x, volume não responder instantâneo, ou o sistema "pensar demais" → usuário volta pro GNOME em 2 minutos.

**Execução determinística para skills de sistema:**
- Wi-Fi → nmcli direto (sem LLM)
- Volume → pactl direto (sem LLM)
- Apps → .desktop direto (sem LLM)
- Sessão → systemctl direto (sem LLM)
- Pacotes → apt direto (sem LLM)
- Janelas → wmctrl direto (sem LLM)
- Clipboard → xclip direto (sem LLM)
- Bateria/Brilho → psutil/brightnessctl direto (sem LLM)

LLM só para intents desconhecidos. Pattern matching resolve 80%+.
Modelo híbrido: regex → cache com stemming → LLM classificador → LLM completo.

---

## Próximos passos

### Fase 6 — Harmoni Intelligence (opcional)
- Token Optimizer (Ollama comprime input antes de enviar ao cloud)
- Intelligence Client (cliente HTTP para API cloud)
- Intents Intelligence no parser (NEWS, EXPLAIN, WRITE, SUMMARIZE, TRANSLATE)
- UX de ativação ("Posso resolver com Harmoni Intelligence. [Ativar]")
- Auth flow (Google OAuth → JWT)

### Fase 7 — Demo Voz
- Wake word / push-to-talk contínuo
- Confirmação por voz — "sim"/"não"/"cancela"
- Navegação por voz — "configurações"/"volta"
- 3 fluxos matadores + momento mágico + roteiro 60s

### Fase 8 — Distribuição
- Install script 1-liner (detecta distro)
- AppImage portable
- Distro própria base Debian (ISO) — Harmoni OS

---

*Atualizado: Maio 2026 — v0.12.0*
