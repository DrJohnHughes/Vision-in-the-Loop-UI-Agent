# src/actions/driver.py

# Single exit point for logging no matter how the method returns (or throws)
#     finally: writes one JSONL record.
#
# Status taxonomy: ok:executed, ok:dry-run, blocked:*, ignored:*, error:*—easy to filter in dashboards.

from __future__ import annotations        # Needed for <3.11

import os, pathlib, time, json
from pathlib import Path

import json, pathlib, time
from typing import Iterable, Optional, Tuple, Dict

import pyautogui
import pygetwindow as gw

from src.planner.policy import Action

# resolve repo root (…/repo/src/actions/driver.py -> parents[2] == repo root)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_env_trace = os.environ.get("TRACE_DIR")
_DEFAULT_TRACE_DIR = Path(os.environ.get("TRACE_DIR", _REPO_ROOT / "traces"))
_DEFAULT_TRACE_DIR.mkdir(parents=True, exist_ok=True)

print("[driver] REPO_ROOT:", '\\'.join(str(_REPO_ROOT).split("\\")[-1:]))
print("[driver] TRACE_DIR:", '\\'.join(str(_DEFAULT_TRACE_DIR).split("\\")[-2:]))

class ActionDriver:
    def __init__(
        self,
        window_title: Optional[str] = None,
        allow_actions: Iterable[str] = ("click", "type", "hotkey", "noop"),
        dry_run: bool = True,
        click_delay_s: float = 0.05,
        trace_dir: Path = _DEFAULT_TRACE_DIR,

    ):
        # store and ensure directory exists
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)

        self.window_title = window_title
        self.allow = set(a.lower() for a in allow_actions)
        self.dry = dry_run
        self.click_delay_s = click_delay_s




    # ---------- focus & bounds ----------
    def _focus_window(self) -> Optional[Any]:
        if not self.window_title:
            return None
        wins = gw.getWindowsWithTitle(self.window_title)
        if not wins:
            print(f"[driver] window not found: {self.window_title!r}")
            return None
        w = wins[0]
        if not w.isActive:
            w.activate()
            time.sleep(0.15)
        return w

    def _within_bounds(self, w: Any, coords: Tuple[int, int]) -> bool:
        if not w:
            return True  # no window restriction
        x, y = coords
        return (w.left <= x <= w.right) and (w.top <= y <= w.bottom)

    def _action_to_dict(self, a: Action) -> dict:
        # pydantic v2
        if hasattr(a, "model_dump"):
            return a.model_dump()
        # pydantic v1
        if hasattr(a, "dict"):
            return a.dict()
        # dataclass or simple object
        return getattr(a, "__dict__", {"repr": repr(a)})

    def _trace(self, a: Action, status: str, error: Optional[str], w: Optional[Any],
               context: Optional[dict] = None, t_start: Optional[float] = None):
        rec = {
            "ts": time.time(),
            "mode": "dry_run" if self.dry else "execute",
            "window": self.window_title,
            "focused_window": (w.title if w else None),
            "action": self._action_to_dict(a),
            "violations": getattr(a, "violations", None),
            "status": status,
            "error": error,
            "context": context or {},      # added context
        }
        if t_start is not None:
            rec["duration_ms"] = int((time.time() - t_start) * 1000)
        trace_file = self.trace_dir / "trace.jsonl"
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        with open(trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    # ---------- run ----------
    def run(self, a: Action, context: Optional[dict] = None):
        status = "init"
        err = None
        w = None
        t0 = time.time()

        try:
            if a.action not in self.allow:
                status = "blocked:not-allowed"
                print(f"[driver] blocked by allow-list: {a.action}")
                return
            w = self._focus_window()

            if a.action == "noop":
                status = "ok:noop"
                print("[driver] NOOP")
                return

            if a.action == "click":
                if a.coords is None:
                    status = "ignored:no-coords"
                    print("[driver] click ignored: no coords provided.")
                    return
                if w and not self._within_bounds(w, a.coords):
                    status = "blocked:out-of-bounds"
                    print(f"[driver] click blocked: {a.coords} outside window bounds.")
                    return
                print(f"[driver] click at {a.coords}")
                if not self.dry:
                    pyautogui.moveTo(a.coords[0], a.coords[1])
                    pyautogui.click()
                    time.sleep(self.click_delay_s)
                status = "ok:dry-run" if self.dry else "ok:executed"
                return

            if a.action == "type":
                txt = getattr(a, "text", "")
                print(f"[driver] type: {txt!r}")
                if not self.dry and txt:
                    pyautogui.typewrite(txt, interval=0.01)
                status = "ok:dry-run" if self.dry else "ok:executed"
                return

            if a.action == "hotkey":
                keys = tuple(getattr(a, "keys", ()))
                print(f"[driver] hotkey: {keys}")
                if not self.dry and keys:
                    pyautogui.hotkey(*keys)
                status = "ok:dry-run" if self.dry else "ok:executed"
                return

            status = f"ignored:unknown-action:{a.action}"
            print(f"[driver] unknown action: {a.action!r}")

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            status = "error:exception"
            raise
        finally:
            self._trace(a, status, err, w, context=context, t_start=t0)
