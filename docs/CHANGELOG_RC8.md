# CIOS v1.1.0-rc8 — Changelog

> Wayland-native UI + Greeter gráfico
> 11-12 Maio 2026

---

## Resumo

Migração completa de X11/Tkinter para Wayland/GTK4. O CIOS agora roda
como sistema operacional nativo em Wayland, sem dependência de X11 para
a interface principal.

---

## Noite de 10-11/Mai (sessão greetd + DRM)

- **greetd** substitui LightDM como display manager (Wayland-native)
- **seatd** para acesso DRM/input sem root
- Usuários adicionados a video/render/input groups
- Correção de DRM device busy (espera Xorg liberar)
- Componentes de IA deferidos para pós-login (`sudo cios-setup-ai`)
- Modelo Mistral não baixa mais durante instalação
- Correção de path absoluto do agreety (`/usr/sbin/agreety`)
- Criação do user `greeter` no postinst
- Remoção de referências residuais ao LightDM/slick-greeter

## Dia 11/Mai (GTK4 + xdg-shell)

- **GTK4 UI** — splash, onboarding, app principal migrados de Tkinter
- **xdg-shell** adicionado ao compositor (apps Wayland nativos)
- Libs de sistema excluídas do bundle (fix conflito glib/gio)
- `GDK_BACKEND=wayland` forçado no runtime
- IPC "ready" para dismiss do splash overlay
- Fix campo `"command"` (não `"cmd"`) no protocolo IPC
- Fix socket IPC: esperar resposta antes de fechar
- `WLR_NO_HARDWARE_CURSORS=1` (fix cursor invertido em VMs)
- `XKB_DEFAULT_LAYOUT` para teclado
- `wlr_xdg_toplevel_set_size()` — configure inicial para GTK4 renderizar
- greetd config não sobrescreve em upgrades
- plymouth-themes como dependência (fix label-pango warning)

## Dia 12/Mai (Greeter gráfico + UI completa)

- **Greeter GTK4** — tela de login gráfica com:
  - Logo CIOS
  - Gradientes vermelhos (top-right, bottom-left)
  - Campos user/senha
  - Comunicação com greetd via IPC protocol
- **Topbar** — CIOS brand, CPU, MEM, AI indicator, clock
- **Sidebar** — métricas do sistema (CPU/MEM/Disk) + sugestões
- **Thread panel** — histórico de conversas recentes
- **Hotkey overlay** — input flutuante para comandos rápidos
- Onboarding integrado no app principal (single GTK4 process)
- Fix venv: verifica `gi` em vez de `tkinter`
- Crash handler para logar exceções não tratadas
- Fix contraste de botões no greeter (CSS explícito)

---

## Stack final

```
Boot → Plymouth → greetd → cios-greeter-session
  → cios-shell (compositor Wayland, wlroots 0.18)
    → Greeter GTK4 (login gráfico)
      → Autenticação OK
        → greetd lança cios-session
          → cios-shell (compositor)
            → CIOS runtime GTK4 (prompt + topbar + sidebar)
```

## Dependências alteradas

- Adicionado: `python3-gi`, `gir1.2-gtk-4.0`, `greetd`, `seatd`, `plymouth-themes`
- Removido: `lightdm`, `lightdm-gtk-greeter`, `python3-tk` (não mais obrigatório)
- Libs bundled: filtradas via ldd + RPATH (sem ldconfig global)

---

*12 Maio 2026*
