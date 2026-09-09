"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analytics, auth, businesses, datasets
from app.db import Base, engine

# The schema is created on import for local/dev use; a deployed environment
# should run migrations instead.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Business Intelligence & Analysis Copilot",
    version="0.1.0",
    description=(
        "Analytics engine calculates, evidence supports, AI interprets. "
        "See docs/PRD.md and docs/PROCESS.md."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(businesses.router)
app.include_router(datasets.router)
app.include_router(analytics.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/concepts", tags=["meta"])
def list_concepts() -> list[dict]:
    """The canonical vocabulary, for the mapping-confirmation UI."""
    from app.semantic.concepts import CONCEPTS

    return [
        {
            "name": c.name,
            "label": c.label,
            "role": c.role.value,
            "description": c.description,
            "synonyms": list(c.synonyms[:6]),
        }
        for c in CONCEPTS.values()
    ]
