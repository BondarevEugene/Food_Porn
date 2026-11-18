"""Editorial diagnostics for coherent, child-friendly stories.

Heuristics deliberately do not claim to replace a human editor or AI review.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.little_legend.story_graph import StoryGraph


class EditorialIssue(BaseModel):
    code: str
    severity: str
    scene_id: str | None = None
    message: str
    suggestion: str


class EditorialReport(BaseModel):
    score: int = Field(ge=0, le=100)
    issues: list[EditorialIssue]
    scenes: int
    publishable: bool = False


def audit_story(graph: StoryGraph) -> EditorialReport:
    """Check scene completeness, causality and narrative progression."""
    issues: list[EditorialIssue] = []
    ordered = sorted(graph.nodes, key=lambda node: node.order)
    for node in ordered:
        if not node.summary.strip():
            issues.append(EditorialIssue(
                code="missing_scene", severity="error", scene_id=node.id,
                message="Сцена не описана",
                suggestion="Опишите событие и то, как оно меняет ситуацию героя.",
            ))
        if not node.conflict.strip():
            issues.append(EditorialIssue(
                code="missing_conflict", severity="warning", scene_id=node.id,
                message="Не указано препятствие",
                suggestion="Что мешает герою получить желаемое?",
            ))
        if not node.consequence.strip():
            issues.append(EditorialIssue(
                code="missing_consequence", severity="warning", scene_id=node.id,
                message="Не указано последствие",
                suggestion="Что изменится после этой сцены?",
            ))
    if len(ordered) >= 6:
        acts = {node.act for node in ordered}
        if acts != {1, 2, 3}:
            issues.append(EditorialIssue(
                code="missing_act", severity="warning",
                message="Не все три акта представлены",
                suggestion="Добавьте начало, испытания и развязку.",
            ))
    links = {(edge.source, edge.target) for edge in graph.edges}
    for first, second in zip(ordered, ordered[1:]):
        if (first.id, second.id) not in links:
            issues.append(EditorialIssue(
                code="missing_direct_link", severity="info", scene_id=second.id,
                message="Нет прямой связи с предыдущей сценой",
                suggestion="Проверьте переход между событиями и ветвления.",
            ))
    penalty = sum(
        {"error": 8, "warning": 3, "info": 1}[issue.severity]
        for issue in issues
    )
    return EditorialReport(
        score=max(0, 100 - penalty),
        issues=issues,
        scenes=len(ordered),
        publishable=False,
    )
