# src/actions/driver.py

from __future__ import annotations
import time
from typing import Iterable, Optional, Tuple
import pyautogui
import pygetwindow as gw

from src.planner.policy import Action

class ActionDriver:
    def __init__(
        self,
        window_title: Optional[str] = None,
        allow_actions: Iterable[str] = ("click", "type", "hotkey", "noop"),
        dry_run: bool = True,
        click_delay_s: float = 0.05,
    ):
        self.window_title = window_title
        self.allow = set(a.lower() for a in allow_actions)
        self.dry = dry_run
        self.click_delay_s = click_delay_s

    # ---------- focus & bounds ----------
    def _focus_window(self) -> Optional[gw.Win32Window]:
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

    def _within_bounds(self, w: gw.Win32Window, coords: Tuple[int,int]) -> bool:
        if not w:
            return True  # no window restriction
        x, y = coords
        left, top, right, bottom = w.left, w.top, w.right, w.bottom
        return (left <= x <= right) and (top <= y <= bottom)

    # ---------- run ----------
    def run(self, a: Action):
        if a.action not in self.allow:
            print(f"[driver] blocked by allow-list: {a.action}")
            return

        w = self._focus_window()

        if a.action == "noop":
            print("[driver] NOOP")
            return

        if a.action == "click":
            if a.coords is None:
                print("[driver] click ignored: no coords provided (descriptor-only).")
                return
            if w and not self._within_bounds(w, a.coords):
                print(f"[driver] click blocked: {a.coords} outside focused window bounds.")
                return
            print(f"[driver] click at {a.coords}")
            if not self.dry:
                pyautogui.moveTo(a.coords[0], a.coords[1])
                pyautogui.click()
                time.sleep(self.click_delay_s)
            return

        if a.action == "type":
            print(f"[driver] type: {a.text!r}")
            if not self.dry and a.text:
                pyautogui.typewrite(a.text, interval=0.01)
            return

        if a.action == "hotkey":
            print(f"[driver] hotkey: {a.keys}")
            if not self.dry and a.keys:
                pyautogui.hotkey(*a.keys)
            return