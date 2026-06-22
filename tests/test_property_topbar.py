"""Property-based tests for Topbar activity signaling.

Feature: produto-percebido
"""

import os
import tempfile
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.ui.topbar import signal_topbar_idle, signal_topbar_processing

# --- Strategies ---

# Activity strings: non-empty text without newlines or null bytes
_activity = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters=("\n", "\r", "\x00"),
    ),
    min_size=1,
    max_size=300,
)


class TestTopbarActivitySignaling:
    """Property 11: Topbar activity signaling writes correct state.

    Feature: produto-percebido, Property 11: Topbar activity signaling writes correct state
    """

    @given(activity=_activity)
    @settings(max_examples=20)
    def test_signal_processing_writes_correct_state(self, activity: str):
        """For any activity description string, signal_topbar_processing(activity)
        writes "processing|{activity}" to the activity file.

        **Validates: Requirements 7.2**
        """
        with tempfile.TemporaryDirectory() as tmp:
            activity_file = os.path.join(tmp, ".topbar_activity")

            with patch("cios.ui.topbar._ACTIVITY_FILE", activity_file):
                signal_topbar_processing(activity)

            # File must exist after signaling processing
            assert os.path.exists(activity_file), "Activity file was not created"

            with open(activity_file) as f:
                content = f.read()

            expected = f"processing|{activity}"
            assert content == expected, f"Expected '{expected}' but got '{content}'"

    @given(activity=_activity)
    @settings(max_examples=20)
    def test_signal_idle_removes_file(self, activity: str):
        """For any activity description string, after signal_topbar_processing(activity),
        signal_topbar_idle() removes the activity file.

        **Validates: Requirements 7.2**
        """
        with tempfile.TemporaryDirectory() as tmp:
            activity_file = os.path.join(tmp, ".topbar_activity")

            with patch("cios.ui.topbar._ACTIVITY_FILE", activity_file):
                # First create the file via processing signal
                signal_topbar_processing(activity)
                assert os.path.exists(activity_file), (
                    "Activity file should exist after signal_topbar_processing"
                )

                # Then idle should remove it
                signal_topbar_idle()

            assert not os.path.exists(activity_file), (
                "Activity file should be removed after signal_topbar_idle"
            )

    @given(activity=_activity)
    @settings(max_examples=20)
    def test_reading_file_recovers_activity(self, activity: str):
        """Reading the activity file after signal_topbar_processing recovers
        the original activity string by parsing the "processing|{activity}" format.

        **Validates: Requirements 7.2**
        """
        with tempfile.TemporaryDirectory() as tmp:
            activity_file = os.path.join(tmp, ".topbar_activity")

            with patch("cios.ui.topbar._ACTIVITY_FILE", activity_file):
                signal_topbar_processing(activity)

            with open(activity_file) as f:
                content = f.read()

            # Parse the format: "processing|{activity}"
            assert content.startswith("processing|"), (
                f"Content should start with 'processing|', got: '{content}'"
            )

            recovered = content.split("|", 1)[1]
            assert recovered == activity, (
                f"Recovered activity '{recovered}' != original '{activity}'"
            )
