"""
memory/vector_store.py — Cold Memory (ChromaDB)

When conversations get too long, compressor.py summarizes them.
But we also save those ancient messages into a Vector DB so they can be
semantically searched later.
"""
import logging
import chromadb
import uuid
import os

logger = logging.getLogger(__name__)

# Initialize ChromaDB persistent client
# We mount /app/data so this survives container restarts
_client_path = "/app/data/chroma"

# If we are running locally (outside Docker) during dev, use a local folder
if not os.path.exists("/app"):
    _client_path = "./data/chroma"

try:
    _chroma_client = chromadb.PersistentClient(path=_client_path)
    logger.info("ChromaDB initialized")
except Exception as e:
    logger.warning(f"Failed to initialize ChromaDB: {e}")
    _chroma_client = None

def _get_collection(session_id: str):
    if not _chroma_client:
        return None
    # We use one collection per session for simplicity and isolation
    # ChromaDB collection names must be valid (no special chars)
    safe_session_id = "".join([c if c.isalnum() else "_" for c in session_id])
    if len(safe_session_id) < 3:
        safe_session_id = safe_session_id.ljust(3, "0")
        
    try:
        return _chroma_client.get_or_create_collection(name=f"session_{safe_session_id}")
    except Exception as e:
        logger.error(f"Error getting collection for {session_id}: {e}")
        return None

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Splits a long text into smaller overlapping chunks for better retrieval."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += (chunk_size - overlap)
    return chunks

async def save_to_cold_memory(session_id: str, messages: list[dict]):
    """
    Saves a list of raw messages into the vector database.
    Each message is embedded so it can be searched later.
    """
    collection = _get_collection(session_id)
    if not collection:
        return

    documents = []
    metadatas = []
    ids = []

    for msg in messages:
        # We only care about user and assistant messages that have actual content
        if not msg.get("content") or msg.get("role") not in ["user", "assistant"]:
            continue
            
        content_chunks = chunk_text(msg['content'])
        
        for i, chunk in enumerate(content_chunks):
            doc = f"{msg['role'].upper()}: {chunk}"
            documents.append(doc)
            metadatas.append({"role": msg['role'], "chunk": i})
            ids.append(uuid.uuid4().hex)

    if not documents:
        return

    try:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        logger.info(
            "Cold memory saved", 
            extra={"session_id": session_id, "messages_embedded": len(documents)}
        )
    except Exception as e:
        logger.error(f"Failed to save cold memory: {e}")


async def recall_from_cold_memory(session_id: str, query: str, k: int = 5) -> str:
    """
    Searches the vector database for the top K messages relevant to the query.
    Returns a formatted string of those memories, or empty string if none.
    """
    collection = _get_collection(session_id)
    if not collection:
        return ""

    try:
        # We need to make sure the collection actually has items before querying
        if collection.count() == 0:
            return ""

        results = collection.query(
            query_texts=[query],
            n_results=min(k, collection.count())
        )
        
        if not results or not results['documents'] or not results['documents'][0]:
            return ""
            
        docs = results['documents'][0]
        
        memory_block = "\n".join(docs)
        
        logger.info(
            "Cold memory recalled",
            extra={"session_id": session_id, "memories_found": len(docs)}
        )
        
        return memory_block

    except Exception as e:
        logger.error(f"Failed to recall cold memory: {e}")
        return ""
