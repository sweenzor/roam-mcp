"""Embedding service for semantic search using sentence-transformers."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Model configuration
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384
DEFAULT_BATCH_SIZE = 64


class EmbeddingService:
    """Service for generating text embeddings using sentence-transformers.

    Uses lazy loading to defer model initialization until first use.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        """Initialize the embedding service.

        Args:
            model_name: Name of the sentence-transformers model to use.
        """
        self._model_name = model_name
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazily load and return the embedding model."""
        if self._model is None:
            logger.info("Loading embedding model: %s", self._model_name)
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
            logger.info("Embedding model loaded successfully")
        return self._model

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensions for the current model."""
        return EMBEDDING_DIMENSIONS

    def embed_texts(
        self, texts: list[str], batch_size: int = DEFAULT_BATCH_SIZE
    ) -> NDArray[np.float32]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.
            batch_size: Number of texts to process per batch.

        Returns:
            Array of embeddings with shape (len(texts), dimensions).
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, EMBEDDING_DIMENSIONS)

        logger.debug("Embedding %d texts with batch size %d", len(texts), batch_size)
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.astype(np.float32)

    def embed_single(self, text: str) -> NDArray[np.float32]:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed.

        Returns:
            Embedding array with shape (dimensions,).
        """
        embeddings = self.embed_texts([text])
        return embeddings[0]

    @staticmethod
    def format_block_for_embedding(
        content: str,
        page_title: str | None = None,
        parent_chain: list[str] | None = None,
    ) -> str:
        """Format a block with context for embedding.

        Combines block content with page title and parent context to create
        a richer text representation for embedding.

        Args:
            content: The block's text content.
            page_title: Title of the page containing the block.
            parent_chain: List of parent block contents from root to immediate parent.

        Returns:
            Formatted text string for embedding.
        """
        parts = []

        if page_title:
            parts.append(f"Page: {page_title}")

        if parent_chain:
            path = " > ".join(parent_chain)
            parts.append(f"Path: {path}")

        parts.append(f"Content: {content}")

        return "\n".join(parts)


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service(model_name: str = DEFAULT_MODEL_NAME) -> EmbeddingService:
    """Get or create the singleton embedding service instance.

    Args:
        model_name: Name of the sentence-transformers model to use.

    Returns:
        The shared EmbeddingService instance.
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name)
    return _embedding_service
