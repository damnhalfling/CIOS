"""Onboarding Wizard — first-run setup for Harmoni.

Guides the user through initial configuration:
1. Welcome + language selection
2. LLM provider setup (Ollama local / cloud API key)
3. Wi-Fi connection (if not connected)
4. Quick tour of capabilities
5. Optional: voice setup, hotkey config

Runs automatically on first launch (no ~/.harmoni/settings.json).
Can be re-triggered with `harmoni --setup`.
"""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from harmoni.core import config
from harmoni.core.config import HARMONI_HOME, SETTINGS_PATH, ensure_dirs

logger = logging.getLogger(__name__)

_ONBOARDING_DONE_FLAG = HARMONI_HOME / ".onboarding_done"


def needs_onboarding() -> bool:
    """Check if onboarding should run."""
    return not _ONBOARDING_DONE_FLAG.exists()


def mark_onboarding_done() -> None:
    """Mark onboarding as completed."""
    ensure_dirs()
    _ONBOARDING_DONE_FLAG.touch()


class OnboardingWizard:
    """Interactive onboarding wizard (Tkinter-based)."""

    def __init__(self) -> None:
        self._root = None
        self._current_step = 0
        self._steps = [
            self._step_welcome,
            self._step_provider,
            self._step_network,
            self._step_tour,
            self._step_done,
        ]
        self._settings = {}

    def run(self) -> bool:
        """Run the onboarding wizard. Returns True if completed."""
        try:
            import tkinter as tk
            from tkinter import ttk
        except ImportError:
            # Fallback to CLI onboarding
            return self._run_cli()

        self._root = tk.Tk()
        self._root.title("Harmoni — Setup")
        self._root.configure(bg="#0a0a0f")
        self._root.geometry("600x450")
        self._root.resizable(False, False)

        # Center on screen
        self._root.update_idletasks()
        x = (self._root.winfo_screenwidth() - 600) // 2
        y = (self._root.winfo_screenheight() - 450) // 2
        self._root.geometry(f"+{x}+{y}")

        self._container = tk.Frame(self._root, bg="#0a0a0f")
        self._container.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

        self._show_step()
        self._root.mainloop()

        return _ONBOARDING_DONE_FLAG.exists()

    def _show_step(self) -> None:
        """Display the current step."""
        # Clear container
        for widget in self._container.winfo_children():
            widget.destroy()

        if self._current_step < len(self._steps):
            self._steps[self._current_step]()

    def _next_step(self) -> None:
        """Advance to next step."""
        self._current_step += 1
        if self._current_step >= len(self._steps):
            self._finish()
        else:
            self._show_step()

    def _finish(self) -> None:
        """Complete onboarding."""
        # Save settings
        for key, value in self._settings.items():
            config.set(key, value)
        config.save()
        mark_onboarding_done()
        if self._root:
            self._root.destroy()

    # ── Steps ──

    def _step_welcome(self) -> None:
        """Welcome screen."""
        import tkinter as tk

        tk.Label(
            self._container, text="✦", font=("Inter", 48),
            fg="#7c6ff7", bg="#0a0a0f",
        ).pack(pady=(20, 10))

        tk.Label(
            self._container, text="Bem-vindo ao Harmoni",
            font=("Inter", 20, "bold"), fg="#e2e2e8", bg="#0a0a0f",
        ).pack(pady=(0, 8))

        tk.Label(
            self._container,
            text="Seu sistema operacional cognitivo.\nVamos configurar tudo em menos de 1 minuto.",
            font=("Inter", 12), fg="#8a8a9a", bg="#0a0a0f", justify=tk.CENTER,
        ).pack(pady=(0, 30))

        btn = tk.Button(
            self._container, text="Começar →",
            font=("Inter", 12, "bold"), fg="#fff", bg="#7c6ff7",
            relief=tk.FLAT, padx=30, pady=10,
            command=self._next_step,
            activebackground="#6b5ce7", activeforeground="#fff",
        )
        btn.pack()

    def _step_provider(self) -> None:
        """LLM provider selection."""
        import tkinter as tk

        tk.Label(
            self._container, text="🧠 Modelo de IA",
            font=("Inter", 16, "bold"), fg="#e2e2e8", bg="#0a0a0f",
        ).pack(anchor=tk.W, pady=(0, 8))

        tk.Label(
            self._container,
            text="Escolha como o Harmoni vai pensar.\nOllama roda local (grátis, privado). Cloud é mais rápido.",
            font=("Inter", 11), fg="#8a8a9a", bg="#0a0a0f", justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 20))

        provider_var = tk.StringVar(value="ollama")

        options = [
            ("Ollama (local, grátis, privado)", "ollama"),
            ("OpenAI (GPT-4o-mini, precisa de API key)", "openai"),
            ("Anthropic (Claude, precisa de API key)", "anthropic"),
            ("AWS Bedrock (Claude via AWS)", "bedrock"),
        ]

        for text, value in options:
            rb = tk.Radiobutton(
                self._container, text=text, variable=provider_var, value=value,
                font=("Inter", 11), fg="#b0b0c0", bg="#0a0a0f",
                selectcolor="#1a1a2e", activebackground="#0a0a0f",
                activeforeground="#e2e2e8",
            )
            rb.pack(anchor=tk.W, pady=3)

        # API key entry (shown for cloud providers)
        key_frame = tk.Frame(self._container, bg="#0a0a0f")
        key_frame.pack(fill=tk.X, pady=(15, 0))

        tk.Label(
            key_frame, text="API Key (opcional):",
            font=("Inter", 10), fg="#6b6b7b", bg="#0a0a0f",
        ).pack(anchor=tk.W)

        key_entry = tk.Entry(
            key_frame, font=("Inter", 11), fg="#e2e2e8", bg="#16161e",
            insertbackground="#7c6ff7", relief=tk.FLAT, show="•",
        )
        key_entry.pack(fill=tk.X, pady=(4, 0), ipady=6)

        def save_and_next():
            provider = provider_var.get()
            self._settings["llm_provider"] = provider
            key = key_entry.get().strip()
            if key:
                if provider == "openai":
                    self._settings["openai_api_key"] = key
                elif provider == "anthropic":
                    self._settings["anthropic_api_key"] = key
            self._next_step()

        tk.Button(
            self._container, text="Próximo →",
            font=("Inter", 11), fg="#fff", bg="#7c6ff7",
            relief=tk.FLAT, padx=20, pady=8,
            command=save_and_next,
        ).pack(anchor=tk.E, pady=(20, 0))

    def _step_network(self) -> None:
        """Network check."""
        import tkinter as tk

        tk.Label(
            self._container, text="📶 Conexão",
            font=("Inter", 16, "bold"), fg="#e2e2e8", bg="#0a0a0f",
        ).pack(anchor=tk.W, pady=(0, 8))

        # Check current connection
        connected = False
        ssid = ""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    parts = line.split(":")
                    if len(parts) >= 2 and parts[0] == "yes":
                        connected = True
                        ssid = parts[1]
                        break
        except Exception:
            pass

        if connected:
            tk.Label(
                self._container,
                text=f"✓ Conectado a: {ssid}",
                font=("Inter", 12), fg="#4ade80", bg="#0a0a0f",
            ).pack(anchor=tk.W, pady=(10, 20))
        else:
            tk.Label(
                self._container,
                text="Não conectado. Você pode conectar depois com:\n\"conectar no wifi\"",
                font=("Inter", 11), fg="#facc15", bg="#0a0a0f", justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(10, 20))

        tk.Button(
            self._container, text="Próximo →",
            font=("Inter", 11), fg="#fff", bg="#7c6ff7",
            relief=tk.FLAT, padx=20, pady=8,
            command=self._next_step,
        ).pack(anchor=tk.E, pady=(20, 0))

    def _step_tour(self) -> None:
        """Quick capabilities tour."""
        import tkinter as tk

        tk.Label(
            self._container, text="⚡ O que você pode fazer",
            font=("Inter", 16, "bold"), fg="#e2e2e8", bg="#0a0a0f",
        ).pack(anchor=tk.W, pady=(0, 15))

        capabilities = [
            ("📶", "\"conectar no wifi\"", "Gerencia Wi-Fi automaticamente"),
            ("🔊", "\"aumenta volume\"", "Controle de áudio instantâneo"),
            ("📁", "\"organizar downloads\"", "Organiza arquivos por tipo"),
            ("🚀", "\"abre chrome\"", "Abre qualquer aplicativo"),
            ("📊", "\"tá lento\"", "Diagnóstico inteligente do sistema"),
            ("💾", "\"libera espaço\"", "Análise e limpeza de disco"),
        ]

        for icon, cmd, desc in capabilities:
            row = tk.Frame(self._container, bg="#0a0a0f")
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=icon, font=("Inter", 13), bg="#0a0a0f").pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(row, text=cmd, font=("Inter", 11, "bold"), fg="#a78bfa", bg="#0a0a0f").pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(row, text=desc, font=("Inter", 10), fg="#6b6b7b", bg="#0a0a0f").pack(side=tk.LEFT)

        tk.Button(
            self._container, text="Pronto! →",
            font=("Inter", 11), fg="#fff", bg="#7c6ff7",
            relief=tk.FLAT, padx=20, pady=8,
            command=self._next_step,
        ).pack(anchor=tk.E, pady=(25, 0))

    def _step_done(self) -> None:
        """Completion screen."""
        import tkinter as tk

        tk.Label(
            self._container, text="✓", font=("Inter", 48),
            fg="#4ade80", bg="#0a0a0f",
        ).pack(pady=(30, 10))

        tk.Label(
            self._container, text="Tudo pronto!",
            font=("Inter", 20, "bold"), fg="#e2e2e8", bg="#0a0a0f",
        ).pack(pady=(0, 8))

        tk.Label(
            self._container,
            text="O Harmoni está configurado e pronto para usar.\nDigite qualquer coisa em linguagem natural.",
            font=("Inter", 12), fg="#8a8a9a", bg="#0a0a0f", justify=tk.CENTER,
        ).pack(pady=(0, 30))

        tk.Button(
            self._container, text="Iniciar Harmoni",
            font=("Inter", 12, "bold"), fg="#fff", bg="#7c6ff7",
            relief=tk.FLAT, padx=30, pady=10,
            command=self._finish,
        ).pack()

    # ── CLI Fallback ──

    def _run_cli(self) -> bool:
        """CLI-based onboarding for systems without Tkinter."""
        print("\n  ✦ Harmoni — Setup\n")
        print("  Bem-vindo ao Harmoni, seu sistema operacional cognitivo.\n")

        # Provider
        print("  Escolha o modelo de IA:")
        print("    1. Ollama (local, grátis)")
        print("    2. OpenAI (precisa de API key)")
        print("    3. Anthropic (precisa de API key)")
        print("    4. AWS Bedrock")

        choice = input("\n  Opção [1]: ").strip() or "1"
        providers = {"1": "ollama", "2": "openai", "3": "anthropic", "4": "bedrock"}
        provider = providers.get(choice, "ollama")
        config.set("llm_provider", provider)

        if provider in ("openai", "anthropic"):
            key = input(f"  API Key para {provider}: ").strip()
            if key:
                config.set(f"{provider}_api_key", key)

        config.save()
        mark_onboarding_done()
        print("\n  ✓ Configuração salva! Iniciando Harmoni...\n")
        return True


def run_onboarding() -> bool:
    """Run the onboarding wizard. Returns True if completed."""
    wizard = OnboardingWizard()
    return wizard.run()
