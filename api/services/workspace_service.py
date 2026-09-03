"""Research workspace service — projects, datasets, reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Organization, PlatformExperiment, Project
from .data_service import DataService


class WorkspaceService:
    """Aggregate workspace data from platform DB and experiment exports."""

    def __init__(
        self,
        db_factory: sessionmaker[Session],
        data_service: DataService,
        data_dir: Path | str,
    ) -> None:
        self._db_factory = db_factory
        self._data_service = data_service
        self._data_dir = Path(data_dir)

    def list_projects(self) -> list[dict[str, Any]]:
        with self._db_factory() as session:
            projects = session.scalars(select(Project).order_by(Project.created_at.desc())).all()
            return [self._project_summary(session, p) for p in projects]

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self._db_factory() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise KeyError(f"project not found: {project_id}")
            return self._project_detail(session, project)

    def _project_summary(self, session: Session, project: Project) -> dict[str, Any]:
        experiments = session.scalars(
            select(PlatformExperiment).where(PlatformExperiment.project_id == project.id)
        ).all()
        org = session.get(Organization, project.organization_id)
        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "organization": org.name if org else "",
            "experiment_count": len(experiments),
            "created_at": project.created_at.isoformat() if project.created_at else None,
        }

    def _project_detail(self, session: Session, project: Project) -> dict[str, Any]:
        summary = self._project_summary(session, project)
        experiments = session.scalars(
            select(PlatformExperiment).where(PlatformExperiment.project_id == project.id)
        ).all()

        experiment_rows = []
        for exp in experiments:
            row: dict[str, Any] = {
                "id": exp.id,
                "name": exp.name,
                "external_id": exp.external_id,
                "strategy": exp.strategy,
                "status": exp.status,
            }
            if exp.external_id:
                try:
                    detail = self._data_service.get_experiment(exp.external_id)
                    row["average_sync_error"] = detail.report.get("average_sync_error", 0.0)
                except FileNotFoundError:
                    row["average_sync_error"] = None
            experiment_rows.append(row)

        datasets = self._list_datasets(experiments)
        reports = self._list_reports(experiments)

        return {
            **summary,
            "experiments": experiment_rows,
            "datasets": datasets,
            "reports": reports,
        }

    def _list_datasets(self, experiments: list[PlatformExperiment]) -> list[dict[str, Any]]:
        datasets: list[dict[str, Any]] = []
        for exp in experiments:
            if not exp.external_id:
                continue
            exp_dir = self._data_dir / "experiments" / exp.external_id
            if not exp_dir.exists():
                continue
            for path in sorted(exp_dir.glob("*.jsonl")):
                datasets.append(
                    {
                        "name": path.name,
                        "experiment_id": exp.external_id,
                        "experiment_name": exp.name,
                        "path": str(path.relative_to(self._data_dir)),
                        "type": "jsonl",
                    }
                )
            summary = exp_dir / "summary.json"
            if summary.exists():
                datasets.append(
                    {
                        "name": "summary.json",
                        "experiment_id": exp.external_id,
                        "experiment_name": exp.name,
                        "path": str(summary.relative_to(self._data_dir)),
                        "type": "json",
                    }
                )
        return datasets

    def _list_reports(self, experiments: list[PlatformExperiment]) -> list[dict[str, Any]]:
        reports: list[dict[str, Any]] = []
        for exp in experiments:
            if not exp.external_id:
                continue
            try:
                _, report = self._data_service.analyze_experiment(exp.external_id)
                reports.append(
                    {
                        "experiment_id": exp.external_id,
                        "experiment_name": exp.name,
                        "strategy": exp.strategy,
                        "title": f"Research Report — {exp.name}",
                        "average_sync_error": report.get("average_sync_error"),
                        "correction_success_rate": report.get("correction_success_rate"),
                    }
                )
            except FileNotFoundError:
                continue
        return reports
