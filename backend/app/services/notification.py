import logging

from sqlalchemy import select

from app.db import async_session
from app.models.cart import Cart
from app.models.family import Child

logger = logging.getLogger(__name__)

_firebase_initialized = False


def _ensure_firebase():
    """Initialise the Firebase Admin SDK lazily.

    Production path (Render): credentials live in the
    ``FIREBASE_CREDENTIALS_JSON`` env var as a literal JSON blob —
    Render mounts secrets as env vars, not files, so this is the
    cleanest way to ship the service account.

    Local-dev path: credentials live at the file path declared in
    ``FIREBASE_CREDENTIALS_PATH``. We fall through to that when the
    env-var blob isn't set.

    No credentials → push notifications are disabled but the rest of
    the API keeps working.
    """
    global _firebase_initialized
    if _firebase_initialized:
        return
    try:
        import json
        import os

        import firebase_admin

        from app.config import settings

        if firebase_admin._apps:
            _firebase_initialized = True
            return

        cred = None
        cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON", "").strip()
        if cred_json:
            try:
                info = json.loads(cred_json)
                cred = firebase_admin.credentials.Certificate(info)
                logger.info("Firebase credentials loaded from FIREBASE_CREDENTIALS_JSON env var")
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "FIREBASE_CREDENTIALS_JSON is set but unparseable (%s) — "
                    "falling back to FIREBASE_CREDENTIALS_PATH", exc,
                )

        if cred is None:
            path = settings.firebase_credentials_path
            if path and os.path.exists(path):
                cred = firebase_admin.credentials.Certificate(path)
                logger.info("Firebase credentials loaded from %s", path)

        if cred is None:
            logger.warning(
                "Firebase init skipped: neither FIREBASE_CREDENTIALS_JSON nor "
                "a valid FIREBASE_CREDENTIALS_PATH is set. Push notifications "
                "will be disabled.",
            )
            return

        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
    except Exception as e:  # noqa: BLE001 — push is best-effort
        logger.warning("Firebase init failed (push notifications disabled): %s", e)


async def notify_children(cart: Cart):
    """Send FCM push notifications to all children in the family."""
    _ensure_firebase()

    async with async_session() as db:
        result = await db.execute(
            select(Child).where(Child.family_id == cart.family_id)
        )
        children = result.scalars().all()

    tokens = [c.fcm_token for c in children if c.fcm_token]
    if not tokens:
        logger.info("No FCM tokens for family %s — skipping push", cart.family_id)
        return

    try:
        from firebase_admin import messaging

        item_count = cart.item_count or 0
        total = cart.estimated_total or 0
        platform = cart.best_platform or "best platform"

        notification = messaging.Notification(
            title=f"Mom needs {item_count} items (₹{total:.0f})",
            body=f"Best price on {platform}. Tap to approve.",
        )

        data = {
            "cart_id": str(cart.id),
            "family_id": str(cart.family_id),
            "item_count": str(item_count),
            "estimated_total": f"{total:.2f}",
            "type": "cart_approval",
        }

        for token in tokens:
            try:
                message = messaging.Message(
                    notification=notification,
                    data=data,
                    token=token,
                    webpush=messaging.WebpushConfig(
                        fcm_options=messaging.WebpushFCMOptions(link="/cart/" + str(cart.id)),
                    ),
                )
                messaging.send(message)
            except Exception as e:
                logger.warning("FCM send failed for token %s: %s", token[:20], e)

    except ImportError:
        logger.warning("firebase_admin not available — push notifications disabled")


async def notify_family_children(
    family_id,
    title: str,
    body: str,
    data: dict | None = None,
    db=None,
):
    """Generic push notification to all children in a family."""
    _ensure_firebase()

    if db:
        result = await db.execute(select(Child).where(Child.family_id == family_id))
        children = result.scalars().all()
    else:
        async with async_session() as session:
            result = await session.execute(select(Child).where(Child.family_id == family_id))
            children = result.scalars().all()

    tokens = [c.fcm_token for c in children if c.fcm_token]
    if not tokens:
        logger.info("No FCM tokens for family %s — skipping push", family_id)
        return

    try:
        from firebase_admin import messaging

        payload = {k: str(v) if not isinstance(v, str) else v for k, v in (data or {}).items()}

        for token in tokens:
            try:
                message = messaging.Message(
                    notification=messaging.Notification(title=title, body=body),
                    data=payload,
                    token=token,
                )
                messaging.send(message)
            except Exception as e:
                logger.warning("FCM generic send failed for token %s: %s", token[:20], e)
    except ImportError:
        logger.warning("firebase_admin not available — push notifications disabled")


async def notify_cart_handled(cart: Cart, handler_name: str):
    """Notify other siblings that a cart was handled."""
    async with async_session() as db:
        result = await db.execute(
            select(Child).where(
                Child.family_id == cart.family_id,
                Child.id != cart.approved_by,
            )
        )
        siblings = result.scalars().all()

    tokens = [c.fcm_token for c in siblings if c.fcm_token]
    if not tokens:
        return

    try:
        from firebase_admin import messaging

        for token in tokens:
            try:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=f"Handled by {handler_name}",
                        body=f"Mom's {cart.item_count} items (₹{cart.estimated_total:.0f}) — approved",
                    ),
                    data={"cart_id": str(cart.id), "type": "cart_handled"},
                    token=token,
                )
                messaging.send(message)
            except Exception:  # noqa: BLE001 — push delivery is best-effort
                logger.exception(
                    "FCM push failed for cart %s token %s...", cart.id, token[:12],
                )
    except ImportError:
        # Firebase admin not installed in this environment — silent OK.
        pass


# notify_children_ride removed — rides are out of scope.
