"""Little Legend: owner-scoped story drafts inside the existing Food_Porn app."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
    select,
    update,
)

from app.database.session import async_session_maker, engine
from app.little_legend.blueprint import (
    BookBlueprint,
    print_preflight,
    quick_blueprint,
    visual_consistency_check,
)
from app.little_legend.character_identity import (
    IdentityBible,
    identity_review,
    quick_identity_bible,
)
from app.little_legend.consent import (
    PHOTO_NOTICE,
    TERMS,
    ConsentDecision,
    ConsentRecord,
    consent_status,
    record_decision,
    withdraw_photo_consent,
)
from app.little_legend.editorial import audit_story
from app.little_legend.editorial_review import EditorialDecision, editorial_preflight
from app.little_legend.hero_contract import (
    audit_hero_presence,
    contract_from_blueprint,
    hero_writing_brief,
    scene_directives,
)
from app.little_legend.manuscript_repository import (
    ChapterApproval,
    ChapterEdit,
    approve_chapter,
    edit_chapter,
    mutate_owned_manuscript,
    upsert_generated_chapter,
)
from app.little_legend.narrative_design import StoryDesign, design_guidance
from app.little_legend.portrait_studio import PortraitPlan, portrait_preflight
from app.little_legend.print_renderer import render_print_proof
from app.little_legend.privacy_lifecycle import (
    PrivacyLaunchConfig,
    photo_launch_preflight,
    reset_photo_approvals,
)
from app.little_legend.secure_vault import upload_capability
from app.little_legend.story_graph import StoryGraph, build_graph, graph_report
from app.little_legend.story_writer import (
    ChapterDraft,
    StoryManuscript,
    manuscript_review,
)
from app.little_legend.vault_registry import vault_summary
from app.miniapp.auth import current_user

router = APIRouter(prefix="/little-legend", tags=["little-legend"])
metadata = MetaData()
stories = Table(
    "little_legend_stories", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("owner_id", BigInteger, nullable=False, index=True),
    Column("title", String(180), nullable=False),
    Column("hero", String(100), nullable=False),
    Column("data", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

DEFAULT_SCENES = [
    "Знакомство с героем", "Необычное событие", "Первый союзник",
    "Тайное послание", "Первая загадка", "Опасная находка",
    "Неожиданный поворот", "Испытание дружбы", "Разгадка тайны",
    "План спасения", "Главное испытание", "Развязка и новая тайна",
]


class StoryDraft(BaseModel):
    title: str = Field(default="Новая история", min_length=1, max_length=180)
    hero: str = Field(default="Оля", min_length=1, max_length=100)
    genre: str = Field(default="Научная фантастика", max_length=100)
    setup: str = Field(default="", max_length=4000)
    mystery: str = Field(default="", max_length=4000)
    ending: str = Field(default="", max_length=4000)
    habits: str = Field(default="", max_length=2000)
    phrases: str = Field(default="", max_length=2000)
    dedication: str = Field(default="", max_length=1000)
    city: str = Field(default="", max_length=100)
    scenes: list[str] = Field(default_factory=lambda: list(DEFAULT_SCENES), min_length=1, max_length=40)
    graph: StoryGraph | None = None
    blueprint: BookBlueprint | None = None
    design: StoryDesign = Field(default_factory=StoryDesign)
    identity_bible: IdentityBible | None = None
    consent: ConsentRecord = Field(default_factory=ConsentRecord)
    portrait_plan: PortraitPlan = Field(default_factory=PortraitPlan)
    manuscript: StoryManuscript | None = None
    writer_job_ids: dict[str, str] = Field(default_factory=dict)
    editorial_decision: EditorialDecision = Field(default_factory=EditorialDecision)


async def initialize_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: metadata.create_all(sync, checkfirst=True))


def _owner(user: Annotated[dict, Depends(current_user)]) -> int:
    return int(user["id"])


@router.get("/api/stories")
async def list_stories(owner: Annotated[int, Depends(_owner)]):
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(stories.c.id, stories.c.title, stories.c.hero, stories.c.updated_at)
            .where(stories.c.owner_id == owner).order_by(stories.c.id.desc()).limit(100)
        )).mappings().all()
    return [dict(row) for row in rows]


@router.post("/api/stories", status_code=201)
async def create_story(draft: StoryDraft, owner: Annotated[int, Depends(_owner)]):
    now = datetime.now(UTC)
    async with async_session_maker() as session:
        result = await session.execute(insert(stories).values(
            owner_id=owner, title=draft.title, hero=draft.hero,
            data=draft.model_dump_json(), updated_at=now
        ).returning(stories.c.id))
        story_id = result.scalar_one()
        await session.commit()
    return {"id": story_id}


@router.get("/api/stories/{story_id}")
async def read_story(story_id: int, owner: Annotated[int, Depends(_owner)]):
    async with async_session_maker() as session:
        row = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner
        ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Story not found")
    return json.loads(row)


@router.put("/api/stories/{story_id}")
async def save_story(story_id: int, draft: StoryDraft, owner: Annotated[int, Depends(_owner)]):
    async with async_session_maker() as session:
        current = (await session.execute(
            select(stories.c.data).where(
                stories.c.id == story_id, stories.c.owner_id == owner
            ).with_for_update()
        )).scalar_one_or_none()
        if current is None:
            raise HTTPException(404, "Story not found")
        previous = StoryDraft.model_validate_json(current)
        # Older clients submit only basic fields. Preserve independent graph
        # and character settings rather than silently deleting their work.
        if "graph" not in draft.model_fields_set:
            draft.graph = previous.graph
            if draft.graph is not None:
                ordered = sorted(draft.graph.nodes, key=lambda node: node.order)
                if draft.scenes != previous.scenes:
                    for node, summary in zip(ordered, draft.scenes, strict=False):
                        node.summary = summary
        if "blueprint" not in draft.model_fields_set:
            draft.blueprint = previous.blueprint
        if "design" not in draft.model_fields_set:
            draft.design = previous.design
        if "identity_bible" not in draft.model_fields_set:
            draft.identity_bible = previous.identity_bible
        if previous.manuscript is not None and draft.hero != previous.hero:
            raise HTTPException(409, "Cannot change the hero of an existing manuscript")
        if "writer_job_ids" not in draft.model_fields_set:
            draft.writer_job_ids = previous.writer_job_ids
        elif draft.writer_job_ids != previous.writer_job_ids:
            raise HTTPException(409, "Writer checkpoints are managed internally")
        if "editorial_decision" not in draft.model_fields_set:
            draft.editorial_decision = previous.editorial_decision
        elif draft.editorial_decision != previous.editorial_decision:
            raise HTTPException(409, "Use the editorial review endpoint")
        if "manuscript" not in draft.model_fields_set:
            draft.manuscript = previous.manuscript
        elif draft.manuscript != previous.manuscript:
            raise HTTPException(409, "Use chapter editor to modify the manuscript")
        # Consent is never overwritten by a generic story editor payload.
        draft.consent = previous.consent
        if "portrait_plan" not in draft.model_fields_set:
            draft.portrait_plan = previous.portrait_plan
        result = await session.execute(update(stories).where(
            stories.c.id == story_id, stories.c.owner_id == owner
        ).values(title=draft.title, hero=draft.hero, data=draft.model_dump_json(),
                 updated_at=datetime.now(UTC)))
        await session.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Story not found")
    return {"saved": True}


@router.delete("/api/stories/{story_id}")
async def remove_story(story_id: int, owner: Annotated[int, Depends(_owner)]):
    async with async_session_maker() as session:
        result = await session.execute(delete(stories).where(
            stories.c.id == story_id, stories.c.owner_id == owner
        ))
        await session.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Story not found")
    return {"deleted": True}





async def _owned_draft(story_id: int, owner: int) -> StoryDraft:
    async with async_session_maker() as session:
        raw = (await session.execute(
            select(stories.c.data).where(
                stories.c.id == story_id, stories.c.owner_id == owner
            )
        )).scalar_one_or_none()
    if raw is None:
        raise HTTPException(404, "Story not found")
    return StoryDraft.model_validate_json(raw)




@router.get("/api/stories/{story_id}/hero-contract")
async def read_hero_contract(
    story_id: int, owner: Annotated[int, Depends(_owner)],
):
    """Owner-scoped canonical hero facts and scene-writing directives."""
    draft = await _owned_draft(story_id, owner)
    blueprint = draft.blueprint or quick_blueprint(draft.hero)
    hero_profile = next(
        (item for item in blueprint.characters if item.role == "hero"), None
    )
    if hero_profile is None or hero_profile.name != draft.hero:
        raise HTTPException(422, "Hero profile must match story hero")
    # Older story forms stored habits and phrases outside the blueprint.
    # Preserve these user-authored facts without overwriting richer settings.
    blueprint = blueprint.model_copy(deep=True)
    hero_profile = next(item for item in blueprint.characters if item.role == "hero")
    if not hero_profile.mannerisms.strip() and draft.habits.strip():
        hero_profile.mannerisms = draft.habits
    if not hero_profile.favorite_phrases.strip() and draft.phrases.strip():
        hero_profile.favorite_phrases = draft.phrases
    contract = contract_from_blueprint(blueprint, draft.hero)
    graph = draft.graph or build_graph(draft.scenes)
    return {
        "contract": contract.model_dump(mode="json"),
        "writing_brief": hero_writing_brief(contract, blueprint),
        "scene_directives": scene_directives(contract, graph),
        "audit": audit_hero_presence(contract, {}, graph),
        "ai_generated": False,
    }





@router.get("/api/stories/{story_id}/editorial-review")
async def read_editorial_review(
    story_id: int, owner: Annotated[int, Depends(_owner)],
):
    draft = await _owned_draft(story_id, owner)
    if draft.manuscript is None:
        raise HTTPException(409, "Manuscript is not created")
    blueprint = draft.blueprint or quick_blueprint(draft.hero)
    try:
        contract = contract_from_blueprint(blueprint, draft.hero)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    graph = draft.graph or build_graph(draft.scenes)
    return editorial_preflight(
        draft.manuscript, graph, contract, draft.editorial_decision,
    )


@router.put("/api/stories/{story_id}/editorial-review")
async def save_editorial_review(
    story_id: int, decision: EditorialDecision,
    owner: Annotated[int, Depends(_owner)],
):
    def transform(manuscript, draft):
        if not manuscript.chapters:
            raise ValueError("Write the manuscript before editorial review")
        draft.editorial_decision = decision
        return manuscript

    await mutate_owned_manuscript(
        story_id=story_id, owner_id=owner, transform=transform,
    )
    return await read_editorial_review(story_id, owner)

@router.get("/api/stories/{story_id}/manuscript")
async def read_manuscript(
    story_id: int, owner: Annotated[int, Depends(_owner)],
):
    draft = await _owned_draft(story_id, owner)
    manuscript = draft.manuscript or StoryManuscript(hero_name=draft.hero)
    graph = draft.graph or build_graph(draft.scenes)
    return {
        "manuscript": manuscript.model_dump(mode="json"),
        "review": manuscript_review(manuscript, graph),
    }




@router.post("/api/stories/{story_id}/manuscript/{scene_id}/draft")
async def create_manuscript_chapter_draft(
    story_id: int, scene_id: str, edit: ChapterEdit,
    owner: Annotated[int, Depends(_owner)],
):
    """Create an initial chapter; later edits use the revision-safe PUT."""
    def transform(manuscript, draft):
        graph = draft.graph or build_graph(draft.scenes)
        if scene_id not in {node.id for node in graph.nodes}:
            raise ValueError("Unknown story scene")
        if any(chapter.scene_id == scene_id for chapter in manuscript.chapters):
            raise PermissionError("Chapter already exists; use the chapter editor")
        return upsert_generated_chapter(
            manuscript, ChapterDraft(scene_id=scene_id, text=edit.text, notes=edit.notes),
        )

    manuscript = await mutate_owned_manuscript(
        story_id=story_id, owner_id=owner, transform=transform,
    )
    return {"saved": True, "manuscript": manuscript.model_dump(mode="json")}

@router.put("/api/stories/{story_id}/manuscript/{scene_id}")
async def edit_manuscript_chapter(
    story_id: int, scene_id: str, edit: ChapterEdit,
    owner: Annotated[int, Depends(_owner)],
):
    def transform(manuscript, draft):
        graph = draft.graph or build_graph(draft.scenes)
        if scene_id not in {node.id for node in graph.nodes}:
            raise ValueError("Unknown story scene")
        return edit_chapter(manuscript, scene_id, edit)

    manuscript = await mutate_owned_manuscript(
        story_id=story_id, owner_id=owner, transform=transform,
    )
    return {"saved": True, "manuscript": manuscript.model_dump(mode="json")}


@router.post("/api/stories/{story_id}/manuscript/{scene_id}/approval")
async def set_manuscript_chapter_approval(
    story_id: int, scene_id: str, decision: ChapterApproval,
    owner: Annotated[int, Depends(_owner)],
):
    def transform(manuscript, draft):
        graph = draft.graph or build_graph(draft.scenes)
        if scene_id not in {node.id for node in graph.nodes}:
            raise ValueError("Unknown story scene")
        return approve_chapter(manuscript, scene_id, decision.approved)

    manuscript = await mutate_owned_manuscript(
        story_id=story_id, owner_id=owner, transform=transform,
    )
    return {"saved": True, "manuscript": manuscript.model_dump(mode="json")}

@router.get("/api/stories/{story_id}/consent")
async def read_consent(story_id: int, owner: Annotated[int, Depends(_owner)]):
    draft = await _owned_draft(story_id, owner)
    return {
        "terms": TERMS,
        "photo_notice": PHOTO_NOTICE,
        "status": consent_status(draft.consent),
    }


@router.post("/api/stories/{story_id}/consent")
async def accept_consent(
    story_id: int, decision: ConsentDecision,
    owner: Annotated[int, Depends(_owner)],
):
    async with async_session_maker() as session:
        row = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "Story not found")
        current = StoryDraft.model_validate_json(row)
        try:
            updated = record_decision(current.consent, decision)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        current.consent = updated
        await session.execute(update(stories).where(
            stories.c.id == story_id, stories.c.owner_id == owner
        ).values(data=current.model_dump_json(), updated_at=datetime.now(UTC)))
        await session.commit()
    return {"status": consent_status(updated)}


@router.post("/api/stories/{story_id}/consent/withdraw")
async def withdraw_consent(
    story_id: int, owner: Annotated[int, Depends(_owner)],
):
    async with async_session_maker() as session:
        row = (await session.execute(select(stories.c.data).where(
            stories.c.id == story_id, stories.c.owner_id == owner
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "Story not found")
        current = StoryDraft.model_validate_json(row)
        current.consent = withdraw_photo_consent(current.consent)
        current.identity_bible, current.portrait_plan, _events = reset_photo_approvals(
            current.identity_bible, current.portrait_plan
        )
        await session.execute(update(stories).where(
            stories.c.id == story_id, stories.c.owner_id == owner
        ).values(data=current.model_dump_json(), updated_at=datetime.now(UTC)))
        await session.commit()
    return {"status": consent_status(current.consent)}


@router.get("/api/stories/{story_id}/vault-summary")
async def read_vault_summary(
    story_id: int, owner: Annotated[int, Depends(_owner)],
):
    await _owned_draft(story_id, owner)
    async with async_session_maker() as session:
        counts = await vault_summary(session, owner_id=owner, story_id=story_id)
    return {"counts": counts, "media_upload_enabled": False}


@router.get("/api/stories/{story_id}/photo-vault")
async def photo_vault_status(story_id: int, owner: Annotated[int, Depends(_owner)]):
    # Always verify the story owner before revealing even feature status.
    await _owned_draft(story_id, owner)
    return upload_capability()


@router.get("/api/stories/{story_id}/privacy-readiness")
async def read_privacy_readiness(
    story_id: int, owner: Annotated[int, Depends(_owner)],
):
    draft = await _owned_draft(story_id, owner)
    bible = draft.identity_bible or quick_identity_bible(
        draft.blueprint or quick_blueprint(draft.hero), draft.hero
    )
    return {
        "consent": consent_status(draft.consent),
        "portrait": portrait_preflight(draft.portrait_plan, bible, draft.consent),
        "launch": photo_launch_preflight(PrivacyLaunchConfig()),
    }


@router.get("/api/stories/{story_id}/portrait")
async def read_portrait(story_id: int, owner: Annotated[int, Depends(_owner)]):
    draft = await _owned_draft(story_id, owner)
    bible = draft.identity_bible or quick_identity_bible(
        draft.blueprint or quick_blueprint(draft.hero), draft.hero
    )
    return {
        "plan": draft.portrait_plan.model_dump(),
        "preflight": portrait_preflight(draft.portrait_plan, bible, draft.consent),
    }


@router.put("/api/stories/{story_id}/portrait")
async def save_portrait(
    story_id: int, plan: PortraitPlan,
    owner: Annotated[int, Depends(_owner)],
):
    draft = await _owned_draft(story_id, owner)
    draft.portrait_plan = plan
    await save_story(story_id, draft, owner)
    bible = draft.identity_bible or quick_identity_bible(
        draft.blueprint or quick_blueprint(draft.hero), draft.hero
    )
    return {
        "saved": True,
        "preflight": portrait_preflight(plan, bible, draft.consent),
    }


@router.get("/api/stories/{story_id}/identity")
async def read_identity(story_id: int, owner: Annotated[int, Depends(_owner)]):
    draft = await _owned_draft(story_id, owner)
    blueprint = draft.blueprint or quick_blueprint(draft.hero)
    bible = draft.identity_bible or quick_identity_bible(blueprint, draft.hero)
    graph = draft.graph or build_graph(draft.scenes)
    return {"identity": bible.model_dump(), "review": identity_review(bible, graph)}


@router.put("/api/stories/{story_id}/identity")
async def save_identity(
    story_id: int, bible: IdentityBible, owner: Annotated[int, Depends(_owner)],
):
    draft = await _owned_draft(story_id, owner)
    if bible.hero_name != draft.hero:
        raise HTTPException(422, "Hero name must match story hero")
    draft.identity_bible = bible
    await save_story(story_id, draft, owner)
    graph = draft.graph or build_graph(draft.scenes)
    return {"saved": True, "review": identity_review(bible, graph)}


@router.get("/api/stories/{story_id}/design")
async def read_design(story_id: int, owner: Annotated[int, Depends(_owner)]):
    draft = await _owned_draft(story_id, owner)
    graph = draft.graph or build_graph(draft.scenes)
    blueprint = draft.blueprint or quick_blueprint(draft.hero)
    return {
        "design": draft.design.model_dump(),
        "guidance": design_guidance(graph, draft.design, blueprint),
    }


@router.put("/api/stories/{story_id}/design")
async def save_design(
    story_id: int, design: StoryDesign, owner: Annotated[int, Depends(_owner)],
):
    draft = await _owned_draft(story_id, owner)
    draft.design = design
    await save_story(story_id, draft, owner)
    return {"saved": True}


@router.get("/api/stories/{story_id}/blueprint")
async def read_blueprint(story_id: int, owner: Annotated[int, Depends(_owner)]):
    draft = await _owned_draft(story_id, owner)
    blueprint = draft.blueprint or quick_blueprint(draft.hero)
    return {
        "blueprint": blueprint.model_dump(),
        "visual_check": visual_consistency_check(blueprint),
        "preflight": print_preflight(blueprint.publishing),
    }


@router.put("/api/stories/{story_id}/blueprint")
async def save_blueprint(
    story_id: int, blueprint: BookBlueprint,
    owner: Annotated[int, Depends(_owner)],
):
    draft = await _owned_draft(story_id, owner)
    draft.blueprint = blueprint
    await save_story(story_id, draft, owner)
    return {
        "saved": True,
        "visual_check": visual_consistency_check(blueprint),
        "preflight": print_preflight(blueprint.publishing),
    }


@router.get("/api/stories/{story_id}/graph")
async def story_graph(story_id: int, owner: Annotated[int, Depends(_owner)]):
    draft = await _owned_draft(story_id, owner)
    graph = draft.graph or build_graph(draft.scenes)
    return {"graph": graph.model_dump(), "report": graph_report(graph),
            "editorial": audit_story(graph).model_dump()}


@router.put("/api/stories/{story_id}/graph")
async def save_story_graph(
    story_id: int, graph: StoryGraph, owner: Annotated[int, Depends(_owner)],
):
    draft = await _owned_draft(story_id, owner)
    draft.graph = graph
    draft.scenes = [
        node.summary for node in sorted(graph.nodes, key=lambda n: n.order)
    ]
    await save_story(story_id, draft, owner)
    return {"saved": True, "report": graph_report(graph),
            "editorial": audit_story(graph).model_dump()}


@router.get("/api/stories/{story_id}/proof.pdf")
async def story_proof(story_id: int, owner: Annotated[int, Depends(_owner)]):
    draft = await _owned_draft(story_id, owner)
    graph = draft.graph or build_graph(draft.scenes)
    data = render_print_proof(
        title=draft.title, hero=draft.hero, dedication=draft.dedication,
        city=draft.city, graph=graph,
    )
    return Response(
        content=data, media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="little-legend-proof.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("", response_class=HTMLResponse)
async def studio():
    # The shell is public; all user data endpoints require signed Telegram initData.
    return HTMLResponse(STUDIO_HTML, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


STUDIO_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Little Legend · Story Director</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{font-family:system-ui,sans-serif;color:#23314a;background:#f5f6fc}
*{box-sizing:border-box}body{margin:0 auto;max-width:760px;padding:18px}
header{display:flex;justify-content:space-between;align-items:center}
h1{font-size:25px;margin:12px 0}h2{font-size:19px}
.card{background:white;border:1px solid #dce0ed;border-radius:17px;padding:17px;margin:12px 0}
label{display:block;font-size:13px;font-weight:600;margin:12px 0 5px}
input,textarea,select{width:100%;padding:12px;border:1px solid #cbd2e4;border-radius:10px;font:inherit}
textarea{min-height:76px;resize:vertical}
button{border:0;border-radius:11px;padding:12px 15px;background:#545ac7;color:white;font:inherit;cursor:pointer}
button.secondary{background:#e9ebfa;color:#323b80}
nav{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}
nav button{flex:1} .graph-node{border-left:4px solid #545ac7;padding:12px;margin:10px 0;background:#f0f1fc;border-radius:8px}.graph-arrow{text-align:center;color:#545ac7;font-weight:bold}.hidden{display:none}.scene{display:flex;align-items:center;gap:8px;margin:9px 0}
.scene span{min-width:25px;color:#626d85}.scene textarea{min-height:58px}
.note{font-size:13px;color:#677187}.error{color:#ad263a}

:root{--ink:#293149;--muted:#6b7492;--line:#e4e8f4;--shadow:0 14px 38px rgba(62,67,123,.08)}
body{background:radial-gradient(ellipse at top left,#e8efff 0,transparent 48%),linear-gradient(150deg,#f9f7ff,#f4f8ff);color:var(--ink);padding:18px 16px 110px;min-height:100vh}
header{background:rgba(255,255,255,.78);border:1px solid var(--line);border-radius:16px;padding:14px 16px;box-shadow:var(--shadow)}
h1{font-family:Georgia,serif;font-size:clamp(27px,6vw,37px);letter-spacing:-.6px;line-height:1.15;margin:25px 0 10px}
h2{font-family:Georgia,serif;font-size:22px;margin:0 0 12px}
.card{border-color:var(--line);box-shadow:var(--shadow);padding:21px;border-radius:20px}
input,textarea,select{background:#fcfdff;border:1px solid #d8dff0;outline:none}
input:focus,textarea:focus,select:focus{border-color:#8982d4;box-shadow:0 0 0 3px #e9e5ff}
button{background:linear-gradient(130deg,#6253b7,#516fc2);font-weight:650}
button:active{transform:scale(.98)}
button.secondary{background:#e9ecfb;color:#3e478b}
nav{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
nav button{font-size:13px;padding:12px 8px}
.hero-lead{color:var(--muted);line-height:1.6;max-width:520px}
.graph-node{border-left:4px solid #8571ca;background:#f8f8ff}
.note{line-height:1.55}
@media(min-width:640px){nav{grid-template-columns:repeat(3,minmax(0,1fr))}}
</style></head><body>
<header><strong>✦ LITTLE LEGEND</strong><span>Story Director</span></header>
<h1>История, в которой ваш ребёнок — герой</h1>
<p class="hero-lead">Придумайте приключение за пару минут или станьте режиссёром каждой сцены. Личные детали необязательны.</p>
<div id="authError" class="error hidden">Откройте студию кнопкой из Telegram-бота.</div>
<div id="workspace" class="hidden">
<nav><button class="secondary" onclick="tab('idea')">01 · Идея</button><button class="secondary" onclick="tab('hero')">02 · Герой</button><button class="secondary" onclick="openDesign()">03 · Драматургия</button><button class="secondary" onclick="tab('scenes')">04 · Сцены</button><button class="secondary" onclick="openPrivacy()">Безопасность</button><button class="secondary" onclick="openPortrait()">Портрет</button><button class="secondary" onclick="openConsent()">05 · Согласие</button><button class="secondary" onclick="openIdentity()">06 · Внешность</button><button class="secondary" onclick="openDirector()">07 · Стиль</button><button class="secondary" onclick="tab('edition')">08 · Издание</button></nav>
<section id="idea" class="card">
<h2>Ваша история</h2>
<label>Название</label><input id="title" maxlength="180">
<label>Жанр</label><select id="genre"><option>Научная фантастика</option><option>Фэнтези</option><option>Детектив</option><option>Приключения</option><option>Сказка на ночь</option></select>
<label>Завязка</label><textarea id="setup" maxlength="4000"></textarea>
<label>Интрига</label><textarea id="mystery" maxlength="4000"></textarea>
<label>Развязка</label><textarea id="ending" maxlength="4000"></textarea>
</section>
<section id="hero" class="card hidden"><h2>Главный герой</h2>
<label>Имя ребёнка</label><input id="heroName" maxlength="100">
<label>Привычки (необязательно)</label><textarea id="habits" maxlength="2000"></textarea>
<label>Любимые выражения (необязательно)</label><textarea id="phrases" maxlength="2000"></textarea>
<p class="note">Загрузка детских фотографий будет включена после добавления согласия родителей и защищённого хранилища.</p></section>
<section id="scenes" class="card hidden"><h2>Режиссёрская раскадровка</h2><p class="note">Изменяйте поворот в любой сцене. Автоматическая генерация графа появится на следующем этапе.</p><div id="sceneList"></div></section>
<section id="privacy" class="card hidden"><h2>Проверка безопасности · Little Legend</h2>
<p class="note">Это контроль готовности, а не подтверждение запуска обработки фотографий.</p>
<button onclick="openPrivacy()">Обновить проверку</button>
<p id="privacyStatus" class="note" role="status"></p>
<div id="privacyChecks" class="note"></div>
</section>
<section id="portrait" class="card hidden"><h2>Эталонный портрет · подготовка</h2>
<p class="note">Настройте будущий портрет. Загрузка фото и генерация пока отключены — изображения ребёнка не передаются.</p>
<label>Режим</label><select id="portraitMode" onchange="portraitModeChanged()"><option value="quick">Быстро</option><option value="director">Подробно</option></select>
<label>Стиль иллюстраций</label><input id="portraitStyle" maxlength="120" value="storybook">
<label>Одежда</label><input id="portraitOutfit" maxlength="250">
<div id="portraitAdvanced" class="hidden">
<label>Выражение лица</label><input id="portraitExpression" maxlength="120">
<label>Фон</label><input id="portraitBackground" maxlength="150">
<label>Кадрирование</label><select id="portraitFraming"><option value="head-and-shoulders">Плечевой портрет</option><option value="half-body">По пояс</option><option value="full-body">В полный рост</option></select>
<label>Освещение</label><input id="portraitLighting" maxlength="120">
<label>Чего избегать (каждое с новой строки)</label><textarea id="portraitAvoid"></textarea>
</div>
<label><input id="portraitApproved" type="checkbox" style="width:auto"> Я проверил(а) текстовые настройки портрета</label>
<button onclick="savePortrait()">Сохранить настройки</button><p id="portraitStatus" class="note" role="status"></p>
</section>
<section id="consent" class="card hidden"><h2>Безопасность и согласие</h2>
<p class="note">Перед использованием фотографий ребёнка необходимо ознакомиться с условиями. Загрузка фотографий пока отключена.</p>
<h3>Условия использования</h3><p class="note" id="consentTerms"></p>
<h3>Фотографии ребёнка</h3><p class="note" id="consentPhotoNotice"></p>
<label><input id="consentTermsCheck" type="checkbox" style="width:auto"> Я прочитал(а) и принимаю условия использования</label>
<label><input id="consentParentCheck" type="checkbox" style="width:auto"> Я совершеннолетний родитель или законный представитель и вправе предоставлять материалы ребёнка</label>
<label><input id="consentPhotoCheck" type="checkbox" disabled style="width:auto"> Отдельно соглашаюсь на будущую обработку фотографий ребёнка для создания книги</label>
<button onclick="acceptConsent()">Сохранить согласия</button>
<button class="secondary" onclick="withdrawConsent()">Отозвать согласие на фотографии</button>
<p id="consentStatus" class="note" role="status"></p>
</section>
<section id="identity" class="card hidden"><h2>Визуальная библия героя</h2>
<p class="note">Зафиксируйте внешность ребёнка. Фотографии пока не загружаются.</p>
<label>Режим</label><select id="identityMode" onchange="identityMode()"><option value="quick">Быстро</option><option value="director">Подробно</option></select>
<label>Волосы</label><input id="identityHair" maxlength="200">
<label>Глаза</label><input id="identityEyes" maxlength="200">
<div id="identityAdvanced" class="hidden">
<label>Черты лица</label><textarea id="identityFace" maxlength="300"></textarea>
<label>Пропорции</label><textarea id="identityProportions" maxlength="300"></textarea>
<label>Неизменные приметы (каждая с новой строки)</label><textarea id="identityFixed"></textarea>
<label>Что нельзя менять (каждое с новой строки)</label><textarea id="identityForbidden"></textarea>
</div>
<label><input id="identityReviewed" type="checkbox" style="width:auto"> Я проверил(а) описание внешности</label>
<p class="note">Это не согласие на обработку фото. Фотофункции будут доступны только после отдельного защищённого процесса согласия.</p>
<button class="secondary" onclick="saveIdentity()">Сохранить внешность</button><p id="identityStatus" class="note"></p></section>
<section id="design" class="card hidden"><h2>Душа вашей истории</h2>
<p class="note">Быстро: можно пропустить. Подробно: задайте эмоциональную арку героя.</p>
<label>Режим драматургии</label><select id="designMode" onchange="designMode()"><option value="quick">Быстро</option><option value="director">Подробно</option></select>
<div id="designAdvanced" class="hidden">
<label>Желание героя</label><textarea id="desire" maxlength="1000"></textarea>
<label>Чему он научится</label><textarea id="need" maxlength="1000"></textarea>
<label>Что поставлено на карту</label><textarea id="stakes" maxlength="1000"></textarea>
<label>Решающий выбор героя</label><textarea id="decisive_choice" maxlength="1000"></textarea>
<label>Как он изменится</label><textarea id="transformation" maxlength="1000"></textarea>
<label>Главная тема</label><input id="theme" maxlength="300">
<label>Повторяющийся символ</label><input id="recurring_symbol" maxlength="300">
<label>Чего не должно быть в истории</label><textarea id="emotional_safety_note" maxlength="600"></textarea>
</div>
<button class="secondary" onclick="saveDesign()">Сохранить драматургию</button><p id="designStatus" class="note"></p>
<p id="designTips" class="note"></p>
</section>
<section id="graph" class="card hidden"><h2>Story Graph · причинно-следственная карта</h2><p class="note">Это линейный каркас сюжета. Для изменения содержания редактируйте сцены, затем сохраняйте черновик.</p><div id="graphList"></div><p id="graphReport" class="note"></p><button onclick="saveGraph()">Сохранить режиссуру</button> <button class="secondary" onclick="showGraph()">Обновить карту</button><p id="graphStatus" class="note"></p></section>
<section id="director" class="card hidden"><h2>Настройки истории</h2>
<p class="note">Быстрый режим — минимум действий. Подробный — управление творческими параметрами.</p>
<label>Режим</label><select id="creativeMode" onchange="directorMode()"><option value="quick">Быстро</option><option value="director">Подробно</option></select>
<label>Возраст (необязательно)</label><input id="childAge" type="number" min="0" max="17">
<div id="advancedControls" class="hidden">
<label>Тон</label><select id="tone"><option value="balanced">Приключенческий</option><option value="gentle">Мягкий</option><option value="epic">Эпический</option></select>
<label>Свобода AI</label><select id="freedom"><option value="balanced">Сбалансированная</option><option value="strict">Строго по замыслу</option><option value="creative">Творческая</option></select>
<label>Объём</label><select id="length"><option value="standard">Стандартный</option><option value="short">Короткий</option><option value="long">Длинный</option></select>
<label>Стиль рисунков</label><select id="artStyle"><option value="storybook">Книжный</option><option value="watercolor">Акварель</option><option value="cinematic">Кинематографический</option><option value="pencil">Карандаш</option><option value="gouache">Гуашь</option></select>
<label>Описание внешности ребёнка</label><textarea id="appearance" maxlength="1200"></textarea>
<label>Неизменные визуальные приметы</label><textarea id="visualNotes" maxlength="1200"></textarea>
</div>
<p class="note">Фотографии пока не принимаются. Для фотопохожести потребуются согласие родителя и утверждение контрольного портрета.</p>
<button class="secondary" onclick="saveDirector()">Сохранить настройки</button><p id="directorStatus" class="note"></p>
</section>
<section id="edition" class="card hidden"><h2>Персональное издание</h2>
<label>Посвящение</label><textarea id="dedication" maxlength="1000"></textarea>
<label>Город выпуска</label><input id="city" maxlength="100">
<p class="note">Авторство, год и номер экземпляра будут оформлены в финальном PDF.</p></section>
<div class="card"><button class="secondary" onclick="openDirector()">Настройки</button> <button class="secondary" onclick="showGraph()">Посмотреть граф</button> <button class="secondary" onclick="proof()">PDF-макет A5</button><p class="note">PDF содержит план сцен, а не готовую книгу для печати.</p><button onclick="save()">Сохранить черновик</button> <button class="secondary" onclick="fresh()">Новая книга</button><p id="status" class="note"></p></div>
<div class="card"><h2>Мои книги</h2><div id="books"></div></div>
</div>
<script>
const tg=window.Telegram?.WebApp;tg?.ready();tg?.expand();
const auth=tg?.initData;let storyId=null;let activeGraph=null;
const fields=['title','genre','setup','mystery','ending','habits','phrases','dedication','city'];
const defaults=['Знакомство с героем','Необычное событие','Первый союзник','Тайное послание','Первая загадка','Опасная находка','Неожиданный поворот','Испытание дружбы','Разгадка тайны','План спасения','Главное испытание','Развязка и новая тайна'];
const $=id=>document.getElementById(id);
function tab(id){['idea','hero','scenes','edition','graph','director','design','identity','consent','portrait','privacy'].forEach(x=>$(x).classList.toggle('hidden',x!==id))}
function drawScenes(items){$('sceneList').replaceChildren();items.forEach((value,i)=>{let row=document.createElement('div');row.className='scene';let n=document.createElement('span');n.textContent=i+1;let t=document.createElement('textarea');t.maxLength=4000;t.value=value;t.dataset.scene=i;row.append(n,t);$('sceneList').append(row)})}
function collect(){let obj={};fields.forEach(k=>obj[k]=$(k).value);obj.hero=$('heroName').value;obj.scenes=[...document.querySelectorAll('[data-scene]')].map(x=>x.value);return obj}
function fill(data){fields.forEach(k=>$(k).value=data[k]||'');$('heroName').value=data.hero||'Оля';drawScenes(data.scenes||defaults)}
async function api(path,method='GET',data){let r=await fetch('/little-legend/api'+path,{method,headers:{Authorization:'tma '+auth,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
async function load(){let books=await api('/stories');$('books').replaceChildren();books.forEach(b=>{let button=document.createElement('button');button.className='secondary';button.style.margin='4px';button.textContent=b.title+' · '+b.hero;button.onclick=async()=>{try{fill(await api('/stories/'+b.id));storyId=b.id;$('status').textContent='Черновик открыт'}catch(e){$('status').textContent=e.message}};$('books').append(button)})}
async function save(){try{let data=collect();if(!data.title.trim()||!data.hero.trim()){throw Error('Укажите название и имя героя')}let result=await api(storyId?'/stories/'+storyId:'/stories',storyId?'PUT':'POST',data);storyId=storyId||result.id;$('status').textContent='Сохранено';await load()}catch(e){$('status').textContent='Ошибка: '+e.message}}
async function showGraph(){try{
if(!storyId){$('status').textContent='Сначала сохраните книгу';return}
const result=await api('/stories/'+storyId+'/graph');activeGraph=result.graph;
$('graphList').replaceChildren();
activeGraph.nodes.forEach((node,i)=>{
const card=document.createElement('div');card.className='graph-node';
const title=document.createElement('strong');title.textContent='Акт '+node.act+' · Сцена '+node.order;
card.append(title);
const fields=[['title','Название'],['summary','Что происходит'],['goal','Цель'],['conflict','Препятствие'],['consequence','Последствие'],['illustration_prompt','Идея иллюстрации']];
fields.forEach(([key,label])=>{
const caption=document.createElement('label');caption.textContent=label;
const input=document.createElement(key==='title'?'input':'textarea');
input.value=node[key]||'';input.maxLength=key==='summary'?4000:key==='illustration_prompt'?2000:key==='title'?160:1000;
input.addEventListener('input',()=>{node[key]=input.value});
card.append(caption,input);
});
const lockLabel=document.createElement('label');lockLabel.textContent='Защитить эту сцену от автоматических изменений ';
const lock=document.createElement('input');lock.type='checkbox';lock.checked=node.locked;lock.style.width='auto';lock.addEventListener('change',()=>{node.locked=lock.checked});lockLabel.append(lock);card.append(lockLabel);
$('graphList').append(card);
if(i<activeGraph.nodes.length-1){const arrow=document.createElement('div');arrow.className='graph-arrow';arrow.textContent='↓';$('graphList').append(arrow)}
});
const audit=result.editorial;
$('graphReport').textContent='Редакторский индекс: '+audit.score+'/100 · Замечаний: '+audit.issues.length+' · '+audit.issues.slice(0,3).map(x=>x.message).join('; ');
tab('graph')
}catch(e){$('status').textContent=e.message}}
async function saveGraph(){try{
if(!storyId||!activeGraph)throw Error('Сначала откройте граф');
const result=await api('/stories/'+storyId+'/graph','PUT',activeGraph);
drawScenes(activeGraph.nodes.slice().sort((a,b)=>a.order-b.order).map(x=>x.summary));
$('graphStatus').textContent='Сохранено · редакторский индекс '+result.editorial.score+'/100';
}catch(e){$('graphStatus').textContent='Ошибка: '+e.message}}
async function proof(){try{if(!storyId){$('status').textContent='Сначала сохраните книгу';return}const r=await fetch('/little-legend/api/stories/'+storyId+'/proof.pdf',{headers:{Authorization:'tma '+auth}});if(!r.ok)throw Error('PDF HTTP '+r.status);const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='little-legend-proof.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000)}catch(e){$('status').textContent=e.message}}
async function openPrivacy(){tab('privacy');if(!storyId){$('privacyStatus').textContent='Сначала сохраните книгу';return}try{const x=await api('/stories/'+storyId+'/privacy-readiness');$('privacyStatus').textContent=x.launch.photo_upload_enabled?'Фото доступны':'Фото недоступны: безопасность и юридические условия ещё не подтверждены';const c=$('privacyChecks');c.replaceChildren();Object.entries(x.launch.checks).forEach(([key,ok])=>{const line=document.createElement('p');line.textContent=(ok?'✓ ':'○ ')+key.replaceAll('_',' ');c.append(line)});x.portrait.blockers.forEach(reason=>{const line=document.createElement('p');line.textContent='• '+reason;c.append(line)})}catch(e){$('privacyStatus').textContent='Ошибка: '+e.message}}
let portraitDraft=null;
function portraitModeChanged(){$('portraitAdvanced').classList.toggle('hidden',$('portraitMode').value!=='director')}
async function openPortrait(){tab('portrait');if(!storyId){$('portraitStatus').textContent='Сначала сохраните книгу';return}try{const x=await api('/stories/'+storyId+'/portrait');portraitDraft=x.plan;const p=x.plan;$('portraitMode').value=p.mode;$('portraitStyle').value=p.style;$('portraitOutfit').value=p.preferred_outfit;$('portraitExpression').value=p.expression;$('portraitBackground').value=p.background;$('portraitFraming').value=p.framing;$('portraitLighting').value=p.lighting;$('portraitAvoid').value=p.avoid.join(String.fromCharCode(10));$('portraitApproved').checked=p.parent_description_approved;portraitModeChanged();$('portraitStatus').textContent=x.preflight.blockers.join(' · ')}catch(e){$('portraitStatus').textContent='Ошибка: '+e.message}}
async function savePortrait(){try{if(!storyId)throw Error('Сначала сохраните книгу');const p={mode:$('portraitMode').value,style:$('portraitStyle').value,preferred_outfit:$('portraitOutfit').value,expression:$('portraitExpression').value,background:$('portraitBackground').value,framing:$('portraitFraming').value,lighting:$('portraitLighting').value,avoid:$('portraitAvoid').value.split(String.fromCharCode(10)).map(x=>x.trim()).filter(Boolean).slice(0,12),parent_description_approved:$('portraitApproved').checked,reference_photo_reviewed:false};const x=await api('/stories/'+storyId+'/portrait','PUT',p);$('portraitStatus').textContent='Настройки сохранены. '+x.preflight.blockers.join(' · ')}catch(e){$('portraitStatus').textContent='Ошибка: '+e.message}}
async function openConsent(){tab('consent');if(!storyId){$('consentStatus').textContent='Сначала сохраните книгу';return}try{const x=await api('/stories/'+storyId+'/consent');$('consentTerms').textContent=x.terms;$('consentPhotoNotice').textContent=x.photo_notice;$('consentTermsCheck').checked=x.status.terms_accepted;$('consentParentCheck').checked=x.status.terms_accepted;$('consentPhotoCheck').checked=x.status.photo_consent_active;$('consentStatus').textContent=x.status.photo_consent_active?'Согласие на фотографии записано; загрузка пока недоступна':'Согласие на фотографии не предоставлено'}catch(e){$('consentStatus').textContent=e.message}}
async function acceptConsent(){try{if(!storyId)throw Error('Сначала сохраните книгу');const decision={accept_terms:$('consentTermsCheck').checked,declare_parental_authority:$('consentParentCheck').checked,consent_to_child_photos:false};const x=await api('/stories/'+storyId+'/consent','POST',decision);$('consentStatus').textContent=x.status.photo_consent_active?'Согласие записано. Загрузка фотографий пока отключена.':'Условия приняты без согласия на фотографии.'}catch(e){$('consentStatus').textContent='Ошибка: '+e.message}}
async function withdrawConsent(){try{if(!storyId)throw Error('Сначала сохраните книгу');await api('/stories/'+storyId+'/consent/withdraw','POST',{});$('consentPhotoCheck').checked=false;$('consentStatus').textContent='Согласие на фотографии отозвано. Фотографии здесь не хранятся.'}catch(e){$('consentStatus').textContent='Ошибка: '+e.message}}
let activeIdentity=null;
function identityMode(){$('identityAdvanced').classList.toggle('hidden',$('identityMode').value!=='director')}
function identityLines(id){return $(id).value.split(String.fromCharCode(10)).map(x=>x.trim()).filter(Boolean).slice(0,12)}
async function openIdentity(){tab('identity');if(!storyId){$('identityStatus').textContent='Сначала сохраните книгу';return}try{const result=await api('/stories/'+storyId+'/identity');activeIdentity=result.identity;const x=activeIdentity.identity;$('identityMode').value=x.mode;$('identityHair').value=x.hair;$('identityEyes').value=x.eyes;$('identityFace').value=x.face;$('identityProportions').value=x.proportions;$('identityFixed').value=x.fixed_details.join(String.fromCharCode(10));$('identityForbidden').value=x.forbidden_changes.join(String.fromCharCode(10));$('identityReviewed').checked=x.parent_reviewed_description;identityMode();$('identityStatus').textContent=result.review.warnings.join(' · ')}catch(e){$('identityStatus').textContent=e.message}}
async function saveIdentity(){try{if(!storyId||!activeIdentity)throw Error('Сначала откройте настройки');const x=activeIdentity.identity;x.mode=$('identityMode').value;x.hair=$('identityHair').value;x.eyes=$('identityEyes').value;x.face=$('identityFace').value;x.proportions=$('identityProportions').value;x.fixed_details=identityLines('identityFixed');x.forbidden_changes=identityLines('identityForbidden');x.parent_reviewed_description=$('identityReviewed').checked;const result=await api('/stories/'+storyId+'/identity','PUT',activeIdentity);$('identityStatus').textContent='Сохранено. '+result.review.warnings.join(' · ')}catch(e){$('identityStatus').textContent='Ошибка: '+e.message}}
const designKeys=['desire','need','stakes','decisive_choice','transformation','theme','recurring_symbol','emotional_safety_note'];
function designMode(){$('designAdvanced').classList.toggle('hidden',$('designMode').value!=='director')}
async function openDesign(){tab('design');if(!storyId){$('designStatus').textContent='Сначала сохраните черновик';return}try{const result=await api('/stories/'+storyId+'/design');designKeys.forEach(k=>$(k).value=result.design[k]||'');$('designMode').value=designKeys.some(k=>result.design[k])?'director':'quick';designMode();$('designTips').textContent=result.guidance.audience_guidance+' · '+result.guidance.missing_arc_elements.length+' элементов арки ещё не заполнены'}catch(e){$('designStatus').textContent=e.message}}
async function saveDesign(){try{if(!storyId)throw Error('Сначала сохраните черновик');const data={};designKeys.forEach(k=>data[k]=$(k).value);await api('/stories/'+storyId+'/design','PUT',data);$('designStatus').textContent='Драматургия сохранена'}catch(e){$('designStatus').textContent=e.message}}
function directorMode(){$('advancedControls').classList.toggle('hidden',$('creativeMode').value!=='director')}
async function openDirector(){tab('director');if(!storyId)return;try{let b=(await api('/stories/'+storyId+'/blueprint')).blueprint;$('creativeMode').value=b.controls.mode;$('childAge').value=b.controls.age??'';$('tone').value=b.controls.tone;$('freedom').value=b.controls.creative_freedom;$('length').value=b.controls.story_length;$('artStyle').value=b.controls.illustration_style;$('appearance').value=b.characters[0]?.appearance||'';$('visualNotes').value=b.characters[0]?.visual_identity_notes||'';directorMode()}catch(e){$('directorStatus').textContent=e.message}}
async function saveDirector(){try{if(!storyId)throw Error('Сначала сохраните книгу');let b=(await api('/stories/'+storyId+'/blueprint')).blueprint;b.controls.mode=$('creativeMode').value;b.controls.age=$('childAge').value===''?null:Number($('childAge').value);b.controls.tone=$('tone').value;b.controls.creative_freedom=$('freedom').value;b.controls.story_length=$('length').value;b.controls.illustration_style=$('artStyle').value;if(!b.characters.length)b.characters=[{name:$('heroName').value,role:'hero'}];b.characters[0].appearance=$('appearance').value;b.characters[0].visual_identity_notes=$('visualNotes').value;await api('/stories/'+storyId+'/blueprint','PUT',b);$('directorStatus').textContent='Настройки сохранены'}catch(e){$('directorStatus').textContent=e.message}}
function fresh(){storyId=null;fill({title:'Новая история',hero:'Оля',genre:'Научная фантастика',scenes:defaults});$('status').textContent='Новый черновик — сохраните его'}
fresh();if(auth){$('workspace').classList.remove('hidden');load().catch(e=>$('status').textContent='Не удалось загрузить книги: '+e.message)}else{$('authError').classList.remove('hidden')}
</script></body></html>"""
