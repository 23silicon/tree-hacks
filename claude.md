Project Structure and Idea 

—------------------------------------------------------------------------
# Tree Hacks: public sentiment search engine 
An OpenClaw-powered search engine deploys agents to timeline and reveal public sentiment 
Shows how sentiment evolves and is an aggregate for current news 
SentimentTree is a visual exploration tool that maps how public sentiment across internet / social platforms chronologically (we use polymarket and kalshi to source initial predictions)

### Features 
Novel graph view that branches from initial search (root node)
Nodes branching from scraped social/news platforms (media sentiment)
Branches have potential to converge to final predictions (polymarket / kalshi)
Users can also place their own predictions and see how branches converge 
Users can also insert their own nodes 
Features
Novel graph view that branches from initial search (root node)
Nodes branching from scraped social platforms (media sentiment)
Each node carries a sentiment score, source platform, timestamp, and summary of the discourse it represents
Branches split when a new sub-narrative emerges (e.g., a jobs report drops and "economy" splits into "wage growth" and "unemployment")
Branches merge when previously distinct narratives start aligning directionally

Sentiment convergence and divergence
The tree reveals when public opinion is fragmenting (many branches, spread apart) vs. consolidating (branches merging, narrowing)
Prediction market prices from Polymarket/Kalshi are available as an optional overlay — one data point among many, not the destination
The real output is the shape of the tree itself: is discourse converging or fracturing, which platforms are leading vs. following, and where did narratives originate

User participation (later after mvp works)
Users can insert their own nodes to surface context the agents missed — a niche blog post, a leaked memo, a local news story
Users can mark a point on the timeline with their own sentiment read and track how it compares to the aggregate over time
Users can annotate branches ("this narrative started because of X event") to add human context the agents can't infer

### Role 1 — Agentic Data Collection (OpenClaw) (Ritchie + andy)
Build agent pipeline that takes a prediction market contract as input and identifies relevant search terms and platforms to scrape
Implement scrapers for target platforms (X, Reddit, news RSS, potentially YouTube transcripts)
Handle rate limiting, deduplication, and platform-specific data formatting
Output a clean stream of timestamped, source-tagged raw data points for the embedding and tagging layer to consume
Handle periodic re-scraping so the tree updates in near real-time for active topics
Coordinate with Role 2 on the schema for raw scraped items (text, source, timestamp, URL)


### Role 2 — Embedding, Tagging, and Search (nikhil )
Build the vector embedding pipeline — take each scraped item and generate embeddings for semantic similarity
Implement relevance filtering: score each item against the prediction contract's core question using cosine similarity or similar, discard noise below a threshold
Run sentiment analysis on each relevant item, scored directionally relative to the contract's yes/no outcome (not just generic positive/negative)
Tag each item with metadata: topic tags, entity extraction, platform source, sentiment direction and confidence
Build semantic search so users can query within the tree ("show me everything about wage growth") and get relevant nodes surfaced
Store embeddings and tags in a vector database for fast retrieval and clustering support
Coordinate with Role 1 on raw input format and with Role 3 on the enriched output format (embedding + tags + sentiment score attached to each data point)


### Role 3 — Algorithm (Node Creation and Branching Logic) (Abhi)
Define the data model for nodes (sentiment score, timestamp, source, summary, branch ID, position, tags, embedding reference)
Build clustering logic using embeddings from Role 2 to group semantically related items into narrative threads — this is what defines a branch
Implement branch split detection: when a cluster of new nodes diverges enough from its parent branch's narrative (measured by embedding distance), spawn a new branch
Implement branch merge detection: when two branches' embeddings and sentiment scores converge over a time window, merge them visually
Compute y-position for each node based on its directional sentiment relative to the prediction outcome
Integrate prediction market price data (Polymarket/Kalshi APIs) and align it to the same timeline as the tree
Handle user-inserted nodes: embed, score, and place them into the correct branch or spawn a new branch if they represent a novel narrative
Handle user predictions: store them as special convergence-point nodes and compare against the market price over time

### Role 4 — Front End (Node-Based UI) + polymarket  (Leo )
Build the tree/graph canvas — nodes connected by edges, laid out chronologically left to right with sentiment on the y-axis
Implement zoom and pan so users can navigate from full-tree overview down to individual node detail
Node interaction: click a node to see the source content, sentiment breakdown, tags, and timestamp
Branch rendering: visually distinguish branches by source platform (color or icon), show splits and merges with clear visual language
Prediction market overlay: render the contract price as a line across the timeline
User input UI: interface for inserting a custom node (text + optional source link) and placing a prediction (a slider or input for their estimated probability)
Time scrub control: a slider or playback control that lets users watch the tree build over time
Responsive layout that handles trees with many branches without becoming unreadable (collapse, filter, or fade less-active branches)



### Role 5 — Integration and Infrastructure
Set up the backend API that connects all four layers (scraping → embedding/tagging → algorithm → frontend)
Design the data flow: how scraped items move through the pipeline from raw text to positioned nodes on the graph
Build the WebSocket or polling layer so the frontend receives new nodes in near real-time as agents scrape and the algorithm places them
Integrate Polymarket/Kalshi APIs for live contract price data and available contract listings
Handle user accounts, stored predictions, and accuracy tracking persistence
Own the deployment stack and make sure the demo runs reliably end to end
Act as the glue — when Role 1's output doesn't match Role 2's expected input, or Role 3's node positions aren't rendering correctly in Role 4's canvas, this person debugs across boundaries
