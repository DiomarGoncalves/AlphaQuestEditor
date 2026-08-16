from __future__ import annotations

"""High-level FTB Quests port routing.

This module composes the conservative converters already used by Alpha Quest
Editor into version-aware routes.  The public UI should call this module rather
than forcing users to know which storage/text migration must happen first.
"""

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable
import shutil

from .format_conversion import (
    ConversionReport,
    convert_json5_to_snbt,
    convert_snbt_to_json5,
    detect_quest_format,
    resolve_quest_root,
)
from .legacy_port import (
    LegacyPortAnalysis,
    LegacyPortReport,
    analyze_legacy_snbt_port,
    port_120_to_121,
    port_121_to_120,
)

GEN_120 = "1.20"
GEN_121 = "1.21"
GEN_2612 = "26.1.2"
GEN_MIXED = "mixed"
GEN_UNKNOWN = "unknown"

SUPPORTED_TARGETS = (GEN_120, GEN_121, GEN_2612)


@dataclass
class PortRouteAnalysis:
    source: Path
    generation: str
    storage_format: str
    legacy: LegacyPortAnalysis | None = None
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        labels = {
            GEN_120: "FTB Quests 1.20.x — SNBT com textos inline",
            GEN_121: "FTB Quests 1.21.x — SNBT + lang externo",
            GEN_2612: "FTB Quests 26.1.2+ — JSON5 + lang dividido",
            GEN_MIXED: "Projeto SNBT parcialmente migrado/misto",
            GEN_UNKNOWN: "Geração não identificada",
        }
        lines = [labels.get(self.generation, self.generation), f"Storage: {self.storage_format}"]
        if self.legacy:
            lines.extend([
                f"Quests: {self.legacy.quests}",
                f"Tasks: {self.legacy.tasks}",
                f"Rewards: {self.legacy.rewards}",
                f"Textos inline: {self.legacy.inline_strings}",
                f"Textos em lang: {self.legacy.external_strings}",
            ])
            if self.legacy.conflicts:
                lines.append(f"Conflitos inline/lang: {self.legacy.conflicts}")
        if self.warnings:
            lines.append("")
            lines.append("Avisos:")
            lines.extend(f"- {w}" for w in self.warnings)
        return "\n".join(lines)


@dataclass
class PortPipelineReport:
    route: str
    source: Path
    destination: Path
    stages: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    intermediate: Path | None = None

    def add_stage(self, name: str, report: ConversionReport | LegacyPortReport) -> None:
        self.stages.append((name, report.summary()))
        for warning in getattr(report, "warnings", []) or []:
            if warning not in self.warnings:
                self.warnings.append(warning)

    def summary(self) -> str:
        lines = [f"Rota: {self.route}", f"Origem: {self.source}", f"Destino: {self.destination}"]
        if self.intermediate:
            lines.append(f"Intermediário 1.21 preservado: {self.intermediate}")
        for index, (name, text) in enumerate(self.stages, 1):
            lines.extend(["", f"Etapa {index}: {name}", text])
        if self.warnings:
            lines.append("")
            lines.append("Avisos consolidados:")
            lines.extend(f"- {w}" for w in self.warnings)
        return "\n".join(lines)


def detect_ftb_generation(source: Path | str, *, locale: str = "en_us") -> PortRouteAnalysis:
    root = resolve_quest_root(source)
    fmt = detect_quest_format(root)
    if fmt == "json5":
        return PortRouteAnalysis(root, GEN_2612, fmt)
    if fmt not in ("snbt", "mixed"):
        return PortRouteAnalysis(root, GEN_UNKNOWN, fmt, warnings=["A origem não parece um Quest Book FTB reconhecido."])

    try:
        legacy = analyze_legacy_snbt_port(root, locale=locale)
    except Exception as exc:
        return PortRouteAnalysis(root, GEN_UNKNOWN, fmt, warnings=[str(exc)])

    if legacy.direction == "120-to-121":
        generation = GEN_120
    elif legacy.direction == "121-to-120":
        generation = GEN_121
    elif legacy.direction == "mixed":
        generation = GEN_MIXED
    else:
        generation = GEN_UNKNOWN
    warnings = list(legacy.warnings)
    return PortRouteAnalysis(root, generation, fmt, legacy=legacy, warnings=warnings)


def available_routes(source_generation: str) -> list[tuple[str, str]]:
    """Return (route-id, label) pairs exposed by the UI."""
    if source_generation == GEN_120:
        return [
            ("120-121", "1.20 → 1.21"),
            ("120-2612-direct", "1.20 → 26.1.2 (direto)"),
            ("120-121-2612", "1.20 → 1.21 → 26.1.2 (manter intermediário)"),
        ]
    if source_generation == GEN_121:
        return [
            ("121-120", "1.21 → 1.20"),
            ("121-2612", "1.21 → 26.1.2"),
        ]
    if source_generation == GEN_2612:
        return [("2612-121", "26.1.2 → 1.21")]
    if source_generation == GEN_MIXED:
        return [
            ("120-121", "Tratar como 1.20 → 1.21"),
            ("121-120", "Tratar como 1.21 → 1.20"),
            ("121-2612", "Tratar como 1.21 → 26.1.2"),
        ]
    return []


def _clear_destination(dst: Path, overwrite: bool) -> None:
    if dst.exists() and any(dst.iterdir()):
        if not overwrite:
            raise FileExistsError(f"A pasta de destino não está vazia: {dst}")
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)


def _sibling_intermediate(dst: Path) -> Path:
    base = dst.parent / f"{dst.name}_intermediate_1.21"
    candidate = base
    i = 2
    while candidate.exists():
        candidate = dst.parent / f"{base.name}_{i}"
        i += 1
    return candidate


def port_route(
    source: Path | str,
    destination: Path | str,
    *,
    route: str,
    locale: str = "en_us",
    overwrite: bool = False,
    remove_lang_on_120_backport: bool = True,
) -> PortPipelineReport:
    src = resolve_quest_root(source)
    dst = Path(destination)
    if not src.exists():
        raise FileNotFoundError(src)
    if src.resolve() == dst.resolve():
        raise ValueError("Origem e destino precisam ser diferentes.")
    locale = (locale or "en_us").strip() or "en_us"
    _clear_destination(dst, overwrite)

    labels = dict(sum((available_routes(g) for g in (GEN_120, GEN_121, GEN_2612, GEN_MIXED)), []))
    report = PortPipelineReport(labels.get(route, route), src, dst)

    if route == "120-121":
        stage = port_120_to_121(src, dst, locale=locale, overwrite=True)
        report.add_stage("Migrar textos 1.20 → 1.21", stage)
        return report

    if route == "121-120":
        stage = port_121_to_120(
            src, dst, locale=locale, overwrite=True,
            remove_lang=remove_lang_on_120_backport,
        )
        report.add_stage("Embutir lang 1.21 → 1.20", stage)
        return report

    if route == "121-2612":
        stage = convert_snbt_to_json5(src, dst, overwrite=True)
        report.add_stage("Converter SNBT 1.21 → JSON5 26.1.2", stage)
        return report

    if route == "2612-121":
        stage = convert_json5_to_snbt(src, dst, overwrite=True, split_lang=False)
        report.add_stage("Converter JSON5 26.1.2 → SNBT 1.21", stage)
        return report

    if route in ("120-2612-direct", "120-121-2612"):
        if route == "120-121-2612":
            stage_root = _sibling_intermediate(dst)
            stage1 = port_120_to_121(src, stage_root, locale=locale, overwrite=False)
            report.intermediate = stage_root
            report.add_stage("1.20 → 1.21 (intermediário preservado)", stage1)
            stage2 = convert_snbt_to_json5(stage_root, dst, overwrite=True)
            report.add_stage("1.21 → 26.1.2", stage2)
            return report

        # Direct user experience, conservative internal pipeline.  The temporary
        # 1.21 tree is removed automatically after the JSON5 result is written.
        with TemporaryDirectory(prefix="alphaquest-port-121-") as tmp:
            stage_root = Path(tmp) / "quests_1.21"
            stage1 = port_120_to_121(src, stage_root, locale=locale, overwrite=False)
            report.add_stage("1.20 → 1.21 (etapa temporária)", stage1)
            stage2 = convert_snbt_to_json5(stage_root, dst, overwrite=True)
            report.add_stage("1.21 → 26.1.2", stage2)
        report.warnings.append("A etapa 1.21 foi usada internamente e removida ao final. Use a rota em etapas se quiser preservar essa cópia.")
        return report

    raise ValueError(f"Rota de port não suportada: {route}")
