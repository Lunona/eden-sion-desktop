"""Notes derived only from an explicitly completed reading of a live document."""
import json
import sqlite3
import threading
import uuid

from memory_notes import chunks
from pet_companion.models import CoreError
from pet_memory.types import MemoryError, require


def _source(memory, scope, identifier, revision=None):
    root = memory._memory(scope, identifier)
    require(root['status'] == 'active' and (revision is None or root['revision'] == revision),
            'inactive_memory', '阅读依据已失效')
    doc = memory.db.execute('SELECT title,body FROM sion_documents WHERE memory_row=?', (root['rowid'],)).fetchone()
    require(doc is not None, 'not_found', '找不到原文')
    return root, doc


def _sample(items, limit):
    if len(items) <= limit:
        return items
    return [items[round(index * (len(items) - 1) / (limit - 1))] for index in range(limit)]


def _checked_anchors(body, anchors):
    if not isinstance(anchors, list) or not 1 <= len(anchors) <= 2:
        return False
    lines = body.splitlines()
    for anchor in anchors:
        if not isinstance(anchor, dict):
            return False
        start, end, column, text = (anchor.get(key) for key in ('line_start', 'line_end', 'column_start', 'text'))
        if any(type(value) is not int for value in (start, end, column)) or not isinstance(text, str):
            return False
        if not 1 <= start <= end <= len(lines) or column < 0 or not text.strip():
            return False
        excerpt = '\n'.join(lines[start - 1:end])
        if start == end:
            excerpt = excerpt[column:column + len(text)]
        if text != excerpt:
            return False
    return True


def note_evidence(memory, scope, item):
    data = item.get('qualifiers', {})
    identifier = data.get('document_id')
    kind, revision = data.get('reading_note'), data.get('source_revision')
    if kind not in ('excerpt', 'interpretation') or not isinstance(identifier, str) or type(revision) is not int:
        return None
    try:
        root, doc = _source(memory, scope, identifier, revision)
    except MemoryError:
        return None
    if root['world'] != item['world_id'] or root['layer'] != item['knowledge_layer']:
        return None
    anchors = data.get('anchors')
    if not _checked_anchors(doc['body'], anchors):
        return None
    if kind == 'excerpt' and (len(anchors) != 1 or item['text'] != '[' + doc['title'][:24] + '] ' + anchors[0]['text']):
        return None
    if kind == 'interpretation' and item['verification'] != 'assistant_statement':
        return None
    return {'title': doc['title'], 'version_id': identifier, 'revision': root['revision'], 'anchors': anchors}


def _public_notes(memory, scope, identifier):
    rows = memory.db.execute("""SELECT child.* FROM links AS link JOIN memories AS child
        ON child.owner=link.owner AND child.pet=link.pet AND child.id=link.child_id
        WHERE link.owner=? AND link.pet=? AND link.parent_id=? AND child.status='active'
        AND child.kind='note' AND json_extract(child.qualifiers,'$.reading_note') IN ('excerpt','interpretation')
        ORDER BY CASE json_extract(child.qualifiers,'$.reading_note') WHEN 'excerpt' THEN 0 ELSE 1 END,
            json_extract(child.qualifiers,'$.anchors[0].line_start'),
            json_extract(child.qualifiers,'$.anchors[0].column_start'),child.id""",
        (scope.owner_id, scope.companion_id, identifier))
    output = []
    for row in rows:
        item = memory._public(row)
        evidence = note_evidence(memory, scope, item)
        if evidence:
            output.append({'id': item['memory_id'], 'kind': item['qualifiers']['reading_note'],
                           'text': item['text'].removeprefix('[' + evidence['title'][:24] + '] '),
                           'source': evidence})
    return output


def public_notes(host, identifier):
    memory, scope = host.rt.memory, host.rt.scope()
    with memory.lock:
        return _public_notes(memory, scope, identifier)


def _model_notes(reply, passages):
    by_id = {part['id']: {key: value for key, value in part.items() if key != 'id'} for part in passages}
    excerpts = reply.get('excerpts') if isinstance(reply, dict) else None
    if not isinstance(excerpts, list) or not 1 <= len(excerpts) <= 3 or any(
            type(index) is not int or index not in by_id for index in excerpts):
        excerpts = [part['id'] for part in _sample(passages, 3)]
    notes = [('excerpt', by_id[index]['text'], [by_id[index]]) for index in dict.fromkeys(excerpts)]
    interpretations = reply.get('interpretations', []) if isinstance(reply, dict) else []
    if not isinstance(interpretations, list):
        return notes
    for item in interpretations[:2]:
        if not isinstance(item, dict):
            continue
        text, refs = item.get('text'), item.get('sources')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 220:
            continue
        if not isinstance(refs, list) or not 1 <= len(refs) <= 2 or any(
                type(index) is not int or index not in by_id for index in refs):
            continue
        notes.append(('interpretation', text.strip(), [by_id[index] for index in dict.fromkeys(refs)]))
    return notes


class ReadingNotes:
    def __init__(self, host):
        self.host = host
        self.thread = None
        self.cancel = None

    @property
    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def interrupt(self):
        if self.cancel:
            self.cancel.set()

    def tick(self, allowed):
        if not allowed:
            self.interrupt()
            return False
        if self.busy:
            return False
        job = self.host.roles.claim_reading_note()
        if not job:
            return False
        self.cancel = threading.Event()
        self.thread = threading.Thread(target=self._prepare, args=(job, self.cancel),
                                       name='companion-reading', daemon=True)
        self.thread.start()
        return True

    def close(self):
        self.interrupt()
        if self.thread:
            self.thread.join(2)

    def _prepare(self, job, cancel):
        host = self.host
        runtime, memory = host.rt, host.rt.memory
        scope = runtime.scope()
        identifier, revision = job['source_id'], job['revision']
        state = 'failed'
        try:
            with memory.lock:
                root, doc = _source(memory, scope, identifier, revision)
                if _public_notes(memory, scope, identifier):
                    state = 'ready'
                    return
            selected = _sample(chunks(doc['body'], doc['title']), 8)
            passages = [{'id': index + 1, **part} for index, part in enumerate(selected)]
            request = {'title': doc['title'], 'passages': passages}
            reply = None
            if (host.api_enabled and host.memory_config.get('automatic', True) and not cancel.is_set()
                    and host.memory_system.reserve('reading', request)):
                try:
                    reply = host.model.ask('memory.reading', request, timeout=15, cancel=cancel)
                    host.memory_system.account('reading', request, reply)
                except CoreError:
                    pass
            notes = _model_notes(reply, passages)
            with runtime.lock:
                if cancel.is_set() or host.closing.is_set() or not host.reading_available():
                    state = 'queued'
                    return
                with memory._tx():
                    root, current = _source(memory, scope, identifier, revision)
                    if current['body'] != doc['body'] or current['title'] != doc['title']:
                        state = 'unavailable'
                        return
                    if not _public_notes(memory, scope, identifier):
                        for kind, text, anchors in notes:
                            if not _checked_anchors(current['body'], anchors):
                                continue
                            body = '[' + current['title'][:24] + '] ' + text
                            qualifiers = {'reading_note': kind, 'document_id': identifier,
                                          'source_revision': revision, 'anchors': anchors}
                            if kind == 'excerpt':
                                qualifiers.update({key: anchors[0][key] for key in ('line_start','line_end','column_start')})
                            event = memory._event(scope, 'reading_' + uuid.uuid4().hex, body,
                                                  'document' if kind == 'excerpt' else 'assistant',
                                                  root['world'], root['layer'], None)
                            memory._store(scope, body, event, 0, len(body), kind='note', subject='companion',
                                          qualifiers=qualifiers, parent_ids=[identifier])
                    state = 'ready' if _public_notes(memory, scope, identifier) else 'failed'
        except MemoryError as error:
            state = 'unavailable' if error.code in ('not_found','inactive_memory','deleted') else 'failed'
        except (ValueError, TypeError, sqlite3.Error):
            state = 'failed'
        finally:
            if not host.closing.is_set():
                host.roles.finish_reading_note(job['id'], state)
                host.role_dirty = True
