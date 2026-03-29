from __future__ import annotations

from transformers import pipeline as hf_pipeline

from .config import PipelineConfig


class SentimentScorer:
    """Directional sentiment scoring using zero-shot classification.

    Given a prediction-market contract question (e.g. "Will Bitcoin reach
    $100k by end of 2026?"), each piece of text is classified into
    "yes" vs "no" direction — NOT generic positive/negative.
    """

    _CLASSIFIER_CACHE: dict[tuple[str, int], object] = {}

    def __init__(
        self,
        contract_question: str,
        config: PipelineConfig | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.contract_question = contract_question
        self._classifier = None

        # Build hypothesis template and labels from the contract question
        self._yes_label = f"This suggests the answer is YES: {contract_question}"
        self._no_label = f"This suggests the answer is NO: {contract_question}"
        self._labels = [self._yes_label, self._no_label]

    @property
    def classifier(self):
        if self._classifier is None:
            cache_key = (self.config.sentiment_model, -1)
            if cache_key not in self._CLASSIFIER_CACHE:
                self._CLASSIFIER_CACHE[cache_key] = hf_pipeline(
                    "zero-shot-classification",
                    model=self.config.sentiment_model,
                    device=-1,  # CPU; set to 0 for GPU
                )
            self._classifier = self._CLASSIFIER_CACHE[cache_key]
        return self._classifier

    def score(self, text: str) -> tuple[float, float]:
        """Score a single text.

        Returns:
            (sentiment_score, sentiment_confidence)
            sentiment_score: -1 (strong no) to 1 (strong yes)
            sentiment_confidence: 0 to 1
        """
        result = self.classifier(
            text,
            candidate_labels=self._labels,
            multi_label=False,
        )
        label_scores = dict(zip(result["labels"], result["scores"]))
        yes_prob = label_scores[self._yes_label]
        no_prob = label_scores[self._no_label]

        # Map to [-1, 1]: yes_prob - no_prob
        sentiment_score = yes_prob - no_prob
        # Confidence is how decisive the classifier is
        sentiment_confidence = abs(sentiment_score)

        return sentiment_score, sentiment_confidence

    def score_batch(self, texts: list[str]) -> list[tuple[float, float]]:
        """Score a batch of texts. Returns list of (score, confidence) tuples."""
        if not texts:
            return []

        results = self.classifier(
            texts,
            candidate_labels=self._labels,
            multi_label=False,
            batch_size=self.config.batch_size,
        )
        # hf pipeline returns a single dict for length-1 input
        if isinstance(results, dict):
            results = [results]

        out: list[tuple[float, float]] = []
        for result in results:
            label_scores = dict(zip(result["labels"], result["scores"]))
            yes_prob = label_scores[self._yes_label]
            no_prob = label_scores[self._no_label]
            score = yes_prob - no_prob
            out.append((score, abs(score)))
        return out
