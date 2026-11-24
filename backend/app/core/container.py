"""Service container: builds and owns the long-lived objects (embedder, stores, retriever, LLM, agent)."""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.graph import KnowledgeAgent
from app.core.config import Settings
from app.core.embeddings import Embedder, build_embedder
from app.core.llm import LLMClient, build_llm
from app.core.logging import get_logger
from app.core.vectorstore import VectorStore
from app.evaluation.evaluator import Evaluator, Judge, build_judge
from app.evaluation.store import EvaluationStore
from app.ingestion.indexer import IngestionService
from app.retrieval.hybrid_retriever import HybridRetriever

logger = get_logger(__name__)


@dataclass
class Container:
    settings: Settings
    embedder: Embedder
    vector_store: VectorStore
    ingestion: IngestionService
    retriever: HybridRetriever
    llm: LLMClient
    agent: KnowledgeAgent
    eval_store: EvaluationStore
    evaluator: Evaluator

    @classmethod
    def build(
        cls,
        settings: Settings,
        *,
        embedder: Embedder | None = None,
        llm: LLMClient | None = None,
        vector_store: VectorStore | None = None,
        judge: Judge | None = None,
    ) -> Container:
        """Wire everything up. Any piece can be injected (tests pass fakes / in-memory stores)."""
        embedder = embedder or build_embedder(settings)
        vector_store = vector_store or VectorStore.from_settings(settings, dim=embedder.dim)
        ingestion = IngestionService.from_settings(settings, embedder, vector_store)
        retriever = HybridRetriever.from_settings(settings, embedder, vector_store, ingestion.bm25)
        llm = llm or build_llm(settings)
        agent = KnowledgeAgent(llm, retriever, settings)
        eval_store = EvaluationStore(settings.data_dir / "eval_results.db")
        evaluator = Evaluator(agent, judge or build_judge(settings, llm, embedder), eval_store,
                              concurrency=settings.eval_concurrency)
        logger.info(
            "Container ready: llm=%s/%s embeddings=%s docs=%d",
            settings.llm_provider, settings.resolved_llm_model, settings.embedding_provider,
            len(ingestion.list_documents()),
        )
        return cls(settings, embedder, vector_store, ingestion, retriever, llm, agent, eval_store, evaluator)

    def close(self) -> None:
        self.vector_store.close()
