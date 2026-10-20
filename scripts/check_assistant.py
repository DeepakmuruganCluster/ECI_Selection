"""Check the Claude API settings the web app uses (~/.config/panel-selector/anthropic.env), without printing the key.

    .venv/bin/python scripts/check_assistant.py

Makes one tiny request and prints OK, or the API's error with what to do about it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import assistant  # noqa: E402


def main() -> int:
    key, ws = assistant.api_key(), assistant.workspace_id()
    if not key:
        print("No ANTHROPIC_API_KEY in ~/.config/panel-selector/anthropic.env")
        return 1
    print(f"key: {key[:11]}… ({len(key)} characters); workspace ID: {'set' if ws else 'not set'}")
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=30,
                                 default_headers={"anthropic-workspace-id": ws} if ws else None)
    try:
        r = client.messages.create(model=assistant.MODEL, max_tokens=10,
                                   messages=[{"role": "user", "content": "Reply with the word ok"}])
    except anthropic.APIStatusError as e:
        msg = str(getattr(e, "message", e))
        print(f"FAILED ({e.status_code}): {msg[:300]}")
        if "workspace" in msg:
            print("→ This key is not tied to a workspace. Add ANTHROPIC_WORKSPACE_ID=wrkspc_… to the settings file "
                  "(Console → Settings → Workspaces), or create the key inside a workspace.")
        elif e.status_code == 401:
            print("→ The key is not accepted (revoked or mistyped). Create a new key in the Console.")
        return 1
    except anthropic.APIConnectionError as e:
        print(f"FAILED: no connection to the API ({e})")
        return 1
    print("OK — the assistant answers:", r.content[0].text.strip()[:40])
    return 0


if __name__ == "__main__":
    sys.exit(main())
