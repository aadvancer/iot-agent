"""Knowledge-base retrieval backed by a persistent ChromaDB vector database.

Each '## ' section of a KB document becomes one chunk. Chunks are embedded with
a neural sentence-embedding model (BAAI/bge-small-en-v1.5 by default, run
locally through fastembed/ONNX) and stored in a ChromaDB collection under
`.cache/chroma` with cosine distance. The collection records a fingerprint of
the KB text and embedding model, and is rebuilt automatically whenever either
changes, so editing a markdown file never leaves stale vectors behind.

Search is hybrid: the dense ranking from ChromaDB is fused with a TF-IDF lexical
ranking by reciprocal rank fusion (RRF). Dense embeddings capture paraphrases
("won't pair" ~ "pairing fails"), while the lexical ranking keeps exact tokens
such as fault codes (E-207) and model names (CAM-I2) decisive. On
eval/retrieval_check.py top-3: dense-only bge-small 10/12, TF-IDF-only 12/12,
equal-weight fusion 11/12, lexical-weighted fusion (below) 12/12. On this small
probe set fusion only matches TF-IDF alone; the dense side is kept for paraphrased queries.

`Embedder` (TF-IDF) is kept for the in-session interaction recall in
agent/memory.py, which indexes a handful of short notes per session.
"""
import hashlib
import json
import re

import chromadb
import faiss
import numpy as np
from chromadb.config import Settings
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


class NeuralEmbedder:
    """Sentence embeddings via fastembed; bge models use a query instruction prefix."""

    def __init__(self, model_name=config.EMBEDDING_MODEL):
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.model = TextEmbedding(model_name, cache_dir=str(config.EMBEDDING_CACHE_DIR))

    def encode_passages(self, texts):
        return [v.tolist() for v in self.model.passage_embed(texts)]

    def encode_query(self, text):
        return next(iter(self.model.query_embed(text))).tolist()


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


def _fingerprint(chunks, model_name):
    payload = json.dumps({"model": model_name, "chunks": chunks}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


RRF_K = 60   # standard reciprocal-rank-fusion constant; damps the weight of top ranks
# The KB is small and code-heavy, so the lexical ranking is the more reliable signal;
# dense similarity is a secondary vote. Chosen on the 12 probes of eval/retrieval_check.py
# (top-1/top-3): dense weight 0.4-0.5 -> 9/12, 12/12; 0.6-0.75 -> 10/12, 12/12; 1.0 -> 10/12, 11/12.
DENSE_WEIGHT = 0.75
LEXICAL_WEIGHT = 1.0


class KnowledgeBase:
    def __init__(self, persist_dir=None, collection_name=config.KB_COLLECTION, embedder=None):
        self.chunks = load_chunks()
        self.ids = [f"{c['doc']}#{i}" for i, c in enumerate(self.chunks)]
        self.lexical = Embedder()
        if self.chunks:
            corpus = [f"{c['title']} {c['text']}" for c in self.chunks]
            self.lexical.fit(corpus)
            self.lexical_matrix = self.lexical.encode(corpus)
        self.embedder = embedder or NeuralEmbedder()
        persist_dir = persist_dir or config.VECTOR_DB_DIR
        persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(persist_dir), settings=Settings(anonymized_telemetry=False))
        self.collection_name = collection_name
        self.collection = self._sync()

    def _sync(self):
        """Reuse the stored collection if it matches the KB and model, otherwise rebuild it."""
        fingerprint = _fingerprint(self.chunks, self.embedder.model_name)
        try:
            collection = self.client.get_collection(self.collection_name)
            if (collection.metadata or {}).get("fingerprint") == fingerprint:
                return collection
            self.client.delete_collection(self.collection_name)
        except Exception:  # collection does not exist yet
            pass
        collection = self.client.create_collection(
            self.collection_name,
            embedding_function=None,
            metadata={"hnsw:space": "cosine", "fingerprint": fingerprint,
                      "embedding_model": self.embedder.model_name},
        )
        if self.chunks:
            collection.add(
                ids=self.ids,
                embeddings=self.embedder.encode_passages(
                    [f"{c['title']}\n{c['text']}" for c in self.chunks]),
                documents=[c["text"] for c in self.chunks],
                metadatas=[{"doc": c["doc"], "title": c["title"]} for c in self.chunks],
            )
        return collection

    def _dense_ranking(self, query, n):
        res = self.collection.query(
            query_embeddings=[self.embedder.encode_query(query)], n_results=n, include=["distances"])
        return [cid for cid, dist in zip(res["ids"][0], res["distances"][0]) if 1.0 - dist > 0]

    def _lexical_ranking(self, query):
        scores = self.lexical_matrix @ self.lexical.encode([query])[0]
        order = np.argsort(-scores, kind="stable")
        return [self.ids[i] for i in order if scores[i] > 0]

    def search(self, query: str, k: int = 3):
        """Top-k chunks by reciprocal rank fusion of dense (Chroma) and lexical (TF-IDF) rankings."""
        if not query.strip() or not self.chunks:
            return []
        fused = {}
        rankings = ((DENSE_WEIGHT, self._dense_ranking(query, len(self.chunks))),
                    (LEXICAL_WEIGHT, self._lexical_ranking(query)))
        for weight, ranking in rankings:
            for rank, cid in enumerate(ranking):
                fused[cid] = fused.get(cid, 0.0) + weight / (RRF_K + rank + 1)
        top = sorted(fused, key=lambda cid: -fused[cid])[:k]
        by_id = dict(zip(self.ids, self.chunks))
        return [{**by_id[cid], "score": round(fused[cid], 4)} for cid in top]


_KB = None


def get_kb() -> KnowledgeBase:
    global _KB
    if _KB is None:
        _KB = KnowledgeBase()
    return _KB
