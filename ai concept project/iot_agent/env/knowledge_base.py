"""FAISS retrieval over the markdown knowledge base.

Each '## ' section of a KB document becomes one chunk. Chunks are embedded with
TF-IDF (word 1-2 grams, L2-normalised) and indexed in a FAISS inner-product
index, i.e. cosine similarity. TF-IDF is used because DeepSeek has no embedding
endpoint and the KB is small and terminology-heavy (fault codes, model names),
where lexical matching works well: on eval/retrieval_check.py it reached top-3
12/12, versus 11/12 for bge-small-en-v1.5 and 10/12 for bge-base-en-v1.5.
The `Embedder` can be swapped for a neural model without touching the rest of the code.
"""
import re

import faiss
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

import config


class Embedder:
    def __init__(self):
        # token pattern keeps codes like "E-305", "HB-200" and "4.5" as single tokens
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                                   token_pattern=r"[A-Za-z0-9][A-Za-z0-9\-\.]*")

    def fit(self, texts):
        self.vec.fit(texts)

    def encode(self, texts) -> np.ndarray:
        m = self.vec.transform(texts).toarray().astype("float32")
        faiss.normalize_L2(m)
        return m


def load_chunks():
    chunks = []
    for path in sorted(config.KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for sec in re.split(r"\n(?=## )", text):
            if not sec.startswith("## "):
                continue  # skip the document title block
            title, _, body = sec[3:].partition("\n")
            chunks.append({"doc": path.stem, "title": title.strip(), "text": body.strip()})
    return chunks


class KnowledgeBase:
    def __init__(self):
        self.chunks = load_chunks()
        corpus = [f"{c['title']} {c['text']}" for c in self.chunks]
        self.embedder = Embedder()
        self.embedder.fit(corpus)
        emb = self.embedder.encode(corpus)
        self.index = faiss.IndexFlatIP(emb.shape[1])
        self.index.add(emb)

    def search(self, query: str, k: int = 3):
        scores, ids = self.index.search(self.embedder.encode([query]), k)
        return [{**self.chunks[i], "score": round(float(s), 3)}
                for s, i in zip(scores[0], ids[0]) if i >= 0 and s > 0]


_KB = None


def get_kb() -> KnowledgeBase:
    global _KB
    if _KB is None:
        _KB = KnowledgeBase()
    return _KB
