from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class HistoryCommand:
    label: str
    # Commands keep only files that actually changed. None means the file did not
    # exist in that side of the operation. This avoids storing a full Quest Book
    # twice for every Ctrl+Z step.
    before: dict[str, bytes | None]
    after: dict[str, bytes | None]


class QuestHistory:
    """Memory-conscious undo/redo for FTB Quests SNBT files.

    Callers take a temporary full snapshot before and after an operation. `push()`
    immediately reduces those snapshots to a file-level delta, so 60 history steps
    do not mean 120 complete copies of every chapter in memory.
    """

    def __init__(self, limit: int = 60) -> None:
        self.limit = max(5, int(limit))
        self.undo_stack: list[HistoryCommand] = []
        self.redo_stack: list[HistoryCommand] = []

    @staticmethod
    def snapshot(root: Path) -> dict[str, bytes]:
        if not root.exists():
            return {}
        out: dict[str, bytes] = {}
        for p in root.rglob("*.snbt"):
            if not p.is_file():
                continue
            try:
                out[p.relative_to(root).as_posix()] = p.read_bytes()
            except OSError:
                continue
        return out

    def push(self, label: str, before: dict[str, bytes], after: dict[str, bytes]) -> bool:
        keys = before.keys() | after.keys()
        changed = [k for k in keys if before.get(k) != after.get(k)]
        if not changed:
            return False
        before_delta = {k: before.get(k) for k in changed}
        after_delta = {k: after.get(k) for k in changed}
        self.undo_stack.append(HistoryCommand(label, before_delta, after_delta))
        if len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        return True

    @staticmethod
    def _apply_delta(root: Path, delta: dict[str, bytes | None]) -> None:
        root.mkdir(parents=True, exist_ok=True)
        for rel, raw in delta.items():
            p = root / rel
            if raw is None:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)

    def undo(self, root: Path) -> str | None:
        if not self.undo_stack:
            return None
        cmd = self.undo_stack.pop()
        self._apply_delta(root, cmd.before)
        self.redo_stack.append(cmd)
        return cmd.label

    def redo(self, root: Path) -> str | None:
        if not self.redo_stack:
            return None
        cmd = self.redo_stack.pop()
        self._apply_delta(root, cmd.after)
        self.undo_stack.append(cmd)
        return cmd.label

    def clear(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self.redo_stack)
