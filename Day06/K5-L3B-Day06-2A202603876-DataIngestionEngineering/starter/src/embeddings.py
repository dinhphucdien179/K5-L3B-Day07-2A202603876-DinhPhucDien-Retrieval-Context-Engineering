"""Real local embeddings, float32 batches and a persistent content-addressed cache."""
from __future__ import annotations
import hashlib
import importlib.metadata
import io
import json
import os
import re
from pathlib import Path
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

from .runtime import RuntimeConfig, atomic_write, effective_cpus
from .ingestion import NORMALIZATION_VERSION


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> NDArray[np.float32]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> NDArray[np.float32]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Local SentenceTransformer adapter; no silent model/device/mock fallback."""

    def __init__(self, model_name: str, *, revision: str, runtime: RuntimeConfig,
                 cache: Path, device: str = 'cpu', max_seq_length: int = 128) -> None:
        self.model_name = model_name
        if not revision or not re.fullmatch(r'[0-9a-f]{40}', revision):
            raise ValueError('Pin the full 40-character model commit SHA before embedding')
        if device not in {'cpu', 'cuda'}:
            raise ValueError('Choose cpu or cuda explicitly')
        if type(max_seq_length) is not int or max_seq_length <= 0:
            raise ValueError('max_seq_length must be a positive integer')
        if device == 'cuda':
            os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError('Install starter/requirements-embedding.txt in the active Python 3.12 environment; no mock fallback') from exc
        if device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA was requested but torch cannot use CUDA; no CPU fallback')
        torch.set_num_threads(min(runtime.native_threads, effective_cpus()))
        torch.set_num_interop_threads(1)
        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        self.model = SentenceTransformer(model_name, revision=revision, device=device,
                                         cache_folder=str(cache / 'models'), trust_remote_code=False)
        runtime.guard('model-load:after')
        if max_seq_length > self.model.max_seq_length:
            raise ValueError('Requested max_seq_length exceeds the model limit')
        self.model.max_seq_length = max_seq_length
        self.dimensions = self.model.get_sentence_embedding_dimension()
        self.runtime = runtime
        self.identity = {'provider': 'sentence-transformers', 'model': model_name, 'revision': revision,
                         'dimensions': self.dimensions, 'max_seq_length': max_seq_length,
                         'normalize_embeddings': True, 'dtype': 'float32', 'device': device,
                         'batch_size': runtime.batch_size, 'normalization_version': NORMALIZATION_VERSION,
                         'sentence_transformers': importlib.metadata.version('sentence-transformers'),
                         'torch': importlib.metadata.version('torch'),
                         'transformers': importlib.metadata.version('transformers')}
        self.identity['native_threads'] = min(runtime.native_threads, effective_cpus())
        self.cached = EmbeddingCache(cache / 'vectors', self.identity, runtime.batch_size, self._encode)

    def _encode(self, texts, role):
        # Reject truncation: a stored chunk must describe the text that was actually embedded.
        if any(len(text) > 16384 for text in texts):
            raise ValueError('Text exceeds the pre-tokenization character budget')
        lengths = self.model.tokenizer(texts, truncation=False, padding=False)['input_ids']
        if any(len(tokens) > self.model.max_seq_length for tokens in lengths):
            raise ValueError('Text exceeds embedding token limit; reduce chunk size or choose a longer-context model')
        self.runtime.guard('embedding:before')
        result = self.model.encode(texts, batch_size=self.runtime.batch_size,
                                   normalize_embeddings=True, convert_to_numpy=True,
                                   show_progress_bar=False, precision='float32', prompt='')
        self.runtime.guard('embedding:after')
        return result

    def embed_documents(self, texts: list[str]) -> NDArray[np.float32]:
        return self.cached.embed(texts, 'document')

    def embed_query(self, question: str) -> NDArray[np.float32]:
        return self.cached.embed([question], 'query')[0]


class EmbeddingCache:
    """One contiguous result per batch; cache files are data, never pickle."""
    def __init__(self, root: Path, identity: dict, batch_size: int, encode):
        self.root, self.identity, self.batch_size, self.encode = root, identity, batch_size, encode
        self.dimensions = identity['dimensions']
        self.hits = self.misses = 0

    def _key(self, text, role):
        content = json.dumps([self.identity, role, text], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()

    def embed(self, texts, role):
        import numpy as np
        if len(texts) > self.batch_size:
            raise ValueError('Caller exceeded embedding batch budget')
        output = np.empty((len(texts), self.dimensions), dtype=np.float32)
        missing = {}
        for index, text in enumerate(texts):
            key = self._key(text, role)
            path = self.root / f'{key}.npy'
            try:
                if path.stat().st_size > self.dimensions * 4 + 512:
                    raise ValueError('Oversized cached vector')
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != path.with_suffix('.sha256').read_text():
                    raise ValueError('Cached vector checksum mismatch')
                cached = np.load(io.BytesIO(raw), allow_pickle=False)
                if cached.shape != (self.dimensions,) or cached.dtype != np.float32 or not np.isfinite(cached).all() or not np.any(cached):
                    raise ValueError('Invalid cached vector')
                output[index] = cached
                self.hits += 1
            except (OSError, ValueError, EOFError):
                missing.setdefault(key, {'text': text, 'indices': []})['indices'].append(index)
        if missing:
            values = list(missing.values())
            vectors = self.encode([v['text'] for v in values], role)
            if not isinstance(vectors, np.ndarray) or vectors.dtype != np.float32 or vectors.shape != (len(values), self.dimensions):
                raise ValueError('Embedding provider violated float32 matrix contract')
            if not np.isfinite(vectors).all() or not np.all(np.any(vectors != 0, axis=1)):
                raise ValueError('Nonfinite or zero embedding')
            for (key, value), vector in zip(missing.items(), vectors):
                output[value['indices']] = vector
                stream = io.BytesIO()
                np.save(stream, vector, allow_pickle=False)
                atomic_write(self.root / f'{key}.npy', stream.getbuffer())
                atomic_write(self.root / f'{key}.sha256', hashlib.sha256(stream.getbuffer()).hexdigest().encode())
            self.misses += len(values)
        return output
