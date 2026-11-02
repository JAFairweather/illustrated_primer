"""Read a notebook answer from structured agent transcripts, matched to its request.

Only text user/assistant messages are read. Tool output and model reasoning are never
answers. No terminal scraping, session resuming, or agent process control is needed.
"""
import glob
import json
import os
import time
import threading
from collections import OrderedDict


def notebook_prompt(text, image_path, marker, ink_enabled=False, prepared_attachment=False, image_primary=False,
                    draft_check=None):
    """Shared lesson-first prompt; runtime advertises only enabled capabilities."""
    from notebook_lesson_prompt import reply_prompt
    return reply_prompt(text, image_path, marker, ink_enabled, prepared_attachment, image_primary, draft_check)


def message_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(block.get("text", "") for block in content
                     if isinstance(block, dict) and block.get("type") in ("text", "input_text", "output_text"))


def read_events(path):
    # Bound I/O even when a transcript includes large image/tool records.
    with open(path, "rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        stream.seek(max(0, size - 8_000_000))
        if size > 8_000_000:
            stream.readline()
        rows = []
        for line in stream:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except (ValueError, UnicodeError):
                continue
    # Pi/OpenClaw session files are trees: use only the latest active branch.
    entries = {row["id"]: row for row in rows if row.get("id") and "parentId" in row}
    if entries:
        last = next((row for row in reversed(rows) if row.get("id") in entries), None)
        branch, seen = [], set()
        while last and last["id"] not in seen:
            seen.add(last["id"])
            branch.append(last)
            last = entries.get(last.get("parentId"))
        rows = list(reversed(branch))
    return rows


def request_answer(rows, marker):
    """Return a final answer after exactly this user request, never another turn."""
    matched, answer, candidate = False, None, None
    for row in rows:
        if row.get("isSidechain") or row.get("isMeta"):
            continue
        kind = row.get("type")
        payload = row.get("payload") or {}
        if kind == "response_item" and payload.get("type") == "message":
            msg = payload
        elif kind in ("user", "assistant"):
            msg = dict(row.get("message") or {}, role=kind)
        elif kind == "message":
            msg = row.get("message") or {}
        elif kind == "event_msg" and payload.get("type") == "task_complete":
            final = payload.get("last_agent_message")
            if matched and isinstance(final, str) and final.strip():
                answer = final.strip()
            continue
        elif kind == 'result':
            # Claude's terminal result is separate from streamed assistant
            # records. An assistant text chunk alone is not completion proof.
            if matched:
                if row.get('subtype') == 'success' and row.get('is_error') is False:
                    final = row.get('result')
                    answer = final.strip() if isinstance(final, str) and final.strip() else candidate
                else:
                    answer = candidate = None
            continue
        else:
            continue
        role, text = msg.get("role"), message_text(msg.get("content"))
        if role == "user" and text:
            if marker in text:
                matched, answer, candidate = True, None, None
            elif matched:
                # A new unrelated user turn cannot provide this request's answer.
                break
        elif matched and role == "assistant":
            if (msg.get("channel") in ("analysis", "commentary")
                    or msg.get("stopReason") in ("toolUse", "error", "aborted", "length", "max_tokens")
                    or msg.get("stop_reason") in ("tool_use", "max_tokens")
                    or any(b.get("type") in ("tool_use", "toolCall")
                           for b in (msg.get("content") or []) if isinstance(b, dict))):
                answer = candidate = None
            elif text.strip():
                candidate = text.strip()
                completed = (msg.get('channel') == 'final' or msg.get('stopReason') == 'stop'
                             or msg.get('stop_reason') == 'end_turn')
                # Unknown/absent/truncated finish metadata is held, never
                # treated as final merely because it contains readable text.
                answer = candidate if completed else None
    return matched, answer


class ReplyReader:
    def __init__(self, roots=None, discovery_interval=5):
        self.home = os.path.expanduser("~")
        self.configured_roots = list(roots) if roots is not None else None
        self.discovery_interval = max(.5, discovery_interval)
        self.roots = self._roots()
        self.files = {}
        self.indexed_at = None
        self.lock = threading.RLock()
        self.checked = OrderedDict()
        self.sources = {}
        self.discovered = {}
        self.observed = {}

    def _roots(self):
        if self.configured_roots is not None:
            return list(dict.fromkeys(self.configured_roots))
        home = self.home
        return list(dict.fromkeys([
            home + "/.claude/projects", home + "/.codex/sessions",
            home + "/.pi/agent/sessions", home + "/.openclaw/agents",
            *glob.glob(home + "/.nvoy-harness/*/codex/sessions"),
            *glob.glob(home + "/.nvoy-harness/*/pi/agent/sessions"),
            *glob.glob(home + "/.nvoy-harness/*/*/sessions"),
            *glob.glob(home + "/.nvoy-harness/*/*/.pi/agent/sessions"),
            *glob.glob(home + "/.nvoy-harness/*/*/.openclaw/agents"),
        ]))

    def _refresh_index(self):
        now = time.monotonic()
        if self.indexed_at is not None and now - self.indexed_at < self.discovery_interval:
            return
        # Refresh harness roots too: an agent may start after this reader did.
        self.roots = self._roots()
        files = {}
        for root in self.roots:
            real_root = os.path.realpath(root)
            for directory, children, names in os.walk(root, followlinks=False):
                children[:] = [name for name in children
                               if not os.path.islink(os.path.join(directory, name))]
                for name in names:
                    if not name.endswith('.jsonl'):
                        continue
                    path = os.path.join(directory, name)
                    if os.path.commonpath([os.path.realpath(path), real_root]) == real_root:
                        files[path] = real_root
        self.files = files
        self.indexed_at = now

    def _stat(self, path):
        root = self.files.get(path)
        if root is None or os.path.commonpath([os.path.realpath(path), root]) != root:
            raise ValueError('transcript left its indexed root')
        return os.stat(path)

    def inventory(self):
        with self.lock:
            self._refresh_index()
            out = []
            for root in self.roots:
                recent = []
                real_root = os.path.realpath(root)
                for path in self.files:
                    if os.path.commonpath([os.path.realpath(path), real_root]) != real_root:
                        continue
                    try:
                        recent.append(self._stat(path).st_mtime)
                    except (OSError, ValueError):
                        continue
                out.append({"path": root, "available": os.path.isdir(root), "files": len(recent),
                            "last_modified": max(recent, default=None)})
            return out

    def answer(self, marker, sent):
        with self.lock:
            return self._answer(marker, sent)

    def _answer(self, marker, sent):
        paths = [self.sources[marker]] if marker in self.sources else []
        if not paths:
            now = time.monotonic()
            if now - self.discovered.get(marker, -100) < .5:
                return None
            self.discovered[marker] = now
            self._refresh_index()
            candidates = []
            for path in self.files:
                try:
                    modified = self._stat(path).st_mtime
                    if modified >= sent - 5:
                        candidates.append((modified, path))
                except (OSError, ValueError):
                    continue
            paths = [path for _, path in sorted(candidates, reverse=True)[:200]]
        for path in paths:
            try:
                stat = self._stat(path)
                key = (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)
                previous = self.observed.get(marker)
                if previous and previous[:2] == (path, key):
                    return previous[2]
                cached = self.checked.get((marker, path))
                if cached and cached[0] == key:
                    matched, answer = cached[1:]
                else:
                    matched, answer = request_answer(read_events(path), marker)
                    self.checked[(marker, path)] = (key, matched, answer)
                    self.checked.move_to_end((marker, path))
                    while len(self.checked) > 1024:
                        self.checked.popitem(last=False)
                if matched:
                    self.sources[marker] = path
                    self.observed[marker] = (path, key, answer)
                    return answer
            except (OSError, ValueError):
                if self.sources.get(marker) == path:
                    self.sources.pop(marker, None)
                    self.observed.pop(marker, None)
                continue
        return None
