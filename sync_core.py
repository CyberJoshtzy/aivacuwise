"""Ai-Vacuwise cloud sync: the shared rules used by the cloud hub and by each server's sync agent.

Records travel between servers by their uuid, never by their local id, because local ids
(1, 2, 3...) are different on every server. Foreign keys are sent as the parent's uuid and
turned back into a local id on arrival.

Conflict rule: last write wins, by updated_at. Check-ins, transfers and pings are events that are
only ever added, so they never conflict.
"""

import datetime as _dt
import enum

from sqlalchemy import Boolean, DateTime
from sqlalchemy.exc import IntegrityError

import models

# Order matters: parents before children.
# (table name, model, {fk column: parent model}, natural-key columns that must stay unique)
SPEC = [
    ("barangays", models.Barangay, {}, ["name"]),
    ("users", models.User, {"barangay_id": models.Barangay}, ["username", "email"]),
    ("evacuation_centers", models.EvacuationCenter, {"barangay_id": models.Barangay}, []),
    (
        "households",
        models.Household,
        {"registered_barangay_id": models.Barangay, "head_of_family_evacuee_id": models.Evacuee},
        [],
    ),
    (
        "evacuees",
        models.Evacuee,
        {"registered_barangay_id": models.Barangay, "household_id": models.Household},
        [],
    ),
    ("trackers", models.Tracker, {"assigned_evacuee_id": models.Evacuee}, ["device_id"]),
    (
        "checkin_records",
        models.CheckinRecord,
        {"evacuee_id": models.Evacuee, "evacuation_center_id": models.EvacuationCenter},
        [],
    ),
    (
        "transfers",
        models.Transfer,
        {
            "evacuee_id": models.Evacuee,
            "from_center_id": models.EvacuationCenter,
            "to_center_id": models.EvacuationCenter,
            "approved_by": models.User,
        },
        [],
    ),
    (
        "tracker_pings",
        models.TrackerPing,
        {"tracker_id": models.Tracker, "evacuation_center_id": models.EvacuationCenter},
        [],
    ),
    ("gps_pings", models.GpsPing, {"tracker_id": models.Tracker}, []),
    (
        "incidents",
        models.Incident,
        {
            "barangay_id": models.Barangay,
            "evacuation_center_id": models.EvacuationCenter,
            "started_by": models.User,
            "ended_by": models.User,
        },
        [],
    ),
]
BY_TABLE = {t: (cls, fks, keys) for t, cls, fks, keys in SPEC}
ORDER = {t: i for i, (t, _c, _f, _k) in enumerate(SPEC)}
SKIP_COLUMNS = {"id", "sync_dirty"}
ALIAS_PREFIX = "alias:"


def _tname(cls):
    return cls.__table__.name


def _parse_time(v):
    if v is None or isinstance(v, _dt.datetime):
        return v
    return _dt.datetime.fromisoformat(str(v).replace("Z", ""))


# ---------------------------------------------------------------- outgoing
def serialize(db, obj, cache=None):
    """One record as a plain dict, with foreign keys written as the parent's uuid."""
    cache = cache if cache is not None else {}
    table = _tname(type(obj))
    _cls, fks, _keys = BY_TABLE[table]
    data = {}
    for col in obj.__table__.columns:
        name = col.name
        if name in SKIP_COLUMNS:
            continue
        v = getattr(obj, name)
        if name in fks and v is not None:
            parent = fks[name]
            key = (_tname(parent), v)
            if key not in cache:
                p = db.query(parent).filter(parent.id == v).first()
                cache[key] = p.uuid if p else None
            v = cache[key]
        elif isinstance(v, _dt.datetime):
            v = v.isoformat()
        elif isinstance(v, enum.Enum):
            v = v.value
        data[name] = v
    return {"table": table, "uuid": obj.uuid, "data": data}


# ---------------------------------------------------------------- incoming
def _aliases(db):
    return {
        r.key[len(ALIAS_PREFIX) :]: r.value
        for r in db.query(models.SyncState)
        .filter(models.SyncState.key.like(ALIAS_PREFIX + "%"))
        .all()
    }


def _find(db, cls, uuid, aliases):
    if not uuid:
        return None
    uuid = aliases.get(uuid, uuid)
    return db.query(cls).filter(cls.uuid == uuid).first()


def apply_rows(db, rows):
    """Insert or update incoming records.
    Returns (applied, skipped, aliased, waiting): applied = (table, uuid) saved here; skipped = already
    had this or a newer version; aliased = linked to the same record registered here; waiting = its
    parent has not arrived yet, so the sender must send it again later.
    Must be called with db.info['sync_import'] = True so local stamping is switched off."""
    db.info["sync_import"] = True
    aliases = _aliases(db)
    applied, skipped, aliased, waiting, pending = [], [], [], [], []
    for row in sorted(rows, key=lambda r: ORDER.get(r.get("table"), 99)):
        table, uuid, data = row.get("table"), row.get("uuid"), dict(row.get("data") or {})
        if table not in BY_TABLE or not uuid:
            skipped.append(uuid)
            continue
        cls, fks, keys = BY_TABLE[table]
        obj = _find(db, cls, uuid, aliases)
        incoming_time = _parse_time(data.get("updated_at"))
        if obj is not None:
            if obj.uuid != uuid:  # an alias: same real-world record known under another uuid here
                skipped.append(uuid)
                continue
            if obj.updated_at and incoming_time and incoming_time <= obj.updated_at:
                skipped.append(uuid)  # we already have this version or a newer one
                continue
        else:
            # Same barangay / account / device registered separately on two servers: link, don't duplicate.
            twin = None
            for k in keys:
                if data.get(k):
                    twin = db.query(cls).filter(getattr(cls, k) == data[k]).first()
                    if twin:
                        break
            if twin is not None:
                db.merge(models.SyncState(key=ALIAS_PREFIX + uuid, value=twin.uuid))
                aliases[uuid] = twin.uuid
                aliased.append(uuid)
                continue
            obj = cls()
        missing_required = False
        for col in cls.__table__.columns:
            name = col.name
            if name in SKIP_COLUMNS or name not in data:
                continue
            v = data[name]
            if name in fks:
                parent = _find(db, fks[name], v, aliases) if v else None
                if v and parent is None:
                    if not col.nullable:
                        missing_required = True
                        break
                    pending.append((obj, name, fks[name], v))
                v = parent.id if parent is not None else None
            elif isinstance(col.type, DateTime):
                v = _parse_time(v)
            elif isinstance(col.type, Boolean) and v is not None:
                v = bool(v)
            setattr(obj, name, v)
        if missing_required:
            waiting.append(uuid)  # its parent has not arrived yet; the sender will retry later
            continue
        obj.uuid = uuid
        obj.sync_dirty = False
        db.add(obj)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            waiting.append(uuid)
            continue
        applied.append((table, uuid))
    # Second pass for links that pointed forward (for example a household's head of family).
    for obj, name, parent_cls, puuid in pending:
        parent = _find(db, parent_cls, puuid, aliases)
        if parent is not None and obj in db:
            setattr(obj, name, parent.id)
    db.flush()
    return applied, skipped, aliased, waiting


def apply_tombstones(db, tombstones):
    """Delete records that were deleted on another server. Returns the list of (table, uuid) removed."""
    db.info["sync_import"] = True
    aliases = _aliases(db)
    removed = []
    for t in sorted(tombstones, key=lambda x: -ORDER.get(x.get("table"), 0)):
        table, uuid = t.get("table"), t.get("uuid")
        if table not in BY_TABLE:
            continue
        cls = BY_TABLE[table][0]
        obj = _find(db, cls, uuid, aliases)
        if obj is None:
            continue
        try:
            with db.begin_nested():
                if table == "evacuees":  # same clean-up as the local Delete Evacuee button
                    db.query(models.Tracker).filter(
                        models.Tracker.assigned_evacuee_id == obj.id
                    ).update({models.Tracker.assigned_evacuee_id: None}, synchronize_session=False)
                    db.query(models.Household).filter(
                        models.Household.head_of_family_evacuee_id == obj.id
                    ).update(
                        {models.Household.head_of_family_evacuee_id: None},
                        synchronize_session=False,
                    )
                    db.query(models.Transfer).filter(models.Transfer.evacuee_id == obj.id).delete(
                        synchronize_session=False
                    )
                    db.query(models.CheckinRecord).filter(
                        models.CheckinRecord.evacuee_id == obj.id
                    ).delete(synchronize_session=False)
                db.delete(obj)
                db.flush()
            removed.append((table, uuid))
        except IntegrityError:
            pass  # still referenced by something here; keep it rather than break local data
    return removed


# ---------------------------------------------------------------- what a server has to send
def dirty_rows(db, limit=300):
    """Records created or changed on this server that the hub has not confirmed yet, parents first."""
    rows, cache = [], {}
    for _t, cls, _f, _k in SPEC:
        for obj in (
            db.query(cls)
            .filter(cls.sync_dirty.is_(True))
            .order_by(cls.id)
            .limit(limit - len(rows))
            .all()
        ):
            rows.append(serialize(db, obj, cache))
        if len(rows) >= limit:
            break
    return rows


def mark_clean(db, rows):
    """After the hub accepted rows, clear their flag, unless the record changed again meanwhile."""
    for r in rows:
        cls = BY_TABLE[r["table"]][0]
        when = _parse_time(r["data"].get("updated_at"))
        db.query(cls).filter(cls.uuid == r["uuid"], cls.updated_at == when).update(
            {cls.sync_dirty: False}, synchronize_session=False
        )
