import sys
from pathlib import Path

# Ensure the sentiment-tree package root is on sys.path
# so `from pipeline.x import Y` works regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))
