# src/planner/policy.py

# Deny-by-default: Only actions in the allow_actions set are run.
# Window sandbox: if window_title is set, clicks outside that window’s bounds are blocked.
# Dry-run is True by default; flip to False only when you’re confident.

from __future__ import annotations
import json, re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

VIOLATION = List[str]  # tag strings

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
    violations: Optional[List[str]] = None     # Added violations

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
    Also attach violations tags (e.g., 'format:missing-text', 'format:no-coords').
    """
    vios: List[str] = []
    act = (obj.get("action") or "").lower()
    if act not in ALLOWED_ACTIONS:
        return Action(action="noop", violations=["allowlist:action"])

    if act == "click":
        coords = _as_tuple_xy(obj.get("coords"))
        target = obj.get("target")
        # Require coords OR a target description (driver may ignore target-only)
        if coords is None and not target:
            return Action(action="noop", violations=["format:click-missing-coords-or-target"])
        return Action(action="click", coords=coords, target=target, violations=(["desc-only"] if coords is None else None))

    if act == "type":
        text = obj.get("text")
        if not isinstance(text, str) or text == "":
            return Action(action="noop", violations=["format:type-missing-text"])
        return Action(action="type", text=text)

    if act == "hotkey":
        keys = obj.get("keys")
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys) or not keys:
            return Action(action="noop", violations=["format:hotkey-missing-keys"])
        return Action(action="hotkey", keys=[k.lower() for k in keys])

    return Action(action="noop", violations=["format:unknown"])

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

# Filename policy as a basic enforcement of "truthfulness"
def enforce_expected_filename(a: Action, expected: Optional[str]) -> Action:
    if a.action == "type" and expected and a.text and a.text != expected:
        a.violations = (a.violations or []) + ["instruction-mismatch:filename"]
    return a