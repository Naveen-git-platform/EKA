"""Server-Sent Events formatting."""
from __future__ import annotations

import json
from typing import Any


def format_sse(event: dict[str, Any]) -> str:
    """Serialise an agent event as one SSE frame: `event: <type>` + single-line JSON `data:` + blank line."""
    name = str(event.get("type", "message"))
    payload = json.dumps(event, ensure_ascii=False, default=str)  # json.dumps never emits raw newlines
    return f"event: {name}\ndata: {payload}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx) so tokens arrive immediately
}
