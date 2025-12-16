"""Unit tests for the vector store."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path

import numpy as np
import pytest
from pytest_mock import MockerFixture

from mcp_server_roam.vector_store import (
    EMBEDDING_DIMENSIONS,
    SyncStatus,
    VectorStore,
    get_vector_store,
)


@pytest.fixture
def temp_db_path() -> Path:
    """Create a temporary database path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def vector_store() -> Generator[VectorStore, None, None]:
    """Create a VectorStore instance with in-memory database for fast tests."""
    store = VectorStore("test-graph", db_path=Path(":memory:"))
    yield store
    store.close()


class TestVectorStoreInit:
    """Tests for VectorStore initialization."""

    def test_init_with_explicit_path(self, temp_db_path: Path) -> None:
        """Test initialization with explicit db path."""
        store = VectorStore("test-graph", db_path=temp_db_path)
        assert store.db_path == temp_db_path
        store.close()

    def test_init_creates_default_path(self, mocker: MockerFixture) -> None:
        """Test that default path is created in ~/.roam-mcp/."""
        mock_mkdir = mocker.patch.object(Path, "mkdir")
        store = VectorStore("my-graph")

        expected_path = Path.home() / ".roam-mcp" / "my-graph_vectors.db"
        assert store.db_path == expected_path
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_schema_created_on_connect(self, temp_db_path: Path) -> None:
        """Test that schema is created when connection is established."""
        store = VectorStore("test-graph", db_path=temp_db_path)

        # Access conn to trigger initialization
        conn = store.conn

        # Check tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        assert "blocks" in tables
        assert "sync_state" in tables
        assert "vec_embeddings" in tables

        store.close()


class TestSyncStatus:
    """Tests for sync status management."""

    def test_get_sync_status_not_initialized(self, vector_store: VectorStore) -> None:
        """Test that new store has NOT_INITIALIZED status."""
        assert vector_store.get_sync_status() == SyncStatus.NOT_INITIALIZED

    def test_set_and_get_sync_status(self, vector_store: VectorStore) -> None:
        """Test setting and getting sync status."""
        vector_store.set_sync_status(SyncStatus.IN_PROGRESS)
        assert vector_store.get_sync_status() == SyncStatus.IN_PROGRESS

        vector_store.set_sync_status(SyncStatus.COMPLETED)
        assert vector_store.get_sync_status() == SyncStatus.COMPLETED

    def test_get_last_sync_timestamp_none(self, vector_store: VectorStore) -> None:
        """Test that new store has no last sync timestamp."""
        assert vector_store.get_last_sync_timestamp() is None

    def test_set_and_get_last_sync_timestamp(self, vector_store: VectorStore) -> None:
        """Test setting and getting last sync timestamp."""
        timestamp = 1700000000000
        vector_store.set_last_sync_timestamp(timestamp)
        assert vector_store.get_last_sync_timestamp() == timestamp


class TestBlockOperations:
    """Tests for block metadata operations."""

    def test_get_block_count_empty(self, vector_store: VectorStore) -> None:
        """Test block count on empty store."""
        assert vector_store.get_block_count() == 0

    def test_upsert_blocks_empty_list(self, vector_store: VectorStore) -> None:
        """Test upserting empty list of blocks."""
        count = vector_store.upsert_blocks([])
        assert count == 0
        assert vector_store.get_block_count() == 0

    def test_upsert_blocks_single(self, vector_store: VectorStore) -> None:
        """Test upserting a single block."""
        blocks = [
            {
                "uid": "block-1",
                "content": "Test content",
                "page_uid": "page-1",
                "page_title": "Test Page",
                "edit_time": 1700000000000,
            }
        ]

        count = vector_store.upsert_blocks(blocks)

        assert count == 1
        assert vector_store.get_block_count() == 1

    def test_upsert_blocks_multiple(self, vector_store: VectorStore) -> None:
        """Test upserting multiple blocks."""
        blocks = [
            {"uid": "block-1", "content": "Content 1"},
            {"uid": "block-2", "content": "Content 2"},
            {"uid": "block-3", "content": "Content 3"},
        ]

        count = vector_store.upsert_blocks(blocks)

        assert count == 3
        assert vector_store.get_block_count() == 3

    def test_upsert_blocks_update_existing(self, vector_store: VectorStore) -> None:
        """Test that upserting existing block updates it."""
        blocks1 = [{"uid": "block-1", "content": "Original content"}]
        blocks2 = [{"uid": "block-1", "content": "Updated content"}]

        vector_store.upsert_blocks(blocks1)
        vector_store.upsert_blocks(blocks2)

        # Should still be 1 block
        assert vector_store.get_block_count() == 1

        # Verify content was updated
        cursor = vector_store.conn.execute(
            "SELECT content FROM blocks WHERE uid = 'block-1'"
        )
        row = cursor.fetchone()
        assert row["content"] == "Updated content"

    def test_upsert_blocks_with_parent_chain(self, vector_store: VectorStore) -> None:
        """Test upserting block with parent chain."""
        blocks = [
            {
                "uid": "block-1",
                "content": "Test content",
                "parent_chain": ["Parent 1", "Parent 2"],
            }
        ]

        vector_store.upsert_blocks(blocks)

        cursor = vector_store.conn.execute(
            "SELECT parent_chain FROM blocks WHERE uid = 'block-1'"
        )
        row = cursor.fetchone()
        assert json.loads(row["parent_chain"]) == ["Parent 1", "Parent 2"]


class TestEmbeddingOperations:
    """Tests for embedding operations."""

    def test_get_embedding_count_empty(self, vector_store: VectorStore) -> None:
        """Test embedding count on empty store."""
        assert vector_store.get_embedding_count() == 0

    def test_upsert_embeddings_empty(self, vector_store: VectorStore) -> None:
        """Test upserting empty embeddings."""
        count = vector_store.upsert_embeddings([], np.array([]))
        assert count == 0

    def test_upsert_embeddings_single(self, vector_store: VectorStore) -> None:
        """Test upserting a single embedding."""
        # First add the block
        vector_store.upsert_blocks([{"uid": "block-1", "content": "Test"}])

        # Then add embedding
        embedding = np.array([[0.1] * EMBEDDING_DIMENSIONS], dtype=np.float32)
        count = vector_store.upsert_embeddings(["block-1"], embedding)

        assert count == 1
        assert vector_store.get_embedding_count() == 1

    def test_upsert_embeddings_multiple(self, vector_store: VectorStore) -> None:
        """Test upserting multiple embeddings."""
        # First add blocks
        blocks = [
            {"uid": "block-1", "content": "Content 1"},
            {"uid": "block-2", "content": "Content 2"},
        ]
        vector_store.upsert_blocks(blocks)

        # Then add embeddings
        embeddings = np.array(
            [
                [0.1] * EMBEDDING_DIMENSIONS,
                [0.2] * EMBEDDING_DIMENSIONS,
            ],
            dtype=np.float32,
        )
        count = vector_store.upsert_embeddings(["block-1", "block-2"], embeddings)

        assert count == 2
        assert vector_store.get_embedding_count() == 2

    def test_upsert_embeddings_updates_embedded_at(
        self, vector_store: VectorStore
    ) -> None:
        """Test that upserting embeddings updates embedded_at timestamp."""
        vector_store.upsert_blocks([{"uid": "block-1", "content": "Test"}])

        # Check embedded_at is NULL initially
        cursor = vector_store.conn.execute(
            "SELECT embedded_at FROM blocks WHERE uid = 'block-1'"
        )
        assert cursor.fetchone()["embedded_at"] is None

        # Add embedding
        embedding = np.array([[0.1] * EMBEDDING_DIMENSIONS], dtype=np.float32)
        vector_store.upsert_embeddings(["block-1"], embedding)

        # Check embedded_at is set
        cursor = vector_store.conn.execute(
            "SELECT embedded_at FROM blocks WHERE uid = 'block-1'"
        )
        assert cursor.fetchone()["embedded_at"] is not None


class TestSearch:
    """Tests for vector similarity search."""

    def test_search_empty_store(self, vector_store: VectorStore) -> None:
        """Test searching empty store returns empty results."""
        query = np.array([0.1] * EMBEDDING_DIMENSIONS, dtype=np.float32)
        results = vector_store.search(query, limit=10)
        assert results == []

    def test_search_returns_results(self, vector_store: VectorStore) -> None:
        """Test search returns matching results."""
        # Add blocks and embeddings
        blocks = [
            {"uid": "block-1", "content": "Content 1", "page_title": "Page 1"},
            {"uid": "block-2", "content": "Content 2", "page_title": "Page 2"},
        ]
        vector_store.upsert_blocks(blocks)

        embeddings = np.array(
            [
                [0.1] * EMBEDDING_DIMENSIONS,
                [0.9] * EMBEDDING_DIMENSIONS,
            ],
            dtype=np.float32,
        )
        vector_store.upsert_embeddings(["block-1", "block-2"], embeddings)

        # Search with query similar to block-1
        query = np.array([0.1] * EMBEDDING_DIMENSIONS, dtype=np.float32)
        results = vector_store.search(query, limit=10)

        assert len(results) == 2
        # First result should be block-1 (exact match)
        assert results[0]["uid"] == "block-1"
        assert results[0]["content"] == "Content 1"
        assert results[0]["page_title"] == "Page 1"
        assert "similarity" in results[0]

    def test_search_respects_limit(self, vector_store: VectorStore) -> None:
        """Test search respects limit parameter."""
        # Add 5 blocks
        blocks = [{"uid": f"block-{i}", "content": f"Content {i}"} for i in range(5)]
        vector_store.upsert_blocks(blocks)

        embeddings = np.array(
            [[float(i) * 0.1] * EMBEDDING_DIMENSIONS for i in range(5)],
            dtype=np.float32,
        )
        vector_store.upsert_embeddings([f"block-{i}" for i in range(5)], embeddings)

        query = np.array([0.0] * EMBEDDING_DIMENSIONS, dtype=np.float32)
        results = vector_store.search(query, limit=2)

        assert len(results) == 2

    def test_search_with_parent_chain(self, vector_store: VectorStore) -> None:
        """Test search returns parent chain in results."""
        blocks = [
            {
                "uid": "block-1",
                "content": "Content 1",
                "parent_chain": ["Parent 1", "Parent 2"],
            }
        ]
        vector_store.upsert_blocks(blocks)

        embedding = np.array([[0.1] * EMBEDDING_DIMENSIONS], dtype=np.float32)
        vector_store.upsert_embeddings(["block-1"], embedding)

        query = np.array([0.1] * EMBEDDING_DIMENSIONS, dtype=np.float32)
        results = vector_store.search(query, limit=1)

        assert len(results) == 1
        assert results[0]["parent_chain"] == ["Parent 1", "Parent 2"]

    def test_search_min_similarity_filters_results(
        self, vector_store: VectorStore
    ) -> None:
        """Test search filters results below min_similarity threshold."""
        # Add blocks with very different embeddings
        blocks = [
            {"uid": "block-1", "content": "Content 1"},
            {"uid": "block-2", "content": "Content 2"},
        ]
        vector_store.upsert_blocks(blocks)

        # Create embeddings that are very different (one near 0.1, one near 0.9)
        embeddings = np.array(
            [
                [0.1] * EMBEDDING_DIMENSIONS,
                [0.9] * EMBEDDING_DIMENSIONS,
            ],
            dtype=np.float32,
        )
        vector_store.upsert_embeddings(["block-1", "block-2"], embeddings)

        # Search with query similar to block-1, but with high min_similarity
        query = np.array([0.1] * EMBEDDING_DIMENSIONS, dtype=np.float32)
        # Set min_similarity very high to filter out non-exact matches
        results = vector_store.search(query, limit=10, min_similarity=0.99)

        # Should only return block-1 (exact match)
        assert len(results) == 1
        assert results[0]["uid"] == "block-1"


class TestBlocksNeedingEmbedding:
    """Tests for get_blocks_needing_embedding."""

    def test_empty_store(self, vector_store: VectorStore) -> None:
        """Test returns empty list for empty store."""
        blocks = vector_store.get_blocks_needing_embedding()
        assert blocks == []

    def test_returns_unembedded_blocks(self, vector_store: VectorStore) -> None:
        """Test returns blocks without embeddings."""
        vector_store.upsert_blocks(
            [
                {"uid": "block-1", "content": "Content 1"},
                {"uid": "block-2", "content": "Content 2"},
            ]
        )

        blocks = vector_store.get_blocks_needing_embedding()

        assert len(blocks) == 2
        uids = {b["uid"] for b in blocks}
        assert uids == {"block-1", "block-2"}

    def test_excludes_embedded_blocks(self, vector_store: VectorStore) -> None:
        """Test excludes blocks that already have embeddings."""
        vector_store.upsert_blocks(
            [
                {"uid": "block-1", "content": "Content 1"},
                {"uid": "block-2", "content": "Content 2"},
            ]
        )

        # Embed block-1
        embedding = np.array([[0.1] * EMBEDDING_DIMENSIONS], dtype=np.float32)
        vector_store.upsert_embeddings(["block-1"], embedding)

        blocks = vector_store.get_blocks_needing_embedding()

        assert len(blocks) == 1
        assert blocks[0]["uid"] == "block-2"

    def test_respects_limit(self, vector_store: VectorStore) -> None:
        """Test respects limit parameter."""
        blocks = [{"uid": f"block-{i}", "content": f"Content {i}"} for i in range(10)]
        vector_store.upsert_blocks(blocks)

        result = vector_store.get_blocks_needing_embedding(limit=5)

        assert len(result) == 5


class TestDropAllData:
    """Tests for drop_all_data."""

    def test_drops_all_data(self, vector_store: VectorStore) -> None:
        """Test that drop_all_data clears all tables."""
        # Add data
        vector_store.upsert_blocks([{"uid": "block-1", "content": "Test"}])
        embedding = np.array([[0.1] * EMBEDDING_DIMENSIONS], dtype=np.float32)
        vector_store.upsert_embeddings(["block-1"], embedding)
        vector_store.set_sync_status(SyncStatus.COMPLETED)
        vector_store.set_last_sync_timestamp(1700000000000)

        # Drop all data
        vector_store.drop_all_data()

        # Verify everything is cleared
        assert vector_store.get_block_count() == 0
        assert vector_store.get_embedding_count() == 0
        assert vector_store.get_sync_status() == SyncStatus.NOT_INITIALIZED
        assert vector_store.get_last_sync_timestamp() is None


class TestClose:
    """Tests for close method."""

    def test_close_connection(self, temp_db_path: Path) -> None:
        """Test closing the connection."""
        store = VectorStore("test-graph", db_path=temp_db_path)

        # Access conn to establish connection
        _ = store.conn
        assert store._conn is not None

        store.close()
        assert store._conn is None

    def test_close_without_connection(self, temp_db_path: Path) -> None:
        """Test closing when no connection exists."""
        store = VectorStore("test-graph", db_path=temp_db_path)
        # Don't access conn
        store.close()  # Should not raise


class TestGetVectorStore:
    """Tests for get_vector_store singleton function."""

    def test_creates_singleton_per_graph(self, mocker: MockerFixture) -> None:
        """Test that get_vector_store creates singleton per graph name."""
        import mcp_server_roam.vector_store as vs_module

        # Reset singletons
        vs_module._vector_stores = {}

        # Mock the VectorStore class to return different instances each time
        mock_store_a = mocker.MagicMock()
        mock_store_b = mocker.MagicMock()
        mock_class = mocker.patch.object(
            vs_module,
            "VectorStore",
            side_effect=[mock_store_a, mock_store_b],
        )

        store1 = get_vector_store("graph-a")
        store2 = get_vector_store("graph-a")
        store3 = get_vector_store("graph-b")

        assert store1 is store2  # Same graph should return same instance
        assert store1 is not store3  # Different graph should return different instance
        assert mock_class.call_count == 2  # Only 2 VectorStore instances created

    def test_returns_existing_store(self, mocker: MockerFixture) -> None:
        """Test that get_vector_store returns existing store."""
        import mcp_server_roam.vector_store as vs_module

        # Reset singletons
        vs_module._vector_stores = {}

        mock_store = mocker.MagicMock()
        mocker.patch.object(vs_module, "VectorStore", return_value=mock_store)

        store1 = get_vector_store("test-graph")
        store2 = get_vector_store("test-graph")

        assert store1 is store2
        # VectorStore should only be called once
        vs_module.VectorStore.assert_called_once_with("test-graph")
