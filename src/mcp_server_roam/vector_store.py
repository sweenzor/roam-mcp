"""Vector store using SQLite + sqlite-vec for semantic search."""

import json
import logging
import sqlite3
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import sqlite_vec

if TYPE_CHECKING:
    from numpy.typing import NDArray

import numpy as np

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_DATA_DIR = Path.home() / ".roam-mcp"
EMBEDDING_DIMENSIONS = 384


class SyncStatus(str, Enum):
    """Status of the vector index synchronization."""

    NOT_INITIALIZED = "not_initialized"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class VectorStore:
    """SQLite-based vector store using sqlite-vec for similarity search."""

    def __init__(
        self,
        graph_name: str,
        db_path: Path | None = None,
    ) -> None:
        """Initialize the vector store.

        Args:
            graph_name: Name of the Roam graph (used for default db path).
            db_path: Optional explicit path for the database file.
        """
        self._graph_name = graph_name
        if db_path is None:
            data_dir = DEFAULT_DATA_DIR
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / f"{graph_name}_vectors.db"
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        logger.info("VectorStore initialized with db: %s", self._db_path)

    @property
    def db_path(self) -> Path:
        """Return the database file path."""
        return self._db_path

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create the database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        # Main blocks table for metadata
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                uid TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                page_uid TEXT,
                page_title TEXT,
                parent_uid TEXT,
                parent_chain TEXT,
                edit_time INTEGER,
                embedded_at INTEGER
            )
        """)

        # Sync state tracking
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Vector embeddings table using sqlite-vec
        self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings USING vec0(
                uid TEXT PRIMARY KEY,
                embedding FLOAT[{EMBEDDING_DIMENSIONS}]
            )
        """)

        # Index for efficient lookups
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blocks_edit_time
            ON blocks(edit_time)
        """)

        self.conn.commit()
        logger.debug("Database schema initialized")

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get_sync_status(self) -> SyncStatus:
        """Get the current sync status."""
        cursor = self.conn.execute(
            "SELECT value FROM sync_state WHERE key = 'status'"
        )
        row = cursor.fetchone()
        if row is None:
            return SyncStatus.NOT_INITIALIZED
        return SyncStatus(row["value"])

    def set_sync_status(self, status: SyncStatus) -> None:
        """Set the sync status."""
        self.conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES ('status', ?)",
            (status.value,),
        )
        self.conn.commit()

    def get_last_sync_timestamp(self) -> int | None:
        """Get the timestamp of the last successful sync."""
        cursor = self.conn.execute(
            "SELECT value FROM sync_state WHERE key = 'last_sync_timestamp'"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return int(row["value"])

    def set_last_sync_timestamp(self, timestamp: int) -> None:
        """Set the last sync timestamp."""
        self.conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES "
            "('last_sync_timestamp', ?)",
            (str(timestamp),),
        )
        self.conn.commit()

    def get_block_count(self) -> int:
        """Get the total number of blocks in the store."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM blocks")
        return cursor.fetchone()[0]

    def get_embedding_count(self) -> int:
        """Get the total number of embeddings in the store."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM vec_embeddings")
        return cursor.fetchone()[0]

    def upsert_blocks(self, blocks: list[dict]) -> int:
        """Insert or update block metadata.

        Args:
            blocks: List of block dictionaries with keys:
                - uid: Block UID (required)
                - content: Block text content (required)
                - page_uid: UID of the containing page
                - page_title: Title of the containing page
                - parent_uid: UID of the parent block
                - parent_chain: List of parent content strings
                - edit_time: Edit timestamp in milliseconds

        Returns:
            Number of blocks upserted.
        """
        if not blocks:
            return 0

        cursor = self.conn.cursor()
        count = 0

        for block in blocks:
            parent_chain_json = (
                json.dumps(block.get("parent_chain"))
                if block.get("parent_chain")
                else None
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO blocks
                (uid, content, page_uid, page_title, parent_uid, parent_chain,
                 edit_time, embedded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    block["uid"],
                    block["content"],
                    block.get("page_uid"),
                    block.get("page_title"),
                    block.get("parent_uid"),
                    parent_chain_json,
                    block.get("edit_time"),
                ),
            )
            count += 1

        self.conn.commit()
        return count

    def upsert_embeddings(
        self,
        uids: list[str],
        embeddings: "NDArray[np.float32]",
    ) -> int:
        """Insert or update embeddings for blocks.

        Args:
            uids: List of block UIDs.
            embeddings: Array of embeddings with shape (len(uids), dimensions).

        Returns:
            Number of embeddings upserted.
        """
        if len(uids) == 0:
            return 0

        cursor = self.conn.cursor()

        # Delete existing embeddings for these UIDs
        placeholders = ",".join("?" * len(uids))
        cursor.execute(
            f"DELETE FROM vec_embeddings WHERE uid IN ({placeholders})",
            uids,
        )

        # Insert new embeddings
        for uid, embedding in zip(uids, embeddings, strict=False):
            # sqlite-vec accepts numpy arrays directly if they're float32
            cursor.execute(
                "INSERT INTO vec_embeddings (uid, embedding) VALUES (?, ?)",
                (uid, embedding.astype(np.float32)),
            )

        # Update embedded_at timestamp for these blocks
        import time

        now = int(time.time() * 1000)
        cursor.execute(
            f"UPDATE blocks SET embedded_at = ? WHERE uid IN ({placeholders})",
            [now, *uids],
        )

        self.conn.commit()
        return len(uids)

    def search(
        self,
        query_embedding: "NDArray[np.float32]",
        limit: int = 10,
        min_similarity: float = 0.0,
    ) -> list[dict]:
        """Search for similar blocks using vector similarity.

        Args:
            query_embedding: Query embedding vector.
            limit: Maximum number of results to return.
            min_similarity: Minimum cosine similarity threshold (0-1).

        Returns:
            List of result dictionaries with keys:
                - uid: Block UID
                - content: Block text content
                - page_title: Title of containing page
                - parent_chain: List of parent content strings
                - similarity: Cosine similarity score (0-1)
        """
        logger.debug(
            "Vector search: limit=%d, min_similarity=%.2f", limit, min_similarity
        )
        # sqlite-vec uses L2 distance, convert to similarity
        # For normalized vectors: similarity = 1 - (distance^2 / 2)
        # Note: sqlite-vec requires k = ? parameter for KNN queries
        cursor = self.conn.execute(
            """
            SELECT
                v.uid,
                v.distance,
                b.content,
                b.page_title,
                b.parent_chain
            FROM vec_embeddings v
            JOIN blocks b ON v.uid = b.uid
            WHERE v.embedding MATCH ? AND v.k = ?
            ORDER BY v.distance
            """,
            (query_embedding.astype(np.float32), limit),
        )

        results = []
        for row in cursor:
            # Convert L2 distance to approximate cosine similarity
            # For unit vectors: cos_sim ≈ 1 - (l2_dist^2 / 2)
            distance = row["distance"]
            similarity = max(0.0, 1.0 - (distance * distance / 2.0))

            if similarity < min_similarity:
                continue

            parent_chain = (
                json.loads(row["parent_chain"]) if row["parent_chain"] else None
            )

            results.append({
                "uid": row["uid"],
                "content": row["content"],
                "page_title": row["page_title"],
                "parent_chain": parent_chain,
                "similarity": similarity,
            })

        logger.debug("Vector search returned %d results", len(results))
        return results

    def get_blocks_needing_embedding(self, limit: int = 1000) -> list[dict]:
        """Get blocks that have been stored but not yet embedded.

        Args:
            limit: Maximum number of blocks to return.

        Returns:
            List of block dictionaries.
        """
        cursor = self.conn.execute(
            """
            SELECT uid, content, page_title, parent_chain
            FROM blocks
            WHERE embedded_at IS NULL
            LIMIT ?
            """,
            (limit,),
        )

        blocks = []
        for row in cursor:
            parent_chain = (
                json.loads(row["parent_chain"]) if row["parent_chain"] else None
            )
            blocks.append({
                "uid": row["uid"],
                "content": row["content"],
                "page_title": row["page_title"],
                "parent_chain": parent_chain,
            })

        return blocks

    def drop_all_data(self) -> None:
        """Drop all data from the store (for full resync)."""
        self.conn.execute("DELETE FROM vec_embeddings")
        self.conn.execute("DELETE FROM blocks")
        self.conn.execute("DELETE FROM sync_state")
        self.conn.commit()
        logger.info("All vector store data dropped")


# Singleton instances per graph
_vector_stores: dict[str, VectorStore] = {}


def get_vector_store(graph_name: str) -> VectorStore:
    """Get or create the vector store for a graph.

    Args:
        graph_name: Name of the Roam graph.

    Returns:
        The VectorStore instance for the graph.
    """
    if graph_name not in _vector_stores:
        _vector_stores[graph_name] = VectorStore(graph_name)
    return _vector_stores[graph_name]
