"""Deterministic Story Graph foundation for the Little Legend director."""
from __future__ import annotations

from collections import deque
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Beat = Literal[
    "opening", "inciting", "ally", "clue", "puzzle", "danger",
    "reversal", "relationship", "revelation", "plan", "climax", "resolution",
]
BEATS: tuple[Beat, ...] = (
    "opening", "inciting", "ally", "clue", "puzzle", "danger",
    "reversal", "relationship", "revelation", "plan", "climax", "resolution",
)
ACTS = ("Начало", "Испытания", "Развязка")
QUESTIONS = (
    "Кто герой и чего он хочет?",
    "Что нарушило привычный мир?",
    "Кто помогает и почему?",
    "Какая улика меняет цель?",
    "Какую загадку нужно решить?",
    "Чем герой рискует?",
    "Что оказалось не таким, как думали?",
    "Как меняются отношения?",
    "Какое открытие объясняет тайну?",
    "Какой план выберет герой?",
    "Что герой должен сделать сам?",
    "Что изменилось и что осталось на будущее?",
)


class SceneNode(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    order: int = Field(ge=1, le=40)
    beat: Beat
    act: int = Field(ge=1, le=3)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=4000)
    goal: str = Field(default="", max_length=1000)
    conflict: str = Field(default="", max_length=1000)
    consequence: str = Field(default="", max_length=1000)
    illustration_prompt: str = Field(default="", max_length=2000)
    locked: bool = False


class StoryEdge(BaseModel):
    source: str
    target: str
    kind: Literal["causes", "choice", "reveal"] = "causes"


class StoryGraph(BaseModel):
    version: int = 1
    nodes: list[SceneNode] = Field(min_length=1, max_length=40)
    edges: list[StoryEdge] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_connections(self) -> StoryGraph:
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("Scene IDs must be unique")
        if sorted(node.order for node in self.nodes) != list(range(1, len(ids) + 1)):
            raise ValueError("Scene order must be contiguous")
        known = set(ids)
        adjacency: dict[str, list[str]] = {key: [] for key in ids}
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError("Edge references unknown scene")
            if edge.source == edge.target:
                raise ValueError("Self-referential story edge")
            adjacency[edge.source].append(edge.target)
        first = min(self.nodes, key=lambda n: n.order).id
        seen = {first}
        queue = deque([first])
        while queue:
            for target in adjacency[queue.popleft()]:
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
        if seen != known:
            raise ValueError("Every scene must be reachable from the opening")
        return self


def build_graph(scenes: list[str]) -> StoryGraph:
    """Turn existing editable scene summaries into a connected linear story graph.

    This is an editable scaffold, not AI-generated prose or branching narrative.
    """
    nodes = [
        SceneNode(
            id=f"scene_{i + 1}", order=i + 1,
            beat=BEATS[min(i * len(BEATS) // len(scenes), len(BEATS) - 1)],
            act=min(3, i * 3 // len(scenes) + 1),
            title=f"Сцена {i + 1}",
            summary=summary.strip(),
            goal=QUESTIONS[min(i * len(QUESTIONS) // len(scenes), len(QUESTIONS) - 1)],
        )
        for i, summary in enumerate(scenes)
    ]
    edges = [
        StoryEdge(source=nodes[i].id, target=nodes[i + 1].id)
        for i in range(len(nodes) - 1)
    ]
    return StoryGraph(nodes=nodes, edges=edges)


def graph_report(graph: StoryGraph) -> dict:
    return {
        "scenes": len(graph.nodes),
        "acts": {ACTS[act - 1]: sum(n.act == act for n in graph.nodes) for act in range(1, 4)},
        "empty_scenes": [node.order for node in graph.nodes if not node.summary],
        "missing_conflicts": [node.order for node in graph.nodes if not node.conflict],
        "locked_scenes": [node.order for node in graph.nodes if node.locked],
        "ready_for_editorial_review": all(node.summary for node in graph.nodes),
    }
