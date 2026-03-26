"""Integration tests for DetoxifyClassifier.

These tests load the detoxify model inside a worker process and verify
correct dispatch, output format, and pool lifecycle.
"""

from __future__ import annotations

import asyncio

import pytest

from sentinel.infrastructure.safety.detoxify_classifier import DetoxifyClassifier

# Expected detoxify "original" model output keys.
_EXPECTED_KEYS = {
    "toxicity",
    "severe_toxicity",
    "obscene",
    "threat",
    "insult",
    "identity_attack",
}


@pytest.fixture
def classifier() -> DetoxifyClassifier:
    """Fresh classifier per test; shut down after use."""
    c = DetoxifyClassifier(max_workers=1)
    yield c
    c.shutdown(wait=True)


class TestPredict:
    @pytest.mark.asyncio
    async def test_benign_text_returns_low_scores(
        self, classifier: DetoxifyClassifier
    ) -> None:
        scores = await classifier.predict("I love programming and open source.")
        assert isinstance(scores, dict)
        for key in _EXPECTED_KEYS:
            assert key in scores, f"Missing key: {key}"
            assert 0.0 <= scores[key] <= 1.0, f"Score out of range for {key}"
        assert scores["toxicity"] < 0.1

    @pytest.mark.asyncio
    async def test_all_expected_keys_present(
        self, classifier: DetoxifyClassifier
    ) -> None:
        scores = await classifier.predict("Hello world.")
        assert set(scores.keys()) >= _EXPECTED_KEYS

    @pytest.mark.asyncio
    async def test_scores_are_python_floats(
        self, classifier: DetoxifyClassifier
    ) -> None:
        scores = await classifier.predict("The sky is blue.")
        for value in scores.values():
            assert isinstance(value, float), f"Expected float, got {type(value)}"

    @pytest.mark.asyncio
    async def test_completes_within_timeout(
        self, classifier: DetoxifyClassifier
    ) -> None:
        """First call loads the model in the worker; must finish within 10s."""
        scores = await asyncio.wait_for(
            classifier.predict("Unit testing is important."),
            timeout=10.0,
        )
        assert "toxicity" in scores


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_is_idempotent_after_predict(self) -> None:
        c = DetoxifyClassifier(max_workers=1)
        await c.predict("test")
        c.shutdown(wait=True)
        # Second shutdown call must not raise.
        c.shutdown(wait=False)
