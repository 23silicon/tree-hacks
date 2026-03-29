# Hivemind — Agent Architecture

## Overview

User asks a question like **"How did the Iran war develop?"**
→ OpenClaw dispatches a swarm of specialized agents
→ Agents collect, extract, connect, and structure data
→ Output feeds into an interactive branched timeline visualizer

```
 USER QUERY: "How did the Iran war develop?"
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                   OPENCLAW GATEWAY                       │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │            CONDUCTOR AGENT (Coordinator)            │ │
│  │                                                     │ │
│  │  1. Decomposes query into sub-queries               │ │
│  │  2. Determines time range & aspects to investigate  │ │
│  │  3. Dispatches source agents in parallel            │ │
│  │  4. Collects results, sends to extraction pipeline  │ │
│  └──────────┬──────────┬──────────┬───────────────────┘ │
│             │          │          │                      │
│     ┌───────▼──┐ ┌─────▼────┐ ┌──▼─────────┐           │
│     │ NEWS     │ │ SOCIAL   │ │ MARKET     │           │
│     │ SCOUT    │ │ SCOUT    │ │ SCOUT      │           │
│     │          │ │          │ │            │           │
│     │ Google   │ │ Bluesky  │ │ Polymarket │           │
│     │ News RSS │ │ Firehose │ │ Gamma API  │           │
│     │ NewsAPI  │ │ (Twitter)│ │ (Kalshi)   │           │
│     └────┬─────┘ └────┬─────┘ └─────┬──────┘           │
│          │             │             │                   │
│          └─────────────┼─────────────┘                   │
│                        ▼                                 │
│  ┌─────────────────────────────────────────────────────┐│
│  │              EVENT EXTRACTOR AGENT                   ││
│  │                                                      ││
│  │  Takes raw posts/articles → structured Events:       ││
│  │  - What happened (title + description)               ││
│  │  - When (date)                                       ││
│  │  - Category (military/diplomatic/economic/social)    ││
│  │  - Impact (escalation/de-escalation/neutral)         ││
│  │  - Source references                                 ││
│  └──────────────────────┬──────────────────────────────┘│
│                         ▼                                │
│  ┌─────────────────────────────────────────────────────┐│
│  │              NARRATIVE WEAVER AGENT                  ││
│  │                                                      ││
│  │  Takes Events → builds the branched timeline:        ││
│  │  - Groups events into narrative threads              ││
│  │    (military, diplomatic, economic, humanitarian)    ││
│  │  - Identifies causal links (Event A → caused B)     ││
│  │  - Detects branch points (where timelines diverge)  ││
│  │  - Assigns parent/child relationships               ││
│  │  - Outputs the full graph structure                  ││
│  └──────────────────────┬──────────────────────────────┘│
│                         ▼                                │
│  ┌─────────────────────────────────────────────────────┐│
│  │              SENTIMENT LAYER AGENT                   ││
│  │                                                      ││
│  │  Enriches each event with sentiment data:            ││
│  │  - Public sentiment at time of event                 ││
│  │  - Market probability at time of event               ││
│  │  - Sentiment vs market divergence                    ││
│  │  - Emotional tone (fear, anger, hope, etc.)          ││
│  └──────────────────────┬──────────────────────────────┘│
└─────────────────────────┼────────────────────────────────┘
                          ▼
              ┌───────────────────────┐
              │   STRUCTURED OUTPUT   │
              │      (JSON)           │
              └───────────┬───────────┘
                          ▼
              ┌───────────────────────┐
              │  FRONTEND VISUALIZER  │
              │                       │
              │  Interactive branched  │
              │  timeline with zoom,  │
              │  focus, and explore   │
              └───────────────────────┘
```

## The 6 Agents

### 1. CONDUCTOR (Coordinator)
**Role:** Receives user query, breaks it down, orchestrates everything.

**Input:** Raw user question — "How did the Iran war develop?"

**Process:**
- Parse intent: what topic, what time range, what aspects
- Generate sub-queries for each source:
  - News: "iran war timeline 2026", "iran us military", "iran sanctions"
  - Social: "iran, war, missile, ceasefire, troops"
  - Markets: "iran", "war", "oil"
- Dispatch Scout agents in parallel
- Collect all results
- Pass to Event Extractor

**Output:** Collected raw data from all sources

**OpenClaw:** Runs as the main session, uses `sessions_send` to dispatch and collect from other agents.

---

### 2. NEWS SCOUT
**Role:** Collects news articles from Google News RSS (+ NewsAPI if key available).

**Input:** Sub-queries from Conductor

**Process:**
- Fetch Google News RSS for each sub-query
- Deduplicate by URL hash
- Return sorted by timestamp

**Output:** `List[Post]` — news articles with title, source, date, URL

---

### 3. SOCIAL SCOUT
**Role:** Collects social media posts from Bluesky firehose (+ Twitter via Twikit if credentials available).

**Input:** Keywords from Conductor

**Process:**
- Connect to Bluesky JetStream WebSocket
- Filter by keywords in real-time
- Collect for N seconds

**Output:** `List[Post]` — social posts with author, text, timestamp

---

### 4. MARKET SCOUT
**Role:** Collects prediction market data from Polymarket.

**Input:** Topic keywords from Conductor

**Process:**
- Search Polymarket Gamma API for matching markets
- Get current prices + price history

**Output:** `List[MarketData]` — market questions, yes/no prices, volume

---

### 5. EVENT EXTRACTOR
**Role:** The brain — turns raw text into structured timeline events.

**Input:** All collected Posts from the 3 Scouts

**Process (LLM-powered):**
- Batch posts chronologically
- For each batch, ask Claude to extract:
  - **What:** A clear event title + description
  - **When:** Exact or approximate date
  - **Category:** military / diplomatic / economic / social / humanitarian
  - **Impact:** escalation / de-escalation / neutral
  - **Key actors:** Who was involved
- Deduplicate events (many articles describe the same event)
- Sort chronologically

**Output:** `List[Event]` — structured events with metadata

**This is the most critical agent.** The quality of the timeline depends entirely on how well this agent extracts and deduplicates events.

---

### 6. NARRATIVE WEAVER
**Role:** Connects events into a branched narrative graph.

**Input:** `List[Event]` from Event Extractor + market data

**Process (LLM-powered):**
- Identify narrative threads:
  - "Military operations" thread
  - "Diplomatic efforts" thread
  - "Economic impact" thread
  - "Public reaction" thread
- For each event, determine:
  - Which thread(s) it belongs to
  - What event(s) caused it (parent links)
  - What event(s) it led to (child links)
  - Is this a branch point? (where one event causes multiple divergent outcomes)
- Enrich with sentiment/market data at each point
- Build the final graph structure

**Output:** Complete timeline graph JSON:
```json
{
  "threads": [
    {
      "id": "military",
      "name": "Military Operations",
      "color": "#ff6b6b"
    }
  ],
  "events": [
    {
      "id": "evt_001",
      "title": "US launches strikes on Iranian targets",
      "date": "2026-03-15",
      "category": "military",
      "impact": "escalation",
      "threads": ["military"],
      "sentiment": -0.72,
      "market_probability": 0.65,
      "parents": [],
      "children": ["evt_002", "evt_003", "evt_004"]
    },
    {
      "id": "evt_002",
      "title": "Iran retaliates with missile barrage",
      "date": "2026-03-16",
      "threads": ["military"],
      "parents": ["evt_001"],
      "children": ["evt_005"]
    },
    {
      "id": "evt_003",
      "title": "Oil prices surge 20%",
      "date": "2026-03-15",
      "threads": ["economic"],
      "parents": ["evt_001"],
      "children": ["evt_006"]
    },
    {
      "id": "evt_004",
      "title": "UN Security Council emergency session",
      "date": "2026-03-16",
      "threads": ["diplomatic"],
      "parents": ["evt_001"],
      "children": ["evt_007"]
    }
  ]
}
```

---

## Data Flow Summary

```
User Query
    │
    ▼
CONDUCTOR ─── breaks into sub-queries
    │
    ├──▶ NEWS SCOUT ────── Google News RSS ──▶ List[Post]
    ├──▶ SOCIAL SCOUT ──── Bluesky Firehose ─▶ List[Post]  (parallel)
    ├──▶ MARKET SCOUT ──── Polymarket API ───▶ List[MarketData]
    │
    ▼
EVENT EXTRACTOR ─── raw posts → structured events (LLM)
    │
    ▼
NARRATIVE WEAVER ── events → branched graph with causal links (LLM)
    │
    ▼
JSON Output → Frontend Visualizer
```

## OpenClaw Integration

Each agent runs as an OpenClaw skill in its own workspace:

```
~/.openclaw/workspace/skills/
├── hivemind-conductor/SKILL.md
├── hivemind-news-scout/SKILL.md
├── hivemind-social-scout/SKILL.md
├── hivemind-market-scout/SKILL.md
├── hivemind-event-extractor/SKILL.md
└── hivemind-narrative-weaver/SKILL.md
```

Communication via `sessions_send`:
- Conductor → Scouts: "go collect data for these queries"
- Scouts → Conductor: "here are my results"
- Conductor → Event Extractor: "process these posts"
- Event Extractor → Narrative Weaver: "here are the events"
- Narrative Weaver → Frontend: "here's the graph JSON"

Lobster pipeline orchestrates the full flow in one command.

## Repository Runtime Realization

In this repository, the above OpenClaw orchestration is realized through a local API-first execution loop:

- Frontend issues local `/api` workflow requests.
- FastAPI serves as the conductor for source collection, enrichment, and graph assembly.
- Workflow and prediction endpoints provide both single-response and streaming modes.
- OpenClaw manifest and contracts remain the canonical interface definition for ingest and emit payloads.

This preserves OpenClaw compatibility while enabling reliable local development and demo execution.
