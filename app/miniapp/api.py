"""Authenticated Mini App: gifts, menus, payments, files and administration."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import func, select

from app.bot.handlers.wallpaper import make_preview, parse_five_goals, save_photo
from app.config import get_settings
from app.crm.service import dashboard as crm_dashboard
from app.crm.service import save_settings as crm_save_settings
from app.database.models import (
    EmailDelivery,
    FileKind,
    ItemCategory,
    Language,
    Menu,
    MenuStatus,
    ScheduledDelivery,
    ShareLink,
    WallpaperExport,
    WallpaperOrder,
    WallpaperSceneVersion,
)
from app.database.repositories import (
    CustomerRepository,
    MenuRepository,
    WallpaperOrderRepository,
    WallpaperStudioRepository,
    WayForPayPaymentRepository,
)
from app.database.session import async_session_maker
from app.miniapp.auth import current_user
from app.services.admin_access import has_admin_access
from app.services.dish_input import normalize_dish_payload
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
from app.services.wallpaper_studio import (
    EDIT_MODES,
    WallpaperExportService,
    WallpaperSceneEditor,
    archive_source_photos,
    current_scene_preview,
)
from app.services.wayforpay import WayForPayService, apply_verified_payment

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/miniapp")
STATIC = Path(__file__).with_name("static")
_tasks: set[asyncio.Task] = set()
_user_jobs: set[int] = set()
_studio_jobs: set[int] = set()


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


async def _wayforpay_checkout(
    *, product: str, reference_id: int, owner_id: int, description: str
) -> dict[str, str]:
    service = WayForPayService(get_settings())
    if not service.ready:
        raise HTTPException(503, "WayForPay is temporarily unavailable")
    async with async_session_maker() as session:
        attempt, url = await service.create_checkout(
            session,
            telegram_user_id=owner_id,
            product=product,
            reference_id=reference_id,
            description=description,
        )
    return {
        "url": url,
        "amount": f"{attempt.amount:.2f}",
        "currency": "UAH",
        "provider": "wayforpay",
    }


async def _wayforpay_is_paid(product: str, reference_id: int, owner_id: int) -> bool:
    service = WayForPayService(get_settings())
    if not service.ready:
        return False
    async with async_session_maker() as session:
        repository = WayForPayPaymentRepository(session)
        attempt = await repository.latest_for_product(product, str(reference_id), owner_id)
        if attempt is None:
            return False
        if attempt.status == "approved":
            return True
        try:
            payload = await service.check_status(attempt)
            return await apply_verified_payment(session, attempt, payload)
        except Exception:
            logger.exception("Mini App WayForPay check failed for %s #%s", product, reference_id)
            return False


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
        "admin": await has_admin_access(uid, user.get("username"), settings, async_session_maker),
        "language": customer.language.value if customer else user.get("language_code", "uk")[:2],
        "customer": {"name": customer.name, "phone": customer.phone} if customer else None,
        "payment_ready": settings.menu_price_stars > 0 and settings.gift_price_stars > 0,
        "menu_payment_ready": settings.menu_price_stars > 0,
        "gift_payment_ready": settings.gift_price_stars > 0,
        "wayforpay_ready": WayForPayService(settings).ready,
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
    source_channel = user.get("source_channel", "telegram")
    stars_ready = source_channel == "telegram" and settings.gift_price_stars > 0
    if not free and not (stars_ready or PaymentService(settings).portmone_ready):
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
           "source_channel": source_channel,
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
        planner = GoalScenePlanner(settings)
        if hasattr(planner, "set_tracking_context"):
            planner.set_tracking_context(user_id=uid, order_id=job_id)
        plan = await planner.plan(photos=photos, goals=job["goals"], lang=job["language"])
        job["progress"] = "render"
        _write_job(uid, job_id, job)
        render_dir = settings.generated_dir / "wallpapers" / str(uid) / job_id
        archived_sources = await asyncio.to_thread(archive_source_photos, photos, render_dir)
        if not isinstance(archived_sources, list):
            archived_sources = []
        renderer = ReplicateVisionBoardRenderer(
            output_dir=render_dir,
            model=settings.wallpaper_image_model, quality=settings.wallpaper_image_quality)
        if hasattr(renderer, "set_tracking_context"):
            renderer.set_tracking_context(user_id=uid, order_id=job_id)
        formats = await renderer.generate_goal_story(
            user_id=uid, photo_paths=photos, goals=job["goals"],
            assignments=plan.assignments, scenes=plan.scenes, style=job["style"])
        mobile, desktop = formats["mobile"], formats["desktop"]
        raw_mobile = formats.get("raw_mobile", mobile)
        raw_desktop = formats.get("raw_desktop", desktop)
        job["progress"] = "quality"
        _write_job(uid, job_id, job)
        await asyncio.to_thread(_validate_gift_files, mobile, desktop)
        await asyncio.to_thread(make_preview, mobile)
        if job["free"]:
            async with async_session_maker() as session:
                order = WallpaperOrder(
                    telegram_user_id=uid, amount=Decimal("0"), stars_amount=0,
                    mobile_path=str(mobile), desktop_path=str(desktop), paid=True,
                    payment_id=f"VIP_JOB_{job_id}", payment_system="vip_bypass",
                    paid_at=datetime.now(UTC),
                    source_channel=job.get("source_channel", "telegram"),
                    goals=list(job["goals"]),
                    scene_prompts=list(plan.scenes),
                    scene_assignments=list(plan.assignments),
                    source_photo_paths=archived_sources,
                    visual_style=job["style"],
                    original_mobile_path=str(mobile),
                    original_desktop_path=str(desktop),
                    raw_mobile_path=str(raw_mobile),
                    raw_desktop_path=str(raw_desktop),
                )
                session.add(order)
                await session.commit()
                await session.refresh(order)
            job["order_id"] = order.id
            job["status"] = "ready"
        else:
            cost = plan.ai_cost_usd + renderer.total_cost_usd
            price = checkout_price_uah(cost, settings.usd_exchange_rate)
            async with async_session_maker() as session:
                order = await WallpaperOrderRepository(session).create(
                    telegram_user_id=uid, amount=price, mobile_path=str(mobile), desktop_path=str(desktop),
                    stars_amount=(
                        settings.gift_price_stars
                        if job.get("source_channel", "telegram") == "telegram"
                        else None
                    ),
                    source_channel=job.get("source_channel", "telegram"),
                    goals=list(job["goals"]),
                    scene_prompts=list(plan.scenes),
                    scene_assignments=list(plan.assignments),
                    source_photo_paths=archived_sources,
                    visual_style=job["style"],
                    raw_mobile_path=str(raw_mobile),
                    raw_desktop_path=str(raw_desktop),
                )
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
        if bot and job.get("source_channel", "telegram") == "telegram":
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
            if await _wayforpay_is_paid("wallpaper", order.id, user["id"]):
                job["status"] = "ready"
                _write_job(user["id"], job_id, job)
                return {"paid": True}
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
                        user: Annotated[dict, Depends(current_user)],
                        provider: str | None = None) -> dict:
    job = _read_job(user["id"], job_id)
    if not job.get("order_id") or job["status"] not in {"payment", "payment_unavailable"}:
        raise HTTPException(409, "No outstanding payment")
    async with async_session_maker() as session:
        order = await WallpaperOrderRepository(session).get_for_user(job["order_id"], user["id"])
    if order is None or order.paid:
        raise HTTPException(409, "No outstanding payment")
    if provider == "wayforpay":
        return await _wayforpay_checkout(
            product="wallpaper",
            reference_id=order.id,
            owner_id=user["id"],
            description=f"Food Porn digital gift #{order.id}",
        )
    if order.source_channel == "telegram" and order.stars_amount:
        bot = getattr(request.app.state, "bot", None)
        if bot is None:
            raise HTTPException(503, "Bot is not running")
        url = await create_invoice(
            bot, OrderRef("wallpaper", order.id, user["id"], order.stars_amount)
        )
        provider = "stars"
    else:
        payment = PaymentService(get_settings())
        if not payment.portmone_ready:
            raise HTTPException(503, "Card payment is temporarily unavailable")
        url = await payment.create_portmone_invoice(
            order.id,
            order.amount,
            f"Food Porn digital gift #{order.id}",
            product="wallpaper",
        )
        provider = "portmone"
    job["invoice"] = url
    job["status"] = "payment"
    job.pop("error", None)
    _write_job(user["id"], job_id, job)
    return {
        "url": url,
        "stars": order.stars_amount,
        "amount": str(order.amount),
        "currency": "UAH" if provider == "portmone" else None,
        "provider": provider,
    }


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


@router.post("/api/deliveries/schedule")
async def schedule_delivery(
    payload: dict, user: Annotated[dict, Depends(current_user)]
) -> dict:
    """Schedule a paid digital gift without revealing its price to the recipient."""
    kind = str(payload.get("kind") or "")
    reference = str(payload.get("reference_id") or "")
    email = normalize_recipient(str(payload.get("email") or ""))
    try:
        send_at = datetime.fromisoformat(str(payload.get("send_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "send_at must be an ISO date with timezone") from exc
    if send_at.tzinfo is None:
        raise HTTPException(422, "send_at must include a timezone")
    send_at = send_at.astimezone(UTC)
    now = datetime.now(UTC)
    if not now + timedelta(minutes=5) <= send_at <= now + timedelta(days=365):
        raise HTTPException(422, "Delivery must be 5 minutes to 365 days in the future")

    if kind == "menu":
        menu = await _own_menu(int(reference), user["id"])
        if not menu.is_paid:
            raise HTTPException(403, "Complete the order before scheduling")
        files = {item.kind: Path(item.path) for item in menu.files}
        paths = [files.get(FileKind.PRINT_PDF), files.get(FileKind.RECIPE_SHEET)]
    elif kind == "wallpaper":
        order = await _own_wallpaper(int(reference), user["id"])
        if not order.paid:
            raise HTTPException(403, "Complete the order before scheduling")
        paths = [Path(order.mobile_path), Path(order.desktop_path)]
    elif kind == "gift":
        job = _read_job(user["id"], reference)
        if job.get("status") != "ready":
            raise HTTPException(403, "Gift is not ready")
        order = await _own_wallpaper(int(job["order_id"]), user["id"])
        if not order.paid:
            raise HTTPException(403, "Complete the order before scheduling")
        paths = [Path(order.mobile_path), Path(order.desktop_path)]
    else:
        raise HTTPException(422, "Unknown delivery kind")
    attachments = [path for path in paths if path is not None]
    if len(attachments) != len(paths) or not all(path.is_file() for path in attachments):
        raise HTTPException(409, "Complete files are not ready")
    async with async_session_maker() as session:
        delivery = ScheduledDelivery(
            owner_user_id=user["id"],
            kind=kind,
            reference_id=reference,
            recipient_email=email,
            subject="Food Porn · для вас подготовлен особенный подарок",
            attachments=[str(path) for path in attachments],
            send_at=send_at,
            status="pending",
        )
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)
    return {"id": delivery.id, "status": delivery.status, "send_at": send_at.isoformat()}


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


def _scene_version_payload(version: WallpaperSceneVersion) -> dict:
    return {
        "id": version.id,
        "scene_index": version.scene_index,
        "number": version.version_number,
        "mode": version.edit_mode,
        "instruction": version.instruction,
        "selected": version.is_selected,
        "cost_usd": str(version.ai_cost_usd),
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "preview_url": f"/miniapp/api/wallpapers/{version.order_id}/studio/versions/{version.id}",
    }


@router.get("/api/wallpapers/{order_id}/studio")
async def wallpaper_studio(order_id: int, user: Annotated[dict, Depends(current_user)]) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    if not order.paid:
        raise HTTPException(403, "Scene Studio unlocks after payment")
    async with async_session_maker() as session:
        repository = WallpaperStudioRepository(session)
        versions = await repository.versions(order.id)
        exports = await repository.exports(order.id)
    revision = WallpaperExportService(order).source_revision
    return {
        "order_id": order.id,
        "editable": bool(order.goals and order.scene_prompts and order.source_photo_paths),
        "goals": list(order.goals or []),
        "scenes": list(order.scene_prompts or []),
        "locked": list(order.locked_scene_indexes or []),
        "style": order.visual_style or "dark",
        "final_phrase": order.final_phrase or "",
        "versions": [_scene_version_payload(item) for item in versions],
        "exports": [
            {
                "kind": item.kind,
                "ready": item.source_revision == revision and Path(item.path).is_file(),
                "url": f"/miniapp/api/wallpapers/{order.id}/exports/{item.kind}",
            }
            for item in exports
        ],
    }


@router.post("/api/wallpapers/{order_id}/studio/scenes/{scene_index}/lock")
async def lock_wallpaper_scene(
    order_id: int, scene_index: int, payload: dict,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    await _own_wallpaper(order_id, user["id"])
    async with async_session_maker() as session:
        order = await session.get(WallpaperOrder, order_id)
        if order is None or order.telegram_user_id != user["id"] or not order.paid:
            raise HTTPException(404)
        if not 0 <= scene_index < len(order.goals or []):
            raise HTTPException(422, "Unknown scene")
        locked = set(int(value) for value in (order.locked_scene_indexes or []))
        if bool(payload.get("locked", True)):
            locked.add(scene_index)
        else:
            locked.discard(scene_index)
        order.locked_scene_indexes = sorted(locked)
        await session.commit()
        return {"scene_index": scene_index, "locked": scene_index in locked}


@router.post("/api/wallpapers/{order_id}/studio/scenes/{scene_index}/variants")
async def create_wallpaper_scene_variant(
    order_id: int, scene_index: int, payload: dict,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    if order_id in _studio_jobs:
        raise HTTPException(409, "Another Scene Studio operation is still running")
    edit_mode = str(payload.get("mode", "scene"))
    instruction = str(payload.get("instruction", ""))
    if edit_mode not in EDIT_MODES:
        raise HTTPException(422, "Choose scene, clothing, background or mood")
    _studio_jobs.add(order_id)
    try:
        async with async_session_maker() as session:
            order = await session.get(WallpaperOrder, order_id)
            if order is None or order.telegram_user_id != user["id"] or not order.paid:
                raise HTTPException(404)
            settings = get_settings()
            renderer = ReplicateVisionBoardRenderer(
                output_dir=Path(order.mobile_path).parent,
                model=settings.wallpaper_image_model,
                quality=settings.wallpaper_image_quality,
            )
            renderer.set_tracking_context(user_id=user["id"], order_id=f"studio:{order.id}")
            editor = WallpaperSceneEditor(renderer)
            try:
                path, cost = await editor.generate_variant(order, scene_index, edit_mode, instruction)
            except PermissionError as exc:
                raise HTTPException(409, str(exc)) from exc
            except (ValueError, FileNotFoundError) as exc:
                raise HTTPException(422, str(exc)) from exc
            version = await WallpaperStudioRepository(session).add_version(
                order_id=order.id,
                scene_index=scene_index,
                scene_asset_path=str(path),
                edit_mode=edit_mode,
                instruction=instruction,
                ai_cost_usd=cost,
            )
            return _scene_version_payload(version)
    finally:
        _studio_jobs.discard(order_id)


@router.post("/api/wallpapers/{order_id}/studio/versions/{version_id}/select")
async def select_wallpaper_scene_variant(
    order_id: int, version_id: int,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    if order_id in _studio_jobs:
        raise HTTPException(409, "Another Scene Studio operation is still running")
    _studio_jobs.add(order_id)
    try:
        async with async_session_maker() as session:
            order = await session.get(WallpaperOrder, order_id)
            if order is None or order.telegram_user_id != user["id"] or not order.paid:
                raise HTTPException(404)
            repository = WallpaperStudioRepository(session)
            version = await repository.get_version(version_id, order.id)
            if version is None:
                raise HTTPException(404, "Scene version not found")
            if version.scene_index in set(order.locked_scene_indexes or []):
                raise HTTPException(409, "Unlock this scene before selecting another version")
            renderer = ReplicateVisionBoardRenderer(output_dir=Path(order.mobile_path).parent)
            outputs = await WallpaperSceneEditor(renderer).apply_variant(
                order, version.scene_index, version.scene_asset_path, str(version.id)
            )
            order.mobile_path = str(outputs["mobile"])
            order.desktop_path = str(outputs["desktop"])
            order.raw_mobile_path = str(outputs["raw_mobile"])
            order.raw_desktop_path = str(outputs["raw_desktop"])
            await repository.select_version(order, version)
            await asyncio.to_thread(make_preview, Path(order.mobile_path))
            return {"selected": version.id, "scene_index": version.scene_index}
    finally:
        _studio_jobs.discard(order_id)


@router.get("/api/wallpapers/{order_id}/studio/scenes/{scene_index}/current")
async def wallpaper_scene_current(
    order_id: int, scene_index: int,
    user: Annotated[dict, Depends(current_user)],
) -> FileResponse:
    order = await _own_wallpaper(order_id, user["id"])
    if not order.paid or not 0 <= scene_index < len(order.goals or []):
        raise HTTPException(404)
    destination = Path(order.mobile_path).parent / "scene_studio" / f"current_scene_{scene_index}.png"
    await asyncio.to_thread(current_scene_preview, order, scene_index, destination)
    return FileResponse(destination, media_type="image/png", headers={"Cache-Control": "private, no-store"})


@router.get("/api/wallpapers/{order_id}/studio/versions/{version_id}")
async def wallpaper_scene_version_file(
    order_id: int, version_id: int,
    user: Annotated[dict, Depends(current_user)],
) -> FileResponse:
    await _own_wallpaper(order_id, user["id"])
    async with async_session_maker() as session:
        version = await WallpaperStudioRepository(session).get_version(version_id, order_id)
    if version is None or not Path(version.scene_asset_path).is_file():
        raise HTTPException(404)
    return FileResponse(version.scene_asset_path, media_type="image/png",
                        headers={"Cache-Control": "private, no-store"})


@router.post("/api/wallpapers/{order_id}/exports")
async def create_wallpaper_exports(
    order_id: int, user: Annotated[dict, Depends(current_user)]
) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    if not order.paid:
        raise HTTPException(403)
    service = WallpaperExportService(order)
    rendered = await asyncio.to_thread(service.render_static)
    async with async_session_maker() as session:
        repository = WallpaperStudioRepository(session)
        for kind, (path, width, height) in rendered.items():
            await repository.save_export(
                order_id=order.id, kind=kind, path=str(path), mime_type="image/png",
                source_revision=service.source_revision, width=width, height=height,
            )
    return {"ready": list(rendered), "revision": service.source_revision}


async def _save_audio_upload(upload: UploadFile | None, destination: Path, limit: int) -> Path | None:
    if upload is None or not upload.filename:
        return None
    allowed = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg", "audio/mp4"}
    if upload.content_type not in allowed:
        raise HTTPException(422, "Upload MP3, WAV, OGG or M4A audio")
    content = await upload.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, "Audio file is too large")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


@router.post("/api/wallpapers/{order_id}/video")
async def create_wallpaper_video(
    order_id: int,
    user: Annotated[dict, Depends(current_user)],
    final_phrase: str = Form(""),
    duration_seconds: int = Form(15),
    ai_voice: bool = Form(False),
    voice: Annotated[UploadFile | None, File()] = None,
    music: Annotated[UploadFile | None, File()] = None,
) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    if not order.paid:
        raise HTTPException(403)
    if order_id in _studio_jobs:
        raise HTTPException(409, "Another Scene Studio operation is still running")
    _studio_jobs.add(order_id)
    try:
        settings = get_settings()
        upload_root = Path(order.mobile_path).parent / "scene_studio" / "audio"
        limit = settings.max_upload_mb * 1024 * 1024
        voice_path = await _save_audio_upload(voice, upload_root / "voice", limit)
        music_path = await _save_audio_upload(music, upload_root / "music", limit)
        phrase = " ".join(final_phrase.split()).strip()[:500]
        if not phrase:
            phrase = "Твоя прекрасная история уже начинается."
        service = WallpaperExportService(order)
        try:
            path = await service.render_video(
                settings=settings,
                goals=list(order.goals or []),
                final_phrase=phrase,
                duration_seconds=duration_seconds,
                voice_path=voice_path,
                music_path=music_path,
                ai_voice=ai_voice and voice_path is None,
            )
        except (ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            raise HTTPException(422, str(exc)) from exc
        async with async_session_maker() as session:
            current = await session.get(WallpaperOrder, order.id)
            current.final_phrase = phrase
            await WallpaperStudioRepository(session).save_export(
                order_id=order.id, kind="video", path=str(path), mime_type="video/mp4",
                source_revision=service.source_revision,
                width=720, height=1280,
                duration_seconds=Decimal(min(20, max(10, duration_seconds))),
            )
        return {"kind": "video", "ready": True,
                "url": f"/miniapp/api/wallpapers/{order.id}/exports/video"}
    finally:
        _studio_jobs.discard(order_id)


@router.get("/api/wallpapers/{order_id}/exports/{kind}")
async def wallpaper_export_file(
    order_id: int, kind: str, user: Annotated[dict, Depends(current_user)]
) -> FileResponse:
    order = await _own_wallpaper(order_id, user["id"])
    if not order.paid:
        raise HTTPException(403)
    async with async_session_maker() as session:
        export = await session.scalar(
            select(WallpaperExport).where(
                WallpaperExport.order_id == order.id, WallpaperExport.kind == kind
            )
        )
    current_revision = WallpaperExportService(order).source_revision
    if export is None or export.source_revision != current_revision or not Path(export.path).is_file():
        raise HTTPException(409, "Create this format for the current revision first")
    return FileResponse(export.path, media_type=export.mime_type, filename=Path(export.path).name,
                        headers={"Cache-Control": "private, no-store"})


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
                             user: Annotated[dict, Depends(current_user)],
                             provider: str | None = None) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    if order.paid:
        raise HTTPException(409, "Already paid")
    if provider == "wayforpay":
        return await _wayforpay_checkout(
            product="wallpaper",
            reference_id=order.id,
            owner_id=user["id"],
            description=f"Food Porn digital gift #{order.id}",
        )
    if order.source_channel == "telegram" and order.stars_amount:
        bot = getattr(request.app.state, "bot", None)
        if bot is None:
            raise HTTPException(503, "Bot is not running")
        url = await create_invoice(
            bot, OrderRef("wallpaper", order.id, user["id"], order.stars_amount)
        )
        return {"url": url, "stars": order.stars_amount, "provider": "stars"}
    payment = PaymentService(get_settings())
    if not payment.portmone_ready:
        raise HTTPException(503, "Card payment is temporarily unavailable")
    url = await payment.create_portmone_invoice(
        order.id,
        order.amount,
        f"Food Porn digital gift #{order.id}",
        product="wallpaper",
    )
    return {"url": url, "amount": str(order.amount), "currency": "UAH", "provider": "portmone"}


@router.post("/api/wallpapers/{order_id}/verify")
async def verify_wallpaper(order_id: int, user: Annotated[dict, Depends(current_user)]) -> dict:
    order = await _own_wallpaper(order_id, user["id"])
    if not order.paid:
        if await _wayforpay_is_paid("wallpaper", order.id, user["id"]):
            return {"paid": True}
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
    is_free = await has_free_generation_access(
        user["id"], user.get("username"), settings, async_session_maker
    )
    card_ready = PaymentService(settings).portmone_ready
    stars_ready = user.get("source_channel", "telegram") == "telegram" and settings.menu_price_stars > 0
    if not is_free and not (stars_ready or card_ready):
        raise HTTPException(503, "Payment is temporarily unavailable; generation has not started")
    if language not in {"uk", "ru", "en"}:
        raise HTTPException(422, "Unknown language")
    try:
        items = normalize_dish_payload(json.loads(dishes))
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
                country="Not provided", city="Not provided",
                source_channel=user.get("source_channel", "telegram"),
                external_user_id=user.get("external_user_id"),
            )
        repo = MenuRepository(session)
        menu = await repo.create(customer, source_channel=user.get("source_channel", "telegram"))
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
                        user: Annotated[dict, Depends(current_user)],
                        provider: str | None = None) -> dict:
    menu = await _own_menu(menu_id, user["id"])
    if menu.is_paid or menu.status != MenuStatus.WAITING_FOR_PAYMENT or menu.price_amount is None:
        raise HTTPException(409, "No outstanding payment for this menu")
    if provider == "wayforpay":
        return await _wayforpay_checkout(
            product="menu",
            reference_id=menu.id,
            owner_id=user["id"],
            description=f"Food Porn digital menu #{menu.id}",
        )
    if menu.source_channel == "telegram" and menu.stars_amount:
        bot = getattr(request.app.state, "bot", None)
        if bot is None:
            raise HTTPException(503, "Bot is not running")
        url = await create_invoice(bot, OrderRef("menu", menu.id, user["id"], menu.stars_amount))
        return {"url": url, "stars": menu.stars_amount, "provider": "stars"}
    payment = PaymentService(get_settings())
    if not payment.portmone_ready:
        raise HTTPException(503, "Card payment is temporarily unavailable")
    url = await payment.create_portmone_invoice(
        menu.id,
        menu.price_amount,
        f"Food Porn digital menu #{menu.id}",
        product="menu",
    )
    return {"url": url, "amount": str(menu.price_amount), "currency": "UAH", "provider": "portmone"}


@router.post("/api/menus/{menu_id}/verify")
async def verify_menu(menu_id: int, user: Annotated[dict, Depends(current_user)]) -> dict:
    menu = await _own_menu(menu_id, user["id"])
    if menu.status in (MenuStatus.FAILED, MenuStatus.QUEUED):
        raise HTTPException(409, "The print file is being repaired or is incomplete")
    if not menu.is_paid:
        if await _wayforpay_is_paid("menu", menu.id, user["id"]):
            menu.is_paid = True
            menu.payment_system = "wayforpay"
        if menu.stars_amount:
            if not menu.is_paid:
                return {"paid": False}
        if not menu.is_paid and (
            menu.status != MenuStatus.WAITING_FOR_PAYMENT or menu.price_amount is None
        ):
            raise HTTPException(409, "No payment to check")
        verified = None
        if not menu.is_paid:
            verified = await PaymentService(get_settings()).verify_portmone_payment(
                menu.id, menu.price_amount
            )
            if verified is None:
                return {"paid": False}
        pdf = next((Path(item.path) for item in menu.files if item.kind == FileKind.PRINT_PDF), None)
        recipes = next((Path(item.path) for item in menu.files if item.kind == FileKind.RECIPE_SHEET), None)
        if pdf is None or not pdf.is_file() or recipes is None or not recipes.is_file():
            raise HTTPException(503, "Payment received, but print files are temporarily unavailable")
        if not menu.is_paid:
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
        if plan.get("version") not in {1, 2} or not isinstance(plan.get("shopping"), list):
            raise ValueError("Invalid plan")
        return plan
    except (OSError, ValueError, TypeError, AttributeError):
        raise HTTPException(404, "This order predates the evening plan; use the recipe PDF") from None


@router.get("/api/admin")
async def admin_dashboard(user: Annotated[dict, Depends(current_user)]) -> dict:
    settings = get_settings()
    if not await has_admin_access(user["id"], user.get("username"), settings, async_session_maker):
        raise HTTPException(403)
    async with async_session_maker() as session:
        data = await crm_dashboard(session, 30)
        vip = await get_vip_users(session, settings.default_vip_users)
        menu_price = await get_setting(session, "menu_price_uah", str(settings.menu_price))
    return {**data, "paid_gifts": data["paid_gifts"], "vip": vip, "menu_price": menu_price,
            "revenue": data["revenue_uah"], "stars_revenue": data["revenue_stars"],
            "stars_ready": settings.menu_price_stars > 0 and settings.gift_price_stars > 0,
            "payment_ready": PaymentService(settings).portmone_ready, "crm_url": "/crm", "owner": user["id"] in settings.admin_telegram_ids}


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
    if not await has_admin_access(user["id"], user.get("username"), get_settings(), async_session_maker):
        raise HTTPException(403)
    try:
        price = Decimal(str(payload["price"])).quantize(Decimal("0.01"))
        if not price.is_finite() or not Decimal("1") <= price <= Decimal("100000"):
            raise ValueError()
    except (KeyError, ValueError, ArithmeticError) as exc:
        raise HTTPException(422, "Enter a price from 1 to 100000 UAH") from exc
    async with async_session_maker() as session:
        await crm_save_settings(session, {"menu_price_uah": str(price)}, f"telegram:{user['id']}")
    return {"menu_price": str(price)}
