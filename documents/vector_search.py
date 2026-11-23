import chromadb
from django.conf import settings
from ollama import Client


EMBEDDING_MODEL = "embeddinggemma"
COLLECTION_NAME = "document_pages"
MIN_SIMILARITY = 0.4


class VectorSearchError(Exception):
    """Shown when local semantic search cannot run."""


def _get_collection():
    client = chromadb.PersistentClient(
        path=str(settings.BASE_DIR / ".vector_store")
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _embed(texts):
    try:
        client = Client(host="http://127.0.0.1:11434", timeout=180)
        response = client.embed(model=EMBEDDING_MODEL, input=texts)
        return response.embeddings
    except Exception as problem:
        raise VectorSearchError(
            "Local embedding model nahi mila. Check karo Ollama chal raha "
            "hai aur embeddinggemma installed hai."
        ) from problem


def index_document_pages(document):
    """Save any unindexed, non-empty pages in the local vector store."""
    pages = list(
        document.pages.exclude(text="")
        .only("page_number", "text")
        .order_by("page_number")
    )
    if not pages:
        return 0

    try:
        collection = _get_collection()
        page_ids = [
            f"document-{document.pk}-page-{page.page_number}"
            for page in pages
        ]
        existing = collection.get(ids=page_ids, include=["metadatas"])
        existing_ids = set(existing["ids"])

        new_pages = [
            (page_id, page)
            for page_id, page in zip(page_ids, pages)
            if page_id not in existing_ids
        ]
        if not new_pages:
            return 0

        ids = [page_id for page_id, _ in new_pages]
        texts = [page.text for _, page in new_pages]
        embeddings = _embed(texts)
        metadatas = [
            {
                "owner_id": str(document.owner_id),
                "document_id": str(document.pk),
                "page_number": page.page_number,
            }
            for _, page in new_pages
        ]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        return len(new_pages)
    except VectorSearchError:
        raise
    except Exception as problem:
        raise VectorSearchError(
            "PDF pages ko local vector store mein save nahi kar paaye."
        ) from problem

def delete_document_vectors(document):
    """Remove this document's pages from the local vector store."""
    try:
        collection = _get_collection()
        filters = {
            "$and": [
                {"owner_id": {"$eq": str(document.owner_id)}},
                {"document_id": {"$eq": str(document.pk)}},
            ]
        }
        collection.delete(where=filters)
    except Exception as problem:
        raise VectorSearchError(
            "PDF ke search vectors delete nahi kar paaye."
        ) from problem

def search_document_pages(document, question, limit=3):
    """Find the closest pages for a question, only within this user's PDF."""
    try:
        index_document_pages(document)
        collection = _get_collection()

        filters = {
            "$and": [
                {"owner_id": {"$eq": str(document.owner_id)}},
                {"document_id": {"$eq": str(document.pk)}},
            ]
        }
        stored_pages = collection.get(
            where=filters,
            include=["metadatas"],
        )
        page_count = len(stored_pages["ids"])
        if not page_count:
            return []

        question_embedding = _embed([question])[0]
        matches = collection.query(
            query_embeddings=[question_embedding],
            where=filters,
            n_results=min(limit, page_count),
            include=["documents", "metadatas", "distances"],
        )

        results = []
        for text, metadata, distance in zip(
            matches["documents"][0],
            matches["metadatas"][0],
            matches["distances"][0],
        ):
            snippets = [
                line.strip()
                for line in text.splitlines()
                if line.strip()
            ][:6]

            similarity = 1 - distance
            if similarity < MIN_SIMILARITY:
                continue

            results.append(
                {
                    "page_number": metadata["page_number"],
                    "snippets": snippets or [text[:1000]],
                    "context": text[:6000],
                    "score": similarity,
                }
            )

        return results
    except VectorSearchError:
        raise
    except Exception as problem:
        raise VectorSearchError(
            "Local semantic search nahi chal paaya."
        ) from problem