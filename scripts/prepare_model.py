"""Package the embedding model locally; --download is setup-only and explicit."""
import argparse
import os
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--download", action="store_true", help="Allow the initial model download during setup, never during analysis")
args = parser.parse_args()
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
if not args.download:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
from sentence_transformers import SentenceTransformer

target = Path(__file__).resolve().parents[1] / "models" / "all-MiniLM-L6-v2"
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", local_files_only=not args.download)
model.save(str(target))
print(f"Local model ready: {target}")
