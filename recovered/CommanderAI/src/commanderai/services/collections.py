"""Stored (uploaded) collections in the database."""

from __future__ import annotations

from commanderai.errors import CollectionNotFoundError, EmptyCollectionError, InvalidRequestError
from commanderai.services.collection import parse_source
from commanderai.services.context import ServiceContext
from commanderai.storage import CollectionRepository, StoredCollection


def _repo(ctx: ServiceContext) -> CollectionRepository:
    from commanderai.services.library import database

    return CollectionRepository(database(ctx.settings))


def _stats(content: str) -> tuple[int, int]:
    entries = parse_source(content)
    if not entries:
        raise EmptyCollectionError("No cards found in collection")
    return len(entries), sum(e.quantity for e in entries)


def save_collection(ctx: ServiceContext, name: str, content: str) -> StoredCollection:
    name = name.strip()
    if not name:
        raise InvalidRequestError("Collection name cannot be empty")
    repo = _repo(ctx)
    if repo.get_by_name(name):
        raise InvalidRequestError(f"A collection named '{name}' already exists", name=name)
    entries, copies = _stats(content)
    return repo.add(name, content, entries, copies)


def replace_collection(ctx: ServiceContext, collection_id: int, content: str) -> StoredCollection:
    get_collection(ctx, collection_id)
    entries, copies = _stats(content)
    _repo(ctx).replace_content(collection_id, content, entries, copies)
    return get_collection(ctx, collection_id)


def rename_collection(ctx: ServiceContext, collection_id: int, name: str) -> StoredCollection:
    name = name.strip()
    if not name:
        raise InvalidRequestError("Collection name cannot be empty")
    existing = _repo(ctx).get_by_name(name)
    if existing and existing.id != collection_id:
        raise InvalidRequestError(f"A collection named '{name}' already exists", name=name)
    get_collection(ctx, collection_id)
    _repo(ctx).rename(collection_id, name)
    return get_collection(ctx, collection_id)


def get_collection(ctx: ServiceContext, collection_id: int) -> StoredCollection:
    stored = _repo(ctx).get(collection_id)
    if stored is None:
        raise CollectionNotFoundError(
            f"Collection #{collection_id} not found", id=collection_id, kind="stored"
        )
    return stored


def list_collections(ctx: ServiceContext) -> list[StoredCollection]:
    return _repo(ctx).list()


def delete_collection(ctx: ServiceContext, collection_id: int) -> StoredCollection:
    stored = get_collection(ctx, collection_id)
    _repo(ctx).delete(collection_id)
    return stored
