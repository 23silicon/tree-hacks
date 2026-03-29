from __future__ import annotations

import spacy
from spacy.language import Language

from .config import PipelineConfig


class Tagger:
    """Named entity recognition and topic tagging using spaCy."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._nlp: Language | None = None

    @property
    def nlp(self) -> Language:
        if self._nlp is None:
            self._nlp = spacy.load(self.config.spacy_model)
        return self._nlp

    def extract_entities(self, text: str) -> list[str]:
        """Extract named entities from text."""
        doc = self.nlp(text)
        # Deduplicate while preserving order
        seen: set[str] = set()
        entities: list[str] = []
        for ent in doc.ents:
            key = ent.text.strip()
            if key and key not in seen:
                seen.add(key)
                entities.append(key)
        return entities

    def extract_topic_tags(self, text: str) -> list[str]:
        """Simple keyword-based topic tagging.

        Checks if any of the configured topic labels appear in the text
        (case-insensitive). For a production system you'd use a classifier,
        but this is fast and good enough for a hackathon.
        """
        text_lower = text.lower()
        return [label for label in self.config.topic_labels if label in text_lower]

    def tag(self, text: str) -> tuple[list[str], list[str]]:
        """Run entity extraction and topic tagging.

        Returns:
            (entities, topic_tags)
        """
        return self.extract_entities(text), self.extract_topic_tags(text)

    def tag_batch(self, texts: list[str]) -> list[tuple[list[str], list[str]]]:
        """Tag a batch of texts. Returns list of (entities, topic_tags)."""
        return [self.tag(text) for text in texts]
