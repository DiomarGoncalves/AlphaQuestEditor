from __future__ import annotations

from collections import Counter, defaultdict

from .models import Problem
from .mod_index import ModIndex
from .questbook import QuestBook


HEX_MAX = 0x7FFFFFFFFFFFFFFF


def _valid_ftb_id(value: str) -> bool:
    if not value:
        return False
    try:
        number = int(value, 16)
    except ValueError:
        return False
    return 0 < number <= HEX_MAX


def validate(book: QuestBook, mods: ModIndex) -> list[Problem]:
    problems: list[Problem] = []
    all_quests = [q for ch in book.chapters for q in ch.quests]
    ids = [q.quest_id for q in all_quests if q.quest_id]
    counts = Counter(ids)

    for q in all_quests:
        if not q.quest_id:
            problems.append(Problem("error", "quest.missing_id", "Quest sem ID.", q.source_file))
        elif not _valid_ftb_id(q.quest_id):
            problems.append(Problem("error", "quest.invalid_id", f"ID de quest inválido: {q.quest_id}", q.source_file, q.quest_id))
        elif counts[q.quest_id] > 1:
            problems.append(Problem("error", "quest.duplicate_id", f"ID duplicado: {q.quest_id}", q.source_file, q.quest_id))

        if not q.title or q.title in (q.quest_id, "Unnamed"):
            problems.append(Problem("warning", "quest.missing_title", "Quest sem título pt_br/en_us.", q.source_file, q.quest_id))
        if q.title_key and q.title_key not in book.lang_pt:
            problems.append(Problem("warning", "lang.pt_missing", f"Tradução pt_br ausente: {q.title_key}", q.source_file, q.quest_id))
        if q.title_key and q.title_key not in book.lang_en:
            problems.append(Problem("info", "lang.en_missing", f"Tradução en_us ausente: {q.title_key}", q.source_file, q.quest_id))

        for dep in q.dependencies:
            if dep not in counts:
                problems.append(Problem("error", "dependency.missing", f"Dependência não encontrada: {dep}", q.source_file, q.quest_id))
            elif dep == q.quest_id:
                problems.append(Problem("error", "dependency.self", "Quest depende dela mesma.", q.source_file, q.quest_id))

        for task in q.tasks:
            if task.task_type == "item" and task.item_id and task.item_id not in mods.items:
                problems.append(Problem("warning", "item.not_indexed", f"Item não encontrado no índice de mods: {task.item_id}", q.source_file, q.quest_id))
            if task.task_type == "item" and not task.item_id:
                problems.append(Problem("error", "item.missing", "Task do tipo item sem item configurado.", q.source_file, q.quest_id))

    # Cycle detection across the dependency graph.
    graph = {q.quest_id: [d for d in q.dependencies if d in counts] for q in all_quests if q.quest_id}
    state: dict[str, int] = defaultdict(int)
    stack: list[str] = []
    reported: set[tuple[str, ...]] = set()

    def dfs(node: str):
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if state[nxt] == 0:
                dfs(nxt)
            elif state[nxt] == 1:
                try:
                    idx = stack.index(nxt)
                    cycle = tuple(stack[idx:] + [nxt])
                except ValueError:
                    cycle = (node, nxt)
                key = tuple(sorted(set(cycle)))
                if key not in reported:
                    reported.add(key)
                    q = book.quest_by_id.get(node)
                    problems.append(Problem("error", "dependency.cycle", "Dependência circular: " + " → ".join(cycle), q.source_file if q else None, node))
        stack.pop()
        state[node] = 2

    for node in graph:
        if state[node] == 0:
            dfs(node)

    for err in mods.errors:
        problems.append(Problem("warning", "mod.scan", f"Falha ao ler mod: {err}"))
    return problems
