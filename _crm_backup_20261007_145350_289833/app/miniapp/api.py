"""Authenticated Mini App: gifts, menus, payments, files and administration."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import func, or_, select

from app.bot.handlers.wallpaper import make_preview, parse_five_goals, save_photo
from app.config import get_settings
from app.database.models import (
    Customer,
    EmailDelivery,
    FileKind,
    ItemCategory,
    Language,
    Menu,
    MenuStatus,
    ShareLink,
    WallpaperOrder,
)
from app.database.repositories import CustomerRepository, MenuRepository, WallpaperOrderRepository
from app.database.session import async_session_maker
from app.miniapp.auth import current_user
from app.services.email_service import normalize_recipient, send_ready_order_email
from app.services.free_access import has_free_generation_access
from app.services.gift_pricing import checkout_price_uah
from app.services.goal_story import GoalScenePlanner
from app.services.payment import PaymentService
from app.services.print_bundle import create_print_bundle
from app.services.printshop import PrintshopService
from app.services.replicate_vision_board import ImageSafetyError, ReplicateVisionBoardRenderer
from app.services.settings_service import get_setting, get_vip_users, set_setting
from app.services.stars import OrderRef, create_invoice
from app.services.storage import InvalidImageError, StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/miniapp")
STATIC = Path(__file__).with_name("static")
_tasks: set[asyncio.Task] = set()
_user_jobs: set[int] = set()


def _validate_gift_files(mobile: Path, desktop: Path) -> None:
    for path in (mobile, desktop):
        if not path.is_file() or path.stat().st_size < 20_000:
            raise ValueError("Gift artwork is incomplete")
        with Image.open(path) as image:
            image.load()
            if min(image.size) < 900 or image.convert("L").entropy() < 1:
                raise ValueError("Gift artwork failed visual quality checks")


def _job_dir(user_id: int, job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(404, "Order not found")
    return get_settings().storage_root / "miniapp_jobs" / str(user_id) / job_id


def _read_job(user_id: int, job_id: str) -> dict:
    try:
        return json.loads((_job_dir(user_id, job_id) / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Order not found") from exc


def _write_job(user_id: int, job_id: str, data: dict) -> None:
    folder = _job_dir(user_id, job_id)
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / "job.tmp"
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temp.replace(folder / "job.json")


def _track(task: asyncio.Task) -> None:
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _public_job(job: dict) -> dict:
    return {key: job.get(key) for key in ("id", "status", "style", "goals", "price", "stars", "invoice", "order_id", "error", "progress")}


async def _shared_gift(token: str) -> tuple[dict, dict[str, Path | None]]:
    """A share token is a bearer grant to finished gift media only."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{32}", token):
        raise HTTPException(404, "Gift not found")
    async with async_session_maker() as session:
        link = await session.get(ShareLink, token)
        if link is None:
            raise HTTPException(404, "Gift not found")
        if link.kind == "menu":
            menu = await session.get(Menu, int(link.reference_id))
            if (menu is None or not menu.is_paid or menu.status in
                    (MenuStatus.DRAFT, MenuStatus.QUEUED, MenuStatus.FAILED)):
                raise HTTPException(404, "Gift not ready")
            await session.refresh(menu, ["files", "items", "customer"])
            paths = {file.kind: Path(file.path) for file in menu.files}
            return ({"kind": "menu", "language": menu.customer.language.value if menu.customer else "uk",
                     "items": [item.title for item in menu.items if item.title != "—"]},
                    {"cover": paths.get(FileKind.PREVIEW_OUTSIDE),
                     "inside": paths.get(FileKind.PREVIEW_INSIDE),
                     "download": paths.get(FileKind.PRINT_PDF)})
        if link.kind == "gift":
            try:
                job = _read_job(link.owner_telegram_id, link.reference_id)
            except HTTPException:
                raise HTTPException(404, "Gift not found") from None
            if job.get("status") != "ready":
                raise HTTPException(404, "Gift not ready")
            if job.get("order_id"):
                order = await session.get(WallpaperOrder, job["order_id"])
                if order is None or not order.paid or order.telegram_user_id != link.owner_telegram_id:
                    raise HTTPException(404, "Gift not ready")
                mobile = Path(order.mobile_path)
            elif job.get("free"):
                uid = link.owner_telegram_id
                mobile = (get_settings().generated_dir / "wallpapers" / str(uid) /
                          link.reference_id / f"manifestation_{uid}_mobile.png")
            else:
                raise HTTPException(404, "Gift not ready")
            cover = mobile.with_name(f"preview_{mobile.stem}.jpg")
            return ({"kind": "gift", "language": job.get("language", "uk"),
                     "goals": job.get("goals", [])},
                    {"cover": cover if cover.is_file() else mobile, "download": mobile})
        if link.kind == "wallpaper":
            order = await session.get(WallpaperOrder, int(link.reference_id))
            if order is None or not order.paid or order.telegram_user_id != link.owner_telegram_id:
                raise HTTPException(404, "Gift not ready")
            mobile = Path(order.mobile_path)
            cover = mobile.with_name(f"preview_{mobile.stem}.jpg")
            return ({"kind": "gift", "language": "uk", "goals": []},
                    {"cover": cover if cover.is_file() else mobile, "download": mobile})
    raise HTTPException(404, "Gift not found")


@router.get("")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@router.get("/open/{token}")
async def open_present(token: str) -> FileResponse:
    await _shared_gift(token)
    return FileResponse(STATIC / "present.html", headers={"Cache-Control": "private, no-store",
                                                          "Referrer-Policy": "no-referrer"})


@router.get("/open/{token}/data")
async def shared_gift_data(token: str) -> dict:
    info, paths = await _shared_gift(token)
    if not paths["cover"] or not paths["cover"].is_file():
        raise HTTPException(404, "Gift image unavailable")
    return {**info, "has_inside": bool(paths.get("inside") and paths["inside"].is_file())}


@router.get("/open/{token}/media/{kind}")
async def shared_gift_media(token: str, kind: str) -> FileResponse:
    _, paths = await _shared_gift(token)
    if kind not in {"cover", "inside", "download"}:
        raise HTTPException(404)
    path = paths.get(kind)
    if path is None or not path.is_file():
        raise HTTPException(404, "Gift image unavailable")
    return FileResponse(path, filename=path.name if kind == "download" else None,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "no-referrer"})


@router.get("/static/{name}")
async def static_file(name: str) -> FileResponse:
    if name not in {"app.js", "style.css", "gift-ribbon.svg", "kitchen-cloche.svg",
                    "present.js", "present.css"}:
        raise HTTPException(404)
    return FileResponse(STATIC / name, headers={"Cache-Control": "no-store"})


@router.get("/static/fonts/{name}")
async def static_font(name: str) -> FileResponse:
    if name not in {"atelier-serif-bold.woff", "romantic-serif-italic.ttf"}:
        raise HTTPException(404)
    return FileResponse(STATIC / "fonts" / name,
                        media_type="font/ttf" if name.endswith(".ttf") else "font/woff",
                        headers={"Cache-Control": "no-store"})


@router.get("/api/home")
async def home(user: Annotated[dict, Depends(current_user)]) -> dict:
    settings = get_settings()
    uid = user["id"]
    async with async_session_maker() as session:
        customer = await CustomerRepository(session).by_telegram_id(uid)
        menus = await MenuRepository(session).recent_for_customer(customer.id, 20) if customer else []
        orders = (await session.execute(select(WallpaperOrder).where(
            WallpaperOrder.telegram_user_id == uid).order_by(WallpaperOrder.id.desc()).limit(20)
        )).scalars().all()
    jobs = []
    root = settings.storage_root / "miniapp_jobs" / str(uid)
    if root.is_dir():
        for folder in sorted(root.iterdir(), reverse=True)[:20]:
            if folder.is_dir():
                try:
                    item = _read_job(uid, folder.name)
                    if item["status"] == "generating" and folder.name not in {
                        getattr(task, "job_id", None) for task in _tasks if not task.done()
                    }:
                        item["status"] = "interrupted"
                        _write_job(uid, folder.name, item)
                    jobs.append(_public_job(item))
                except HTTPException:
                    continue
    return {
        "user": {"id": uid, "name": user.get("first_name", ""), "username": user.get("username")},
        "admin": uid in settings.admin_telegram_ids,
        "language": customer.language.value if customer else user.get("language_code", "uk")[:2],
        "customer": {"name": customer.name, "phone": customer.phone} if customer else None,
        "payment_ready": settings.menu_price_stars > 0 and settings.gift_price_stars > 0,
        "menu_payment_ready": settings.menu_price_stars > 0,
        "gift_payment_ready": settings.gift_price_stars > 0,
        "free_access": await has_free_generation_access(uid, user.get("username"), settings, async_session_maker),
        "jobs": jobs,
        "wallpapers": [{"id": o.id, "paid": o.paid, "amount": str(o.amount),
                        "stars": o.stars_amount,
                        "created_at": o.created_at.isoformat() if o.created_at else None} for o in orders],
        "menus": [{"id": m.id, "status": m.status.value, "paid": m.is_paid,
                   "created_at": m.created_at.isoformat() if m.created_at else None,
                   "amount": str(m.price_amount) if m.price_amount else None} for m in menus],
    }


async def _read_upload(upload: UploadFile, limit: int) -> bytes:
    if upload.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(422, "Please upload a JPEG, PNG or WebP photo")
    payload = await upload.read(limit + 1)
    if len(payload) > limit:
        raise HTTPException(413, "Photo is too large")
    return payload


@router.post("/api/gifts")
async def create_gift(
    photos: Annotated[list[UploadFile], File()],
    user: Annotated[dict, Depends(current_user)],
    goals: str = Form(...), style: str = Form("dark"), language: str = Form("uk"),
) -> dict:
    uid = user["id"]
    settings = get_settings()
    try:
        parsed = parse_five_goals(goals)
    except ValueError as exc:
        raise HTTPException(422, "Enter five to nine wishes, one per line") from exc
    if not 1 <= len(photos) <= 7 or style not in {"dark", "light", "color"} or language not in {"uk", "ru", "en"}:
        raise HTTPException(422, "Choose one to seven photos and an atmosphere")
    if uid in _user_jobs:
        raise HTTPException(409, "Another gift is being created")
    free = await has_free_generation_access(uid, user.get("username"), settings, async_session_maker)
    if not free and settings.gift_price_stars < 1:
        raise HTTPException(503, "Payment is temporarily unavailable; generation has not started")
    # Reserve the user slot before awaiting uploads.
    if uid in _user_jobs:
        raise HTTPException(409, "Another gift is being created")
    _user_jobs.add(uid)
    job_id = uuid.uuid4().hex
    folder = _job_dir(uid, job_id)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    try:
        for index, photo in enumerate(photos):
            payload = await _read_upload(photo, settings.max_upload_mb * 1024 * 1024)
            path = folder / f"photo_{index}.jpg"
            try:
                await asyncio.to_thread(save_photo, payload, path)
            except (OSError, ValueError) as exc:
                raise HTTPException(422, f"Could not read photo {index + 1}") from exc
            paths.append(path)
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        _user_jobs.discard(uid)
        raise
    job = {"id": job_id, "user_id": uid, "goals": parsed, "style": style,
           "language": language, "status": "generating",
           "free": free, "price": None, "stars": None, "invoice": None, "order_id": None,
           "progress": "plan"}
    _write_job(uid, job_id, job)
    task = asyncio.create_task(_generate_gift(uid, job_id, paths, user.get("username")))
    task.job_id = job_id
    _track(task)
    return _public_job(job)


async def _generate_gift(uid: int, job_id: str, photos: list[Path], username: str | None) -> None:
    settings = get_settings()
    job = _read_job(uid, job_id)
    try:
        plan = await GoalScenePlanner(settings).plan(
            photos=photos, goals=job["goals"], lang=job["language"])
        job["progress"] = "render"
        _write_job(uid, job_id, job)
        renderer = ReplicateVisionBoardRenderer(
            output_dir=settings.generated_dir / "wallpapers" / str(uid) / job_id,
            model=settings.wallpaper_image_model, quality=settings.wallpaper_image_quality)
        formats = await renderer.generate_goal_story(
            user_id=uid, photo_paths=photos, goals=job["goals"],
            assignments=plan.assignments, scenes=plan.scenes, style=job["style"])
        mobile, desktop = formats["mobile"], formats["desktop"]
        job["progress"] = "quality"
        _write_job(uid, job_id, job)
        await asyncio.to_thread(_validate_gift_files, mobile, desktop)
        await asyncio.to_thread(make_preview, mobile)
        if job["free"]:
            job["status"] = "ready"
        else:
            cost = plan.ai_cost_usd + renderer.total_cost_usd
            price = checkout_price_uah(cost, settings.usd_exchange_rate)
            async with async_session_maker() as session:
                order = await WallpaperOrderRepository(session).create(
                    telegram_user_id=uid, amount=price, mobile_path=str(mobile), desktop_path=str(desktop),
                    stars_amount=settings.gift_price_stars)
            job["order_id"] = order.id
            job["price"] = str(price)
            job["stars"] = order.stars_amount
            job["status"] = "payment"
        _write_job(uid, job_id, job)
    except ImageSafetyError as exc:
        job["status"] = "blocked"
        job["error"] = "Please try another photo or clarify the wishes" if exc.stage == "input" else "A scene was declined; please try again"
        _write_job(uid, job_id, job)
    except Exception:
        logger.exception("Mini App gift failed for user %s job %s", uid, job_id)
        job["status"] = "payment_unavailable" if job.get("order_id") else "failed"
        job["error"] = ("The artwork is saved; payment is temporarily unavailable. Try the checkout again later."
                        if job.get("order_id") else "Could not finish your gift. Please try again later.")
        _write_job(uid, job_id, job)
    finally:
        # A cancelled task keeps the input for an explicit retry after restart.
        if job["status"] != "generating":
            for path in photos:
                path.unlink(missing_ok=True)
        _user_jobs.discard(uid)
        # Telegram is the notification channel; the complete files remain behind authenticated API.
        bot = getattr(__import__("app.main", fromlist=["app"]).app.state, "bot", None)
        if bot:
            try:
                await bot.send_message(uid, "💛 Подарунок готовий. Відкрийте майстерню в боті." if job["status"] in {"payment", "ready"}
                                       else "💛 Не вдалося завершити подарунок. Відкрийте майстерню, щоб спробувати знову.")
            except Exception:
                logger.exception("Could not notify gift customer %s", uid)


@router.get("/api/gifts/{job_id}")
async def gift_status(job_id: str, user: Annotated[dict, Depends(current_user)]) -> dict:
    job = _read_job(user["id"], job_id)
    if job["status"] == "generating" and job_id not in {
        getattr(task, "job_id", None) for task in _tasks if not task.done()
    }:
        job["status"] = "interrupted"
        _write_job(user["id"], job_id, job)
    return _public_job(job)


@router.post("/api/gifts/{job_id}/retry")
async def retry_gift(job_id: str, user: Annotated[dict, Depends(current_user)]) -> dict:
    uid = user["id"]
    job = _read_job(uid, job_id)
    if job["status"] != "interrupted" or uid in _user_jobs:
        raise HTTPException(409, "This gift cannot be resumed")
    folder = _job_dir(uid, job_id)
    paths = sorted(folder.glob("photo_*.jpg"))
    if not 1 <= len(paths) <= 7:
        raise HTTPException(409, "Please upload the photos again in a new gift")
    _user_jobs.add(uid)
    job["status"] = "generating"
    _write_job(uid, job_id, job)
    task = asyncio.create_task(_generate_gift(uid, job_id, paths, user.get("username")))
    task.job_id = job_id
    _track(task)
    return _public_job(job)


@router.post("/api/gifts/{job_id}/verify")
async def verify_gift(job_id: str, user: Annotated[dict, Depends(current_user)]) -> dict:
    job = _read_job(user["id"], job_id)
    if not job.get("order_id"):
        raise HTTPException(409, "No payment to check")
    async with async_session_maker() as session:
        repo = WallpaperOrderRepository(session)
        order = await repo.get_for_user(job["order_id"], user["id"])
        if order is None:
            raise HTTPException(404)
        if not order.paid:
            if order.stars_amount:
                return {"paid": False}
            verified = await PaymentService(get_settings()).verify_portmone_payment(
                order.id, order.amount, product="wallpaper")
            if verified is None:
                return {"paid": False}
            await repo.mark_paid(order, verified.payment_id)
    job["status"] = "ready"
    _write_job(user["id"], job_id, job)
    return {"paid": True}


@router.post("/api/gifts/{job_id}/checkout")
async def gift_checkout(job_id: str, request: Request,
                        user: Annotated[dict, Depends(current_user)]) -> dict:
    job = _read_job(user["id"], job_id)
    if not job.get("order_id") or job["status"] not in {"payment", "payment_unavailable"}:
        raise HTTPException(409, "No outstanding payment")
    async with async_session_maker() as session:
        order = await WallpaperOrderRepository(session).get_for_user(job["order_id"], user["id"])
    if order is None or order.paid:
        raise HTTPException(409, "No outstanding payment")
    if not order.stars_amount:
        raise HTTPException(409, "This historic order has no Star price")
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(503, "Bot is not running")
    url = await create_invoice(bot, OrderRef("wallpaper", order.id, user["id"], order.stars_amount))
    job["invoice"] = url
    job["status"] = "payment"
    job.pop("error", None)
    _write_job(user["id"], job_id, job)
    return {"url": url, "stars": order.stars_amount, "provider": "stars"}


@router.get("/api/gifts/{job_id}/files/{kind}")
async def gift_file(job_id: str, kind: str, user: Annotated[dict, Depends(current_user)]) -> FileResponse:
    job = _read_job(user["id"], job_id)
    if job["status"] not in {"payment", "payment_unavailable", "ready"}:
        raise HTTPException(404)
    if job.get("order_id"):
        async with async_session_maker() as session:
            order = await WallpaperOrderRepository(session).get_for_user(job["order_id"], user["id"])
        if order is None:
            raise HTTPException(404)
        mobile, desktop = Path(order.mobile_path), Path(order.desktop_path)
        unlocked = order.paid
    else:
        if not job["free"]:
            raise HTTPException(403)
        root = get_settings().generated_dir / "wallpapers" / str(user["id"]) / job_id
        mobile = root / f"manifestation_{user['id']}_mobile.png"
        desktop = root / f"manifestation_{user['id']}_desktop.png"
        unlocked = True
    if kind == "preview":
        path = mobile.with_name(f"preview_{mobile.stem}.jpg")
    elif unlocked and kind in {"mobile", "desktop"}:
        path = mobile if kind == "mobile" else desktop
    elif unlocked and kind == "print":
        path = await asyncio.to_thread(create_print_bundle, job.get("order_id") or user["id"],
            mobile, desktop, width_mm=get_settings().print_poster_width_mm,
            height_mm=get_settings().print_poster_height_mm, dpi=get_settings().print_dpi)
    else:
        raise HTTPException(403, "Payment has not been confirmed")
    if not path.is_file():
        raise HTTPException(404, "File unavailable")
    return FileResponse(path, filename=path.name if kind != "preview" else None,
                        headers={"Cache-Control": "private, no-store"})


async def _own_wallpaper(order_id: int, uid: int) -> WallpaperOrder:
    async with async_session_maker() as session:
        order = await WallpaperOrderRepository(session).get_for_user(order_id, uid)
    if order is None:
        raise HTTPException(404, "Order not found")
    return order


async def _deliver_email(uid: int, kind: str, ref: str, email: str, paths: list[Path]) -> dict:
    try:
        address = normalize_recipient(email)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    async with async_session_maker() as session:
        count = await session.scalar(select(func.count(EmailDelivery.id)).where(
            EmailDelivery.owner_telegram_id == uid, EmailDelivery.kind == kind,
            EmailDelivery.reference_id == ref,
            EmailDelivery.created_at >= datetime.now(UTC) - timedelta(hours=24)))
        if count >= 3:
            raise HTTPException(429, "Email limit reached for this order today")
    try:
        await send_ready_order_email(address, f"Food Porn · ваш заказ #{ref}", paths)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.exception("Could not email %s order %s", kind, ref)
        raise HTTPException(503, "Не удалось отправить письмо; проверьте SMTP и повторите позже") from exc
    async with async_session_maker() as session:
        session.add(EmailDelivery(owner_telegram_id=uid, kind=kind,
                                  reference_id=ref, recipient_email=address))
        await session.commit()
    return {"sent": True, "email": address}


async def _create_share(uid: int, kind: str, ref: str, request: Request) -> dict:
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(503, "Bot is not running")
    async with async_session_maker() as session:
        link = await session.scalar(select(ShareLink).where(
            ShareLink.owner_telegram_id == uid, ShareLink.kind == kind,
            ShareLink.reference_id == ref).limit(1))
        if link is None:
            link = ShareLink(token=secrets.token_urlsafe(24), owner_telegram_id=uid,
                             kind=kind, reference_id=ref)
            session.add(link)
            await session.commit()
    bot_info = await bot.get_me()
    url = f"https://t.me/{bot_info.username}?start=share_{link.token}"
    answer = {"url": url}
    if get_settings().miniapp_url:
        answer["present_url"] = f"{get_settings().miniapp_url.rstrip('/')}/open/{link.token}"
    try:
        prepared = await bot.save_prepared_inline_message(
            user_id=uid,
            result=InlineQueryResultArticle(
                id=secrets.token_hex(8), title="Особливий подарунок",
                input_message_content=InputTextMessageContent(
                    message_text=f"Для тебе — дещо особливе ✦\nВідкрий подарунок: {url}"),
            ),
            allow_user_chats=True, allow_group_chats=True,
        )
        answer["prepared_message_id"] = prepared.id
    except Exception:
        logger.exception("Native gift sharing unavailable; using deep link")
    return answer


@router.post("/api/menus/{menu_id}/email")
async def email_menu(menu_id: int, payload: dict,
                     user: Annotated[dict, Depends(current_user)]) -> dict:
    menu = await _own_menu(menu_id, user["id"])
    if not menu.is_paid or menu.status in (MenuStatus.QUEUED, MenuStatus.FAILED):
        raise HTTPException(403, "Complete files are not available")
    files = {file.kind: Path(file.path) for file in menu.files}
    if any(kind not in files for kind in (FileKind.PRINT_PDF, FileKind.RECIPE_SHEET)):
        raise HTTPException(409, "Полный заказ пока не собран")
    return await _deliver_email(user["id"], "menu", str(menu_id), str(payload.get("email", "")),
                                [files[kind] for kind in (FileKind.PRINT_PDF, FileKind.RECIPE_SHEET)])


@router.post("/api/menus/{menu_id}/share")
async def share_menu(menu_id: int, request: Request,
                     user: Annotated[dict, Depends(current_user)]) -> dict:
    menu = await _own_menu(menu_id, user["id"])
    if not menu.is_paid or menu.status in (MenuStatus.QUEUED, MenuStatus.FAILED):
        raise HTTPException(403, "Complete the order before sharing")
    return await _create_share(user["id"], "menu", str(menu_id), request)


@router.post("/api/gifts/{job_id}/email")
async def email_gift(job_id: str, payload: dict,
                     user: Annotated[dict, Depends(current_user)]) -> dict:
    job = _read_job(user["id"], job_id)
    if job["status"] != "ready":
        raise HTTPException(403, "Gift is not ready")
    if job.get("order_id"):
        order = await _own_wallpaper(job["order_id"], user["id"])
        if not order.paid:
            raise HTTPException(403)
        paths = [Path(order.mobile_path), Path(order.desktop_path)]
    else:
        root = get_settings().generated_dir / "wallpapers" / str(user["id"]) / job_id
        paths = [root / f"manifestation_{user['id']}_mobile.png",
                 root / f"manifestation_{user['id']}_desktop.png"]
    if all(path.is_file() for path in paths):
        bundle = await asyncio.to_thread(
            create_print_bundle, job.get("order_id") or user["id"], paths[0], paths[1],
            width_mm=get_settings().print_poster_width_mm,
            height_mm=get_settings().print_poster_height_mm, dpi=get_settings().print_dpi)
        paths.append(bundle)
    return await _deliver_email(user["id"], "gift", job_id, str(payload.get("email", "")), paths)


@router.post("/api/gifts/{job_id}/share")
async def share_gift(job_id: str, request: Request,
                     user: Annotated[dict, Depends(current_user)]) -> dict:
    job = _read_job(user["id"], job_id)
    if job["status"] != "ready":
        raise HTTPException(403, "Gift is not ready")
    if job.get("order_id") and not (await _own_wallpaper(job["order_id"], user["id"])).paid:
        raise HTTPException(403)
    return await _create_share(user["id"], "gift", job_id, request)


@router.get("/api/wallpapers/{order_id}")
async def wallpaper_status(order_id: int, user: Annotated[dict, Depends(current_user)]) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    return {"id": order.id, "paid": order.paid, "amount": str(order.amount),
            "stars": order.stars_amount,
            "created_at": order.created_at.isoformat() if order.created_at else None}


@router.post("/api/wallpapers/{order_id}/email")
async def email_wallpaper(order_id: int, payload: dict,
                          user: Annotated[dict, Depends(current_user)]) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    if not order.paid:
        raise HTTPException(403, "Gift is not ready")
    paths = [Path(order.mobile_path), Path(order.desktop_path)]
    if not all(path.is_file() for path in paths):
        raise HTTPException(409, "Полный заказ пока не собран")
    bundle = await asyncio.to_thread(
        create_print_bundle, order.id, paths[0], paths[1],
        width_mm=get_settings().print_poster_width_mm,
        height_mm=get_settings().print_poster_height_mm, dpi=get_settings().print_dpi)
    return await _deliver_email(user["id"], "wallpaper", str(order_id),
                                str(payload.get("email", "")), paths + [bundle])


@router.post("/api/wallpapers/{order_id}/share")
async def share_wallpaper(order_id: int, request: Request,
                          user: Annotated[dict, Depends(current_user)]) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    if not order.paid:
        raise HTTPException(403, "Gift is not ready")
    return await _create_share(user["id"], "wallpaper", str(order_id), request)


@router.post("/api/wallpapers/{order_id}/checkout")
async def wallpaper_checkout(order_id: int, request: Request,
                             user: Annotated[dict, Depends(current_user)]) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    if order.paid:
        raise HTTPException(409, "Already paid")
    if not order.stars_amount:
        raise HTTPException(409, "This historic order has no Star price")
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(503, "Bot is not running")
    url = await create_invoice(bot, OrderRef("wallpaper", order.id, user["id"], order.stars_amount))
    return {"url": url, "stars": order.stars_amount, "provider": "stars"}


@router.post("/api/wallpapers/{order_id}/verify")
async def verify_wallpaper(order_id: int, user: Annotated[dict, Depends(current_user)]) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    if not order.paid:
        if order.stars_amount:
            return {"paid": False}
        verified = await PaymentService(get_settings()).verify_portmone_payment(
            order.id, order.amount, product="wallpaper")
        if verified is None:
            return {"paid": False}
        async with async_session_maker() as session:
            repo = WallpaperOrderRepository(session)
            current = await repo.get_for_user(order_id, user["id"])
            if current is None:
                raise HTTPException(404)
            if not current.paid:
                await repo.mark_paid(current, verified.payment_id)
    return {"paid": True}


@router.get("/api/wallpapers/{order_id}/files/{kind}")
async def wallpaper_file(order_id: int, kind: str, user: Annotated[dict, Depends(current_user)]) -> FileResponse:
    order = await _own_wallpaper(order_id, user["id"])
    mobile, desktop = Path(order.mobile_path), Path(order.desktop_path)
    if kind == "preview":
        path = mobile.with_name(f"preview_{mobile.stem}.jpg")
        if not path.is_file() and mobile.is_file():
            path = await asyncio.to_thread(make_preview, mobile)
    elif not order.paid:
        raise HTTPException(403, "Payment has not been confirmed")
    elif kind in {"mobile", "desktop"}:
        path = mobile if kind == "mobile" else desktop
    elif kind == "print":
        path = await asyncio.to_thread(create_print_bundle, order.id, mobile, desktop,
            width_mm=get_settings().print_poster_width_mm,
            height_mm=get_settings().print_poster_height_mm, dpi=get_settings().print_dpi)
    else:
        raise HTTPException(404)
    if not path.is_file():
        raise HTTPException(404, "File unavailable")
    return FileResponse(path, filename=path.name if kind != "preview" else None,
                        headers={"Cache-Control": "private, no-store"})


@router.post("/api/menus")
async def create_menu(
    request: Request, cover: Annotated[UploadFile, File()],
    spread: Annotated[UploadFile, File()],
    user: Annotated[dict, Depends(current_user)],
    dishes: str = Form(...), name: str = Form(""), phone: str = Form(""),
    language: str = Form("uk"),
) -> dict:
    settings = get_settings()
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(503, "Run the Mini App together with the bot via launcher.py start")
    if not await has_free_generation_access(user["id"], user.get("username"), settings, async_session_maker) and settings.menu_price_stars < 1:
        raise HTTPException(503, "Payment is temporarily unavailable; generation has not started")
    if language not in {"uk", "ru", "en"}:
        raise HTTPException(422, "Unknown language")
    try:
        items = json.loads(dishes)
        if not isinstance(items, list) or not 1 <= len(items) <= 18:
            raise ValueError()
        for item in items:
            if (not isinstance(item, dict) or item.get("category") not in ItemCategory._value2member_map_
                    or not isinstance(item.get("title"), str) or not 2 <= len(item["title"].strip()) <= 180):
                raise ValueError()
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Add 1–18 dishes with a category and name") from exc
    async with async_session_maker() as session:
        customer_repo = CustomerRepository(session)
        customer = await customer_repo.by_telegram_id(user["id"])
        if customer is None:
            phone = phone.strip()
            if not re.fullmatch(r"\+[1-9]\d{7,14}", phone) or not name.strip():
                raise HTTPException(422, "Enter your name and international phone number")
            existing = await customer_repo.by_phone(phone)
            if existing and existing.telegram_user_id != user["id"]:
                raise HTTPException(409, "This phone belongs to another account")
            customer = await customer_repo.register(
                telegram_user_id=user["id"], phone=phone, name=name.strip()[:100],
                language=Language(language),
                country="Not provided", city="Not provided")
        repo = MenuRepository(session)
        menu = await repo.create(customer)
        try:
            storage = StorageService(settings)
            paths = {}
            for role, upload in (("cover", cover), ("spread", spread)):
                payload = await _read_upload(upload, settings.max_upload_mb * 1024 * 1024)
                try:
                    paths[role] = await asyncio.to_thread(storage.save_validated_bytes, payload, menu_id=menu.id, role=role)
                except InvalidImageError as exc:
                    raise HTTPException(422, f"Could not read {role} photo") from exc
            await repo.set_photos(menu.id, cover=str(paths["cover"]), spread=str(paths["spread"]))
            for index, item in enumerate(items, 1):
                await repo.add_item(menu_id=menu.id, category=ItemCategory(item["category"]),
                                    position=index, title=item["title"])
            await repo.set_status(menu.id, MenuStatus.QUEUED)
        except Exception:
            await repo.set_status(menu.id, MenuStatus.FAILED, "Incomplete upload")
            raise
    await pipeline.submit(menu.id, user["id"])
    return {"id": menu.id, "status": "queued"}


@router.post("/api/language")
async def set_language(payload: dict, user: Annotated[dict, Depends(current_user)]) -> dict:
    language = payload.get("language")
    if language not in {"uk", "ru", "en"}:
        raise HTTPException(422, "Unknown language")
    async with async_session_maker() as session:
        customer = await CustomerRepository(session).by_telegram_id(user["id"])
        if customer:
            customer.language = Language(language)
            await session.commit()
    return {"language": language}


async def _own_menu(menu_id: int, uid: int):
    async with async_session_maker() as session:
        menu = await MenuRepository(session).get(menu_id, full=True)
        if menu is None or menu.customer.telegram_user_id != uid:
            raise HTTPException(404)
        return menu


@router.get("/api/menus/{menu_id}")
async def menu_status(menu_id: int, user: Annotated[dict, Depends(current_user)]) -> dict:
    menu = await _own_menu(menu_id, user["id"])
    selected = [item for item in menu.items if item.title != "—"]
    completed = sum(item.generation_status.value == "done" for item in selected)
    return {"id": menu.id, "status": menu.status.value, "paid": menu.is_paid,
            "amount": str(menu.price_amount) if menu.price_amount else None,
            "stars": menu.stars_amount,
            "progress": {"completed": completed, "total": len(selected)},
            "items": [{"title": item.title, "category": item.category.value} for item in menu.items],
            "error": menu.error_message if menu.status == MenuStatus.FAILED else None}


@router.post("/api/menus/{menu_id}/checkout")
async def menu_checkout(menu_id: int, request: Request,
                        user: Annotated[dict, Depends(current_user)]) -> dict:
    menu = await _own_menu(menu_id, user["id"])
    if menu.is_paid or menu.status != MenuStatus.WAITING_FOR_PAYMENT or menu.price_amount is None:
        raise HTTPException(409, "No outstanding payment for this menu")
    if not menu.stars_amount:
        raise HTTPException(409, "This historic order has no Star price")
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(503, "Bot is not running")
    url = await create_invoice(bot, OrderRef("menu", menu.id, user["id"], menu.stars_amount))
    return {"url": url, "stars": menu.stars_amount, "provider": "stars"}


@router.post("/api/menus/{menu_id}/verify")
async def verify_menu(menu_id: int, user: Annotated[dict, Depends(current_user)]) -> dict:
    menu = await _own_menu(menu_id, user["id"])
    if menu.status in (MenuStatus.FAILED, MenuStatus.QUEUED):
        raise HTTPException(409, "The print file is being repaired or is incomplete")
    if not menu.is_paid:
        if menu.stars_amount:
            return {"paid": False}
        if menu.status != MenuStatus.WAITING_FOR_PAYMENT or menu.price_amount is None:
            raise HTTPException(409, "No payment to check")
        verified = await PaymentService(get_settings()).verify_portmone_payment(menu.id, menu.price_amount)
        if verified is None:
            return {"paid": False}
        pdf = next((Path(item.path) for item in menu.files if item.kind == FileKind.PRINT_PDF), None)
        recipes = next((Path(item.path) for item in menu.files if item.kind == FileKind.RECIPE_SHEET), None)
        if pdf is None or not pdf.is_file() or recipes is None or not recipes.is_file():
            raise HTTPException(503, "Payment received, but print files are temporarily unavailable")
        async with async_session_maker() as session:
            await MenuRepository(session).mark_as_paid(menu.id, verified.payment_id, "portmone")
        menu.is_paid = True
    if menu.payment_system != "telegram_stars" and menu.status != MenuStatus.SENT_TO_PRINTSHOP:
        pdf = next((Path(item.path) for item in menu.files if item.kind == FileKind.PRINT_PDF), None)
        if pdf and pdf.is_file():
            try:
                sent = await PrintshopService(get_settings()).dispatch_to_printshop(
                    menu.id, pdf, f"Telegram User ID: {user['id']}")
                if sent:
                    async with async_session_maker() as session:
                        await MenuRepository(session).mark_sent_to_printshop(menu.id)
            except Exception:
                logger.exception("Printshop delivery failed for paid menu %s", menu.id)
    return {"paid": True}


@router.get("/api/menus/{menu_id}/files/{kind}")
async def menu_file(menu_id: int, kind: str, user: Annotated[dict, Depends(current_user)]) -> FileResponse:
    menu = await _own_menu(menu_id, user["id"])
    if menu.status in (MenuStatus.FAILED, MenuStatus.QUEUED) and kind != "preview":
        raise HTTPException(409, "The print file is being repaired or is incomplete")
    allowed = {"preview": FileKind.PREVIEW_OUTSIDE, "pdf": FileKind.PRINT_PDF,
               "recipes": FileKind.RECIPE_SHEET}
    if kind not in allowed or (kind != "preview" and not menu.is_paid):
        raise HTTPException(403)
    item = next((file for file in menu.files if file.kind == allowed[kind]), None)
    if item is None or not Path(item.path).is_file():
        raise HTTPException(404)
    return FileResponse(item.path, filename=Path(item.path).name if kind != "preview" else None,
                        headers={"Cache-Control": "private, no-store"})


@router.get("/api/menus/{menu_id}/evening")
async def menu_evening(menu_id: int, user: Annotated[dict, Depends(current_user)]) -> dict:
    menu = await _own_menu(menu_id, user["id"])
    if not menu.is_paid or menu.status in (MenuStatus.DRAFT, MenuStatus.QUEUED, MenuStatus.FAILED):
        raise HTTPException(403, "Evening plan unlocks after payment")
    path = get_settings().generated_dir / str(menu_id) / "evening_plan.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
        if plan.get("version") != 1 or not isinstance(plan.get("shopping"), list):
            raise ValueError("Invalid plan")
        return plan
    except (OSError, ValueError, TypeError, AttributeError):
        raise HTTPException(404, "This order predates the evening plan; use the recipe PDF") from None


@router.get("/api/admin")
async def admin_dashboard(user: Annotated[dict, Depends(current_user)]) -> dict:
    settings = get_settings()
    if user["id"] not in settings.admin_telegram_ids:
        raise HTTPException(403)
    async with async_session_maker() as session:
        customers = await session.scalar(select(func.count(Customer.id)))
        menus = await session.scalar(select(func.count(Menu.id)))
        gifts = await session.scalar(select(func.count(WallpaperOrder.id)))
        paid_gifts = await session.scalar(select(func.count(WallpaperOrder.id)).where(WallpaperOrder.paid.is_(True)))
        gift_revenue = await session.scalar(select(func.sum(WallpaperOrder.amount)).where(
            WallpaperOrder.paid.is_(True), or_(WallpaperOrder.payment_system.is_(None),
                                               WallpaperOrder.payment_system != "telegram_stars")))
        menu_revenue = await session.scalar(select(func.sum(Menu.price_amount)).where(
            Menu.is_paid.is_(True), or_(Menu.payment_system.is_(None),
                                       Menu.payment_system != "telegram_stars")))
        gift_stars = await session.scalar(select(func.sum(WallpaperOrder.stars_amount)).where(
            WallpaperOrder.paid.is_(True), WallpaperOrder.payment_system == "telegram_stars"))
        menu_stars = await session.scalar(select(func.sum(Menu.stars_amount)).where(
            Menu.is_paid.is_(True), Menu.payment_system == "telegram_stars"))
        vip = await get_vip_users(session, settings.default_vip_users)
        menu_price = await get_setting(session, "menu_price_uah", str(settings.menu_price))
        recent = (await session.execute(select(Menu).order_by(Menu.id.desc()).limit(10))).scalars().all()
    return {"customers": customers, "menus": menus, "gifts": gifts, "paid_gifts": paid_gifts,
            "vip": vip, "menu_price": menu_price,
            "revenue": str((gift_revenue or 0) + (menu_revenue or 0)),
            "stars_revenue": (gift_stars or 0) + (menu_stars or 0),
            "stars_ready": settings.menu_price_stars > 0 and settings.gift_price_stars > 0,
            "payment_ready": PaymentService(settings).portmone_ready,
            "recent": [{"id": item.id, "status": item.status.value} for item in recent]}


@router.post("/api/admin/vip")
async def update_vip(payload: dict, user: Annotated[dict, Depends(current_user)]) -> dict:
    if user["id"] not in get_settings().admin_telegram_ids:
        raise HTTPException(403)
    names = payload.get("names")
    if not isinstance(names, list) or len(names) > 100 or any(
        not isinstance(name, str) or not re.fullmatch(r"@?[A-Za-z0-9_]{5,32}", name) for name in names
    ):
        raise HTTPException(422, "Provide valid Telegram usernames")
    normalized = list(dict.fromkeys(name.lstrip("@").casefold() for name in names))
    async with async_session_maker() as session:
        await set_setting(session, "vip_usernames", ",".join(normalized))
    return {"vip": normalized}


@router.post("/api/admin/menu-price")
async def update_menu_price(payload: dict, user: Annotated[dict, Depends(current_user)]) -> dict:
    if user["id"] not in get_settings().admin_telegram_ids:
        raise HTTPException(403)
    try:
        price = Decimal(str(payload["price"])).quantize(Decimal("0.01"))
        if not price.is_finite() or not Decimal("1") <= price <= Decimal("100000"):
            raise ValueError()
    except (KeyError, ValueError, ArithmeticError) as exc:
        raise HTTPException(422, "Enter a price from 1 to 100000 UAH") from exc
    async with async_session_maker() as session:
        await set_setting(session, "menu_price_uah", str(price))
    return {"menu_price": str(price)}
