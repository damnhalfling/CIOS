# CIOS — Migração Tkinter → GTK4 (Wayland Nativo)

> Objetivo: Remover dependência de X11/XWayland. UI roda nativa em Wayland.
> Atualizado: Maio 2026

---

## Motivação

Tkinter depende de X11 (Xlib). No stack atual:
- cios-shell (Wayland compositor) inicia XWayland para o tkinter
- XWayland é instável em VMs e adiciona complexidade
- Remover X11 = boot mais rápido, menos dependências, menos bugs

## Stack novo

```
cios-shell (Wayland) → Python runtime → GTK4 (Wayland nativo)
                                       → gtk4-layer-shell (topbar, overlay)
```

## Dependências

```
python3-gi (PyGObject)
gir1.2-gtk-4.0
libgtk-4-1
gtk4-layer-shell (para topbar/overlay)
```

## Fases de migração

### Fase 1 — Boot funcional (PRIORIDADE)
- [ ] splash.py → GTK4 (window fullscreen, progress bar, state ring via Cairo)
- [ ] onboarding.py → GTK4 (wizard steps, buttons, radio)
- [ ] main.py → detectar GTK4 em vez de tkinter

### Fase 2 — GUI principal
- [ ] gui.py → GTK4 (prompt, feed, state ring, system status)
- [ ] theme.py → GTK4 CSS stylesheet
- [ ] ScrollFrame → GtkScrolledWindow
- [ ] StateRing → Cairo drawing area com animação
- [ ] ThreadPanel → GtkListBox

### Fase 3 — Componentes secundários
- [ ] hotkey.py → layer-shell overlay
- [ ] topbar.py → layer-shell exclusive zone
- [ ] gui_secondary.py → GTK4 window em monitor secundário
- [ ] gallery_component.py → GtkGridView
- [ ] image_viewer.py → GtkPicture

### Fase 4 — Limpeza
- [ ] Remover tkinter de dependências
- [ ] Remover XWayland do compositor (opcional, manter para apps legados)
- [ ] Remover python3-tk do Depends
- [ ] Atualizar testes

## Mapeamento Tkinter → GTK4

| Tkinter | GTK4 |
|---------|------|
| tk.Tk() | Gtk.Application + Gtk.ApplicationWindow |
| tk.Frame | Gtk.Box |
| tk.Label | Gtk.Label |
| tk.Entry | Gtk.Entry |
| tk.Text | Gtk.TextView |
| tk.Button | Gtk.Button |
| tk.Canvas | Gtk.DrawingArea (Cairo) |
| tk.Toplevel | Gtk.Window |
| root.after(ms, cb) | GLib.timeout_add(ms, cb) |
| widget.bind("<event>") | GtkEventController |
| pack/grid | Gtk.Box / Gtk.Grid |
| overrideredirect | layer-shell |
| PhotoImage | GdkPixbuf / Gtk.Picture |

## Interface preservada (não muda)

- CIOSBridge API (execute_command, get_system_status, etc.)
- ThreadManager
- Design tokens (theme.py — cores, espaçamentos, timings)
- Protocolo splash (file-based progress)
- IPC com compositor (Unix socket JSON)

---

*Criado: Maio 2026*
