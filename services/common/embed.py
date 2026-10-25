"""Local embeddings (architecture decision 8, ADR 0005): BGE-M3 dense vectors, run with ONNX Runtime.

BAAI publishes an ONNX export of BGE-M3 in the model repository (`onnx/`). Its `sentence_embedding`
output is the normalised CLS vector, which is BGE-M3's dense mode, so the vectors match the
PyTorch model without installing PyTorch. Report text never leaves the machine for embedding.

Vectors are cached on disk by a hash of (model, text): re-ingesting the same document or asking
the same question costs nothing, and an eval re-run embeds only what changed.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(os.environ.get("EMBEDDING_CACHE_DIR", REPO / "data" / "cache" / "embeddings"))
MODEL_ID = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))
MAX_TOKENS = 512          # chunks are about 250 tokens; questions far less
PAD_ID = 1                # XLM-RoBERTa tokenizer used by BGE-M3


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


class CachedEmbedder:
    """Wraps an embedder with the on-disk content-hash cache. The model loads only on a cache miss."""

    def __init__(self, inner: Embedder, cache_dir: Path = CACHE_DIR):
        self.inner, self.cache_dir = inner, cache_dir
        self.name, self.dim = inner.name, inner.dim
        self.hits = self.misses = 0

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        todo: list[int] = []
        for i, t in enumerate(texts):
            p = self.cache_dir / f"{_key(self.name, t)}.npy"
            if p.exists():
                out[i] = np.load(p)
                self.hits += 1
            else:
                todo.append(i)
        if todo:
            self.misses += len(todo)
            vecs = self.inner.embed([texts[i] for i in todo])
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            for i, v in zip(todo, vecs):
                out[i] = v
                np.save(self.cache_dir / f"{_key(self.name, texts[i])}.npy", v.astype(np.float32))
        return out


class BgeM3Onnx:
    """BGE-M3 dense embeddings via ONNX Runtime on CPU. First use downloads about 2.3 GB to the HF cache."""

    def __init__(self, model_id: str = MODEL_ID, batch_size: int = 8):
        self.name, self.dim, self.batch_size = model_id, DIM, batch_size
        self._session = self._tokenizer = None

    def _load(self) -> None:
        import onnxruntime as ort
        from huggingface_hub import snapshot_download
        from tokenizers import Tokenizer

        local = os.environ.get("EMBEDDING_MODEL_DIR")
        root = Path(local) if local else Path(snapshot_download(self.name, allow_patterns=["onnx/*"]))
        self._session = ort.InferenceSession(str(root / "onnx" / "model.onnx"), providers=["CPUExecutionProvider"])
        tok = Tokenizer.from_file(str(root / "onnx" / "tokenizer.json"))
        tok.enable_truncation(MAX_TOKENS)
        self._tokenizer = tok

    def embed(self, texts: list[str]) -> np.ndarray:
        if self._session is None:
            self._load()
        out = []
        for start in range(0, len(texts), self.batch_size):
            enc = self._tokenizer.encode_batch(texts[start:start + self.batch_size])
            width = max(len(e.ids) for e in enc)
            ids = np.array([e.ids + [PAD_ID] * (width - len(e.ids)) for e in enc], dtype=np.int64)
            mask = np.array([[1] * len(e.ids) + [0] * (width - len(e.ids)) for e in enc], dtype=np.int64)
            _, sentence = self._session.run(None, {"input_ids": ids, "attention_mask": mask})
            out.append(sentence.astype(np.float32))
        return np.vstack(out) if out else np.zeros((0, self.dim), dtype=np.float32)


class HashEmbedder:
    """Deterministic bag-of-words vectors for unit tests: no model download, stable across runs."""

    def __init__(self, dim: int = 64):
        self.name, self.dim = f"hash-{dim}", dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in t.lower().split():
                w = w.strip(".,:;?!()%")
                if w:
                    out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


def default_embedder() -> CachedEmbedder:
    return CachedEmbedder(BgeM3Onnx())
