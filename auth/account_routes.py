"""What a signed-in person keeps under their account.

    GET/POST        /auth/me/projects
    GET/PUT/DELETE  /auth/me/projects/{id}
    GET/POST        /auth/me/projects/{id}/experiments
    PUT/DELETE      /auth/me/projects/{id}/experiments/{record_id}
    GET/PUT         /auth/me/learning-progress        { completed: [moduleId] }
    GET             /auth/me/lab-sessions             the full LabSession documents
    PUT/DELETE      /auth/me/lab-sessions/{id}

Shapes match ``lib/api-client.ts`` and ``docs/engineering-lab-simulation.md``
in jumetra-frontend. The owner always comes from the session, never the body.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from database.models import LabSessionRecord, UserProfile, UserProject, UserProjectExperiment

from .routes import current_user_id

router = APIRouter(prefix="/auth/me", tags=["account"])

LAB_SESSION_LIMIT_BYTES = 700_000
CATEGORIES = ("mobile_robot", "robotic_arm", "drone", "iot", "automation", "education", "research", "other")


def _factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.db_factory


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class Teammate(BaseModel):
    id: str = Field(max_length=64)
    display_name: str = Field(max_length=200)
    email: str = Field(max_length=255)


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    objectives: str = Field(default="", max_length=4000)
    contributors: str = Field(default="", max_length=2000)
    category: str = Field(default="other", max_length=64)
    hardware: list[str] = Field(default_factory=list, max_length=100)
    teammates: list[Teammate] = Field(default_factory=list, max_length=50)


class ExperimentInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(default="", max_length=4000)
    hardware: list[str] = Field(default_factory=list, max_length=100)
    procedure: str = Field(default="", max_length=8000)
    observations: str = Field(default="", max_length=8000)
    results: str = Field(default="", max_length=8000)
    notes: str = Field(default="", max_length=8000)


class LearningProgressInput(BaseModel):
    completed: list[str] = Field(default_factory=list, max_length=500)


def _project_payload(row: UserProject) -> dict[str, Any]:
    return {
        "id": row.id,
        "owner_id": row.owner_id,
        "name": row.name,
        "description": row.description,
        "objectives": row.objectives,
        "contributors": row.contributors,
        "category": row.category,
        "hardware": list(row.hardware or []),
        "teammates": list(row.teammates or []),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _experiment_payload(row: UserProjectExperiment) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "title": row.title,
        "objective": row.objective,
        "hardware": list(row.hardware or []),
        "procedure": row.procedure,
        "observations": row.observations,
        "results": row.results,
        "notes": row.notes,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _own_project(session: Session, owner_id: str, project_id: str) -> UserProject:
    row = session.get(UserProject, project_id)
    if row is None or row.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="That project doesn't exist.")
    return row


# ----- projects -----


@router.get("/projects")
def list_projects(request: Request, user_id: str = Depends(current_user_id)) -> list[dict[str, Any]]:
    with _factory(request)() as session:
        rows = session.scalars(select(UserProject).where(UserProject.owner_id == user_id).order_by(UserProject.updated_at.desc())).all()
        return [_project_payload(r) for r in rows]


@router.post("/projects", status_code=201)
def create_project(body: ProjectInput, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    with _factory(request)() as session:
        row = UserProject(owner_id=user_id, **body.model_dump())
        row.teammates = [t.model_dump() for t in body.teammates]
        session.add(row)
        session.commit()
        session.refresh(row)
        return _project_payload(row)


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    with _factory(request)() as session:
        return _project_payload(_own_project(session, user_id, project_id))


@router.put("/projects/{project_id}")
def update_project(project_id: str, body: ProjectInput, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    with _factory(request)() as session:
        row = _own_project(session, user_id, project_id)
        for name, value in body.model_dump().items():
            setattr(row, name, value)
        row.teammates = [t.model_dump() for t in body.teammates]
        session.commit()
        session.refresh(row)
        return _project_payload(row)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, bool]:
    with _factory(request)() as session:
        row = _own_project(session, user_id, project_id)
        for exp in session.scalars(select(UserProjectExperiment).where(UserProjectExperiment.project_id == row.id)):
            session.delete(exp)
        session.delete(row)
        session.commit()
    return {"deleted": True}


# ----- experiments -----


@router.get("/projects/{project_id}/experiments")
def list_experiments(project_id: str, request: Request, user_id: str = Depends(current_user_id)) -> list[dict[str, Any]]:
    with _factory(request)() as session:
        project = _own_project(session, user_id, project_id)
        rows = session.scalars(
            select(UserProjectExperiment).where(UserProjectExperiment.project_id == project.id).order_by(UserProjectExperiment.created_at)
        ).all()
        return [_experiment_payload(r) for r in rows]


@router.post("/projects/{project_id}/experiments", status_code=201)
def create_experiment(project_id: str, body: ExperimentInput, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    with _factory(request)() as session:
        project = _own_project(session, user_id, project_id)
        row = UserProjectExperiment(project_id=project.id, **body.model_dump())
        session.add(row)
        session.commit()
        session.refresh(row)
        return _experiment_payload(row)


def _own_experiment(session: Session, user_id: str, project_id: str, record_id: str) -> UserProjectExperiment:
    project = _own_project(session, user_id, project_id)
    row = session.get(UserProjectExperiment, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="That experiment record doesn't exist.")
    return row


@router.put("/projects/{project_id}/experiments/{record_id}")
def update_experiment(
    project_id: str, record_id: str, body: ExperimentInput, request: Request, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    with _factory(request)() as session:
        row = _own_experiment(session, user_id, project_id, record_id)
        for name, value in body.model_dump().items():
            setattr(row, name, value)
        session.commit()
        session.refresh(row)
        return _experiment_payload(row)


@router.delete("/projects/{project_id}/experiments/{record_id}")
def delete_experiment(project_id: str, record_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, bool]:
    with _factory(request)() as session:
        row = _own_experiment(session, user_id, project_id, record_id)
        session.delete(row)
        session.commit()
    return {"deleted": True}


# ----- learning progress -----


def _profile(session: Session, user_id: str) -> UserProfile:
    profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        profile = UserProfile(user_id=user_id)
        session.add(profile)
        session.flush()
    return profile


@router.get("/learning-progress")
def get_learning_progress(request: Request, user_id: str = Depends(current_user_id)) -> dict[str, list[str]]:
    with _factory(request)() as session:
        return {"completed": list(_profile(session, user_id).learning_progress or [])}


@router.put("/learning-progress")
def put_learning_progress(body: LearningProgressInput, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, list[str]]:
    completed = sorted({m.strip() for m in body.completed if m and m.strip()})
    with _factory(request)() as session:
        profile = _profile(session, user_id)
        profile.learning_progress = completed
        session.commit()
        return {"completed": completed}


# ----- lab sessions -----


def _lab_session_doc(body: dict[str, Any], session_id: str) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="A lab session must be a JSON object.")
    if body.get("id") not in (None, session_id):
        raise HTTPException(status_code=422, detail="The session id in the URL and the body don't match.")
    body["id"] = session_id
    size = len(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    if size > LAB_SESSION_LIMIT_BYTES:
        raise HTTPException(status_code=413, detail="This lab session is too large to save. Clear its log and try again.")
    return body


@router.get("/lab-sessions")
def list_lab_sessions(request: Request, user_id: str = Depends(current_user_id)) -> list[dict[str, Any]]:
    with _factory(request)() as session:
        rows = session.scalars(select(LabSessionRecord).where(LabSessionRecord.owner_id == user_id).order_by(LabSessionRecord.updated_at.desc())).all()
        return [dict(r.document) for r in rows]


@router.put("/lab-sessions/{session_id}")
async def put_lab_session(session_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    if len(session_id) > 64:
        raise HTTPException(status_code=422, detail="That session id is too long.")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="A lab session must be JSON.") from exc
    doc = _lab_session_doc(body, session_id)
    client_updated = str(doc.get("updatedAt") or "") or None
    with _factory(request)() as session:
        row = session.get(LabSessionRecord, (session_id, user_id))
        if row is None:
            row = LabSessionRecord(id=session_id, owner_id=user_id, document=doc, name=str(doc.get("name") or ""), client_updated_at=client_updated)
            session.add(row)
        else:
            # A newer server copy wins over an older client copy.
            if row.client_updated_at and client_updated and client_updated < row.client_updated_at:
                return dict(row.document)
            row.document = doc
            row.name = str(doc.get("name") or "")
            row.client_updated_at = client_updated
        session.commit()
        return doc


@router.delete("/lab-sessions/{session_id}")
def delete_lab_session(session_id: str, request: Request, user_id: str = Depends(current_user_id)) -> dict[str, bool]:
    with _factory(request)() as session:
        row = session.get(LabSessionRecord, (session_id, user_id))
        if row is not None:
            session.delete(row)
            session.commit()
    return {"deleted": True}
