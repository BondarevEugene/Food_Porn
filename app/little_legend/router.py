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
from app.little_legend.print_renderer import render_print_proof
from app.little_legend.story_graph import StoryGraph, build_graph, graph_report
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


@router.get("/api/stories/{story_id}/graph")
async def story_graph(story_id: int, owner: Annotated[int, Depends(_owner)]):
    draft = await _owned_draft(story_id, owner)
    graph = draft.graph or build_graph(draft.scenes)
    return {"graph": graph.model_dump(), "report": graph_report(graph)}


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
    return {"saved": True, "report": graph_report(graph)}


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
</style></head><body>
<header><strong>✦ LITTLE LEGEND</strong><span>Story Director</span></header>
<h1>Книга о вашем ребёнке</h1>
<p class="note">Черновик сохраняется в вашем Telegram-аккаунте. Все личные детали необязательны.</p>
<div id="authError" class="error hidden">Откройте студию кнопкой из Telegram-бота.</div>
<div id="workspace" class="hidden">
<nav><button class="secondary" onclick="tab('idea')">Быстрая сказка</button><button class="secondary" onclick="tab('hero')">Герой</button><button class="secondary" onclick="tab('scenes')">12 сцен</button><button class="secondary" onclick="tab('edition')">Издание</button></nav>
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
<section id="graph" class="card hidden"><h2>Story Graph · причинно-следственная карта</h2><p class="note">Это линейный каркас сюжета. Для изменения содержания редактируйте сцены, затем сохраняйте черновик.</p><div id="graphList"></div><p id="graphReport" class="note"></p></section>
<section id="edition" class="card hidden"><h2>Персональное издание</h2>
<label>Посвящение</label><textarea id="dedication" maxlength="1000"></textarea>
<label>Город выпуска</label><input id="city" maxlength="100">
<p class="note">Авторство, год и номер экземпляра будут оформлены в финальном PDF.</p></section>
<div class="card"><button class="secondary" onclick="showGraph()">Посмотреть граф</button> <button class="secondary" onclick="proof()">PDF-макет A5</button><p class="note">PDF содержит план сцен, а не готовую книгу для печати.</p><button onclick="save()">Сохранить черновик</button> <button class="secondary" onclick="fresh()">Новая книга</button><p id="status" class="note"></p></div>
<div class="card"><h2>Мои книги</h2><div id="books"></div></div>
</div>
<script>
const tg=window.Telegram?.WebApp;tg?.ready();tg?.expand();
const auth=tg?.initData;let storyId=null;
const fields=['title','genre','setup','mystery','ending','habits','phrases','dedication','city'];
const defaults=['Знакомство с героем','Необычное событие','Первый союзник','Тайное послание','Первая загадка','Опасная находка','Неожиданный поворот','Испытание дружбы','Разгадка тайны','План спасения','Главное испытание','Развязка и новая тайна'];
const $=id=>document.getElementById(id);
function tab(id){['idea','hero','scenes','edition','graph'].forEach(x=>$(x).classList.toggle('hidden',x!==id))}
function drawScenes(items){$('sceneList').replaceChildren();items.forEach((value,i)=>{let row=document.createElement('div');row.className='scene';let n=document.createElement('span');n.textContent=i+1;let t=document.createElement('textarea');t.maxLength=4000;t.value=value;t.dataset.scene=i;row.append(n,t);$('sceneList').append(row)})}
function collect(){let obj={};fields.forEach(k=>obj[k]=$(k).value);obj.hero=$('heroName').value;obj.scenes=[...document.querySelectorAll('[data-scene]')].map(x=>x.value);return obj}
function fill(data){fields.forEach(k=>$(k).value=data[k]||'');$('heroName').value=data.hero||'Оля';drawScenes(data.scenes||defaults)}
async function api(path,method='GET',data){let r=await fetch('/little-legend/api'+path,{method,headers:{Authorization:'tma '+auth,'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
async function load(){let books=await api('/stories');$('books').replaceChildren();books.forEach(b=>{let button=document.createElement('button');button.className='secondary';button.style.margin='4px';button.textContent=b.title+' · '+b.hero;button.onclick=async()=>{try{fill(await api('/stories/'+b.id));storyId=b.id;$('status').textContent='Черновик открыт'}catch(e){$('status').textContent=e.message}};$('books').append(button)})}
async function save(){try{let data=collect();if(!data.title.trim()||!data.hero.trim()){throw Error('Укажите название и имя героя')}let result=await api(storyId?'/stories/'+storyId:'/stories',storyId?'PUT':'POST',data);storyId=storyId||result.id;$('status').textContent='Сохранено';await load()}catch(e){$('status').textContent='Ошибка: '+e.message}}
async function showGraph(){try{if(!storyId){$('status').textContent='Сначала сохраните книгу';return}const result=await api('/stories/'+storyId+'/graph');const nodes=result.graph.nodes;$('graphList').replaceChildren();nodes.forEach((n,i)=>{let el=document.createElement('div');el.className='graph-node';let h=document.createElement('strong');h.textContent='Акт '+n.act+' · '+n.title;let p=document.createElement('p');p.textContent=n.summary||'Сцена не заполнена';let goal=document.createElement('small');goal.textContent='Задача: '+n.goal;el.append(h,p,goal);$('graphList').append(el);if(i<nodes.length-1){let arrow=document.createElement('div');arrow.className='graph-arrow';arrow.textContent='↓ вызывает следующее событие';$('graphList').append(arrow)}});$('graphReport').textContent='Пустых сцен: '+result.report.empty_scenes.length+' · Без описания конфликта: '+result.report.missing_conflicts.length;tab('graph')}catch(e){$('status').textContent=e.message}}
async function proof(){try{if(!storyId){$('status').textContent='Сначала сохраните книгу';return}const r=await fetch('/little-legend/api/stories/'+storyId+'/proof.pdf',{headers:{Authorization:'tma '+auth}});if(!r.ok)throw Error('PDF HTTP '+r.status);const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='little-legend-proof.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000)}catch(e){$('status').textContent=e.message}}
function fresh(){storyId=null;fill({title:'Новая история',hero:'Оля',genre:'Научная фантастика',scenes:defaults});$('status').textContent='Новый черновик — сохраните его'}
fresh();if(auth){$('workspace').classList.remove('hidden');load().catch(e=>$('status').textContent='Не удалось загрузить книги: '+e.message)}else{$('authError').classList.remove('hidden')}
</script></body></html>"""
