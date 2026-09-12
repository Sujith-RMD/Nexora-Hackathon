"""Local offline semantic matching module using SentenceTransformer.

Embeds JD requirements and candidate resume chunks, computes cosine similarities,
tracks the best-matching contextual chunk per requirement, and produces weighted
aggregate semantic scores.
"""

import re
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

_DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
_CACHED_MODEL: Optional[Any] = None


def get_semantic_model(model_name: str = _DEFAULT_MODEL_NAME) -> Any:
    """Load and cache the local SentenceTransformer model singleton."""
    global _CACHED_MODEL
    if _CACHED_MODEL is None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers is not installed. Please install requirements.txt."
            )
        _CACHED_MODEL = SentenceTransformer(model_name)
    return _CACHED_MODEL


def chunk_sections(
    sections: Dict[str, str],
    max_chars: int = 500,
    overlap: int = 100,
) -> List[Dict[str, str]]:
    """Chunk resume sections into coherent context passages with section tags."""
    chunks: List[Dict[str, str]] = []

    for section_name, text in sections.items():
        if not text or not text.strip():
            continue

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n[•\*\-]\s*", text) if p.strip()]

        for para in paragraphs:
            if len(para) <= max_chars:
                chunks.append({"section": section_name, "text": para})
            else:
                # Break long paragraphs into overlapping sentences or word blocks
                words = para.split()
                current_block: List[str] = []
                current_len = 0

                for word in words:
                    current_block.append(word)
                    current_len += len(word) + 1
                    if current_len >= max_chars:
                        chunk_text = " ".join(current_block)
                        chunks.append({"section": section_name, "text": chunk_text})
                        # Keep last few words for overlap
                        overlap_words = current_block[-12:]
                        current_block = list(overlap_words)
                        current_len = sum(len(w) + 1 for w in current_block)

                if current_block:
                    chunks.append({"section": section_name, "text": " ".join(current_block)})

    return chunks


def calibrate_cosine_similarity(cos_sim: float) -> float:
    """Calibrate raw sentence-transformer cosine similarity to a balanced 0-100 scale.

    Raw all-MiniLM-L6-v2 cosine similarities typically distribute:
      - <= 0.10: unrelated / noise -> 0
      - ~ 0.30: weak / broad context -> ~ 30
      - ~ 0.50: strong thematic match -> ~ 65
      - >= 0.72: near exact / direct match -> 100
    """
    if cos_sim <= 0.10:
        return 0.0
    # Map range [0.10, 0.72] to [0.0, 100.0]
    scaled = ((cos_sim - 0.10) / (0.72 - 0.10)) * 100.0
    return round(max(0.0, min(100.0, scaled)), 2)


def semantic_match(
    jd: Dict[str, Any],
    candidate: Dict[str, Any],
    model: Optional[Any] = None,
) -> Dict[str, Any]:
    """Compute requirement-level semantic scores against candidate resume chunks.

    Returns:
      {
        "semantic_score": float (0-100),
        "requirement_matches": [
           {
             "requirement_id": str,
             "requirement_name": str,
             "semantic_score": float,
             "best_chunk": str,
             "best_section": str
           }
        ]
      }
    """
    transformer = model or get_semantic_model()
    requirements = jd.get("requirements", [])
    sections = candidate.get("sections", {})

    chunks = chunk_sections(sections)

    if not requirements:
        return {"semantic_score": 0.0, "requirement_matches": []}

    # If resume has no chunks, all requirements get 0.0
    if not chunks:
        empty_matches = [
            {
                "requirement_id": req.get("id", f"req_{req.get('name', '')}"),
                "requirement_name": req.get("name", ""),
                "semantic_score": 0.0,
                "best_chunk": "",
                "best_section": "none",
            }
            for req in requirements
        ]
        return {"semantic_score": 0.0, "requirement_matches": empty_matches}

    # Prepare requirement texts
    req_texts: List[str] = []
    for req in requirements:
        name = str(req.get("name", ""))
        source = str(req.get("source_text", ""))
        category = str(req.get("category", ""))
        # Combine canonical name and JD sentence cue for richer contextual representation
        if source and source.lower() != name.lower():
            text_rep = f"{name}: {source}"
        else:
            text_rep = f"{category} skill: {name}" if category else name
        req_texts.append(text_rep)

    chunk_texts = [c["text"] for c in chunks]

    # Batch encode requirements and chunks
    req_embeddings = transformer.encode(
        req_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    chunk_embeddings = transformer.encode(
        chunk_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    # Compute cosine similarity matrix (reqs x chunks) via dot product of normalized vectors
    similarity_matrix = np.dot(req_embeddings, chunk_embeddings.T)

    req_matches: List[Dict[str, Any]] = []
    total_weight = 0.0
    weighted_score_sum = 0.0

    for i, req in enumerate(requirements):
        weight = float(req.get("weight", 1.0))
        total_weight += weight

        sims = similarity_matrix[i]
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        best_chunk_obj = chunks[best_idx]

        calibrated_score = calibrate_cosine_similarity(best_sim)
        weighted_score_sum += calibrated_score * weight

        req_matches.append(
            {
                "requirement_id": req.get("id", f"req_{req.get('name', '')}"),
                "requirement_name": req.get("name", ""),
                "semantic_score": calibrated_score,
                "best_chunk": best_chunk_obj["text"],
                "best_section": best_chunk_obj["section"],
            }
        )

    aggregate_score = (
        round(weighted_score_sum / total_weight, 2) if total_weight > 0 else 0.0
    )

    return {
        "semantic_score": aggregate_score,
        "requirement_matches": req_matches,
    }
