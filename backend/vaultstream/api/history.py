"""Watch history endpoints. All require an authenticated user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from vaultstream.api.deps import CurrentUser
from vaultstream.db import get_db
from vaultstream.schemas.history import (
    ProgressAck,
    ProgressUpdate,
    ResumePoint,
    WatchProgressOut,
)
from vaultstream.services import history as history_service

router = APIRouter(prefix="/history", tags=["history"])


@router.post(
    "/progress",
    response_model=ProgressAck,
    summary="Record playback position",
    responses={404: {"description": "No movie with that row_index"}},
)
def record_progress(
    payload: ProgressUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> ProgressAck:
    """Upsert the resume point for a title.

    Called every few seconds by the player, so it stays deliberately cheap and
    is fully idempotent: a repeated ping just overwrites the position.
    """
    try:
        record = history_service.record_progress(
            db,
            user.id,
            payload.row_index,
            payload.position_seconds,
            payload.duration_seconds,
        )
    except history_service.ProgressTooSmall:
        # Not an error the client should react to: acknowledge and store nothing.
        # This is the blocked-autoplay case, which would otherwise create a
        # history row for a title the user never actually watched.
        return ProgressAck(
            row_index=payload.row_index,
            position_seconds=0.0,
            completed=False,
            percent_complete=None,
        )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No movie with row_index {payload.row_index}",
        )
    db.commit()

    return ProgressAck(
        row_index=record.row_index,
        position_seconds=record.position_seconds,
        completed=record.completed,
        percent_complete=history_service.percent_complete(
            record.position_seconds, record.duration_seconds
        ),
    )


@router.get(
    "",
    response_model=list[WatchProgressOut],
    summary="Everything the user has started, most recent first",
)
def list_history(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WatchProgressOut]:
    return history_service.list_history(db, user.id, limit=limit, offset=offset)


@router.get(
    "/continue",
    response_model=list[WatchProgressOut],
    summary="Titles worth resuming",
)
def continue_watching(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[WatchProgressOut]:
    """Unfinished titles with meaningful progress, most recent first."""
    return history_service.list_continue_watching(db, user.id, limit=limit)


@router.get(
    "/resume/{row_index}",
    response_model=ResumePoint,
    summary="Where playback should start for a title",
)
def get_resume_point(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    row_index: Annotated[int, Path(ge=0)],
) -> ResumePoint:
    """Always 200: an untouched title simply resumes from zero."""
    point = history_service.get_resume_point(db, user.id, row_index)
    if point is None:
        return ResumePoint(row_index=row_index, position_seconds=0.0, completed=False)
    return point


@router.delete(
    "/{row_index}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove one title from history",
)
def delete_progress(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    row_index: Annotated[int, Path(ge=0)],
) -> Response:
    """Idempotent: succeeds whether or not the title was in history."""
    history_service.delete_progress(db, user.id, row_index)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the user's entire watch history",
)
def clear_history(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    history_service.clear_history(db, user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
