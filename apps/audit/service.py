"""Writing to and checking the audit log."""

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction

from . import context
from .models import GENESIS_HASH, AuditEntry

# Serialises writers so the hash chain has one order (a PostgreSQL advisory lock).
LOCK_ID = 7_120_004

_UNSET = object()


def _clean(detail):
    """The detail as plain JSON values, so the stored copy hashes the same as the original."""
    return json.loads(json.dumps(detail or {}, cls=DjangoJSONEncoder))


def record(action, *, target=None, outcome=AuditEntry.Outcome.SUCCESS, detail=None, actor=_UNSET,
           label=""):
    """Append one entry. ``actor`` defaults to whoever is making the current request.

    Never put personal data (medical, guardian or identity details, passwords, card data) in
    ``detail``: the log is read by administrators and kept for years (SO-1).
    """
    if actor is _UNSET:
        actor = context.current_actor()
    request = context.current_request()
    ip = request.META.get("REMOTE_ADDR") if request is not None else None
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_ID])
        last = AuditEntry.objects.order_by("-seq").first()
        entry = AuditEntry(
            seq=last.seq + 1 if last else 1,
            prev_hash=last.hash if last else GENESIS_HASH,
            actor=actor,
            actor_label=label or (actor.username if actor else "system"),
            action=action,
            category=action.split(".")[0],
            outcome=outcome,
            detail=_clean(detail),
            ip_address=ip or None,
        )
        if target is not None:
            entry.target_type = target._meta.label_lower
            entry.target_id = str(target.pk)
            entry.target_repr = str(target)[:200]
        entry.hash = entry.compute_hash()
        entry.save(force_insert=True)
    return entry


def verify_chain():
    """Recompute every hash. Returns (entries checked, [problems])."""
    problems = []
    previous_hash, previous_seq, checked = GENESIS_HASH, 0, 0
    for entry in AuditEntry.objects.order_by("seq").iterator():
        checked += 1
        if entry.seq != previous_seq + 1:
            problems.append(f"entry #{entry.seq}: entries are missing before it")
        if entry.prev_hash != previous_hash:
            problems.append(f"entry #{entry.seq}: does not follow the entry before it")
        if entry.hash != entry.compute_hash():
            problems.append(f"entry #{entry.seq}: contents were changed")
        previous_hash, previous_seq = entry.hash, entry.seq
    return checked, problems
