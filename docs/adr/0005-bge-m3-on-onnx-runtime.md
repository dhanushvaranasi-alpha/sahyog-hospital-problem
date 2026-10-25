# ADR 0005 — Run BGE-M3 with ONNX Runtime instead of PyTorch

```yaml
title: BGE-M3 dense embeddings are computed with ONNX Runtime from the ONNX export BAAI publishes
context: ADR 0003 chose local BGE-M3 and pinned sentence-transformers, which pulls in PyTorch. Installing it for W2 failed twice in practice. The PyPI torch wheel for x86-64 Linux is the CUDA build, which timed out downloading; the CPU wheel lives on download.pytorch.org, which this build's network does not reach. On ARM64 Linux the CPU wheel is 454 MB before the model itself.
options:
  - name: sentence-transformers + PyTorch (ADR 0003 as written)
    cost: Reference implementation; adds PyTorch (hundreds of MB to over 2 GB depending on platform) for one model
  - name: ONNX Runtime + tokenizers on BAAI's ONNX export (onnx/ in the BAAI/bge-m3 repository)
    cost: About 20 MB of libraries; same weights (2.27 GB); dense vectors only (no sparse or multi-vector modes, which this build does not use)
  - name: A hosted embedding API
    cost: Rejected in ADR 0003 (egress of clinical text, budget)
decision: ONNX Runtime. The export's `sentence_embedding` output was checked against BGE-M3's dense definition (the L2-normalised CLS vector of `token_embeddings`): maximum absolute difference 0.0 on test sentences. Revisit if sparse or multi-vector retrieval is needed (Pro hybrid search).
consequences: sentence-transformers leaves the dependency list. First use downloads only the onnx/ folder. Vectors are cached on disk by sha256(model, text) in data/cache/embeddings, so re-ingest and eval re-runs embed only new text. CPU throughput on a 2-core cloud box was about 2 chunks per second; the 100 synthetic reports (541 chunks) took 153 s cold and 1.7 s from cache.
versions_pinned: onnxruntime == 1.31.0; tokenizers == 0.23.3; huggingface-hub == 2.2.0
checked_on: 2026-10-25
status: accepted (supersedes the runtime in ADR 0003; the model choice in ADR 0003 stands)
```
