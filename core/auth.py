"""Login and roles (owner 2026-10-16): every designer signs in; what they may do follows their roles.

Roles: designer (create and edit projects, panels and templates copies), checker (mark a version checked), approver
(mark a checked version approved), admin (add and remove users). A user may hold several roles.

Passwords are never stored: only a salted scrypt hash (hashlib, n = 2**14, r = 8, p = 1). A session is a random token
in an HttpOnly, SameSite=Strict cookie, kept in memory (a restart signs everyone out) and dropped after 12 h idle.
Five wrong passwords for one name lock that name for 60 s. The first user is created on the first start (setup) and is
an admin; after that only an admin adds users.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
USERS = ROOT / "auth" / "users.yaml"
ROLES = ("designer", "checker", "approver", "admin")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 ._\-]{1,39}$")
IDLE_S = 12 * 3600
_lock = threading.Lock()
_sessions: dict[str, dict] = {}
_fails: dict[str, list[float]] = {}
_local = threading.local()


def _load() -> dict:
    return (yaml.safe_load(USERS.read_text()) or {}).get("users", {}) if USERS.exists() else {}


def _save(users: dict) -> None:
    USERS.parent.mkdir(parents=True, exist_ok=True)
    USERS.write_text("# Panel Selector users: names, roles and salted scrypt password hashes (never the passwords).\n"
                     + yaml.safe_dump({"users": users}, sort_keys=True, allow_unicode=True))
    try:
        USERS.chmod(0o600)
    except OSError:
        pass


def _hash(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def _check_pw(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        return hmac.compare_digest(_hash(pw, bytes.fromhex(salt)), stored)
    except (ValueError, TypeError):
        return False


def _valid(name, pw, roles) -> list[str]:
    if not isinstance(name, str) or not NAME.match(name):
        raise ValueError("user name: 2–40 characters, starting with a letter (letters, digits, space, . _ -)")
    if not isinstance(pw, str) or len(pw) < 8 or len(pw) > 200:
        raise ValueError("password: at least 8 characters")
    roles = [r for r in (roles or []) if r in ROLES]
    if not roles:
        raise ValueError(f"give at least one role: {', '.join(ROLES)}")
    return roles


def setup_needed() -> bool:
    return not _load()


def setup(name: str, pw: str) -> dict:
    """The first user (admin + every role), only while no user exists."""
    with _lock:
        if _load():
            raise PermissionError("setup is done: ask an admin to add you")
        roles = _valid(name, pw, list(ROLES))
        _save({name: {"roles": roles, "hash": _hash(pw), "created": datetime.now().isoformat(timespec="seconds")}})
    return {"name": name, "roles": roles}


def add_user(name: str, pw: str, roles: list[str]) -> dict:
    with _lock:
        users = _load()
        if name in users:
            raise ValueError(f"{name} exists already")
        roles = _valid(name, pw, roles)
        users[name] = {"roles": roles, "hash": _hash(pw), "created": datetime.now().isoformat(timespec="seconds")}
        _save(users)
    return {"name": name, "roles": roles}


def set_roles(name: str, roles: list[str]) -> dict:
    with _lock:
        users = _load()
        if name not in users:
            raise ValueError(f"no user {name}")
        roles = [r for r in roles or [] if r in ROLES]
        if not roles:
            raise ValueError("give at least one role")
        if "admin" not in roles and _admins(users) == [name]:
            raise ValueError("the last admin keeps the admin role")
        users[name]["roles"] = roles
        _save(users)
    return {"name": name, "roles": roles}


def _admins(users: dict) -> list[str]:
    return [n for n, u in users.items() if "admin" in u.get("roles", [])]


def remove_user(name: str) -> None:
    with _lock:
        users = _load()
        if name not in users:
            raise ValueError(f"no user {name}")
        if _admins(users) == [name]:
            raise ValueError("the last admin cannot be removed")
        del users[name]
        _save(users)
        for t in [t for t, s in _sessions.items() if s["user"] == name]:
            _sessions.pop(t, None)


def set_password(name: str, pw: str) -> None:
    with _lock:
        users = _load()
        if name not in users:
            raise ValueError(f"no user {name}")
        _valid(name, pw, users[name]["roles"])
        users[name]["hash"] = _hash(pw)
        _save(users)


def listing() -> list[dict]:
    return [{"name": n, "roles": u.get("roles", []), "created": u.get("created")} for n, u in sorted(_load().items())]


def login(name: str, pw: str) -> str:
    """A new session token, or PermissionError (same message for an unknown name and a wrong password)."""
    now = time.time()
    with _lock:
        recent = [t for t in _fails.get(str(name), []) if now - t < 60]
        if len(recent) >= 5:
            raise PermissionError("too many wrong passwords: wait a minute")
        u = _load().get(str(name))
        if not u or not isinstance(pw, str) or not _check_pw(pw, u["hash"]):
            _fails[str(name)] = recent + [now]
            raise PermissionError("name or password not recognised")
        _fails.pop(str(name), None)
        token = secrets.token_urlsafe(32)
        _sessions[token] = {"user": name, "at": now, "last": now}
    return token


def session(token: str | None) -> dict | None:
    """{'name', 'roles'} for a live session (refreshes its idle time), else None."""
    if not token:
        return None
    with _lock:
        s = _sessions.get(token)
        if s is None:
            return None
        if time.time() - s["last"] > IDLE_S:
            _sessions.pop(token, None)
            return None
        u = _load().get(s["user"])
        if u is None:
            _sessions.pop(token, None)
            return None
        s["last"] = time.time()
        return {"name": s["user"], "roles": list(u.get("roles", []))}


def logout(token: str | None) -> None:
    with _lock:
        _sessions.pop(token or "", None)


# the signed-in user of the request being handled (one thread per request): versions record who made them
def set_current(user: dict | None) -> None:
    _local.user = user


def current() -> dict | None:
    return getattr(_local, "user", None)


def require(role: str) -> dict:
    u = current()
    if u is None:
        raise PermissionError("sign in first")
    if role not in u["roles"] and "admin" not in u["roles"]:
        raise PermissionError(f"needs the {role} role")
    return u
