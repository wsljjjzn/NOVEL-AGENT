"""
knowledge_base.retriever — 混合检索器（向量 + BM25 + RRF 融合 + Rerank）。
"""

import os, time, threading
from typing import Any, Optional

from src.utils.logger import logger


class RetrievalResult:
    """检索结果条目。"""
    def __init__(self, content: Any, score: float, source: str, chunk_id: str = ""):
        self.content = content
        self.score = score
        self.source = source
        self.chunk_id = chunk_id


class BaseRetriever:
    """检索器基类 — 定义混合检索接口。"""
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def vector_search(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        raise NotImplementedError

    def bm25_search(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        raise NotImplementedError

    def hybrid_search(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        vector_results = self.vector_search(query, top_k=top_k)
        bm25_results = self.bm25_search(query, top_k=top_k)
        rrf_k = 60
        scores = {}
        for rank, r in enumerate(vector_results):
            scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (rrf_k + rank + 1)
        for rank, r in enumerate(bm25_results):
            scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (rrf_k + rank + 1)
        all_results = {}
        for r in vector_results + bm25_results:
            if r.chunk_id not in all_results:
                all_results[r.chunk_id] = r
        sorted_results = sorted(
            all_results.values(),
            key=lambda r: scores.get(r.chunk_id, 0), reverse=True,
        )
        for r in sorted_results:
            r.score = scores.get(r.chunk_id, 0)
            r.source = "hybrid"
        return sorted_results[:top_k]

    def rerank(self, query: str, results: list[RetrievalResult], top_k: int = 5) -> list[RetrievalResult]:
        raise NotImplementedError


def _fallback_embed(texts: list[str]) -> list[list[float]]:
    return [[0.0] * 768 for _ in texts]


class Retriever(BaseRetriever):
    """混合检索器 — 延迟初始化 ChromaDB + BM25 + RRF。"""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self._chroma_collection = None
        self._bm25_model = None
        self._bm25_corpus = []
        self._bm25_chunk_ids = []
        self._embed_fn = None
        self._reranker = None
        self._skip_model = self.config.get("skip_model", False)

    # ---- Embedding（超时保护） ----

    def _get_embed_fn(self):
        if self._embed_fn is not None:
            return self._embed_fn
        if self._skip_model:
            self._embed_fn = _fallback_embed
            return self._embed_fn

        # 尝试加载模型，设置超时
        result = [None]
        def load():
            try:
                from sentence_transformers import SentenceTransformer
                model_name = self.config.get("embedding_model", "BAAI/bge-m3")
                logger.info(f"加载 embedding 模型: {model_name}")
                model = SentenceTransformer(model_name, trust_remote_code=True)
                result[0] = lambda texts: model.encode(
                    texts, normalize_embeddings=True, show_progress_bar=False
                ).tolist()
            except Exception as e:
                logger.warning(f"Embedding 模型加载失败: {e}")
                result[0] = _fallback_embed

        t = threading.Thread(target=load, daemon=True)
        t.start()
        t.join(timeout=30)  # 最多等 30 秒
        if result[0] is None:
            logger.warning("Embedding 模型加载超时（30s），使用 fallback")
            self._embed_fn = _fallback_embed
        else:
            self._embed_fn = result[0]
        return self._embed_fn

    # ---- ChromaDB ----

    def _init_chroma(self):
        if self._chroma_collection is not None:
            return self._chroma_collection
        try:
            import chromadb
            persist_dir = self.config.get("persist_directory", "data/embeddings")
            os.makedirs(persist_dir, exist_ok=True)
            client = chromadb.PersistentClient(path=persist_dir)
            name = self.config.get("collection_name", "writing_knowledge")
            self._chroma_collection = client.get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"ChromaDB 就绪: {name}")
        except Exception as e:
            logger.warning(f"ChromaDB 初始化失败，使用内存模式: {e}")
            try:
                import chromadb
                client = chromadb.Client()
                self._chroma_collection = client.get_or_create_collection(
                    name="writing_knowledge_mem",
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as e2:
                logger.warning(f"ChromaDB 内存模式也失败: {e2}")
        return self._chroma_collection

    def index_chunks(self, chunks: list[Any], text_field: str = "text",
                     id_field: str = "chunk_id", metadata_fields: list[str] = None):
        texts = [getattr(c, text_field, "") for c in chunks]
        ids = [getattr(c, id_field, f"chunk_{i}") for i, c in enumerate(chunks)]
        metadata = [{"source": getattr(c, "source_file", "")} for c in chunks]

        # 向量入库
        try:
            collection = self._init_chroma()
            if collection is None:
                return
            embed_fn = self._get_embed_fn()
            embeddings = embed_fn(texts)
            batch_size = 100
            for i in range(0, len(texts), batch_size):
                end = min(i + batch_size, len(texts))
                collection.add(
                    ids=ids[i:end], documents=texts[i:end],
                    embeddings=embeddings[i:end], metadatas=metadata[i:end],
                )
            logger.info(f"ChromaDB 索引 {len(chunks)} 块")
        except Exception as e:
            logger.warning(f"ChromaDB 索引失败: {e}")

        # BM25 入库
        try:
            from rank_bm25 import BM25Okapi
            import jieba
            tokenized = [list(jieba.cut(t)) for t in texts]
            self._bm25_model = BM25Okapi(tokenized)
            self._bm25_corpus = texts
            self._bm25_chunk_ids = ids
            logger.info(f"BM25 索引 {len(chunks)} 块")
        except Exception as e:
            logger.warning(f"BM25 索引失败: {e}")

    def vector_search(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        collection = self._init_chroma()
        if collection is None:
            return []
        embed_fn = self._get_embed_fn()
        try:
            q_emb = embed_fn([query])[0]
            results = collection.query(query_embeddings=[q_emb], n_results=min(top_k, collection.count() or 1))
            if not results or not results.get("ids"):
                return []
            return [
                RetrievalResult(
                    content={"text": (results.get("documents") or [[""]])[0][i],
                             "metadata": (results.get("metadatas") or [{}])[0][i]},
                    score=1.0 - (results.get("distances") or [[0.5]])[0][i],
                    source="vector", chunk_id=results["ids"][0][i],
                )
                for i in range(len(results["ids"][0]))
            ]
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            return []

    def bm25_search(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        if self._bm25_model is None:
            return []
        try:
            import jieba
            tokenized = list(jieba.cut(query))
            scores = self._bm25_model.get_scores(tokenized)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
            return [
                RetrievalResult(content={"text": self._bm25_corpus[i]},
                                score=float(scores[i]), source="bm25",
                                chunk_id=self._bm25_chunk_ids[i])
                for i in top_indices if scores[i] > 0
            ]
        except Exception as e:
            logger.warning(f"BM25 检索失败: {e}")
            return []

    def rerank(self, query: str, results: list[RetrievalResult], top_k: int = 5) -> list[RetrievalResult]:
        if not results:
            return results
        try:
            from FlagEmbedding import FlagReranker
            if self._reranker is None:
                self._reranker = FlagReranker(
                    self.config.get("reranker_model", "BAAI/bge-reranker-v2-m3"),
                    use_fp16=False,
                )
            pairs = [(query, r.content.get("text", "")) for r in results]
            scores = self._reranker.compute_score(pairs, normalize=True)
            scored = list(zip(results, scores))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [r for r, _ in scored[:top_k]]
        except Exception as e:
            logger.warning(f"Rerank 失败: {e}")
            return results[:top_k]
