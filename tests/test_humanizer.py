"""Tests for the Humanizer module."""

import os
from unittest.mock import patch

import pytest

# Force English for consistent test results
os.environ["LANG"] = "en_US.UTF-8"
os.environ["LC_MESSAGES"] = ""
os.environ["LC_ALL"] = ""
os.environ["LANGUAGE"] = ""

from harmoni.core.humanizer import (
    humanize_step,
    humanize_summary,
    humanize_error,
    humanize_result,
    _detect_language,
    _translate_pt,
)
import harmoni.core.humanizer
harmoni.core.humanizer._LANG = "en"


class TestHumanizeStep:
    """Step translation from technical to human language."""

    @pytest.mark.parametrize("technical,expected", [
        ("Install dependencies (npm install)", "Installing required components…"),
        ("Port 3000 in use — killing process", "Freeing up connection on port 3000…"),
        ("Starting server (npm run dev)", "Launching your project…"),
        ("Server running on port 3000 (PID 1234)", "Your project is running"),
        ("Server exited immediately", "Something went wrong during startup"),
        ("Could not detect project type", "No recognized project found here"),
        ("Killing process", "Stopping the process…"),
        ("Nothing is listening on port 8080", "Port 8080 is already free"),
        ("Read logs", "Reading system activity…"),
        ("Analyze errors", "Looking for issues…"),
        ("Execute: ls -la", "Running your command…"),
        ("No command provided", "No action specified"),
        # App launcher
        ("Opening Chrome", "Opening Chrome…"),
        ("Chrome is running", "Chrome is ready"),
        ("Failed to open Chrome", "Couldn't open Chrome"),
        # Session
        ("Desligar o computador", "Shutting down…"),
        ("Reiniciar o computador", "Restarting…"),
        ("Suspender (modo dormir)", "Going to sleep…"),
        # Network
        ("Checking Wi-Fi", "Checking connection…"),
        ("Check Wi-Fi", "Checking connection…"),
        ("Connecting to MinhaRede", "Connecting to MinhaRede…"),
        # Audio
        ("Checking volume", "Checking volume…"),
        ("Muting audio", "Muting…"),
        ("Unmuting audio", "Unmuting…"),
        # Disk (these match earlier generic patterns)
        ("Finding large files", "Finding large files…"),
        # Power
        ("Checking battery", "Checking battery…"),
        ("Checking brightness", "Checking brightness…"),
    ])
    def test_step_translations(self, technical, expected):
        result = humanize_step(technical)
        assert result == expected

    def test_unknown_step_strips_noise(self):
        result = humanize_step("Some random step (PID 12345)")
        assert "(PID 12345)" not in result

    def test_empty_step(self):
        result = humanize_step("")
        assert result == ""


class TestHumanizeSummary:
    """Summary translation."""

    @pytest.mark.parametrize("technical,expected", [
        ("Server running on port 3000 (PID 1234)", "Your project is live on port 3000"),
        ("Killed process on port 3000", "Stopped the service on port 3000"),
        ("Port 3000 is free", "Port 3000 is available"),
        ("No recent failures found", "Everything looks good — no recent issues"),
        ("I don't understand that request", 'I\'m not sure what you mean. Try something like "start my backend" or "what\'s running?"'),
        # App launcher
        ("Chrome opened", "Chrome is open"),
        ("App not found: spotify", 'I couldn\'t find an app called "spotify"'),
    ])
    def test_summary_translations(self, technical, expected):
        result = humanize_summary(technical)
        assert result == expected


class TestHumanizeError:
    """Error translation."""

    @pytest.mark.parametrize("error,expected_contains", [
        ("EADDRINUSE: address already in use :::3000", "Port 3000 is busy"),
        ("Port 3000 already in use", "Port 3000 is busy"),
        ("EACCES: permission denied", "Permission needed"),
        ("MODULE_NOT_FOUND: Cannot find module 'express'", "Missing component detected"),
        ("ENOSPC: no space left on device", "Storage is full"),
        ("ECONNREFUSED", "Service not reachable"),
        ("SyntaxError: Unexpected token", "Code error detected"),
        ("Command timed out after 120s", "Took too long — stopped"),
        ("BLOCKED: dangerous command", "Blocked for safety"),
    ])
    def test_error_translations(self, error, expected_contains):
        result = humanize_error(error)
        assert expected_contains in result

    def test_empty_error(self):
        assert humanize_error("") == ""

    def test_long_error_truncated(self):
        long_error = "x" * 500
        result = humanize_error(long_error)
        assert len(result) <= 120


class TestPTBRTranslation:
    """PT-BR translation layer."""

    def test_translate_pt_when_pt(self):
        with patch("harmoni.core.humanizer._LANG", "pt"):
            result = _translate_pt("Checking connection…")
            assert result == "Verificando conexão…"

    def test_translate_pt_when_en(self):
        with patch("harmoni.core.humanizer._LANG", "en"):
            result = _translate_pt("Checking connection…")
            assert result == "Checking connection…"

    def test_translate_multiple_phrases(self):
        with patch("harmoni.core.humanizer._LANG", "pt"):
            result = _translate_pt("Volume: 75%")
            assert "Volume:" in result


class TestLanguageDetection:
    """Language auto-detection."""

    def test_detect_pt_from_lang(self):
        with patch.dict(os.environ, {"LANG": "pt_BR.UTF-8"}, clear=False):
            assert _detect_language() == "pt"

    def test_detect_en_default(self):
        with patch.dict(os.environ, {"LANG": "en_US.UTF-8", "LC_MESSAGES": "", "LC_ALL": "", "LANGUAGE": ""}, clear=False):
            assert _detect_language() == "en"


class TestHumanizeResult:
    """Full result humanization."""

    def test_humanize_result_structure(self):
        from harmoni.core.planner import PlanResult

        plan_result = PlanResult(
            plan_steps=["Starting server (npm run dev)", "Server running on port 3000 (PID 1234)"],
            results=[],
            outcome="success",
            summary="Server running on port 3000 (PID 1234)",
            voice_mode="full",
        )

        steps, summary, outcome, voice_mode = humanize_result(plan_result)
        assert len(steps) == 2
        # Depending on locale, could be EN or PT
        assert "project" in steps[0].lower() or "projeto" in steps[0].lower()
        assert "3000" in summary
        assert outcome == "success"
        assert voice_mode == "full"
