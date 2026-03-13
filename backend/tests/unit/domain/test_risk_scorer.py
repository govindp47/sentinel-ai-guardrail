"""Unit tests for RiskScorer."""
from __future__ import annotations

import pytest

from sentinel.domain.engines.prompt_validation.injection_detector import InjectionCheckResult
from sentinel.domain.engines.prompt_validation.pii_detector import PIICheckResult
from sentinel.domain.engines.prompt_validation.policy_filter import PolicyCheckResult
from sentinel.domain.engines.prompt_validation.risk_scorer import RiskScorer


@pytest.fixture
def scorer() -> RiskScorer:
    return RiskScorer()


def _inj(status: str) -> InjectionCheckResult:
    return InjectionCheckResult(status=status, detail=None)  # type: ignore[arg-type]


def _pii(status: str) -> PIICheckResult:
    return PIICheckResult(status=status, pii_types=(), masked_text="")  # type: ignore[arg-type]


def _pol(status: str) -> PolicyCheckResult:
    return PolicyCheckResult(status=status, violated_category=None)  # type: ignore[arg-type]


class TestRiskScorerWeights:
    def test_zero_signals(self, scorer: RiskScorer) -> None:
        assert scorer.score(_inj("pass"), _pii("pass"), _pol("pass")) == 0

    def test_injection_block_only(self, scorer: RiskScorer) -> None:
        assert scorer.score(_inj("block"), _pii("pass"), _pol("pass")) == 60

    def test_injection_flag_only(self, scorer: RiskScorer) -> None:
        assert scorer.score(_inj("flag"), _pii("pass"), _pol("pass")) == 30

    def test_pii_flag_only(self, scorer: RiskScorer) -> None:
        assert scorer.score(_inj("pass"), _pii("flag"), _pol("pass")) == 15

    def test_policy_block_only(self, scorer: RiskScorer) -> None:
        assert scorer.score(_inj("pass"), _pii("pass"), _pol("block")) == 50

    def test_injection_block_plus_pii(self, scorer: RiskScorer) -> None:
        # 60 + 15 = 75
        assert scorer.score(_inj("block"), _pii("flag"), _pol("pass")) == 75

    def test_all_signals_capped_at_100(self, scorer: RiskScorer) -> None:
        # 60 + 15 + 50 = 125 → clamped to 100
        result = scorer.score(_inj("block"), _pii("flag"), _pol("block"))
        assert result == 100

    def test_injection_flag_plus_policy_block(self, scorer: RiskScorer) -> None:
        # 30 + 50 = 80
        assert scorer.score(_inj("flag"), _pii("pass"), _pol("block")) == 80

    def test_output_always_in_range(self, scorer: RiskScorer) -> None:
        for inj in ("pass", "flag", "block"):
            for pii in ("pass", "flag"):
                for pol in ("pass", "block"):
                    result = scorer.score(_inj(inj), _pii(pii), _pol(pol))
                    assert 0 <= result <= 100
