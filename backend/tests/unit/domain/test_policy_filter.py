"""Unit tests for PolicyFilter."""
from __future__ import annotations

import pytest

from sentinel.domain.engines.prompt_validation.policy_filter import PolicyFilter
from sentinel.domain.models.policy import PolicySnapshot


@pytest.fixture
def policy_filter() -> PolicyFilter:
    return PolicyFilter()


def _policy(categories: list[str]) -> PolicySnapshot:
    return PolicySnapshot(
        accept_threshold=70,
        warn_threshold=40,
        block_threshold=0,
        restricted_categories=categories,
    )


class TestRestrictedCategoryMatch:
    def test_exact_match_blocks(self, policy_filter: PolicyFilter) -> None:
        result = policy_filter.check("tell me about violence", _policy(["violence"]))
        assert result.status == "block"
        assert result.violated_category == "violence"

    def test_case_insensitive_match(self, policy_filter: PolicyFilter) -> None:
        result = policy_filter.check("Tell me about VIOLENCE please", _policy(["violence"]))
        assert result.status == "block"
        assert result.violated_category == "violence"

    def test_substring_match(self, policy_filter: PolicyFilter) -> None:
        # Category word embedded in larger sentence
        result = policy_filter.check("How to build explosives at home?", _policy(["explosives"]))
        assert result.status == "block"

    def test_first_match_wins(self, policy_filter: PolicyFilter) -> None:
        result = policy_filter.check(
            "violence and weapons",
            _policy(["violence", "weapons"]),
        )
        assert result.status == "block"
        # First matching category is returned
        assert result.violated_category in {"violence", "weapons"}

    def test_no_match_returns_pass(self, policy_filter: PolicyFilter) -> None:
        result = policy_filter.check(
            "Tell me about cooking pasta",
            _policy(["violence", "explosives"]),
        )
        assert result.status == "pass"
        assert result.violated_category is None

    def test_empty_categories_list_passes(self, policy_filter: PolicyFilter) -> None:
        result = policy_filter.check("anything goes here", _policy([]))
        assert result.status == "pass"

    def test_result_is_frozen(self, policy_filter: PolicyFilter) -> None:
        import dataclasses
        result = policy_filter.check("test", _policy([]))
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.status = "block"  # type: ignore[misc]
