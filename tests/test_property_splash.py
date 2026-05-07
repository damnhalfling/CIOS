"""Property-based tests for Splash progress protocol.

Feature: produto-percebido
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.ui.splash import update_splash_progress


# --- Strategies ---

# Stage names: non-empty strings without pipe characters or newlines
_stage_name = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters=("|", "\n", "\r", "\x00"),
    ),
    min_size=1,
    max_size=200,
)

# Total: positive integers
_total = st.integers(min_value=1, max_value=10_000)


@st.composite
def _current_total(draw):
    """Generate (current, total) where 0 <= current <= total and total >= 1."""
    total = draw(_total)
    current = draw(st.integers(min_value=0, max_value=total))
    return current, total


class TestSplashProgressProtocol:
    """Property 10: Splash progress protocol writes correct format.

    Feature: produto-percebido, Property 10: Splash progress protocol writes correct format
    """

    @given(stage=_stage_name, ct=_current_total())
    @settings(max_examples=100)
    def test_splash_progress_writes_correct_format(self, stage: str, ct: tuple):
        """For any stage name (non-empty, no pipes/newlines), current (non-negative),
        and total (positive, current <= total), update_splash_progress writes
        "{stage}|{current}|{total}" and reading the file parses back to original values.

        **Validates: Requirements 6.2**
        """
        current, total = ct

        with tempfile.TemporaryDirectory() as tmp:
            progress_file = Path(tmp) / ".splash_progress"

            with patch("cios.ui.splash._PROGRESS_FILE", str(progress_file)):
                update_splash_progress(stage, current, total)

            # File must exist after writing
            assert progress_file.exists(), "Progress file was not created"

            content = progress_file.read_text()

            # Assert exact format: "{stage}|{current}|{total}"
            expected = f"{stage}|{current}|{total}"
            assert content == expected, (
                f"Expected '{expected}' but got '{content}'"
            )

            # Parse back and verify round-trip
            parts = content.split("|")
            assert len(parts) == 3, (
                f"Expected 3 pipe-separated parts, got {len(parts)}: {parts}"
            )

            parsed_stage = parts[0]
            parsed_current = int(parts[1])
            parsed_total = int(parts[2])

            assert parsed_stage == stage, (
                f"Parsed stage '{parsed_stage}' != original '{stage}'"
            )
            assert parsed_current == current, (
                f"Parsed current {parsed_current} != original {current}"
            )
            assert parsed_total == total, (
                f"Parsed total {parsed_total} != original {total}"
            )
