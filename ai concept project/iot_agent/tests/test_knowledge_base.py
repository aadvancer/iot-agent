import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import config
from env import knowledge_base


class FakeEmbedder:
    """Deterministic bag-of-words embedder so the test needs no model download."""

    model_name = "fake-embedder"
    vocab = ["camera", "signal", "battery", "pairing", "firmware", "escalate"]

    def __init__(self):
        self.passage_calls = 0

    def _vec(self, text):
        v = np.array([text.lower().count(w) for w in self.vocab], dtype="float32") + 1e-3
        return (v / np.linalg.norm(v)).tolist()

    def encode_passages(self, texts):
        self.passage_calls += 1
        return [self._vec(t) for t in texts]

    def encode_query(self, text):
        return self._vec(text)


class ChromaKnowledgeBaseTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.kb_dir = Path(tmp.name) / "kb"
        self.db_dir = Path(tmp.name) / "chroma"
        self.kb_dir.mkdir()
        (self.kb_dir / "manual.md").write_text(
            "# Manual\n\n## Weak signal\nMove the camera closer to improve signal.\n\n"
            "## Battery\nCharge the battery fully.\n",
            encoding="utf-8",
        )
        patcher = mock.patch.object(config, "KB_DIR", self.kb_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _open(self, embedder):
        return knowledge_base.KnowledgeBase(persist_dir=self.db_dir, embedder=embedder)

    def test_search_returns_ranked_chunks_from_vector_db(self):
        kb = self._open(FakeEmbedder())
        hits = kb.search("camera signal drops")
        self.assertEqual(hits[0]["title"], "Weak signal")
        self.assertEqual(hits[0]["doc"], "manual")
        self.assertEqual(set(hits[0]), {"doc", "title", "text", "score"})

    def test_reopening_unchanged_kb_reuses_persisted_vectors(self):
        self._open(FakeEmbedder())
        embedder = FakeEmbedder()
        kb = self._open(embedder)
        self.assertEqual(embedder.passage_calls, 0)
        self.assertEqual(kb.collection.count(), 2)

    def test_editing_kb_rebuilds_collection(self):
        self._open(FakeEmbedder())
        with (self.kb_dir / "manual.md").open("a", encoding="utf-8") as f:
            f.write("\n## Pairing\nHold the pairing button for 3 seconds.\n")
        embedder = FakeEmbedder()
        kb = self._open(embedder)
        self.assertEqual(embedder.passage_calls, 1)
        self.assertEqual(kb.collection.count(), 3)
        self.assertEqual(kb.search("pairing button")[0]["title"], "Pairing")


if __name__ == "__main__":
    unittest.main()
