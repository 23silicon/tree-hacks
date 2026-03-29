"""
=======================================================================
SentimentTree Pipeline — Stage-by-Stage Unit Tests
=======================================================================

These tests walk through EVERY stage of the Role 2 embedding pipeline
with dummy data, printing detailed explanations at each step so you can
see exactly what happens to a piece of scraped data as it flows through.

Pipeline flow:
  Raw Text → [1] Embed → [2] Relevance Filter → [3] Sentiment Score
           → [4] Tag → [5] Vector Store → [6] Semantic Search

Run with:  pytest tests/test_pipeline_stages.py -v -s
           (the -s flag is REQUIRED to see the descriptive print output)
=======================================================================
"""

import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import PipelineConfig
from pipeline.embedder import Embedder
from pipeline.models import EnrichedItem, RawItem
from pipeline.relevance_filter import RelevanceFilter
from pipeline.sentiment_scorer import SentimentScorer
from pipeline.tagger import Tagger
from pipeline.vector_store import VectorStore
from pipeline.semantic_search import SemanticSearch
from pipeline.pipeline import Pipeline


# ─── Shared fixtures ────────────────────────────────────────────────

CONTRACT_QUESTION = "Will Bitcoin reach $100k by end of 2026?"

DUMMY_ITEMS = [
    RawItem(
        text="Bitcoin just broke through $95k resistance with massive volume. "
             "Institutional buyers are piling in through ETF inflows this week.",
        source="reddit",
        timestamp=datetime(2026, 3, 25, 14, 30),
        url="https://reddit.com/r/bitcoin/abc123",
    ),
    RawItem(
        text="The Federal Reserve signaled potential rate cuts which historically "
             "correlates with crypto bull runs. BTC looking strong.",
        source="x",
        timestamp=datetime(2026, 3, 26, 9, 15),
        url="https://x.com/cryptoanalyst/status/123",
    ),
    RawItem(
        text="Major regulatory crackdown incoming — SEC is preparing new enforcement "
             "actions against crypto exchanges. Market uncertainty rising.",
        source="news_rss",
        timestamp=datetime(2026, 3, 26, 11, 0),
        url="https://reuters.com/crypto-sec-crackdown",
    ),
    RawItem(
        text="I just made the best chocolate chip cookies. The secret is browning "
             "the butter first and adding a pinch of sea salt.",
        source="reddit",
        timestamp=datetime(2026, 3, 26, 12, 0),
        url="https://reddit.com/r/baking/xyz789",
    ),
    RawItem(
        text="Bitcoin mining difficulty just hit an all-time high. Hash rate "
             "continues to climb as miners expect higher prices ahead.",
        source="youtube",
        timestamp=datetime(2026, 3, 27, 8, 45),
        url="https://youtube.com/watch?v=mining123",
    ),
]


@pytest.fixture(scope="module")
def config():
    """Pipeline config shared across all tests in this module."""
    tmp_dir = tempfile.mkdtemp(prefix="sentimenttree_test_")
    cfg = PipelineConfig(
        chroma_persist_dir=tmp_dir,
        chroma_collection="test_collection",
    )
    yield cfg
    # Cleanup ChromaDB test data after all tests
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def embedder(config):
    return Embedder(config)


# ─── STAGE 1: Embedder ──────────────────────────────────────────────

class TestStage1Embedder:
    """
    STAGE 1 — EMBEDDING
    ====================
    The Embedder converts raw text into dense vector representations
    (embeddings). Each piece of text becomes a list of 384 floating-point
    numbers that capture its *semantic meaning* — texts about similar
    topics will have vectors that point in similar directions.

    Model: all-MiniLM-L6-v2 (384 dimensions, ~23M parameters)
    """

    def test_single_embedding_shape(self, embedder):
        """Each text produces a 384-dimensional vector."""
        print("\n" + "=" * 70)
        print("STAGE 1 — EMBEDDING: Single text → vector")
        print("=" * 70)
        print(f"\n  Model: {embedder.config.embedding_model}")
        print(f"  Input:  \"{DUMMY_ITEMS[0].text[:80]}...\"")

        embedding = embedder.embed_single(DUMMY_ITEMS[0].text)

        print(f"\n  Output: A vector of {len(embedding)} floating-point numbers")
        print(f"  First 10 values: {[round(v, 4) for v in embedding[:10]]}")
        print(f"  Vector magnitude: {np.linalg.norm(embedding):.4f}")
        print(f"    → Magnitude ≈ 1.0 because sentence-transformers L2-normalizes by default")

        assert len(embedding) == 384, f"Expected 384 dims, got {len(embedding)}"
        assert all(isinstance(v, float) for v in embedding)

    def test_batch_embedding(self, embedder):
        """Batch embedding processes multiple texts at once efficiently."""
        print("\n" + "=" * 70)
        print("STAGE 1 — EMBEDDING: Batch processing")
        print("=" * 70)

        texts = [item.text for item in DUMMY_ITEMS]
        print(f"\n  Processing {len(texts)} texts in a single batch...")
        embeddings = embedder.embed_texts(texts)

        print(f"  Result: {len(embeddings)} vectors, each of dimension {len(embeddings[0])}")
        for i, (item, emb) in enumerate(zip(DUMMY_ITEMS, embeddings)):
            print(f"    [{i}] {item.source:10s} | magnitude={np.linalg.norm(emb):.4f} | \"{item.text[:50]}...\"")

        assert len(embeddings) == len(texts)
        assert all(len(e) == 384 for e in embeddings)

    def test_similar_texts_have_close_embeddings(self, embedder):
        """Semantically similar texts should have high cosine similarity."""
        print("\n" + "=" * 70)
        print("STAGE 1 — EMBEDDING: Semantic similarity demo")
        print("=" * 70)

        text_btc = "Bitcoin price is surging due to institutional demand"
        text_crypto = "Cryptocurrency markets rally as big investors buy in"
        text_cooking = "The best way to bake sourdough bread at home"

        emb_btc = np.array(embedder.embed_single(text_btc))
        emb_crypto = np.array(embedder.embed_single(text_crypto))
        emb_cooking = np.array(embedder.embed_single(text_cooking))

        sim_related = float(np.dot(emb_btc, emb_crypto) / (np.linalg.norm(emb_btc) * np.linalg.norm(emb_crypto)))
        sim_unrelated = float(np.dot(emb_btc, emb_cooking) / (np.linalg.norm(emb_btc) * np.linalg.norm(emb_cooking)))

        print(f"\n  Text A: \"{text_btc}\"")
        print(f"  Text B: \"{text_crypto}\"")
        print(f"  Text C: \"{text_cooking}\"")
        print(f"\n  Cosine similarity A↔B (both about crypto): {sim_related:.4f}")
        print(f"  Cosine similarity A↔C (crypto vs cooking):  {sim_unrelated:.4f}")
        print(f"\n  → Related texts score MUCH higher ({sim_related:.2f} vs {sim_unrelated:.2f})")
        print(f"    This is how the relevance filter will separate signal from noise.")

        assert sim_related > sim_unrelated, "Related texts should be more similar"
        assert sim_related > 0.3, "Related texts should have similarity > 0.3"


# ─── STAGE 2: Relevance Filter ──────────────────────────────────────

class TestStage2RelevanceFilter:
    """
    STAGE 2 — RELEVANCE FILTERING
    ==============================
    The RelevanceFilter compares each item's embedding to the
    prediction contract question's embedding using cosine similarity.
    Items below the threshold are discarded as irrelevant noise.

    This is where the cookie recipe gets thrown out.
    """

    def test_relevance_scoring(self, embedder, config):
        """Score each dummy item against the contract question."""
        print("\n" + "=" * 70)
        print("STAGE 2 — RELEVANCE FILTER: Scoring items against contract")
        print("=" * 70)
        print(f"\n  Contract question: \"{CONTRACT_QUESTION}\"")
        print(f"  Threshold: {config.relevance_threshold}")
        print(f"\n  How it works:")
        print(f"    1. Embed the contract question into a 384-dim vector")
        print(f"    2. Embed each scraped item into a 384-dim vector")
        print(f"    3. Compute cosine similarity between each item and the question")
        print(f"    4. Items below {config.relevance_threshold} threshold → DISCARDED as noise\n")

        rf = RelevanceFilter(CONTRACT_QUESTION, embedder, config)
        texts = [item.text for item in DUMMY_ITEMS]
        embeddings = embedder.embed_texts(texts)
        scores = rf.score_batch(embeddings)

        for i, (item, score) in enumerate(zip(DUMMY_ITEMS, scores)):
            relevant = rf.is_relevant(score)
            status = "✓ RELEVANT" if relevant else "✗ FILTERED OUT"
            print(f"    [{i}] {score:.4f}  {status:15s}  ({item.source:10s}) \"{item.text[:55]}...\"")

        print(f"\n  → The cookie recipe ({scores[3]:.4f}) scores far below the threshold")
        print(f"    because its embedding points in a completely different semantic direction")
        print(f"    than \"Will Bitcoin reach $100k...\"")

        # Cookie recipe should be filtered
        assert not rf.is_relevant(scores[3]), "Cookie recipe should be irrelevant"
        # Bitcoin items should pass
        assert rf.is_relevant(scores[0]), "Bitcoin breakout should be relevant"

    def test_threshold_behavior(self, embedder, config):
        """Demonstrate how adjusting the threshold changes filtering."""
        print("\n" + "=" * 70)
        print("STAGE 2 — RELEVANCE FILTER: Threshold sensitivity")
        print("=" * 70)

        rf = RelevanceFilter(CONTRACT_QUESTION, embedder, config)
        texts = [item.text for item in DUMMY_ITEMS]
        embeddings = embedder.embed_texts(texts)
        scores = rf.score_batch(embeddings)

        for threshold in [0.10, 0.25, 0.40, 0.60]:
            passing = sum(1 for s in scores if s >= threshold)
            print(f"  Threshold {threshold:.2f} → {passing}/{len(scores)} items pass")

        print(f"\n  → Lower threshold = more items pass (more noise, more recall)")
        print(f"    Higher threshold = fewer items pass (less noise, risk missing relevant data)")
        print(f"    Default {config.relevance_threshold} is a balanced starting point for hackathon")


# ─── STAGE 3: Sentiment Scorer ──────────────────────────────────────

class TestStage3SentimentScorer:
    """
    STAGE 3 — DIRECTIONAL SENTIMENT SCORING
    =========================================
    The SentimentScorer uses zero-shot classification (BART-MNLI) to
    determine whether each text suggests YES or NO to the contract question.

    NOT generic positive/negative sentiment — this is CONTRACT-DIRECTIONAL.
    "SEC crackdown" is negative for "Will BTC reach $100k?" even though
    the text itself isn't emotionally negative.

    Model: facebook/bart-large-mnli (~400M parameters)
    """

    def test_sentiment_scoring_single(self, config):
        """Score a single bullish text against the contract."""
        print("\n" + "=" * 70)
        print("STAGE 3 — SENTIMENT SCORER: Single item scoring")
        print("=" * 70)
        print(f"\n  Contract: \"{CONTRACT_QUESTION}\"")
        print(f"  Model: {config.sentiment_model}")
        print(f"\n  How it works:")
        print(f"    1. Creates two hypothesis labels:")
        print(f"       YES = \"This suggests the answer is YES: {CONTRACT_QUESTION}\"")
        print(f"       NO  = \"This suggests the answer is NO: {CONTRACT_QUESTION}\"")
        print(f"    2. BART-MNLI classifies text against these two hypotheses")
        print(f"    3. Score = P(YES) - P(NO), ranging from -1.0 to +1.0")
        print(f"    4. Confidence = |score| (how decisive the classification is)\n")

        scorer = SentimentScorer(CONTRACT_QUESTION, config)
        text = DUMMY_ITEMS[0].text  # Bitcoin breakout text
        score, confidence = scorer.score(text)

        print(f"  Input: \"{text[:80]}...\"")
        print(f"  Score:      {score:+.4f}  ({'bullish / YES' if score > 0 else 'bearish / NO'})")
        print(f"  Confidence: {confidence:.4f}")
        print(f"\n  → Positive score means this text leans toward YES (BTC reaching $100k)")

        assert -1.0 <= score <= 1.0
        assert 0.0 <= confidence <= 1.0

    def test_sentiment_batch_direction(self, config):
        """Batch score all relevant items and show directional results."""
        print("\n" + "=" * 70)
        print("STAGE 3 — SENTIMENT SCORER: Batch scoring with directions")
        print("=" * 70)
        print(f"\n  Contract: \"{CONTRACT_QUESTION}\"\n")

        scorer = SentimentScorer(CONTRACT_QUESTION, config)
        # Skip the cookie recipe (index 3) — it would've been filtered at Stage 2
        relevant_items = [DUMMY_ITEMS[i] for i in [0, 1, 2, 4]]
        texts = [item.text for item in relevant_items]
        results = scorer.score_batch(texts)

        for item, (score, conf) in zip(relevant_items, results):
            direction = "→ YES (bullish)" if score > 0 else "→ NO  (bearish)"
            bar_len = int(abs(score) * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(f"  {score:+.4f} [{bar}] {direction}")
            print(f"         conf={conf:.4f}  ({item.source}) \"{item.text[:55]}...\"\n")

        print(f"  Key insight: 'SEC crackdown' should score bearish even though the text")
        print(f"  isn't emotionally negative — it's negative for BTC reaching $100k.")

        scores_only = [r[0] for r in results]
        assert all(-1.0 <= s <= 1.0 for s in scores_only)


# ─── STAGE 4: Tagger ────────────────────────────────────────────────

class TestStage4Tagger:
    """
    STAGE 4 — ENTITY EXTRACTION & TOPIC TAGGING
    =============================================
    The Tagger uses spaCy's NER (Named Entity Recognition) to extract
    entities (people, orgs, dates, money) and keyword matching for
    topic tags. This metadata helps Role 3 cluster nodes into
    narrative branches.

    Model: en_core_web_sm (spaCy small English model, ~12MB)
    """

    def test_entity_extraction(self, config):
        """Extract named entities from each item."""
        print("\n" + "=" * 70)
        print("STAGE 4 — TAGGER: Named Entity Recognition (NER)")
        print("=" * 70)
        print(f"\n  Model: {config.spacy_model}")
        print(f"\n  How it works:")
        print(f"    spaCy scans text for named entities like:")
        print(f"    - ORG: Organizations (SEC, Federal Reserve)")
        print(f"    - MONEY: Monetary values ($95k)")
        print(f"    - DATE: Temporal expressions (this week)")
        print(f"    - PERSON: People names\n")

        tagger = Tagger(config)

        for item in DUMMY_ITEMS:
            entities = tagger.extract_entities(item.text)
            print(f"  [{item.source:10s}] Entities: {entities}")
            print(f"             \"{item.text[:60]}...\"\n")

        # SEC should be extracted from the regulatory crackdown text
        sec_entities = tagger.extract_entities(DUMMY_ITEMS[2].text)
        assert any("SEC" in e for e in sec_entities), "Should extract SEC from regulatory text"

    def test_topic_tagging(self, config):
        """Tag items with topic labels via keyword matching."""
        print("\n" + "=" * 70)
        print("STAGE 4 — TAGGER: Topic tagging (keyword-based)")
        print("=" * 70)
        print(f"\n  Configured topic labels: {config.topic_labels}")
        print(f"\n  How it works:")
        print(f"    Simple case-insensitive substring match.")
        print(f"    If 'crypto' appears in the text → tagged with 'crypto'.")
        print(f"    Fast and good enough for a hackathon. A production system")
        print(f"    would use a trained classifier.\n")

        tagger = Tagger(config)

        for item in DUMMY_ITEMS:
            _, tags = tagger.tag(item.text)
            print(f"  [{item.source:10s}] Tags: {tags or '(none)'}")
            print(f"             \"{item.text[:60]}...\"\n")

    def test_combined_tag_output(self, config):
        """The tag() method returns both entities and topics together."""
        print("\n" + "=" * 70)
        print("STAGE 4 — TAGGER: Combined output (entities + topics)")
        print("=" * 70)
        print(f"\n  The tag() method returns a tuple: (entities, topic_tags)")
        print(f"  This is what gets attached to each EnrichedItem.\n")

        tagger = Tagger(config)
        entities, topics = tagger.tag(DUMMY_ITEMS[2].text)  # SEC crackdown

        print(f"  Text: \"{DUMMY_ITEMS[2].text[:80]}...\"")
        print(f"  Entities: {entities}")
        print(f"  Topics:   {topics}")
        print(f"\n  → These get stored as metadata in ChromaDB for filtering and display")

        assert isinstance(entities, list)
        assert isinstance(topics, list)


# ─── STAGE 5: Vector Store ──────────────────────────────────────────

class TestStage5VectorStore:
    """
    STAGE 5 — VECTOR STORAGE (ChromaDB)
    ====================================
    The VectorStore persists enriched items with their embeddings into
    ChromaDB, a vector database optimized for similarity search. This
    enables fast retrieval by semantic query and metadata filtering.

    ChromaDB uses HNSW (Hierarchical Navigable Small World) indexing
    for approximate nearest neighbor search — O(log n) query time.
    """

    def test_store_and_count(self, config, embedder):
        """Store items and verify they persist."""
        print("\n" + "=" * 70)
        print("STAGE 5 — VECTOR STORE: Storing enriched items in ChromaDB")
        print("=" * 70)
        print(f"\n  Persist directory: {config.chroma_persist_dir}")
        print(f"  Collection name:  {config.chroma_collection}")
        print(f"  Distance metric:  cosine")
        print(f"\n  How it works:")
        print(f"    1. Each EnrichedItem is stored with its embedding vector")
        print(f"    2. Metadata (source, sentiment, tags, etc.) stored alongside")
        print(f"    3. ChromaDB builds an HNSW index for fast similarity search")
        print(f"    4. Data persists to disk so it survives restarts\n")

        store = VectorStore(config)
        # Start clean — reset if collection exists
        try:
            store.reset()
        except Exception:
            pass  # Collection may not exist yet

        # Create a few dummy enriched items
        dummy_embedding = embedder.embed_single(DUMMY_ITEMS[0].text)
        items = [
            EnrichedItem(
                text=DUMMY_ITEMS[0].text,
                source="reddit",
                timestamp=datetime(2026, 3, 25, 14, 30),
                url="https://reddit.com/abc",
                embedding=dummy_embedding,
                sentiment_score=0.65,
                sentiment_confidence=0.65,
                topic_tags=["crypto", "finance"],
                entities=["ETF", "$95k"],
                relevance_score=0.48,
            ),
            EnrichedItem(
                text=DUMMY_ITEMS[2].text,
                source="news_rss",
                timestamp=datetime(2026, 3, 26, 11, 0),
                url="https://reuters.com/abc",
                embedding=embedder.embed_single(DUMMY_ITEMS[2].text),
                sentiment_score=-0.03,
                sentiment_confidence=0.03,
                topic_tags=["crypto", "regulation"],
                entities=["SEC"],
                relevance_score=0.30,
            ),
        ]

        ids = store.add(items)

        print(f"  Stored {len(ids)} items")
        for i, (item_id, item) in enumerate(zip(ids, items)):
            print(f"    [{i}] ID={item_id[:12]}... | source={item.source:10s} | "
                  f"sentiment={item.sentiment_score:+.2f} | relevance={item.relevance_score:.2f}")
        print(f"\n  Collection count: {store.count()}")

        assert store.count() == 2
        assert len(ids) == 2

    def test_vector_query(self, config, embedder):
        """Query the store by embedding vector for nearest neighbors."""
        print("\n" + "=" * 70)
        print("STAGE 5 — VECTOR STORE: Querying by embedding similarity")
        print("=" * 70)
        print(f"\n  How it works:")
        print(f"    1. Convert query text to embedding vector")
        print(f"    2. ChromaDB finds the N nearest vectors (cosine distance)")
        print(f"    3. Returns documents + metadata + distances, sorted by similarity\n")

        store = VectorStore(config)
        query_text = "Bitcoin institutional investment"
        query_emb = embedder.embed_single(query_text)

        results = store.query(query_embedding=query_emb, n_results=5)

        print(f"  Query: \"{query_text}\"")
        if results["documents"] and results["documents"][0]:
            for i, (doc, dist) in enumerate(zip(results["documents"][0], results["distances"][0])):
                sim = 1.0 - dist
                print(f"    [{i}] similarity={sim:.4f}  \"{doc[:60]}...\"")
        else:
            print(f"    (no results — store may be empty from previous test)")

        print(f"\n  → Lower distance = higher similarity = more relevant result")

        assert results is not None


# ─── STAGE 6: Semantic Search ───────────────────────────────────────

class TestStage6SemanticSearch:
    """
    STAGE 6 — SEMANTIC SEARCH
    ==========================
    The user-facing search layer. Users type a natural language query
    (e.g. "show me everything about wage growth") and get back the
    most semantically relevant nodes from the tree.

    Supports optional filters: by platform source, minimum sentiment.
    """

    def test_search_by_query(self, config, embedder):
        """Search with a natural language query."""
        print("\n" + "=" * 70)
        print("STAGE 6 — SEMANTIC SEARCH: Natural language query")
        print("=" * 70)
        print(f"\n  How it works:")
        print(f"    1. User types a query in the frontend (e.g. 'institutional buying')")
        print(f"    2. Query gets embedded using the same model as the stored items")
        print(f"    3. ChromaDB finds nearest neighbors by cosine similarity")
        print(f"    4. Optional filters (source platform, min sentiment) applied")
        print(f"    5. Results returned to frontend for display as highlighted nodes\n")

        store = VectorStore(config)
        search = SemanticSearch(embedder, store, config)

        query = "Bitcoin institutional buying"
        results = search.search(query, n_results=5)

        print(f"  Query: \"{query}\"")
        print(f"  Results: {len(results)} items\n")
        for i, r in enumerate(results):
            sim = r.get('similarity')
            sim_str = f"{sim:.4f}" if sim is not None else "N/A"
            print(f"    [{i}] similarity={sim_str:>8} "
                  f"| sentiment={r.get('sentiment_score', 0):+.2f} "
                  f"| source={r.get('source', '?'):10s}")
            print(f"        \"{r['text'][:60]}...\"")

        print(f"\n  → This is what powers the tree's search bar in the frontend")

    def test_search_with_source_filter(self, config, embedder):
        """Search filtered to a specific platform."""
        print("\n" + "=" * 70)
        print("STAGE 6 — SEMANTIC SEARCH: Filtered by source platform")
        print("=" * 70)

        store = VectorStore(config)
        search = SemanticSearch(embedder, store, config)

        print(f"\n  Searching only Reddit posts about Bitcoin...")
        results = search.search("Bitcoin", n_results=5, source_filter="reddit")
        print(f"  Results from Reddit: {len(results)}")
        for r in results:
            print(f"    source={r.get('source')} | \"{r['text'][:60]}...\"")

        print(f"\n  Searching only news RSS items...")
        results_news = search.search("Bitcoin", n_results=5, source_filter="news_rss")
        print(f"  Results from news_rss: {len(results_news)}")
        for r in results_news:
            print(f"    source={r.get('source')} | \"{r['text'][:60]}...\"")

        print(f"\n  → Source filtering lets users explore sentiment by platform")
        print(f"    (e.g. 'What is Reddit saying vs. mainstream news?')")


# ─── FULL PIPELINE: End-to-End ──────────────────────────────────────

class TestFullPipeline:
    """
    FULL PIPELINE — END TO END
    ===========================
    Orchestrates all 6 stages together: raw items come in, enriched
    items come out, stored and searchable. This is what Role 1 feeds
    into and Role 3 reads from.
    """

    def test_end_to_end(self, config):
        """Process all dummy items through the complete pipeline."""
        print("\n" + "=" * 70)
        print("FULL PIPELINE — END-TO-END: Raw items → Enriched items")
        print("=" * 70)
        print(f"\n  Contract: \"{CONTRACT_QUESTION}\"")
        print(f"  Input: {len(DUMMY_ITEMS)} raw items from various sources")
        print(f"\n  Pipeline flow:")
        print(f"    [1] Embed all 5 items → 384-dim vectors")
        print(f"    [2] Score relevance → discard noise below {config.relevance_threshold}")
        print(f"    [3] Score sentiment → directional yes/no for contract")
        print(f"    [4] Extract entities + topic tags")
        print(f"    [5] Store in ChromaDB")
        print(f"\n  Processing...\n")

        # Use a separate collection to avoid interfering with other tests
        test_config = PipelineConfig(
            chroma_persist_dir=config.chroma_persist_dir,
            chroma_collection="test_e2e",
        )
        pipe = Pipeline(CONTRACT_QUESTION, test_config)
        enriched = pipe.process(DUMMY_ITEMS, store=True)

        print(f"  Result: {len(enriched)}/{len(DUMMY_ITEMS)} items passed through\n")
        print(f"  {'Source':<12} {'Relevance':>10} {'Sentiment':>10} {'Confidence':>11} {'Tags':<25} {'Entities'}")
        print(f"  {'─' * 12} {'─' * 10} {'─' * 10} {'─' * 11} {'─' * 25} {'─' * 20}")
        for item in enriched:
            print(f"  {item.source:<12} {item.relevance_score:>10.4f} {item.sentiment_score:>+10.4f} "
                  f"{item.sentiment_confidence:>10.4f}  {str(item.topic_tags):<25} {item.entities}")

        print(f"\n  Items in vector store: {pipe.vector_store.count()}")
        print(f"\n  Notice:")
        print(f"    - The cookie recipe is GONE (filtered at Stage 2)")
        print(f"    - Sentiment scores are directional (+ = yes for BTC $100k, - = no)")
        print(f"    - Each item carries entities and tags for Role 3 clustering")

        # Cookie recipe should be filtered
        enriched_texts = [item.text for item in enriched]
        assert not any("chocolate" in t.lower() for t in enriched_texts), \
            "Cookie recipe should have been filtered out"
        assert len(enriched) >= 3, "At least 3 of 5 items should be relevant"

        # Verify all enriched items have required fields
        for item in enriched:
            assert len(item.embedding) == 384
            assert -1.0 <= item.sentiment_score <= 1.0
            assert 0.0 <= item.sentiment_confidence <= 1.0
            assert 0.0 <= item.relevance_score <= 1.0

    def test_enriched_item_schema(self):
        """Verify the EnrichedItem has all fields Role 3 needs."""
        print("\n" + "=" * 70)
        print("SCHEMA CHECK — EnrichedItem (output to Role 3)")
        print("=" * 70)
        print(f"\n  Role 3 (Algorithm/Branching) expects these fields:\n")

        fields = EnrichedItem.model_fields
        for name, field in fields.items():
            desc = field.description or ""
            print(f"    {name:<25} {field.annotation}  {desc}")

        print(f"\n  → This is the contract between Role 2 and Role 3")
        print(f"    Any changes here need to be coordinated with Abhi (Role 3)")

        required_fields = {"text", "source", "timestamp", "url", "embedding",
                           "sentiment_score", "sentiment_confidence",
                           "topic_tags", "entities", "relevance_score"}
        assert required_fields.issubset(set(fields.keys()))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
