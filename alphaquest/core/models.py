from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class ItemEntry:
    item_id: str
    namespace: str
    path: str
    display_name: str = ""
    texture_bytes: bytes | None = None
    source_jar: Path | None = None
    model_path: str | None = None
    texture_ref: str | None = None


@dataclass(slots=True)
class TaskInfo:
    task_id: str = ""
    task_type: str = ""
    item_id: str = ""
    count: int = 1
    title: str = ""
    raw: str = ""


@dataclass(slots=True)
class RewardInfo:
    reward_id: str = ""
    reward_type: str = ""
    item_id: str = ""
    count: int = 1
    amount: int = 0
    raw: str = ""


@dataclass(slots=True)
class QuestInfo:
    quest_id: str
    chapter_id: str
    source_file: Path
    x: float = 0.0
    y: float = 0.0
    size: float = 0.0
    shape: str = ""
    icon_item_id: str = ""
    title_key: str = ""
    title: str = ""
    description_key: str = ""
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    tasks: list[TaskInfo] = field(default_factory=list)
    rewards: list[RewardInfo] = field(default_factory=list)
    optional: bool = False
    invisible: bool = False
    hide_until_deps_complete: str = "default"
    hide_until_deps_visible: str = "default"
    hide_dependency_lines: str = "default"
    hide_dependent_lines: bool = False
    require_sequential_tasks: str = "default"
    can_repeat: str = "default"
    min_required_dependencies: int = 0
    raw_block: str = ""
    block_start: int = -1
    block_end: int = -1

    @property
    def primary_item_id(self) -> str:
        for task in self.tasks:
            if task.task_type == "item" and task.item_id:
                return task.item_id
        return self.icon_item_id


@dataclass(slots=True)
class ChapterGroupInfo:
    group_id: str
    title_key: str
    title: str
    icon_item_id: str = ""
    raw_block: str = ""


@dataclass(slots=True)
class ChapterInfo:
    chapter_id: str
    title_key: str
    title: str
    filename: str
    source_file: Path
    icon_item_id: str = ""
    group_id: str = ""
    order_index: int = 0
    default_quest_shape: str = ""
    default_quest_size: float = 1.0
    quests: list[QuestInfo] = field(default_factory=list)


@dataclass(slots=True)
class Problem:
    severity: str  # error | warning | info
    code: str
    message: str
    file: Optional[Path] = None
    quest_id: str = ""
