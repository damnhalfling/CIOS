"""Property-based tests for output sanitization pipeline and error enrichment.

Feature: produto-percebido
Property 2: Output sanitization pipeline strips all technical artifacts
Property 9: Error enrichment always provides a recovery suggestion

Validates: Requirements 1.6, 3.4, 5.5, 8.1, 8.2, 8.3, 8.4, 8.5
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.error_recovery import enrich_error
from cios.core.handlers._common import sanitize_error as _sanitize_error
from cios.core.humanizer import humanize_error

# ── Forbidden patterns that must NEVER appear in user-facing output ──────

FORBIDDEN_PATTERNS = [
    (re.compile(r"/[\w/.\-]{3,}"), "File paths"),
    (re.compile(r"PID \d+"), "Process IDs"),
    (re.compile(r'File ".*", line \d+'), "Tracebacks"),
    (re.compile(r"\b(errno|E[A-Z]{2,})\b"), "Error codes"),
    (re.compile(r"\w+Error:"), "Python exception class names"),
    (re.compile(r"subprocess\."), "Subprocess references"),
    (re.compile(r"Popen|CalledProcessError"), "Implementation details"),
    (re.compile(r"stderr:"), "Raw stderr"),
]


# ── Strategies for generating error strings with technical artifacts ─────

# File paths
_file_paths = st.sampled_from(
    [
        "/usr/lib/python3/dist-packages/foo.py",
        "/home/user/.local/lib/python3.11/site-packages/bar/baz.py",
        "/etc/systemd/system/cios.service",
        "/var/log/syslog",
        "/tmp/cios_crash_12345.log",
        "/opt/cios/bin/daemon",
        "/usr/bin/python3.11",
        "/proc/1234/status",
    ]
)

# PID references
_pid_refs = st.builds(
    lambda pid: f"PID {pid}",
    st.integers(min_value=1, max_value=99999),
)

# Tracebacks
_tracebacks = st.builds(
    lambda fname, lineno: f'File "{fname}", line {lineno}, in <module>',
    st.sampled_from(
        [
            "/usr/lib/python3/dist-packages/subprocess.py",
            "/home/user/project/main.py",
            "/opt/cios/cios/core/executor.py",
        ]
    ),
    st.integers(min_value=1, max_value=999),
)

# Error codes
_error_codes = st.sampled_from(
    [
        "errno",
        "ENOENT",
        "EACCES",
        "EADDRINUSE",
        "ECONNREFUSED",
        "EPERM",
        "ENOSPC",
        "ETIMEDOUT",
    ]
)

# Python exception class names
_exception_names = st.sampled_from(
    [
        "FileNotFoundError:",
        "PermissionError:",
        "OSError:",
        "ConnectionRefusedError:",
        "TimeoutError:",
        "RuntimeError:",
        "subprocess.CalledProcessError:",
        "ValueError:",
    ]
)

# Subprocess references
_subprocess_refs = st.sampled_from(
    [
        "subprocess.run failed",
        "subprocess.Popen raised",
        "CalledProcessError: Command returned non-zero",
        "Popen(cmd, stdout=PIPE)",
    ]
)

# Random filler text (non-technical)
_filler_text = st.sampled_from(
    [
        "something went wrong",
        "operation failed",
        "could not complete the action",
        "an error occurred while processing",
        "the system encountered a problem",
        "unable to proceed",
        "unexpected failure during execution",
    ]
)


# Composite strategy: build error strings with injected technical artifacts
@st.composite
def _error_with_artifacts(draw):
    """Generate an error string containing at least one technical artifact."""
    parts = []

    # Always include some filler text
    parts.append(draw(_filler_text))

    # Inject at least one artifact, possibly more
    artifact_strategies = [
        _file_paths,
        _pid_refs,
        _tracebacks,
        _error_codes,
        _exception_names,
        _subprocess_refs,
    ]

    # Pick 1-3 artifact types to inject
    num_artifacts = draw(st.integers(min_value=1, max_value=3))
    chosen = draw(
        st.lists(
            st.sampled_from(artifact_strategies),
            min_size=num_artifacts,
            max_size=num_artifacts,
        )
    )

    for strategy in chosen:
        parts.append(draw(strategy))

    # Optionally add stderr: prefix
    if draw(st.booleans()):
        parts.insert(0, "stderr:")

    # Shuffle and join
    order = draw(st.permutations(range(len(parts))))
    shuffled = [parts[i] for i in order]
    separator = draw(st.sampled_from([" ", "\n", " — ", ": "]))
    return separator.join(shuffled)


# ── Property Test ────────────────────────────────────────────────────────


class TestOutputSanitizationPipeline:
    """Property 2: Output sanitization pipeline strips all technical artifacts.

    Feature: produto-percebido, Property 2: Output sanitization pipeline strips all technical artifacts
    """

    @given(error_input=_error_with_artifacts())
    @settings(max_examples=20)
    def test_sanitization_pipeline_strips_all_technical_artifacts(self, error_input: str):
        """For any error string containing file paths, tracebacks, error codes,
        PID references, or Python exception class names, passing it through
        _sanitize_error → humanize_error → enrich_error produces output that
        contains none of those technical patterns.

        **Validates: Requirements 1.6, 3.4, 8.1, 8.3, 8.4, 8.5**
        """
        # Stage 1: sanitize raw error
        sanitized = _sanitize_error(error_input)

        # Stage 2: humanize the sanitized error
        humanized = humanize_error(sanitized)

        # Stage 3: enrich with recovery suggestion
        enriched = enrich_error(humanized)

        # Assert: no forbidden patterns in the final output
        for pattern, description in FORBIDDEN_PATTERNS:
            match = pattern.search(enriched)
            assert match is None, (
                f"Forbidden pattern '{description}' found in output.\n"
                f"Match: '{match.group()}'\n"
                f"Input: {error_input!r}\n"
                f"After sanitize: {sanitized!r}\n"
                f"After humanize: {humanized!r}\n"
                f"After enrich: {enriched!r}"
            )


# ── Strategies for generating human-readable error strings (non-technical) ───

# Human-readable error phrases that would have already been through sanitization
_human_error_phrases = st.sampled_from(
    [
        "something went wrong",
        "operation failed",
        "could not complete the action",
        "an error occurred while processing",
        "the system encountered a problem",
        "unable to proceed",
        "unexpected failure during execution",
        "connection was refused",
        "network timed out",
        "permission was denied",
        "disk is full",
        "port is busy",
        "application not found",
        "package not found",
        "audio system unavailable",
        "bluetooth not available",
        "window not found",
        "pairing failed",
        "wrong password entered",
        "command did not succeed",
        "could not connect to the server",
        "the operation took too long",
        "dependencies are broken",
        "brightness control not available",
    ]
)


@st.composite
def _human_readable_error(draw):
    """Generate a non-empty human-readable error string (post-sanitization).

    These simulate errors that have already been through the sanitization
    pipeline, so they contain no technical artifacts like paths, PIDs, etc.
    """
    # Pick 1-3 phrases and join them
    num_phrases = draw(st.integers(min_value=1, max_value=3))
    phrases = [draw(_human_error_phrases) for _ in range(num_phrases)]
    separator = draw(st.sampled_from([". ", " — ", ": ", ", "]))
    return separator.join(phrases)


# Forbidden patterns for recovery suggestions — stricter than the pipeline
# patterns above. These target actual technical artifacts, not product names
# like "PulseAudio/PipeWire" which legitimately contain a slash.
SUGGESTION_FORBIDDEN_PATTERNS = [
    (re.compile(r"/[\w/.\-]{3,}/[\w/.\-]+"), "File paths (multi-segment)"),
    (re.compile(r"PID \d+"), "Process IDs"),
    (re.compile(r'File ".*", line \d+'), "Tracebacks"),
    (re.compile(r"\b(errno|E[A-Z]{2,})\b"), "Error codes"),
    (re.compile(r"\w+Error:"), "Python exception class names"),
    (re.compile(r"subprocess\."), "Subprocess references"),
    (re.compile(r"Popen|CalledProcessError"), "Implementation details"),
    (re.compile(r"stderr:"), "Raw stderr"),
]


# ── Property 9 Test ──────────────────────────────────────────────────────


class TestErrorEnrichment:
    """Property 9: Error enrichment always provides a recovery suggestion.

    Feature: produto-percebido, Property 9: Error enrichment always provides a recovery suggestion
    """

    @given(error_input=_human_readable_error())
    @settings(max_examples=20)
    def test_enrich_error_always_appends_recovery_suggestion(self, error_input: str):
        """For any non-empty human-readable error string, enrich_error should
        return a string strictly longer than the input, with a non-empty
        appended suggestion that contains no technical artifacts.

        **Validates: Requirements 5.5, 8.2**
        """
        enriched = enrich_error(error_input)

        # 1. Output is strictly longer than input (suggestion was appended)
        assert len(enriched) > len(error_input), (
            f"enrich_error did not make output longer than input.\n"
            f"Input ({len(error_input)} chars): {error_input!r}\n"
            f"Output ({len(enriched)} chars): {enriched!r}"
        )

        # 2. The appended part is non-empty
        # enrich_error uses f"{error}\n{suggestion}" format
        assert enriched.startswith(error_input), (
            f"Enriched output does not start with original error.\n"
            f"Input: {error_input!r}\n"
            f"Output: {enriched!r}"
        )
        appended = enriched[len(error_input) :]
        # Strip the separator (newline) to get the suggestion content
        suggestion = appended.lstrip("\n").strip()
        assert len(suggestion) > 0, (
            f"Appended suggestion is empty.\n"
            f"Input: {error_input!r}\n"
            f"Output: {enriched!r}\n"
            f"Appended raw: {appended!r}"
        )

        # 3. The appended suggestion contains no technical artifacts
        for pattern, description in SUGGESTION_FORBIDDEN_PATTERNS:
            match = pattern.search(suggestion)
            assert match is None, (
                f"Forbidden pattern '{description}' found in recovery suggestion.\n"
                f"Match: '{match.group()}'\n"
                f"Input: {error_input!r}\n"
                f"Suggestion: {suggestion!r}\n"
                f"Full output: {enriched!r}"
            )
