"""Local web app for trying the component selectors. Standard library only.

    .venv/bin/python webapp/server.py            # http://127.0.0.1:8000
    .venv/bin/python webapp/server.py --port 8080
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib  # noqa: E402
import inspect  # noqa: E402
import re  # noqa: E402

from core import review  # noqa: E402
from core.provenance import SOURCES, load_yaml  # noqa: E402

INDEX = Path(__file__).parent / "index.html"


def _bool(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _list(v) -> list:
    """JSON list typed in a form field, e.g. [{"w_mm": 600, "h_mm": 2000, "d_mm": 600}]."""
    out = json.loads(v) if isinstance(v, str) else v
    if not isinstance(out, list):
        raise ValueError("not a list")
    return out


TYPES = {"float": float, "int": int, "str": str, "bool": _bool, "list": _list}


def _param(p: inspect.Parameter) -> dict:
    ann = str(p.annotation).replace("None", "").replace("|", " ").split()
    typ = next((a.split("[")[0] for a in ann if a.split("[")[0] in TYPES), "str")
    default = None if p.default is inspect.Parameter.empty else p.default
    return {"name": p.name, "type": typ, "default": default, "required": p.default is inspect.Parameter.empty}


def discover() -> dict:
    """Every components/<name>/select.py with a review.yaml: its select() and its inputs, read from the code."""
    out = {}
    for name in review.components():
        fn = importlib.import_module(f"components.{name}.select").select
        rv = load_yaml(ROOT / "components" / name / "review.yaml")
        out[name] = {"fn": fn, "params": [_param(p) for p in inspect.signature(fn).parameters.values()],
                     "title": rv.get("title", name), "order": rv.get("order", 99), "fields": rv.get("fields") or {},
                     "out_of_scope": bool(rv.get("out_of_scope"))}
    return out


COMPONENTS = discover()


def component_list() -> list[dict]:
    return [{"name": n, "title": c["title"], "order": c["order"], "params": c["params"], "fields": c["fields"],
             "out_of_scope": c["out_of_scope"]}
            for n, c in COMPONENTS.items()]


def run_component(name: str, body: dict) -> dict:
    c = COMPONENTS[name]
    kwargs = {}
    for p in c["params"]:
        v = body.get(p["name"])
        if v is None or v == "":
            continue
        try:
            kwargs[p["name"]] = TYPES[p["type"]](v)
        except (TypeError, ValueError):
            raise ValueError(f"{p['name']}: not a valid {p['type']} ({v!r})")
    missing = [p["name"] for p in c["params"] if p["required"] and p["name"] not in kwargs]
    if missing:
        raise ValueError(f"{', '.join(missing)} is required")
    res = c["fn"](**kwargs)
    return {**asdict(res), "trace": res.trace()}


MAX_BODY = 1024 * 1024          # bytes: a requirement, a BOM edit or a component's inputs are far smaller
MAX_RFQ_BODY = 13 * 1024 * 1024  # an RFQ PDF (≤ 9 MB) sent base64 in JSON (RFQ import, stage 1)
LOCAL_HOST = re.compile(r"(?:127\.0\.0\.1|localhost|\[::1\])(?::\d{1,5})?")


def _strict(o):
    """JSON has no NaN / Infinity: send them as null so the page can always parse the answer."""
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _strict(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_strict(v) for v in o]
    return o


# what each changing request needs (owner 2026-10-16: login with roles); calculations need only a signed-in user
WRITES = ("/api/bom/save", "/api/bom/undo", "/api/power/save", "/api/power/undo", "/api/power/standby", "/api/power/settings",
          "/api/io/save", "/api/io/undo", "/api/designs/create", "/api/designs/save", "/api/designs/restore",
          "/api/designs/label", "/api/designs/delete", "/api/designs/delete_panel", "/api/designs/undelete", "/api/rfq/upload", "/api/rfq/answer",
          "/api/rfq/standard", "/api/rfq/rules", "/api/rfq/spec_upload", "/api/standards/save",
          "/api/versions/restore", "/api/versions/label")


def _role_for(path: str) -> str | None:
    if path in WRITES:
        return "designer"
    if path.startswith("/api/signoff/") or path == "/api/standards/approve":
        return "approver"          # component sign-off (G7) is the owner's approval; a company standard is approved too
    return None


PAGES = {"start", "projects", "new", "design", "rfq", "templates", "client-projects", "components", "review", "admin", "standards"}


class Handler(BaseHTTPRequestHandler):
    timeout = 30                    # a client that announces a body and never sends it cannot hold a thread

    def _local(self, post: bool = False) -> bool:
        """Only this machine's own names (no DNS rebinding); a browser Origin, when sent, must be this server exactly.
        Exactly one Host header, matched whole. An opaque 'null' origin may not POST; its GETs are answered, but no CORS
        header is ever sent, so such a page cannot read the reply."""
        hosts = self.headers.get_all("Host") or []
        if len(hosts) != 1 or not LOCAL_HOST.fullmatch(hosts[0]):
            return False
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        if origin == "null":
            return not post
        return origin in (f"http://{hosts[0]}",)

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj, cookie: str | None = None) -> None:
        body = json.dumps(_strict(obj), allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _token(self) -> str | None:
        """The session token from the ps_session cookie."""
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "ps_session" and v:
                return v
        return None

    def _user(self):
        from core import auth
        return auth.session(self._token())

    def do_GET(self):
        if not self._local():
            return self._json(403, {"error": "this server answers only to its own local address"})
        path = self.path.split("?", 1)[0]
        # one page per job (owner 2026-10-19): every page address serves the app, which shows that page
        if path in ("/", "/index.html") or path.split("/")[1] in PAGES:
            return self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        from core import auth
        if path == "/api/auth/status":       # the page asks before anything else: setup, sign-in, or who is signed in
            return self._json(200, {"setup_needed": auth.setup_needed(), "user": self._user()})
        if self._user() is None:              # everything else needs a signed-in user (owner 2026-10-16)
            return self._json(401, {"error": "sign in first"})
        if path == "/api/templates":          # ECI templates: the company's standard panels and DOL kits
            from core import templates
            out = []
            for t in templates.listing():
                opts = t["kw_options"] or ([t["kw"]] if t["kw"] is not None else [None])
                out.append({**t, "texts": {("" if k is None else f"{k:g}"): templates.text(t["id"], k) for k in opts},
                            "answers": templates.answers(t["id"])})
            return self._json(200, {"templates": out, "me": self._user()})
        if path == "/api/assistant/status":
            from core import assistant
            self._json(200, {"available": assistant.available(), "workspace": bool(assistant.workspace_id())})
        elif path == "/api/projects":
            from core import project as P
            return self._json(200, [{"name": n, "client": P.client(n), "panels": list(P.panels(n)),
                                     "design_inputs": P.setting("design_inputs", n, {}),
                                     "plant_items_panel": P.setting("plant_items_panel", n)} for n in P.names()])
        elif path == "/api/components":
            self._json(200, component_list())
        elif path == "/api/review":
            self._json(200, review.components())
        elif path.startswith("/api/review/"):
            try:
                self._json(200, review.review(path.removeprefix("/api/review/")))
            except KeyError:
                self._json(404, {"error": "not found"})
        elif m := re.fullmatch(r"/source/([A-Z0-9-]+)", path):
            # a registered, stored spreadsheet source (own databases), for the reviewer to open
            from core.provenance import register
            ref = register().get(m.group(1))
            f = SOURCES / ref["file"] if ref and ref.get("access") == "stored" else None
            if not f or not f.is_file() or f.suffix not in (".csv", ".xls", ".xlsx"):
                return self._json(404, {"error": "not found"})
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", {".csv": "text/csv; charset=utf-8", ".xls": "application/vnd.ms-excel"}.get(
                f.suffix, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
            self.send_header("Content-Disposition", f'attachment; filename="{f.name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif m := re.fullmatch(r"/excerpts/([A-Za-z0-9_-]+\.png)", path):
            img = SOURCES / "excerpts" / m.group(1)
            if img.is_file():
                self._send(200, img.read_bytes(), "image/png")
            else:
                self._json(404, {"error": "not found"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        """Gate every state-changing / computing request, then route it; every failure gets a JSON answer."""
        if not self._local(post=True):
            return self._json(403, {"error": "requests from other sites or host names are refused"})
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            self.close_connection = True
            return self._json(411, {"error": "send the body with a Content-Length"})
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self._json(415, {"error": "send JSON (Content-Type: application/json)"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        limit = MAX_RFQ_BODY if self.path in ("/api/rfq/upload", "/api/rfq/spec_upload") else MAX_BODY
        if n < 0 or n > limit:
            self.close_connection = True
            return self._json(413, {"error": f"request body too large (max {limit // 1024} KB)"})
        try:
            obj = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": "the body is not valid JSON"})
        if not isinstance(obj, dict):
            return self._json(400, {"error": "the body must be a JSON object"})
        self._obj = obj
        from core import auth
        if self.path.startswith("/api/auth/"):
            return self._auth(obj)
        user = self._user()
        if user is None:
            return self._json(401, {"error": "sign in first"})
        need = _role_for(self.path)
        if need and need not in user["roles"] and "admin" not in user["roles"]:
            return self._json(403, {"error": f"your account does not have the {need} role"})
        auth.set_current(user)
        try:
            self._post()
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
            self._json(400, {"error": f"input not usable: {e}"})
        except Exception as e:  # never a dropped connection; details stay in the server log
            sys.stderr.write(f"POST {self.path}: {type(e).__name__}: {e}\n")
            self._json(500, {"error": "the request could not be processed"})
        finally:
            auth.set_current(None)

    def _auth(self, body: dict):
        """Sign-in, first-run setup, sign-out, and (admin) users."""
        from core import auth
        action = self.path.removeprefix("/api/auth/")
        cookie = lambda t, age: f"ps_session={t}; HttpOnly; SameSite=Strict; Path=/" + (f"; Max-Age={age}" if age is not None else "")
        try:
            if action == "setup":
                u = auth.setup(body.get("name"), body.get("password"))
                return self._json(200, {"user": u}, cookie(auth.login(u["name"], body.get("password")), None))
            if action == "login":
                t = auth.login(body.get("name"), body.get("password"))
                return self._json(200, {"user": auth.session(t)}, cookie(t, None))
            if action == "logout":
                auth.logout(self._token())
                return self._json(200, {"ok": True}, cookie("", 0))
            me = self._user()
            if me is None:
                return self._json(401, {"error": "sign in first"})
            if action == "password":            # one's own password (an admin may set anyone's)
                name = body.get("name") or me["name"]
                if name != me["name"] and "admin" not in me["roles"]:
                    raise PermissionError("only an admin sets another user's password")
                auth.set_password(name, body.get("password"))
                return self._json(200, {"ok": True})
            if "admin" not in me["roles"]:
                raise PermissionError("needs the admin role")
            if action == "users":
                return self._json(200, {"users": auth.listing(), "roles": list(auth.ROLES)})
            if action == "add":
                return self._json(200, {"user": auth.add_user(body.get("name"), body.get("password"), body.get("roles") or [])})
            if action == "roles":
                return self._json(200, {"user": auth.set_roles(body.get("name"), body.get("roles") or [])})
            if action == "remove":
                if body.get("name") == me["name"]:
                    raise ValueError("you cannot remove yourself")
                auth.remove_user(body.get("name"))
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "unknown action"})
        except PermissionError as e:   # a failed sign-in is 401; a refused action of a signed-in user is 403
            return self._json(401 if action == "login" or not self._user() else 403, {"error": str(e)})
        except (ValueError, TypeError) as e:
            return self._json(400, {"error": str(e)})

    def _post(self):
        if self.path == "/api/export/project":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = self._obj
                from core.bom_export import build_project
                params = {p["name"]: p for p in COMPONENTS["project"]["params"]}
                base = {k: TYPES[params[k]["type"]](v) for k, v in body.items() if k in params and v not in (None, "")}
                from core import project as P
                prefix = P.setting("export_prefix", base.get("project")) or P.resolve(base.get("project"))
                title = f"{prefix}_{base.get('panel', 'panel')}"
                data, _ = build_project(base, title=title)
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": str(e)})
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="{title}_BOM.xlsx"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith("/api/bom/"):
            # R-PRJ-17: designer edits to a project BOM — checked by the engine, saved in projects/<name>/overrides.yaml
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = self._obj
                from core import bom_edit
                from core import project as P
                line = body.get("line") or {}
                if not isinstance(line, dict) or not isinstance(body.get("edit") or {}, dict):
                    raise ValueError("line and edit must be objects")
                action = self.path.removeprefix("/api/bom/")
                if action == "search":           # parts catalog, for adding a component (no project needed)
                    return self._json(200, {"parts": bom_edit.search(str(body.get("q") or "")[:80])})
                # check and propose work on any BOM (a project's or a new machine's); save / undo / list need the project
                proj = P.resolve(body.get("project")) if action in ("save", "undo", "list") else None
                if action == "check":
                    return self._json(200, {"check": bom_edit.check(body.get("edit") or {}),
                                            "candidates": bom_edit.candidates(line)})
                if action == "propose":
                    from core import assistant
                    if not assistant.available():
                        return self._json(503, {"error": "AI edits are off: no API key configured"})
                    prompt = str(body.get("prompt") or "").strip()[:1000]
                    if not prompt:
                        raise ValueError("write what you want for this line")
                    cands = bom_edit.candidates(line)
                    try:
                        out = assistant.propose_edit(line, prompt, cands)
                    except Exception as e:  # API errors: the page keeps the manual edit
                        msg = str(e)
                        if "workspace" in msg:
                            msg = "the API key needs a workspace ID (ANTHROPIC_WORKSPACE_ID in ~/.config/panel-selector/anthropic.env)"
                        return self._json(502, {"error": f"assistant unavailable: {msg[:200]}"})
                    out["check"] = bom_edit.check(out["edit"]) if out["edit"] else None
                    out["candidates"] = cands
                    return self._json(200, out)
                if action == "save":
                    rec = bom_edit.save(proj, str(body.get("panel")), line, body.get("edit") or {},
                                        prompt=str(body.get("prompt") or ""), words=str(body.get("words") or ""),
                                        proposed_by="assistant" if body.get("proposed_by") == "assistant" else "designer")
                    return self._json(200, {"saved": rec})
                if action == "undo":
                    eid = body.get("id")
                    if isinstance(eid, bool) or not isinstance(eid, int):
                        raise ValueError(f"id must be a whole number (got {eid!r})")
                    return self._json(200, {"undone": bom_edit.undo(proj, eid)})
                if action == "list":
                    return self._json(200, {"edits": bom_edit.load(proj)})
                return self._json(404, {"error": "unknown BOM action"})
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                return self._json(400, {"error": str(e)})
        if self.path.startswith("/api/power/"):
            # R-PWR-11: designer edits to a project's power calculation, checked by the engine, kept in overrides.yaml
            try:
                from core import bom_edit
                from core import project as P
                body = self._obj
                action = self.path.removeprefix("/api/power/")
                proj = P.resolve(body.get("project"))
                if action == "save":
                    panel, edit = str(body.get("panel") or ""), body.get("edit")
                    if not panel or not isinstance(edit, dict):
                        raise ValueError("panel and edit are needed")
                    from components.project.select import select as project_select
                    import inspect
                    known = set(inspect.signature(project_select.__wrapped__).parameters) - {"panel", "project", "power_edits", "edits"}
                    trial = project_select(panel=panel, project=proj, power_edits=[edit], **{k: v for k, v in body.items() if k in known})
                    err = (((trial.value or {}).get("power_calc") or {}).get("ac3_error")) if trial.status != "invalid" else \
                        next((c.value for c in trial.checks if c.verdict == "fail"), "project not selectable")
                    if err:
                        raise ValueError(err)
                    return self._json(200, {"saved": bom_edit.power_save(proj, panel, edit)})
                if action == "settings":         # panel settings: incomer factor, smallest power wire
                    return self._json(200, {"settings": bom_edit.settings_save(proj, str(body.get("panel") or ""),
                                                                               str(body.get("name") or ""), body.get("value"))})
                if action == "standby":          # R-LL-08: standby units of one tag group, checked on a trial run first
                    panel, tag, units = str(body.get("panel") or ""), body.get("tag"), body.get("units")
                    from components.project.select import select as project_select
                    import inspect
                    known = set(inspect.signature(project_select.__wrapped__).parameters) - {"panel", "project", "standby", "edits", "power_edits"}
                    if units not in (None, ""):
                        trial = project_select(panel=panel, project=proj, standby={tag: units} if isinstance(tag, str) else tag,
                                               **{k: v for k, v in body.items() if k in known})
                        if trial.status == "invalid":
                            raise ValueError(next((c.value for c in trial.checks if c.verdict == "fail"), "not usable"))
                    return self._json(200, {"standby": bom_edit.standby_save(proj, panel, tag, units)})
                if action == "undo":
                    eid = body.get("id")
                    if isinstance(eid, bool) or not isinstance(eid, int):
                        raise ValueError(f"id must be a whole number (got {eid!r})")
                    return self._json(200, {"undone": bom_edit.power_undo(proj, eid)})
                if action == "list":
                    return self._json(200, {"edits": bom_edit.power_list(proj)})
                return self._json(404, {"error": "unknown power action"})
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                return self._json(400, {"error": str(e)})
        if self.path.startswith("/api/io/"):
            # R-IO-12: designer edits to a project's I/O list, checked on a trial run, kept in overrides.yaml
            try:
                from core import bom_edit
                from core import project as P
                body = self._obj
                action = self.path.removeprefix("/api/io/")
                proj = P.resolve(body.get("project"))
                if action == "save":
                    panel, edit = str(body.get("panel") or ""), body.get("edit")
                    if not panel or not isinstance(edit, dict):
                        raise ValueError("panel and edit are needed")
                    from components.project.select import select as project_select
                    import inspect
                    known = set(inspect.signature(project_select.__wrapped__).parameters) - {"panel", "project", "io_edits", "edits", "power_edits"}
                    trial = project_select(panel=panel, project=proj, io_edits=[edit], **{k: v for k, v in body.items() if k in known})
                    err = (trial.value or {}).get("io_error") if trial.status != "invalid" else \
                        next((c.value for c in trial.checks if c.verdict == "fail"), "project not selectable")
                    if err:
                        raise ValueError(err)
                    return self._json(200, {"saved": bom_edit.io_save(proj, panel, edit)})
                if action == "undo":
                    eid = body.get("id")
                    if isinstance(eid, bool) or not isinstance(eid, int):
                        raise ValueError(f"id must be a whole number (got {eid!r})")
                    return self._json(200, {"undone": bom_edit.io_undo(proj, eid)})
                if action == "list":
                    return self._json(200, {"edits": bom_edit.io_list(proj)})
                return self._json(404, {"error": "unknown I/O action"})
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                return self._json(400, {"error": str(e)})
        if self.path == "/api/assistant/page":
            # the assistant for the page the designer is on: proposes power / I/O edits or explains; never applies anything
            try:
                body = self._obj
                from core import assistant
                if not assistant.available():
                    return self._json(503, {"error": "assistant off: no API key configured"})
                page, prompt = str(body.get("page") or ""), str(body.get("prompt") or "").strip()[:1000]
                ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
                if not prompt:
                    raise ValueError("write what you want")
                return self._json(200, assistant.page_assist(page, prompt, ctx))
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:
                return self._json(502, {"error": f"assistant unavailable: {type(e).__name__}: {str(e)[:240]}"})
        if self.path == "/api/assistant":
            # conversational layer: replies and proposes answers; the requirement component still decides everything
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = self._obj
                from core import assistant
                if not assistant.available():
                    return self._json(503, {"error": "assistant off: no API key configured"})
                history = [m for m in body.get("history") or [] if m.get("role") in ("user", "assistant")
                           and isinstance(m.get("content"), str)][-20:]
                if not history or history[-1]["role"] != "user":
                    raise ValueError("the last message must be the designer's")
                level = body.get("level") if body.get("level") in ("fresher", "experienced") else None
                return self._json(200, assistant.chat(history, body.get("state") or {}, level))
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:  # API errors: the page falls back to the strict questions
                return self._json(502, {"error": f"assistant unavailable: {type(e).__name__}: {str(e)[:240]}"})
        if self.path == "/api/alternatives":
            # R-REQ-22: alternatives for one machine BOM line = the design choices behind it, each selected again
            body = self._obj
            params = {p["name"]: p for p in COMPONENTS["requirement"]["params"]}
            inputs = {k: TYPES[params[k]["type"]](v) for k, v in body.items() if k in params and v not in (None, "")}
            line, prompt = body.get("line"), str(body.get("prompt") or "").strip()[:500]
            if not isinstance(line, dict):
                raise ValueError("line must be an object")
            from core.alternatives import alternatives
            out = alternatives(inputs, line, prompt)
            out["ai"] = None
            if prompt and out["options"]:
                from core import assistant
                if assistant.available():
                    try:
                        pick = assistant.pick_alternative(prompt, out["options"])
                        if pick["choice"] is not None:
                            out["options"].insert(0, out["options"].pop(pick["choice"]))
                        out["ai"] = {"reply": pick["reply"], "picked": pick["choice"] is not None}
                    except Exception as e:  # the tool's own ranking stands
                        out["ai"] = {"reply": "", "error": "assistant unavailable — ranked by your words instead"}
                else:
                    out["ai"] = {"reply": "", "error": "assistant off — ranked by your words instead"}
            return self._json(200, out)
        if self.path in ("/api/sld/project", "/api/export/sld/project"):
            # single line diagram of a project panel (same drawing code as a new machine)
            try:
                body = self._obj
                from core.sld import build_sld, sld_html
                from core import project as P
                from components.project.select import select as project_select
                import inspect
                known = set(inspect.signature(project_select.__wrapped__).parameters) - {"panel", "project"}
                proj, panel = P.resolve(body.get("project")), str(body.get("panel") or "")
                res = project_select(panel=panel, project=proj, **{k: v for k, v in body.items() if k in known})
                if res.status == "invalid":
                    raise ValueError(next((c.value for c in res.checks if c.verdict == "fail"), "project not selectable"))
                title = f"{proj} {panel}"[:58]
                from core.drawings import meta_for_project
                if res.value.get("questions"):        # R-PRJ-20: no drawing on assumed values
                    raise ValueError("answer this panel's questions first (project page): " + ", ".join(q["input"] for q in res.value["questions"]))
                st_ = res.value.get("settings") or {}
                inputs_ = {k: body.get(k) if body.get(k) is not None else st_.get(k) for k in ("voltage_v", "fault_ka", "panel_internal_c", "cable_ambient_c")}
                inputs_["voltage_v"] = inputs_["voltage_v"] or 400      # the project path calculates at 400 V (component panel)
                sheets = build_sld(res.value, title=title, meta={**meta_for_project(proj, panel), "inputs": inputs_})
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": str(e)})
            if self.path == "/api/sld/project":
                return self._json(200, {"sheets": sheets})
            data = sld_html(sheets, title).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="SLD_{panel}.html"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith("/api/standards/"):
            # company standards (owner 2026-10-19): approved answers to the company questions, applied to an RFQ in one click
            try:
                body = self._obj
                from core import standards
                action = self.path.removeprefix("/api/standards/")
                if action == "list":
                    return self._json(200, {"standards": standards.listing(), "questions": standards.questions(),
                                            "site": list(standards.SITE)})
                if action == "save":
                    vals = body.get("values") or {}
                    if not isinstance(vals, dict):
                        raise ValueError("values must be an object")
                    return self._json(200, {"standard": standards.save(str(body.get("name") or ""), vals, str(body.get("note") or ""),
                                                                       body.get("id") or None)})
                if action == "approve":
                    return self._json(200, {"standard": standards.approve(str(body.get("id") or ""), int(body.get("v") or 0))})
                return self._json(404, {"error": "unknown standards action"})
            except PermissionError as e:
                return self._json(403, {"error": str(e)})
            except (ValueError, TypeError, KeyError) as e:
                return self._json(400, {"error": str(e)})
        if self.path.startswith("/api/rfq/"):
            # RFQ import, stage 1 (owner 2026-10-18): read a client's equipment panel specification, show it for review
            try:
                body = self._obj
                from core import auth, rfq
                action = self.path.removeprefix("/api/rfq/")
                if action == "upload":
                    import base64, binascii
                    try:
                        data = base64.b64decode(str(body.get("data") or ""), validate=True)
                    except (binascii.Error, ValueError):
                        raise ValueError("the file did not arrive whole (base64)")
                    u = auth.current()
                    return self._json(200, {"rfq": rfq.save(data, str(body.get("filename") or "rfq.pdf"), u["name"] if u else None)})
                if action == "list":
                    return self._json(200, {"rfqs": rfq.listing()})
                if action == "get":
                    from core import rfq_spec
                    rid = str(body.get("id") or "")
                    return self._json(200, {"rfq": rfq.get(rid), "spec": rfq_spec.get(rid)})
                if action == "spec_upload":      # the client's automation / panel specification, read beside the RFQ
                    import base64, binascii
                    from core import rfq_spec
                    try:
                        data = base64.b64decode(str(body.get("data") or ""), validate=True)
                    except (binascii.Error, ValueError):
                        raise ValueError("the file did not arrive whole (base64)")
                    u = auth.current()
                    return self._json(200, {"spec": rfq_spec.save(str(body.get("id") or ""), data, str(body.get("filename") or "spec.pdf"),
                                                                  u["name"] if u else None)})
                if action == "questions":        # stage 2: the questions, the answers, what is still open
                    from core import rfq_answers
                    return self._json(200, {"questions": rfq_answers.questions(str(body.get("id") or ""))})
                if action == "answer":
                    from core import rfq_answers
                    u = auth.current()
                    return self._json(200, {"answer": rfq_answers.answer(str(body.get("id") or ""), str(body.get("scope") or ""),
                                                                         str(body.get("key") or ""), body.get("value"),
                                                                         u["name"] if u else None)})
                if action == "trial":            # one panel through the engine with trial values (nothing saved)
                    from core import rfq_trial
                    vals = body.get("values") or {}
                    if not isinstance(vals, dict):
                        raise ValueError("values must be an object")
                    return self._json(200, {"trial": rfq_trial.trial(str(body.get("id") or ""), str(body.get("panel") or ""), vals)})
                if action == "standard":         # start from an approved company standard (or remove it)
                    from core import rfq_answers
                    u = auth.current()
                    return self._json(200, rfq_answers.apply_standard(str(body.get("id") or ""), body.get("standard") or None,
                                                                      u["name"] if u else None))
                if action == "rules":            # the row rules (running units per group size, feed, current, units)
                    from core import rfq_answers
                    u = auth.current()
                    return self._json(200, rfq_answers.set_rules(str(body.get("id") or ""), body.get("rules") or {},
                                                                 u["name"] if u else None))
                if action == "bom":              # stage 3: one panel's full BOM from the answers, by section
                    from core import rfq_bom
                    b = rfq_bom.build(str(body.get("id") or ""), str(body.get("panel") or ""))
                    b.pop("design_logic", None)
                    return self._json(200, {"bom": b})
                if action == "bom_xlsx":         # stage 3: every panel in one workbook (summary, per panel, all panels)
                    from core import rfq_bom
                    data, _ = rfq_bom.export(str(body.get("id") or ""))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    ref = re.sub(r"[^A-Za-z0-9_-]+", "_", str(rfq.get(str(body.get("id") or "")).get("project_ref") or "RFQ"))[:40]
                    self.send_header("Content-Disposition", f'attachment; filename="{ref}_panels_BOM.xlsx"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                return self._json(404, {"error": "unknown rfq action"})
            except PermissionError as e:
                return self._json(403, {"error": str(e)})
            except (ValueError, TypeError, KeyError) as e:
                return self._json(400, {"error": str(e)})
        if self.path.startswith("/api/designs/"):
            # design projects: Project → panels → design → versions (core/designs.py)
            try:
                body = self._obj
                from core import designs
                action = self.path.removeprefix("/api/designs/")
                pid, panel = body.get("project"), body.get("panel")
                if action == "list":
                    return self._json(200, {"projects": designs.listing()})
                if action == "create":
                    return self._json(200, {"project": designs.create(body.get("name"), body.get("client") or "", body.get("location") or "")})
                if action == "save":
                    return self._json(200, designs.save(pid, panel, body.get("design")))
                if action == "load":
                    return self._json(200, designs.load(pid, panel))
                if action == "history":
                    return self._json(200, {"versions": designs.history(pid, panel)})
                if action == "delete":           # to the bin (designs/.deleted), restorable; approved work needs an admin
                    return self._json(200, designs.delete_project(pid))
                if action == "delete_panel":
                    return self._json(200, designs.delete_panel(pid, panel))
                if action == "deleted":
                    return self._json(200, {"deleted": designs.deleted()})
                if action == "undelete":
                    return self._json(200, designs.undelete(body.get("id")))
                v = body.get("v")
                if isinstance(v, bool) or not isinstance(v, int):
                    raise ValueError(f"v must be a version number (got {v!r})")
                if action == "get":
                    return self._json(200, {"version": designs.get(pid, panel, v)})
                if action == "restore":
                    return self._json(200, designs.restore(pid, panel, v))
                if action == "label":
                    return self._json(200, designs.label(pid, panel, v, body.get("label") or ""))
                if action == "state":
                    return self._json(200, designs.set_state(pid, panel, v, str(body.get("state") or "")))
                return self._json(404, {"error": "unknown designs action"})
            except PermissionError as e:
                return self._json(403, {"error": str(e)})
            except (ValueError, TypeError, KeyError) as e:
                return self._json(400, {"error": str(e)})
        if self.path.startswith("/api/versions/"):
            # project version history: list, look at one, restore one (a restore is a new version)
            try:
                body = self._obj
                from core import bom_edit, versions
                from core import project as P
                proj = P.resolve(body.get("project"))
                f = bom_edit._file(proj)
                action = self.path.removeprefix("/api/versions/")
                if action == "list":
                    return self._json(200, {"versions": versions.listing(f)})
                v = body.get("v")
                if isinstance(v, bool) or not isinstance(v, int):
                    raise ValueError(f"v must be a version number (got {v!r})")
                if action == "get":
                    return self._json(200, {"version": versions.get(f, v)})
                if action == "restore":
                    return self._json(200, {"restored": bom_edit.restore(proj, v)})
                if action == "label":
                    return self._json(200, versions.label(f, v, body.get("label") or ""))
                if action == "state":
                    return self._json(200, versions.set_state(f, v, str(body.get("state") or "")))
                return self._json(404, {"error": "unknown versions action"})
            except PermissionError as e:
                return self._json(403, {"error": str(e)})
            except (ValueError, TypeError, KeyError) as e:
                return self._json(400, {"error": str(e)})
        if self.path == "/api/impact":
            # what one change would change, before it is made (nothing saved): machine or project
            try:
                body = self._obj
                from core import impact
                change = body.get("change") or {}
                if not isinstance(change, dict) or not (change or isinstance(body.get("after"), dict)):
                    raise ValueError("give the change (or the inputs after it)")
                if body.get("kind") == "project":
                    from core import project as P
                    from components.project.select import select as project_select
                    import inspect
                    known = set(inspect.signature(project_select.__wrapped__).parameters) - {"panel", "project"}
                    inputs = {k: v for k, v in (body.get("inputs") or {}).items() if k in known}
                    change = {k: v for k, v in change.items() if k in ("edits", "power_edits", "io_edits", "standby",
                                                                       "incomer_factor", "min_power_wire_mm2")}
                    return self._json(200, impact.project(P.resolve(body.get("project")), str(body.get("panel") or ""), inputs, change))
                params = {p["name"]: p for p in COMPONENTS["requirement"]["params"]}
                conv = lambda d: {k: (TYPES[params[k]["type"]](v) if params[k]["type"] in TYPES and not isinstance(v, (list, dict)) else v)
                                  for k, v in (d or {}).items() if k in params and v not in (None, "")}
                base = conv(body.get("base"))
                ch = {k: v for k, v in change.items() if k in params}
                ch = {k: (None if v is None else conv({k: v}).get(k, v)) for k, v in ch.items()}
                if isinstance(body.get("after"), dict):
                    return self._json(200, impact.machine(base, after=conv(body["after"])))
                return self._json(200, impact.machine(base, ch))
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": str(e)})
        if self.path in ("/api/sld", "/api/export/sld"):
            # single line diagram of a confirmed requirement: JSON sheets for the page, or one printable HTML file
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = self._obj
                from core.sld import build_sld, sld_html
                params = {p["name"]: p for p in COMPONENTS["requirement"]["params"]}
                inputs = {k: TYPES[params[k]["type"]](v) for k, v in body.items() if k in params and v not in (None, "")}
                res = COMPONENTS["requirement"]["fn"](**inputs)
                if res.status == "invalid" or not (res.value or {}).get("selected"):
                    raise ValueError("answer the open questions and confirm before the single line diagram is drawn")
                title = str(body.get("title") or "Panel")[:58]
                level = body.get("level") if body.get("level") in ("fresher", "experienced") else None
                meta = None
                d = body.get("design")
                if isinstance(d, dict) and d.get("project") and d.get("panel"):    # a saved panel: its versions in the title block
                    from core.drawings import meta_for_design
                    try:
                        meta = meta_for_design(str(d["project"]), str(d["panel"]))
                    except ValueError:
                        meta = None
                sheets = build_sld(res.value, title=title, level=level, meta=meta)
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": str(e)})
            if self.path == "/api/sld":
                return self._json(200, {"sheets": sheets})
            data = sld_html(sheets, title).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="Single_line_diagram.html"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/api/export/requirement":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = self._obj
                from core.bom_export import build_requirement
                params = {p["name"]: p for p in COMPONENTS["requirement"]["params"]}
                inputs = {k: TYPES[params[k]["type"]](v) for k, v in body.items() if k in params and v not in (None, "")}
                log = body.get("design_log") if isinstance(body.get("design_log"), list) else []
                level = body.get("level") if body.get("level") in ("fresher", "experienced") else None
                data, _ = build_requirement(inputs, design_log=log, level=level)
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": str(e)})
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="Panel_documents.xlsx"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/api/export/bom":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = self._obj
                from core.bom_export import build
                params = {p["name"]: p for p in COMPONENTS["panel"]["params"]}
                inputs = {}
                for k, v in body.items():
                    if k in params and v not in (None, ""):
                        inputs[k] = TYPES[params[k]["type"]](v)
                title = str(body.get("title") or "Panel")
                proj, _, cpanel = str(body.get("client_panel") or "").rpartition("|")
                data, _ = build(inputs, client_panel=cpanel or None, title=title, project=proj or None)
            except (ValueError, TypeError) as e:
                return self._json(400, {"error": str(e)})
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title)[:40] or "Panel"
            self.send_header("Content-Disposition", f'attachment; filename="{safe}_BOM.xlsx"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith("/api/signoff/"):
            name = self.path.removeprefix("/api/signoff/")
            if name not in review.components():
                return self._json(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                self._json(200, review.sign_off(name, self._obj))
            except ValueError as e:
                self._json(400, {"error": str(e)})
            return
        name = self.path.removeprefix("/api/")
        if not self.path.startswith("/api/") or name not in COMPONENTS:
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = self._obj
            self._json(200, run_component(name, body))
        except ValueError as e:  # includes JSONDecodeError
            self._json(400, {"error": str(e)})

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")


class Server(ThreadingHTTPServer):
    request_queue_size = 64         # the page fetches in parallel; the stdlib default (5) reset bursts of 8+
    daemon_threads = True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    srv = Server((a.host, a.port), Handler)
    print(f"Panel Selector v2 — http://{a.host}:{a.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
