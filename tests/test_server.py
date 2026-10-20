"""Web server: security and robustness (flow + security test agent findings, 2026-10-14).

Starts the real server on a free local port in a thread and talks HTTP to it.
"""
import http.client
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webapp"))
import server  # noqa: E402


COOKIE = {}      # the test user's session (owner 2026-10-16: every request needs a signed-in user)


@pytest.fixture(scope="module")
def port(tmp_path_factory):
    import secrets
    from core import auth
    users = tmp_path_factory.mktemp("auth") / "users.yaml"      # a test user store, never the real one
    old = auth.USERS
    auth.USERS = users
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    srv = server.Server(("127.0.0.1", p), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    COOKIE["pw"] = secrets.token_urlsafe(12)
    c = http.client.HTTPConnection("127.0.0.1", p, timeout=20)
    c.request("POST", "/api/auth/setup", body=json.dumps({"name": "QA admin", "password": COOKIE["pw"]}),
              headers={"Content-Type": "application/json"})
    r = c.getresponse(); r.read()
    COOKIE["value"] = r.getheader("Set-Cookie").split(";")[0]
    c.close()
    yield p
    srv.shutdown()
    auth.USERS = old


def req(port, method, path, body=None, headers=None, raw=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    h = {"Content-Type": "application/json", **({"Cookie": COOKIE["value"]} if COOKIE.get("value") else {}), **(headers or {})}
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    out = r.status, r.read()
    c.close()
    return out


def test_page_and_api_work(port):
    assert req(port, "GET", "/")[0] == 200
    code, b = req(port, "POST", "/api/motor_flc", {"kw": 7.5})
    assert code == 200 and json.loads(b)["value"]["flc_a"] == 15.5


def test_foreign_host_is_refused(port):
    """DNS rebinding: another site's name pointing at 127.0.0.1 must not read or write."""
    assert req(port, "GET", "/api/projects", headers={"Host": "evil.example"})[0] == 403
    assert req(port, "POST", "/api/motor_flc", {"kw": 7.5}, headers={"Host": "evil.example"})[0] == 403


def test_cross_site_post_is_refused(port):
    """CSRF: a page on another origin (or a text/plain 'simple' request) must not sign off or save edits."""
    assert req(port, "POST", "/api/signoff/motor_flc", {"name": "x"}, headers={"Origin": "http://evil.example"})[0] == 403
    assert req(port, "POST", "/api/bom/list", {}, headers={"Content-Type": "text/plain"})[0] == 415
    assert req(port, "POST", "/api/motor_flc", {"kw": 7.5}, headers={"Origin": f"http://127.0.0.1:{port}"})[0] == 200


@pytest.mark.parametrize("path", ["/api/mccb", "/api/requirement", "/api/export/bom", "/api/sld", "/api/bom/check",
                                  "/api/signoff/motor_flc", "/api/export/project", "/api/export/requirement"])
@pytest.mark.parametrize("raw", [b"[1]", b'"x"', b"{bad json", b"1"])
def test_bad_bodies_get_an_answer(port, path, raw):
    """A JSON list / string / garbage used to drop the connection with no response."""
    code, b = req(port, "POST", path, raw=raw)
    assert code == 400 and "error" in json.loads(b)


def test_oversized_body_is_refused(port):
    """Announcing 50 MB is refused before the body is read (no thread waits for it)."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.putrequest("POST", "/api/requirement")
    c.putheader("Content-Type", "application/json")
    c.putheader("Content-Length", str(50 * 1024 * 1024))
    c.endheaders()
    assert c.getresponse().status == 413
    c.close()


def test_responses_are_strict_json(port):
    """NaN / Infinity are not JSON: a page could not parse the answer."""
    code, b = req(port, "POST", "/api/mccb", {"ib_a": "NaN", "fault_ka": 25, "ambient_c": 40})
    assert b"NaN" not in b and b"Infinity" not in b
    json.loads(b)


def test_list_inputs_work_over_http(port):
    """control_circuit coil_power (a list) reached select() as a string: golden T08 failed over HTTP."""
    code, b = req(port, "POST", "/api/control_circuit",
                  {"supply": "transformer", "coil_power": [{"close_va": 77, "hold_va": 9.8, "qty": 2},
                                                           {"close_va": 27, "hold_va": 4.2, "qty": 3}]})
    assert code == 200 and json.loads(b)["value"]["load_va"] == 99.4


def test_bom_errors_are_input_errors(port):
    from core import project as P
    proj = P.names()[0]
    assert req(port, "POST", "/api/bom/check", {"project": proj, "line": "x", "edit": {"action": "qty", "qty": "inf"}})[0] == 400
    assert req(port, "POST", "/api/bom/undo", {"project": proj, "id": 1.5})[0] == 400


def test_xlsx_text_is_cleaned_of_control_characters():
    from core.xlsx import _cell_text
    assert _cell_text("A\x01B\x0bC\tD") == "ABC\tD"


@pytest.mark.parametrize("host", ["[::1]evil:80", "127.0.0.1:evil.example", "127.0.0.1:8020, evil.example", "127.0.0.1.", "LOCALHOST.evil"])
def test_host_must_match_whole(port, host):
    """Regression round 2026-10-14: loose Host parsing accepted these."""
    assert req(port, "GET", "/api/projects", headers={"Host": host})[0] == 403


def test_null_origin_cannot_post(port):
    assert req(port, "POST", "/api/motor_flc", {"kw": 7.5}, headers={"Origin": "null"})[0] == 403


def test_chunked_body_is_refused_clearly(port):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.putrequest("POST", "/api/motor_flc")
    c.putheader("Content-Type", "application/json")
    c.putheader("Transfer-Encoding", "chunked")
    c.endheaders()
    assert c.getresponse().status == 411
    c.close()


def test_bursts_of_parallel_requests_are_answered(port):
    """Regression round 2026-10-14: 8+ simultaneous connections were reset (listen queue of 5)."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(32) as ex:
        codes = list(ex.map(lambda _: req(port, "GET", "/api/components")[0], range(64)))
    assert codes.count(200) == 64



# owner 2026-10-16: login with roles
def test_sign_in_is_required(port):
    assert req(port, "POST", "/api/motor_flc", {"kw": 7.5}, headers={"Cookie": ""})[0] == 401
    assert req(port, "GET", "/api/projects", headers={"Cookie": ""})[0] == 401
    assert req(port, "GET", "/", headers={"Cookie": ""})[0] == 200                          # the sign-in page itself
    code, b = req(port, "GET", "/api/auth/status", headers={"Cookie": ""})
    assert code == 200 and json.loads(b) == {"setup_needed": False, "user": None}
    assert req(port, "POST", "/api/auth/setup", {"name": "Second", "password": "x" * 10}, headers={"Cookie": ""})[0] in (401, 403)


def test_session_cookie_is_httponly_strict(port):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request("POST", "/api/auth/login", body=json.dumps({"name": "QA admin", "password": COOKIE["pw"]}),
              headers={"Content-Type": "application/json"})
    r = c.getresponse(); r.read()
    ck = r.getheader("Set-Cookie")
    assert r.status == 200 and "HttpOnly" in ck and "SameSite=Strict" in ck and "Path=/" in ck
    assert req(port, "POST", "/api/auth/login", {"name": "QA admin", "password": "wrong-pass"})[0] == 401


def test_roles_decide_what_a_user_may_change(port):
    import secrets
    pw = secrets.token_urlsafe(12)
    assert req(port, "POST", "/api/auth/add", {"name": "QA checker", "password": pw, "roles": ["checker"]})[0] == 200
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request("POST", "/api/auth/login", body=json.dumps({"name": "QA checker", "password": pw}), headers={"Content-Type": "application/json"})
    r = c.getresponse(); r.read(); ck = r.getheader("Set-Cookie").split(";")[0]
    assert req(port, "POST", "/api/motor_flc", {"kw": 7.5}, headers={"Cookie": ck})[0] == 200          # calculations: any user
    assert req(port, "POST", "/api/designs/create", {"name": "x"}, headers={"Cookie": ck})[0] == 403    # changes: designer
    assert req(port, "POST", "/api/auth/users", {}, headers={"Cookie": ck})[0] == 403                    # users: admin
    assert req(port, "POST", "/api/auth/remove", {"name": "QA admin"})[0] == 400                       # not yourself
    assert req(port, "POST", "/api/auth/remove", {"name": "QA checker"})[0] == 200
    assert req(port, "POST", "/api/motor_flc", {"kw": 7.5}, headers={"Cookie": ck})[0] == 401          # removed: signed out


# RFQ import, stage 1 (owner 2026-10-18): upload needs the designer role; the file is read and checked before it is kept
def test_rfq_upload_get_list(port, tmp_path, monkeypatch):
    import base64
    import secrets
    from core import rfq
    monkeypatch.setattr(rfq, "RFQS", tmp_path / "rfq")                    # never the real rfq/ folder
    pdf = (Path(__file__).resolve().parents[1] / "sources" / "Sample complete" /
           "Complete Equipment Panel Specification_Siemens_Rev02_WNS2503_03062025.pdf").read_bytes()
    st, j = req(port, "POST", "/api/rfq/upload", {"filename": "spec.pdf", "data": base64.b64encode(pdf).decode()})
    j = json.loads(j)
    assert st == 200 and [p["name"] for p in j["rfq"]["summary"]] == ["BIO/UF", "RO"], j
    st, g = req(port, "POST", "/api/rfq/get", {"id": j["rfq"]["id"]})
    g = json.loads(g)
    assert st == 200 and g["rfq"]["panels"][0]["printed"]["total_kw"] == 264.1
    assert json.loads(req(port, "POST", "/api/rfq/list", {})[1])["rfqs"][0]["id"] == j["rfq"]["id"]
    assert req(port, "POST", "/api/rfq/upload", {"filename": "x.pdf", "data": "not base64!"})[0] == 400
    assert req(port, "POST", "/api/rfq/upload", {"filename": "x.pdf", "data": base64.b64encode(b"hello").decode()})[0] == 400
    pw = secrets.token_urlsafe(12)
    assert req(port, "POST", "/api/auth/add", {"name": "QA viewer", "password": pw, "roles": ["checker"]})[0] == 200
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request("POST", "/api/auth/login", body=json.dumps({"name": "QA viewer", "password": pw}), headers={"Content-Type": "application/json"})
    r = c.getresponse(); r.read(); ck = r.getheader("Set-Cookie").split(";")[0]
    assert req(port, "POST", "/api/rfq/upload", {"filename": "spec.pdf", "data": base64.b64encode(pdf).decode()}, headers={"Cookie": ck})[0] == 403
    assert req(port, "POST", "/api/rfq/get", {"id": j["rfq"]["id"]}, headers={"Cookie": ck})[0] == 200    # viewing: any user
    assert req(port, "POST", "/api/auth/remove", {"name": "QA viewer"})[0] == 200


# RFQ stage 2: the questions are readable by any user; answering needs the designer role and is checked
def test_rfq_questions_and_answer(port, tmp_path, monkeypatch):
    import base64
    from core import rfq
    monkeypatch.setattr(rfq, "RFQS", tmp_path / "rfq")
    pdf = (Path(__file__).resolve().parents[1] / "sources" / "Sample complete" /
           "Complete Equipment Panel Specification_Siemens_Rev02_WNS2503_03062025.pdf").read_bytes()
    rid = json.loads(req(port, "POST", "/api/rfq/upload", {"filename": "spec.pdf", "data": base64.b64encode(pdf).decode()})[1])["rfq"]["id"]
    st, q = req(port, "POST", "/api/rfq/questions", {"id": rid})
    q = json.loads(q)["questions"]
    assert st == 200 and q["complete"] is False and q["project_open"] > 0
    st, a = req(port, "POST", "/api/rfq/answer", {"id": rid, "scope": "project", "key": "fault_ka", "value": 50})
    assert st == 200 and json.loads(a)["answer"]["value"] == 50
    assert req(port, "POST", "/api/rfq/answer", {"id": rid, "scope": "project", "key": "fault_ka", "value": "x"})[0] == 400
    q2 = json.loads(req(port, "POST", "/api/rfq/questions", {"id": rid})[1])["questions"]
    assert q2["project_open"] == q["project_open"] - 1 and q2["history"][-1]["by"]


# RFQ stage 3: a panel's BOM is refused politely (not built) while its questions are open; the workbook still lists it
def test_rfq_bom_routes(port, tmp_path, monkeypatch):
    import base64
    from core import rfq
    monkeypatch.setattr(rfq, "RFQS", tmp_path / "rfq")
    pdf = (Path(__file__).resolve().parents[1] / "sources" / "Sample complete" /
           "Complete Equipment Panel Specification_Siemens_Rev02_WNS2503_03062025.pdf").read_bytes()
    rid = json.loads(req(port, "POST", "/api/rfq/upload", {"filename": "spec.pdf", "data": base64.b64encode(pdf).decode()})[1])["rfq"]["id"]
    st, b = req(port, "POST", "/api/rfq/bom", {"id": rid, "panel": "RO"})
    b = json.loads(b)["bom"]
    assert st == 200 and b["ready"] is False and b["missing"]
    assert req(port, "POST", "/api/rfq/bom", {"id": rid, "panel": "XX"})[0] == 400
    st, data = req(port, "POST", "/api/rfq/bom_xlsx", {"id": rid})
    assert st == 200 and data[:2] == b"PK"                                  # the workbook, panels listed as not built


# one page per job (owner 2026-10-19): every page address serves the app; other addresses are not pages
def test_page_addresses(port):
    for path in ("/start", "/projects", "/new", "/design?project=x&panel=y", "/rfq", "/rfq/RFQ-0123456789", "/templates",
                 "/client-projects", "/components/motor_flc", "/review", "/admin"):
        st, body = req(port, "GET", path)
        assert st == 200 and b"Panel Selector v2" in body, path
    assert req(port, "GET", "/nothing-here")[0] in (401, 404)


# company standards (owner 2026-10-19): the routes; the author cannot approve their own standard (four eyes)
def test_standards_routes(port, tmp_path, monkeypatch):
    from core import standards
    monkeypatch.setattr(standards, "STANDARDS", tmp_path / "standards")
    st, j = req(port, "POST", "/api/standards/list", {})
    j = json.loads(j)
    assert st == 200 and j["standards"] == [] and "fault_ka" in j["site"] and not any(x["key"] == "fault_ka" for x in j["questions"])
    st, s = req(port, "POST", "/api/standards/save", {"name": "QA standard", "values": {"relay_make": "finder"}})
    s = json.loads(s)["standard"]
    assert st == 200 and s["state"] == "draft"
    assert req(port, "POST", "/api/standards/save", {"name": "QA site", "values": {"fault_ka": 50}})[0] == 400
    assert req(port, "POST", "/api/standards/approve", {"id": s["id"], "v": 1})[0] == 403          # its own author
    assert req(port, "GET", "/standards")[0] == 200


# the client's specification with the RFQ (owner 2026-10-20): uploaded beside it, returned with it
def test_rfq_spec_upload(port, tmp_path, monkeypatch):
    import base64
    from core import rfq
    monkeypatch.setattr(rfq, "RFQS", tmp_path / "rfq")
    root = Path(__file__).resolve().parents[1]
    pdf = (root / "sources" / "Sample complete" / "Complete Equipment Panel Specification_Siemens_Rev02_WNS2503_03062025.pdf").read_bytes()
    auto = (root / "sources" / "pdf" / "client" / "ECI-WNS2503" / "Automation_Rittal  Panel Specification_Siemens_Rev02_WNS2503_03062025.pdf").read_bytes()
    rid = json.loads(req(port, "POST", "/api/rfq/upload", {"filename": "spec.pdf", "data": base64.b64encode(pdf).decode()})[1])["rfq"]["id"]
    assert json.loads(req(port, "POST", "/api/rfq/get", {"id": rid})[1])["spec"] is None
    st, j = req(port, "POST", "/api/rfq/spec_upload", {"id": rid, "filename": "auto.pdf", "data": base64.b64encode(auto).decode()})
    assert st == 200 and len(json.loads(j)["spec"]["rows"]) > 20
    g = json.loads(req(port, "POST", "/api/rfq/get", {"id": rid})[1])
    assert g["spec"]["filename"] == "auto.pdf" and "BIO/UF" in g["spec"]["plc"]
    assert req(port, "POST", "/api/rfq/spec_upload", {"id": rid, "filename": "x.pdf", "data": base64.b64encode(b"hello").decode()})[0] == 400
