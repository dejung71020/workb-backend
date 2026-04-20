# app/domains/meeting/agenda_service.py
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domains.meeting.models import Agenda, AgendaItem, Meeting
from app.domains.meeting.schemas import (
    AgendaBulkCreateRequest,
    AgendaItemOut,
    AgendaItemPatch,
)


class AgendaService:
    """회의별 아젠다(부모 agendas + 자식 agenda_items) CRUD."""

    @staticmethod
    def bulk_create_items(
        db: Session,
        meeting_id: int,
        created_by: int,
        body: AgendaBulkCreateRequest,
    ) -> tuple[int, list[AgendaItem]]:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).one_or_none()
        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회의를 찾을 수 없습니다.",
            )

        if not body.items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="items 배열이 비어 있습니다.",
            )

        try:
            agenda = (
                db.query(Agenda).filter(Agenda.meeting_id == meeting_id).one_or_none()
            )
            if agenda is None:
                agenda = Agenda(meeting_id=meeting_id, created_by=created_by)
                db.add(agenda)
                db.flush()

            created: list[AgendaItem] = []
            for row in body.items:
                item = AgendaItem(
                    agenda_id=agenda.id,
                    title=row.title,
                    presenter_id=row.presenter_id,
                    estimated_minutes=row.estimated_minutes,
                    reference_url=row.reference_url,
                    order_index=row.order_index,
                )
                db.add(item)
                db.flush()
                created.append(item)

            db.commit()
            for obj in created:
                db.refresh(obj)
            db.refresh(agenda)
            return int(agenda.id), created
        except HTTPException:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _get_item_for_meeting(
        db: Session, meeting_id: int, item_id: int
    ) -> AgendaItem | None:
        return (
            db.query(AgendaItem)
            .join(Agenda, Agenda.id == AgendaItem.agenda_id)
            .filter(AgendaItem.id == item_id, Agenda.meeting_id == meeting_id)
            .one_or_none()
        )

    @staticmethod
    def patch_item(
        db: Session,
        meeting_id: int,
        item_id: int,
        body: AgendaItemPatch,
    ) -> AgendaItem:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).one_or_none()
        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회의를 찾을 수 없습니다.",
            )

        item = AgendaService._get_item_for_meeting(db, meeting_id, item_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="아젠다 항목을 찾을 수 없습니다.",
            )

        patch_data = body.model_dump(exclude_unset=True)
        if not patch_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="수정할 필드가 없습니다.",
            )

        for key, value in patch_data.items():
            setattr(item, key, value)

        try:
            db.commit()
            db.refresh(item)
            return item
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def delete_item(db: Session, meeting_id: int, item_id: int) -> None:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).one_or_none()
        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="회의를 찾을 수 없습니다.",
            )

        item = AgendaService._get_item_for_meeting(db, meeting_id, item_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="아젠다 항목을 찾을 수 없습니다.",
            )

        try:
            db.delete(item)
            db.commit()
        except Exception:
            db.rollback()
            raise


def agenda_item_to_out(row: AgendaItem) -> AgendaItemOut:
    return AgendaItemOut(
        id=int(row.id),
        agenda_id=int(row.agenda_id),
        title=row.title,
        presenter_id=int(row.presenter_id) if row.presenter_id is not None else None,
        estimated_minutes=row.estimated_minutes,
        reference_url=row.reference_url,
        order_index=int(row.order_index),
    )
