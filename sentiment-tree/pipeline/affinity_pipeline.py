"""Affinity pipeline — orchestrates Stage 1 (embedding filter) + Stage 2 (LLM scoring).

Usage:
    from pipeline.affinity_pipeline import AffinityPipeline
    pipe = AffinityPipeline()
    candidates = pipe.stage1(events, predictions)
    for result_dict in pipe.stream(candidates):
        print(result_dict)
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

from .candidate_filter import CandidateFilter
from .config import PipelineConfig
from .embedder import Embedder
from .llm_scorer import LLMAffinityScorer
from .models import AffinityResult, Event, Prediction


class AffinityPipeline:
    """Two-stage pipeline: embedding candidate filter → LLM affinity scoring."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self.embedder = Embedder(self.config)
        self.candidate_filter = CandidateFilter(self.embedder, self.config)
        self.llm_scorer = LLMAffinityScorer(self.config)

    def stage1(
        self,
        events: list[Event],
        predictions: list[Prediction],
    ) -> list[tuple[Event, Prediction, float]]:
        """Run Stage 1 only: embedding-based candidate filtering."""
        return self.candidate_filter.filter_candidates(events, predictions)

    def stream(
        self,
        candidates: list[tuple[Event, Prediction, float]],
    ) -> Generator[dict[str, Any], None, None]:
        """Stream Stage 2 LLM results as dicts, one pair at a time.

        Yields:
            dict representation of each AffinityResult as the LLM responds.
        """
        for result in self.llm_scorer.score_batch(candidates):
            yield result.model_dump()

    def run(
        self,
        events: list[Event],
        predictions: list[Prediction],
        skip_llm: bool = False,
    ) -> tuple[list[tuple[Event, Prediction, float]], list[dict[str, Any]]]:
        """Run the full two-stage affinity pipeline.

        Args:
            events: Incoming live events.
            predictions: Polymarket/Kalshi prediction contracts.
            skip_llm: If True, only run Stage 1 (useful for testing / cost control).

        Returns:
            (stage1_candidates, stage2_results)
            stage1_candidates: all pairs that passed embedding threshold
            stage2_results: list of AffinityResult dicts (empty if skip_llm)
        """
        candidates = self.stage1(events, predictions)

        if skip_llm or not candidates:
            return candidates, []

        results = list(self.stream(candidates))
        return candidates, results
