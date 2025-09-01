# src/planner/policy.py

# Deny-by-default: Only actions in the allow_actions set are run.
# Window sandbox: if window_title is set, clicks outside that window’s bounds are blocked.
# Dry-run is True by default; flip to False only when you’re confident.

from __future__ import annotations
import json, re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_ACTIONS = {"click", "type", "hotkey", "noop"}

JSON_HINT = (
    "Return ONLY a single JSON object with keys: "
    '{"action":"click|type|hotkey|noop",'
    '"target":"optional description",'
    '"coords":[x,y],'
    '"text":"string for typing",'
    '"keys":["ctrl","s"]}'
)

@dataclass
class Action:
    action: str
    target: Optional[str] = None
    coords: Optional[Tuple[int, int]] = None
    text: Optional[str] = None
    keys: Optional[List[str]] = None

def extract_json_block(text: str) -> Dict[str, Any]:
    """
    Grab the first {...} block that looks like JSON and parse it.
    Falls back to {} on failure.
    """
    # Fast path: the entire response is JSON
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except Exception:
            pass

    # Fallback: regex the first top-level {...}
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        blob = m.group(0)
        try:
            return json.loads(blob)
        except Exception:
            # Remove trailing commas or backticks if present
            blob = re.sub(r",\s*([}\]])", r"\1", blob)
            blob = blob.replace("```", "")
            try:
                return json.loads(blob)
            except Exception:
                return {}
    return {}

def _as_tuple_xy(val) -> Optional[Tuple[int, int]]:
    if isinstance(val, (list, tuple)) and len(val) == 2:
        try:
            x, y = int(val[0]), int(val[1])
            return (x, y)
        except Exception:
            return None
    return None

def validate_action(obj: Dict[str, Any]) -> Action:
    """
    Enforce schema + allow-list. Convert bad plans into 'noop'.
    """
    act = (obj.get("action") or "").lower()
    if act not in ALLOWED_ACTIONS:
        return Action(action="noop")

    if act == "click":
        coords = _as_tuple_xy(obj.get("coords"))
        target = obj.get("target")
        # Require coords OR a target description (driver may ignore target-only)
        if coords is None and not target:
            return Action(action="noop")
        return Action(action="click", coords=coords, target=target)

    if act == "type":
        text = obj.get("text")
        if not isinstance(text, str) or text == "":
            return Action(action="noop")
        return Action(action="type", text=text)

    if act == "hotkey":
        keys = obj.get("keys")
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys) or not keys:
            return Action(action="noop")
        return Action(action="hotkey", keys=[k.lower() for k in keys])

    return Action(action="noop")

def extract_and_validate_action(raw_text: str) -> Action:
    """
    Main entry: take raw LLM text, return a safe Action dataclass.
    """
    obj = extract_json_block(raw_text)
    return validate_action(obj)

def system_prompt() -> str:
    return (
        "You are a Windows UI agent. "
        "Decide the next atomic action to advance the user's goal.\n"
        + JSON_HINT
        + "\nNo explanations. No markdown. JSON only."
    )