"""Unit tests for the embedding service."""

import numpy as np
import pytest
from pytest_mock import MockerFixture

from mcp_server_roam.embedding import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MODEL_NAME,
    EMBEDDING_DIMENSIONS,
    EmbeddingService,
    get_embedding_service,
)


class TestEmbeddingService:
    """Tests for EmbeddingService class."""

    def test_init_default_model(self) -> None:
        """Test initialization with default model name."""
        service = EmbeddingService()
        assert service._model_name == DEFAULT_MODEL_NAME
        assert service._model is None

    def test_init_custom_model(self) -> None:
        """Test initialization with custom model name."""
        service = EmbeddingService("custom-model")
        assert service._model_name == "custom-model"
        assert service._model is None

    def test_dimensions(self) -> None:
        """Test dimensions property returns correct value."""
        service = EmbeddingService()
        assert service.dimensions == EMBEDDING_DIMENSIONS

    def test_model_lazy_loading(self, mocker: MockerFixture) -> None:
        """Test that model is lazily loaded on first access."""
        mock_transformer = mocker.MagicMock()
        mock_model = mocker.MagicMock()
        mock_transformer.return_value = mock_model

        mocker.patch(
            "sentence_transformers.SentenceTransformer",
            mock_transformer,
        )

        service = EmbeddingService()

        # Model should not be loaded yet
        assert service._model is None

        # Access model property
        model = service.model

        # Now model should be loaded
        assert model == mock_model
        mock_transformer.assert_called_once_with(DEFAULT_MODEL_NAME)

    def test_model_singleton_within_instance(self, mocker: MockerFixture) -> None:
        """Test that model is only loaded once per instance."""
        mock_transformer = mocker.MagicMock()
        mock_model = mocker.MagicMock()
        mock_transformer.return_value = mock_model

        mocker.patch(
            "sentence_transformers.SentenceTransformer",
            mock_transformer,
        )

        service = EmbeddingService()

        # Access model multiple times
        _ = service.model
        _ = service.model
        _ = service.model

        # Should only be instantiated once
        mock_transformer.assert_called_once()

    def test_embed_texts_empty_list(self, mocker: MockerFixture) -> None:
        """Test embedding empty list returns empty array."""
        service = EmbeddingService()

        result = service.embed_texts([])

        assert result.shape == (0, EMBEDDING_DIMENSIONS)
        assert result.dtype == np.float32

    def test_embed_texts_single_text(self, mocker: MockerFixture) -> None:
        """Test embedding a single text."""
        mock_transformer = mocker.MagicMock()
        mock_model = mocker.MagicMock()
        mock_transformer.return_value = mock_model

        # Create mock embeddings
        mock_embeddings = np.array([[0.1, 0.2, 0.3] * 128], dtype=np.float64)
        mock_model.encode.return_value = mock_embeddings

        mocker.patch(
            "sentence_transformers.SentenceTransformer",
            mock_transformer,
        )

        service = EmbeddingService()
        result = service.embed_texts(["test text"])

        assert result.shape == (1, EMBEDDING_DIMENSIONS)
        assert result.dtype == np.float32
        mock_model.encode.assert_called_once_with(
            ["test text"],
            batch_size=DEFAULT_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

    def test_embed_texts_multiple_texts(self, mocker: MockerFixture) -> None:
        """Test embedding multiple texts."""
        mock_transformer = mocker.MagicMock()
        mock_model = mocker.MagicMock()
        mock_transformer.return_value = mock_model

        # Create mock embeddings for 3 texts
        mock_embeddings = np.array([
            [0.1] * EMBEDDING_DIMENSIONS,
            [0.2] * EMBEDDING_DIMENSIONS,
            [0.3] * EMBEDDING_DIMENSIONS,
        ], dtype=np.float64)
        mock_model.encode.return_value = mock_embeddings

        mocker.patch(
            "sentence_transformers.SentenceTransformer",
            mock_transformer,
        )

        service = EmbeddingService()
        result = service.embed_texts(["text1", "text2", "text3"])

        assert result.shape == (3, EMBEDDING_DIMENSIONS)
        assert result.dtype == np.float32

    def test_embed_texts_custom_batch_size(self, mocker: MockerFixture) -> None:
        """Test embedding with custom batch size."""
        mock_transformer = mocker.MagicMock()
        mock_model = mocker.MagicMock()
        mock_transformer.return_value = mock_model

        mock_embeddings = np.array([[0.1] * EMBEDDING_DIMENSIONS], dtype=np.float32)
        mock_model.encode.return_value = mock_embeddings

        mocker.patch(
            "sentence_transformers.SentenceTransformer",
            mock_transformer,
        )

        service = EmbeddingService()
        service.embed_texts(["test"], batch_size=32)

        mock_model.encode.assert_called_once_with(
            ["test"],
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

    def test_embed_single(self, mocker: MockerFixture) -> None:
        """Test embedding a single text returns 1D array."""
        mock_transformer = mocker.MagicMock()
        mock_model = mocker.MagicMock()
        mock_transformer.return_value = mock_model

        mock_embeddings = np.array([[0.1] * EMBEDDING_DIMENSIONS], dtype=np.float32)
        mock_model.encode.return_value = mock_embeddings

        mocker.patch(
            "sentence_transformers.SentenceTransformer",
            mock_transformer,
        )

        service = EmbeddingService()
        result = service.embed_single("test text")

        assert result.shape == (EMBEDDING_DIMENSIONS,)
        assert result.dtype == np.float32


class TestFormatBlockForEmbedding:
    """Tests for format_block_for_embedding static method."""

    def test_content_only(self) -> None:
        """Test formatting with content only."""
        result = EmbeddingService.format_block_for_embedding("Test content")
        assert result == "Content: Test content"

    def test_with_page_title(self) -> None:
        """Test formatting with page title."""
        result = EmbeddingService.format_block_for_embedding(
            "Test content", page_title="My Page"
        )
        assert result == "Page: My Page\nContent: Test content"

    def test_with_parent_chain(self) -> None:
        """Test formatting with parent chain."""
        result = EmbeddingService.format_block_for_embedding(
            "Test content", parent_chain=["Parent 1", "Parent 2"]
        )
        assert result == "Path: Parent 1 > Parent 2\nContent: Test content"

    def test_with_all_context(self) -> None:
        """Test formatting with all context provided."""
        result = EmbeddingService.format_block_for_embedding(
            "Test content",
            page_title="My Page",
            parent_chain=["Parent 1", "Parent 2"],
        )
        expected = "Page: My Page\nPath: Parent 1 > Parent 2\nContent: Test content"
        assert result == expected

    def test_empty_content(self) -> None:
        """Test formatting with empty content."""
        result = EmbeddingService.format_block_for_embedding("")
        assert result == "Content: "

    def test_empty_parent_chain(self) -> None:
        """Test formatting with empty parent chain."""
        result = EmbeddingService.format_block_for_embedding(
            "Test content", parent_chain=[]
        )
        # Empty parent chain should not add Path line
        assert result == "Content: Test content"

    def test_none_page_title(self) -> None:
        """Test formatting with None page title."""
        result = EmbeddingService.format_block_for_embedding(
            "Test content", page_title=None
        )
        assert result == "Content: Test content"


class TestGetEmbeddingService:
    """Tests for get_embedding_service singleton function."""

    def test_creates_singleton(self, mocker: MockerFixture) -> None:
        """Test that get_embedding_service creates a singleton."""
        import mcp_server_roam.embedding as embedding_module

        # Reset singleton
        embedding_module._embedding_service = None

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2

    def test_uses_default_model(self, mocker: MockerFixture) -> None:
        """Test that singleton uses default model name."""
        import mcp_server_roam.embedding as embedding_module

        # Reset singleton
        embedding_module._embedding_service = None

        service = get_embedding_service()

        assert service._model_name == DEFAULT_MODEL_NAME

    def test_custom_model_name(self, mocker: MockerFixture) -> None:
        """Test singleton with custom model name."""
        import mcp_server_roam.embedding as embedding_module

        # Reset singleton
        embedding_module._embedding_service = None

        service = get_embedding_service("custom-model")

        assert service._model_name == "custom-model"
