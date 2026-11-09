"""Special dates and private preparation records. The scheduler owns dispatch."""
from datetime import date, datetime, time as day_time, timedelta
import re
import time
import uuid


KINDS = {
    "birthday": ("生日", "生日快乐。愿你今天能安心享受属于自己的时间，也能留下一件以后想起来会微笑的小事。"),
    "anniversary": ("纪念日", "又到了你记下的这一天。愿我们以后回想起来，记得的不只是日期，还有当时说过的话和在意的事。"),
    "other": ("特别日子", "这是你想记住的一天。我给你留了一张小小的信笺。愿今天有值得你好好记住的一刻。"),
}


def upcoming(item, today):
    origin = date.fromisoformat(item["date"])
    if not item["annual"] or today.year < origin.year:
        return origin
    def in_year(year):
        try:
            return origin.replace(year=year)
        except ValueError:
            return date(year, 2, 28)
    for year in (today.year - 1, today.year, today.year + 1):
        if year < origin.year:
            continue
        candidate = in_year(year)
        if candidate >= today - timedelta(days=7) and candidate.isoformat() > item.get("delivered", ""):
            return candidate
    return in_year(today.year + 2)


def update(items, request, today):
    if request.get("action") == "remove":
        identifier = request.get("id")
        items[:] = [item for item in items if item["id"] != identifier]
        return
    title, kind = request.get("title"), request.get("kind")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 60 or kind not in KINDS or len(items) >= 32:
        raise ValueError("请填写日子名称，最多保留32项")
    try:
        occurrence = date.fromisoformat(request["date"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("请选择有效日期") from None
    if not today <= occurrence <= today + timedelta(days=5 * 366):
        raise ValueError("请选择今天至未来五年内的日期")
    items.append({"id": uuid.uuid4().hex, "title": title.strip(), "kind": kind,
                  "date": occurrence.isoformat(), "annual": request.get("annual") is True})


def public_days(items, today):
    return [{"id": item["id"], "title": item["title"], "kind": KINDS[item["kind"]][0],
             "date": upcoming(item, today).isoformat(), "annual": item["annual"],
             "card": item.get("card") if item.get('delivered','9999-12-31')<=today.isoformat() else None} for item in items]


def sanitize_days(items):
    result=[]
    for item in items[:32]:
        if not isinstance(item,dict) or not all(isinstance(item.get(key),str) for key in ('id','title','date','kind')) or item['kind'] not in KINDS:
            continue
        try:
            date.fromisoformat(item['date'])
        except ValueError:
            continue
        item['annual']=item.get('annual') is True
        if not isinstance(item.get('delivered'),str):item.pop('delivered',None)
        for key in ('prepared','card'):
            field=item.get(key)
            expected=('for','at','letter') if key=='prepared' else ('occasion','prepared','letter')
            if not isinstance(field,dict) or not all(isinstance(field.get(name),str) for name in expected):
                item.pop(key,None)
        result.append(item)
    return result


def parse_draft(value, count):
    if not isinstance(value, dict) or set(value) != {"wish", "memory"}:
        return None
    wish, index = value["wish"], value["memory"]
    if type(index) is not int or not 0 <= index < count or not isinstance(wish, str):
        return None
    wish = wish.strip()
    if not 12 <= len(wish) <= 140 or re.search(r"[\x00-\x1f<>]|https?://|我记得|你曾|那次|上次", wish):
        return None
    return wish, index


class SpecialLetters:
    def __init__(self, store, owner, pet, *, clock=time.time):
        self.store, self.key, self.clock = store, (owner, pet), clock
        with store.tx():
            store.db.execute("""CREATE TABLE IF NOT EXISTS companion_letters(
                owner TEXT NOT NULL, pet TEXT NOT NULL, item TEXT NOT NULL, occurrence TEXT NOT NULL,
                state TEXT NOT NULL, attempted INTEGER NOT NULL DEFAULT 0, prepared TEXT, wish TEXT,
                memory_id TEXT, revision INTEGER, PRIMARY KEY(owner,pet,item,occurrence))""")
            store.db.execute("UPDATE companion_letters SET state='paused' WHERE owner=? AND pet=? AND state='preparing'", self.key)

    @staticmethod
    def action_id(item, stamp):
        return "letter:" + item + ":" + stamp

    def _today(self):
        return datetime.fromtimestamp(self.clock()).date()

    def _released(self):
        with self.store.lock:
            rows = self.store.db.execute("""SELECT l.*,a.id AS action_id FROM companion_letters l
                JOIN companion_actions a ON a.owner=l.owner AND a.pet=l.pet
                 AND a.id='letter:'||l.item||':'||l.occurrence
                WHERE l.owner=? AND l.pet=? AND a.kind='special' AND a.dispatched IS NOT NULL
                ORDER BY l.occurrence DESC""", self.key)
            latest = {}
            for row in rows:
                latest.setdefault(row["item"], row)
            return latest

    def _candidates(self, items, today):
        latest = self._released()
        ready = []
        for item in items:
            released = latest.get(item["id"])
            entry = {**item, "delivered": max(item.get("delivered", ""), released["occurrence"] if released else "")}
            occurrence = upcoming(entry, today)
            stamp = occurrence.isoformat()
            if stamp > entry["delivered"] and -7 <= (occurrence - today).days <= 5:
                ready.append((stamp, item))
        return sorted(ready, key=lambda pair: (pair[0], pair[1]["id"]))

    def reserve(self, items, eligible):
        today = self._today()
        for stamp, item in self._candidates(items, today):
            if not eligible():
                return None
            with self.store.tx():
                row = self._row(item["id"], stamp)
                if row and row["state"] != "paused":
                    continue
                if row:
                    self.store.db.execute("""UPDATE companion_letters SET state='preparing'
                        WHERE owner=? AND pet=? AND item=? AND occurrence=?""", (*self.key, item["id"], stamp))
                else:
                    self.store.db.execute("""INSERT INTO companion_letters(owner,pet,item,occurrence,state)
                        VALUES(?,?,?,?,'preparing')""", (*self.key, item["id"], stamp))
            return item, stamp
        return None

    def _row(self, item, stamp):
        return self.store.db.execute("""SELECT * FROM companion_letters
            WHERE owner=? AND pet=? AND item=? AND occurrence=?""", (*self.key, item, stamp)).fetchone()

    def mark_attempt(self, item, stamp):
        with self.store.tx():
            return bool(self.store.db.execute("""UPDATE companion_letters SET attempted=1
                WHERE owner=? AND pet=? AND item=? AND occurrence=? AND state='preparing' AND attempted=0""",
                (*self.key, item, stamp)).rowcount)

    def pause(self, item, stamp):
        with self.store.tx():
            self.store.db.execute("""UPDATE companion_letters SET state='paused'
                WHERE owner=? AND pet=? AND item=? AND occurrence=? AND state='preparing'""",
                (*self.key, item, stamp))

    def seal(self, item, stamp, wish, source=None):
        memory_id, revision = (source["memory_id"], source["revision"]) if source else (None, None)
        with self.store.tx():
            return bool(self.store.db.execute("""UPDATE companion_letters SET state='sealed',prepared=?,wish=?,memory_id=?,revision=?
                WHERE owner=? AND pet=? AND item=? AND occurrence=? AND state='preparing'""",
                (self._today().isoformat(), wish, memory_id, revision, *self.key, item, stamp)).rowcount)

    def due(self, items, eligible):
        today = self._today()
        for stamp, item in self._candidates(items, today):
            if stamp > today.isoformat():
                break
            if not eligible():
                return None
            with self.store.tx():
                row = self._row(item["id"], stamp)
                if row and row["state"] == "preparing":
                    continue
                if not row:
                    self.store.db.execute("""INSERT INTO companion_letters
                        (owner,pet,item,occurrence,state,prepared) VALUES(?,?,?,?,'sealed',?)""",
                        (*self.key, item["id"], stamp, today.isoformat()))
                elif row["state"] == "paused":
                    self.store.db.execute("""UPDATE companion_letters SET state='sealed',prepared=?
                        WHERE owner=? AND pet=? AND item=? AND occurrence=?""",
                        (today.isoformat(), *self.key, item["id"], stamp))
            occurrence = date.fromisoformat(stamp)
            return {"id": self.action_id(item["id"], stamp), "item": item["id"], "occurrence": stamp,
                    "title": item["title"] + "的信笺到了",
                    "due": datetime.combine(occurrence, day_time.min).timestamp(),
                    "expires": datetime.combine(occurrence + timedelta(days=8), day_time.min).timestamp()}
        return None

    def public(self, items, lookup):
        today = self._today()
        stamp = today.isoformat()
        latest = self._released()
        view = []
        for entry in items:
            row = latest.get(entry["id"])
            item = dict(entry)
            if row and row["occurrence"] <= stamp and row["occurrence"] >= item.get("delivered", ""):
                source = lookup(row["memory_id"], row["revision"]) if row["memory_id"] else None
                letter = row["wish"] if source and row["wish"] else KINDS[item["kind"]][1]
                if source:
                    letter = "我记得你提到过「" + source + "」\n\n" + letter
                item["delivered"] = row["occurrence"]
                item["card"] = {"id": row["action_id"], "occasion": row["occurrence"],
                                "letter": letter, "prepared": row["prepared"]}
            view.append(item)
        return public_days(view, today)

    def has_sealed_surprise(self, items):
        today = self._today()
        with self.store.lock:
            for stamp, item in self._candidates(items, today):
                if stamp > today.isoformat():
                    row = self._row(item["id"], stamp)
                    if row and row["state"] == "sealed":
                        return True
        return False

    def remove(self, item):
        with self.store.tx():
            self.store.db.execute("DELETE FROM companion_letters WHERE owner=? AND pet=? AND item=?", (*self.key, item))
