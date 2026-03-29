"""Stage 2 — LLM-based affinity scoring.

For each (event, prediction) pair that survived Stage 1, ask an LLM:
  "Given this real-world event, how does it affect the likelihood of
   this prediction market outcome?"

Returns:
  - direction: -1 (pushes toward NO) to +1 (pushes toward YES)
  - magnitude: 0 (weak/tangential) to 1 (strong/direct evidence)
  - reasoning: one-paragraph explanation

Supports Anthropic (Claude), OpenAI, and Ollama backends.
"""
from __future__ import annotations

import json
import os
from collections.abc import Generator
from typing import Any

from .config import PipelineConfig
from .models import AffinityResult, Event, Prediction


SYSTEM_PROMPT = """\
You are an expert analyst scoring how real-world events affect prediction market outcomes.

You will receive:
- An EVENT (title, description, source summaries)
- A PREDICTION (question, current yes/no probabilities, category)

Your job: determine whether this event is EVIDENCE for or against the prediction resolving YES.

Respond with ONLY valid JSON (no markdown, no code fences):
{
  "direction": <float from -1.0 to 1.0>,
  "magnitude": <float from 0.0 to 1.0>,
  "reasoning": "<one paragraph>"
}

direction:
  +1.0 = strong evidence this prediction resolves YES
  -1.0 = strong evidence this prediction resolves NO
   0.0 = event is relevant but neutral / mixed evidence

magnitude:
  1.0 = direct, causal evidence (e.g. "US launches strike on Iran" for "Will US strike Iran?")
  0.5 = moderate indirect evidence
  0.1 = weak, tangential connection
  0.0 = no real evidential value despite topical overlap

Be precise. A war escalation story is strong evidence for military predictions
but only moderate evidence for economic predictions about the same region.
"""


def _build_user_prompt(event: Event, prediction: Prediction) -> str:
    sources_text = ""
    for s in event.Sources:
        sources_text += f"\n  - {s.Source}: {s.Summary}"

    return f"""\
EVENT:
  Title: {event.Title}
  Description: {event.Description}
  Sources:{sources_text or " (none)"}

PREDICTION:
  Question: {prediction.question}
  Category: {prediction.category}
  Current YES probability: {prediction.yes_probability:.0%}
  Current NO probability: {prediction.no_probability:.0%}
  Closes: {prediction.closes_at.strftime("%Y-%m-%d")}

Score how evidential this event is for this prediction.
"""


class LLMAffinityScorer:
    """Score event-prediction pairs using an LLM."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            provider = self.config.llm_provider

            if provider == "anthropic":
                from anthropic import Anthropic
                api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
                self._client = Anthropic(api_key=api_key)
            elif provider == "ollama":
                from openai import OpenAI
                base_url = self.config.llm_base_url or "http://localhost:11434/v1"
                self._client = OpenAI(api_key="ollama", base_url=base_url)
            else:
                from openai import OpenAI
                kwargs: dict[str, Any] = {}
                if self.config.llm_base_url:
                    kwargs["base_url"] = self.config.llm_base_url
                self._client = OpenAI(
                    api_key=os.environ.get("OPENAI_API_KEY", ""), **kwargs
                )
        return self._client

    def _call_llm(self, user_prompt: str) -> str:
        """Call the configured LLM and return raw response text."""
        if self.config.llm_provider == "anthropic":
            response = self.client.messages.create(
                model=self.config.llm_model,
                max_tokens=300,
                temperature=self.config.llm_temperature,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        else:
            # OpenAI-compatible (OpenAI / Ollama)
            response = self.client.chat.completions.create(
                model=self.config.llm_model,
                temperature=self.config.llm_temperature,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=300,
            )
            return response.choices[0].message.content

    def score_pair(
        self,
        event: Event,
        prediction: Prediction,
        embedding_similarity: float,
    ) -> AffinityResult:
        """Ask the LLM to score one event-prediction pair."""
        user_prompt = _build_user_prompt(event, prediction)

        raw = self._call_llm(user_prompt).strip()
        # Strip markdown code fences if the model adds them anyway
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        parsed = json.loads(raw)

        direction = max(-1.0, min(1.0, float(parsed["direction"])))
        magnitude = max(0.0, min(1.0, float(parsed["magnitude"])))
        reasoning = str(parsed.get("reasoning", ""))

        return AffinityResult(
            event_id=event.ID,
            prediction_id=prediction.id,
            event_title=event.Title,
            prediction_question=prediction.question,
            embedding_similarity=embedding_similarity,
            direction=direction,
            magnitude=magnitude,
            reasoning=reasoning,
        )

    def score_batch(
        self,
        candidates: list[tuple[Event, Prediction, float]],
    ) -> Generator[AffinityResult, None, None]:
        """Yield scored results one at a time as the LLM responds.

        Each element is (event, prediction, embedding_similarity) from Stage 1.
        """
        for event, prediction, sim in candidates:
            yield self.score_pair(event, prediction, sim)
