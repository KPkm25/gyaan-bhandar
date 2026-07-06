"""
Custom Prometheus metrics for the RAG pipeline itself, on top of the
HTTP-level metrics that prometheus_flask_exporter already gives you for free.

Usage in app.py, inside the /ask (or /query) route:

    from metrics import (
        rag_queries_total, failed_queries_total,
        retrieval_latency_seconds, llm_latency_seconds,
    )

    with retrieval_latency_seconds.time():
        retrieved, confidence = search_docs(user_query, k=3)

    rag_queries_total.inc()
    ...
    if something_went_wrong:
        failed_queries_total.inc()
"""
from prometheus_client import Counter, Histogram

rag_queries_total = Counter(
    "rag_queries_total",
    "Total number of RAG queries received",
)

failed_queries_total = Counter(
    "failed_queries_total",
    "Total number of RAG queries that failed or returned an error",
    ["reason"],  # e.g. "empty_query", "no_documents", "llm_error"
)

low_confidence_total = Counter(
    "low_confidence_total",
    "Total number of queries where retrieval confidence was below threshold",
)

retrieval_latency_seconds = Histogram(
    "retrieval_latency_seconds",
    "Time spent retrieving chunks from FAISS",
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "Time spent waiting on the Groq LLM call",
)

total_query_latency_seconds = Histogram(
    "total_query_latency_seconds",
    "End-to-end time for a /ask (or /query) request",
)