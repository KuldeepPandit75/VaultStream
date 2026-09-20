"""People and collection endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from vaultstream.db import get_db
from vaultstream.schemas.catalog import MovieSummary
from vaultstream.schemas.people import CollectionDetail, PersonDetail
from vaultstream.services import people as people_service

router = APIRouter(tags=["people"])


@router.get(
    "/people/{person_id}",
    response_model=PersonDetail,
    summary="A person and their filmography",
    responses={404: {"description": "No such person"}},
)
def get_person(
    db: Annotated[Session, Depends(get_db)],
    person_id: Annotated[int, Path(ge=0)],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> PersonDetail:
    person = people_service.get_person(db, person_id, limit=limit)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No person with id {person_id}",
        )
    return person


@router.get(
    "/collections/{collection_id}",
    response_model=CollectionDetail,
    summary="A franchise and its titles in release order",
    responses={404: {"description": "No such collection"}},
)
def get_collection(
    db: Annotated[Session, Depends(get_db)],
    collection_id: Annotated[int, Path(ge=0)],
) -> CollectionDetail:
    collection = people_service.get_collection(db, collection_id)
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No collection with id {collection_id}",
        )
    return collection


@router.get(
    "/movies/{row_index}/collection",
    response_model=list[MovieSummary],
    summary="Other titles in the same franchise",
)
def get_collection_siblings(
    db: Annotated[Session, Depends(get_db)],
    row_index: Annotated[int, Path(ge=0)],
) -> list[MovieSummary]:
    """Empty list when the title belongs to no collection."""
    return people_service.list_collection_siblings(db, row_index)
