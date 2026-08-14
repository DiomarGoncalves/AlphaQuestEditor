from __future__ import annotations

import json, tempfile, zipfile, sys
from pathlib import Path

# Permite executar este arquivo diretamente (python tests/test_core.py)
# sem exigir instalacao do pacote alphaquest no ambiente.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alphaquest.core.lang import parse_lang_snbt
from alphaquest.core.mod_index import ModIndex
from alphaquest.core.questbook import QuestBook
from alphaquest.core.validator import validate
from alphaquest.core.translation_report import export_translation_report, import_translation_report, collect_translation_rows
from alphaquest.core.history import QuestHistory


def build_fixture(root: Path):
    (root/"mods").mkdir(parents=True); (root/"config/ftbquests/quests/chapters").mkdir(parents=True); (root/"config/ftbquests/quests/lang").mkdir(parents=True); (root/".alphaquest/cache").mkdir(parents=True)
    (root/".alphaquest/cache/vanilla_items_1.21.1.json").write_text(json.dumps([{"name":"stone","displayName":"Stone"},{"name":"apple","displayName":"Apple"}]),encoding="utf-8")
    with zipfile.ZipFile(root/"mods/demo.jar","w") as z:
        z.writestr("assets/demo/models/item/gear.json",json.dumps({"parent":"item/generated","textures":{"layer0":"demo:item/gear"}})); z.writestr("assets/demo/textures/item/gear.png",b"png")
        z.writestr("assets/demo/lang/pt_br.json",json.dumps({"item.demo.gear":"Engrenagem","item.demo.dynamic_widget":"Componente Dinâmico"})); z.writestr("assets/ftbquests/textures/shapes/circle/shape.png",b"shape")
    (root/"config/ftbquests/quests/chapter_groups.snbt").write_text('''{chapter_groups:[{id:"900"}]}''',encoding="utf-8")
    (root/"config/ftbquests/quests/lang/pt_br.snbt").write_text('''{
quest.200.title:"Engrenagem principal"
quest.200.quest_desc:["Primeira linha" "" "Terceira linha"]
chapter.100.title:"Teste"
chapter_group.900.title:"PROGRESSÃO"
}
''',encoding="utf-8")
    (root/"config/ftbquests/quests/lang/en_us.snbt").write_text('''{quest.200.title:"Main Gear" chapter.100.title:"Test"}''',encoding="utf-8")
    (root/"config/ftbquests/quests/chapters/a.snbt").write_text('''{
 id: "100"
 filename: "a"
 group: "900"
 order_index: 3
 default_quest_shape: "circle"
 quests: [{
   id: "200"
   x: 2.5d
   y: -1.0d
   optional: true
   tasks: [{id:"300" type:"item" item:{count:1 id:"demo:gear"} consume_items:true} {id:"301" type:"checkmark" icon:{id:"demo:virtual_badge" components:{"minecraft:custom_model_data":123}}}]
   rewards: [{id:"400" type:"xp" xp:100}]
 }]
}
''',encoding="utf-8")


def test_fixture():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); build_fixture(root)
        mods=ModIndex(); mods.scan(root); assert "demo:gear" in mods.items; assert "demo:dynamic_widget" in mods.items; assert "circle" in mods.quest_shapes
        book=QuestBook(root); book.load(); ch=book.chapters[0]; q=ch.quests[0]
        assert book.chapter_groups[0].title=="PROGRESSÃO" and ch.group_id=="900" and ch.order_index==3
        assert "minecraft:stone" in mods.items and "minecraft:apple" in mods.items
        assert ch.title=="Teste" and q.title=="Engrenagem principal" and q.description=="Primeira linha\n\nTerceira linha"; assert q.shape=="circle" and q.optional; assert q.primary_item_id=="demo:gear"; assert q.display_icon_item_id=="demo:virtual_badge" and q.tasks[1].icon_item_id=="demo:virtual_badge" and q.has_custom_display_icon; assert q.tasks[0].count==1 and "consume_items" in q.tasks[0].raw; assert q.rewards[0].amount==100
        # 0.9.5: decorative/checkmark ItemStacks are exposed even when no mod item model exists.
        assert mods.register_questbook_icons(book)>=1; assert "demo:virtual_badge" in mods.items and "demo:virtual_badge" in mods.quest_display_items
        assert book.save_position(q,4.25,3.5); book.load(); q=book.quest_by_id["200"]; assert (q.x,q.y)==(4.25,3.5)
        # Batch persistence used by the 0.5 visual multi-selection editor.
        assert book.save_positions([(q,5.0,4.0)]); book.load(); q=book.quest_by_id["200"]; assert (q.x,q.y)==(5.0,4.0)
        assert book.save_properties(q,{"shape":"circle","size":1.4,"optional":False,"invisible":True,"hide_dependent_lines":True,"hide_until_deps_complete":"true","hide_until_deps_visible":"default","hide_dependency_lines":"false","require_sequential_tasks":"true","can_repeat":"false","min_required_dependencies":1})
        book.load(); q=book.quest_by_id["200"]; assert abs(q.size-1.4)<.001 and q.invisible and not q.optional and q.min_required_dependencies==1
        new_id=book.create_quest(ch,"Nova Item Quest",1.0,2.0,"demo:gear","item",8); assert new_id; book.load(); nq=book.quest_by_id[new_id]; assert nq.title=="Nova Item Quest" and nq.primary_item_id=="demo:gear" and nq.tasks[0].count==8
        assert book.set_dependencies(nq,["200"]); book.load(); nq=book.quest_by_id[new_id]; assert nq.dependencies==["200"]; assert new_id in book.quest_by_id["200"].dependents
        assert book.set_tasks(nq,[{"type":"item","item_id":"demo:gear","count":2,"consume_items":"true","only_from_crafting":"false","match_components":"fuzzy","task_screen_only":True,"optional_task":True,"disable_toast":True}]); book.load(); nq=book.quest_by_id[new_id]; raw=nq.tasks[0].raw; assert "consume_items: true" in raw and "task_screen_only: true" in raw and "optional_task: true" in raw
        gid=book.create_group("TECNOLOGIA"); assert gid; book.load(); assert gid in book.group_by_id
        cid=book.create_chapter("Mekanism", "mekanism_test", gid); assert cid; book.load(); nch=next(c for c in book.chapters if c.chapter_id==cid); assert nch.group_id==gid and nch.title=="Mekanism"
        assert book.edit_chapter(nch,"Mekanism Editado",cid,gid,"mekanism_editado"); book.load(); nch=next(c for c in book.chapters if c.chapter_id==cid); assert nch.title=="Mekanism Editado" and nch.source_file.name=="mekanism_editado.snbt"
        g=book.group_by_id[gid]; assert book.edit_group(g,"TEC EDIT",gid); book.load(); assert book.group_by_id[gid].title=="TEC EDIT"
        assert book.set_rewards(nq,[{"type":"xp","amount":75},{"type":"xp_levels","amount":3},{"type":"item","item_id":"demo:gear","count":2}]); book.load(); nq=book.quest_by_id[new_id]; assert [r.reward_type for r in nq.rewards]==["xp","xp_levels","item"]; assert nq.rewards[1].amount==3
        dup=book.duplicate_quest(nq); assert dup and dup!=new_id; book.load(); dq=book.quest_by_id[dup]; assert dq.title.endswith("(cópia)") and dq.x==nq.x+1.0 and dq.dependencies==["200"]; assert dq.tasks[0].task_id != nq.tasks[0].task_id; assert {r.reward_id for r in dq.rewards}.isdisjoint({r.reward_id for r in nq.rewards})
        # 0.7: batch dependency edit preserves per-quest content and is safe to add/remove.
        nq=book.quest_by_id[new_id]; dq=book.quest_by_id[dup]
        ok, changed=book.batch_update_dependencies([nq,dq],["200"],"remove"); assert ok and changed==2
        book.load(); assert book.quest_by_id[new_id].dependencies==[] and book.quest_by_id[dup].dependencies==[]
        ok, changed=book.batch_update_dependencies([book.quest_by_id[new_id],book.quest_by_id[dup]],["200"],"add"); assert ok and changed==2
        book.load(); assert book.quest_by_id[new_id].dependencies==["200"] and book.quest_by_id[dup].dependencies==["200"]
        # 0.9.2: explicit dependency mapper semantics: prerequisite(s) -> dependent(s).
        ok, changed=book.map_dependencies(["200"],[new_id,dup],"remove"); assert ok and changed==2
        book.load(); assert book.quest_by_id[new_id].dependencies==[] and book.quest_by_id[dup].dependencies==[]
        ok, changed=book.map_dependencies(["200"],[new_id,dup],"add"); assert ok and changed==2
        book.load(); assert book.quest_by_id[new_id].dependencies==["200"] and book.quest_by_id[dup].dependencies==["200"]
        probs=validate(book,mods); assert not [p for p in probs if p.severity=="error"]
        q=book.quest_by_id["200"]; assert book.delete_quest(q); book.load(); assert "200" not in book.quest_by_id
        pt=parse_lang_snbt(root/"config/ftbquests/quests/lang/pt_br.snbt"); assert pt[f"quest.{new_id}.title"]=="Nova Item Quest"

        # 0.6: persistent registry cache + lazy texture loading.
        assert mods.items["demo:gear"].texture_bytes is None
        assert mods.get_texture_bytes("demo:gear") == b"png"
        mods2=ModIndex(); mods2.scan(root); assert mods2.loaded_from_cache and "demo:gear" in mods2.items
        assert mods2.get_texture_bytes("demo:gear") == b"png"

        # Translation report round-trip keeps multiline descriptions and reports gaps.
        book.load(); report_rows=collect_translation_rows(book)
        desc=next(r for r in report_rows if r["key"]=="quest.200.quest_desc") if "200" in book.quest_by_id else None
        # quest 200 was deleted above; export still includes language-only keys.
        if desc is None:
            desc=next(r for r in report_rows if r["key"]=="quest.200.quest_desc")
        assert desc["pt_br"]=="Primeira linha\n\nTerceira linha" and desc["status"]=="FALTA_EN_US"
        csv_path=root/"translations.csv"; json_path=root/"translations.json"
        assert export_translation_report(book,csv_path)>0; assert export_translation_report(book,json_path)>0
        imported=import_translation_report(csv_path); rec=next(r for r in imported if r["key"]=="quest.200.quest_desc")
        assert rec["pt_br"]=="Primeira linha\n\nTerceira linha"
        assert len(import_translation_report(json_path))==len(report_rows)

        # Global Ctrl+Z history can restore creation/deletion/edit snapshots atomically.
        hist=QuestHistory(); qroot=book.quest_root; before=hist.snapshot(qroot)
        marker=qroot/"lang"/"undo_probe.snbt"; marker.write_text('{probe:"x"}',encoding="utf-8"); after=hist.snapshot(qroot)
        assert hist.push("Teste",before,after); assert marker.exists(); assert hist.undo(qroot)=="Teste" and not marker.exists(); assert hist.redo(qroot)=="Teste" and marker.exists()



def build_json5_fixture(root: Path):
    from alphaquest.core.json5_codec import save as save_json5
    qroot=root/"config/ftbquests/quests"
    (qroot/"chapters").mkdir(parents=True); (qroot/"lang/pt_br/chapters").mkdir(parents=True); (qroot/"lang/en_us/chapters").mkdir(parents=True)
    save_json5(qroot/"data.json5", {"version":13,"fallback_locale":"en_us","default_quest_shape":"circle"})
    save_json5(qroot/"chapter_groups.json5", {"chapter_groups":[{"id":"900"}]})
    save_json5(qroot/"chapters/a.json5", {
        "id":"100","group":"900","order_index":1,"filename":"a","default_quest_shape":"circle",
        "default_hide_dependency_lines":False,
        "quests":[{"id":"200","x":1.5,"y":-2.0,"tasks":[{"id":"300","type":"item","item":{"id":"minecraft:stone","count":1}}],"rewards":[{"id":"400","type":"xp","xp":25}]}],
        "quest_links":[],"images":[]
    })
    save_json5(qroot/"lang/pt_br/chapter.json5", {"chapter.100.title":"Capítulo JSON5"})
    save_json5(qroot/"lang/pt_br/chapter_group.json5", {"chapter_group.900.title":"GRUPO JSON5"})
    save_json5(qroot/"lang/pt_br/chapters/a.json5", {"quest.200.title":"Quest JSON5","quest.200.quest_desc":["Linha A","","Linha C"],"task.300.title":"Pegue Pedra"})
    save_json5(qroot/"lang/en_us/chapter.json5", {"chapter.100.title":"JSON5 Chapter"})
    save_json5(qroot/"lang/en_us/chapters/a.json5", {"quest.200.title":"JSON5 Quest"})
    return qroot


def test_json5_and_conversion():
    from alphaquest.core.json5_codec import load as load_json5
    from alphaquest.core.format_conversion import (
        convert_snbt_to_json5, convert_json5_to_snbt, split_snbt_languages,
        merge_snbt_languages, fill_missing_snbt_translations, purge_merged_snbt_languages,
        detect_quest_format,
    )
    from alphaquest.core.lang import load_locale_tree

    with tempfile.TemporaryDirectory() as td:
        root=Path(td); qroot=build_json5_fixture(root)
        book=QuestBook(root); book.load(); assert book.storage_format=="json5"
        q=book.quest_by_id["200"]; assert q.title=="Quest JSON5" and q.description=="Linha A\n\nLinha C" and q.tasks[0].title=="Pegue Pedra"
        assert book.save_position(q,7.5,8.25); book.load(); q=book.quest_by_id["200"]; assert (q.x,q.y)==(7.5,8.25)
        assert book.save_properties(q,{"size":1.0,"shape":"circle","optional":True,"invisible":False,"hide_dependent_lines":False,"hide_until_deps_complete":"default","hide_until_deps_visible":"default","hide_dependency_lines":"default","require_sequential_tasks":"default","can_repeat":"default","min_required_dependencies":0})
        data=load_json5(q.source_file); rawq=data["quests"][0]; assert rawq.get("optional") is True and "invisible" not in rawq and "hide_dependent_lines" not in rawq
        book.load(); q=book.quest_by_id["200"]
        assert book.set_tasks(q,[{"type":"checkmark","title":"Confirmar JSON5"}]); book.load(); q=book.quest_by_id["200"]; tid=q.tasks[0].task_id
        pt=load_locale_tree(qroot,"pt_br","json5"); assert pt[f"task.{tid}.title"]=="Confirmar JSON5"
        new_id=book.create_quest(book.chapters[0],"Nova JSON5",2,3,"minecraft:stone","item",2); assert new_id; book.load(); assert book.quest_by_id[new_id].title=="Nova JSON5"
        hist=QuestHistory(); before=hist.snapshot(qroot); probe=qroot/"lang/pt_br/probe.json5"; probe.write_text('{probe:"x",}\n',encoding="utf-8"); after=hist.snapshot(qroot); assert hist.push("json",before,after); assert hist.undo(qroot)=="json" and not probe.exists(); assert hist.redo(qroot)=="json" and probe.exists()

    # Storage conversion and legacy language splitter round trips.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); build_fixture(root); src=root/"config/ftbquests/quests"; out=root/"converted_json5"
        rep=convert_snbt_to_json5(src,out); assert rep.stats["chapters"]==1 and detect_quest_format(out)=="json5"
        data=load_json5(out/"data.json5"); assert data["version"]==13 and data["fallback_locale"]=="en_us" and "grid_scale" in data
        ch=load_json5(out/"chapters/a.json5"); assert ch["id"]=="100" and ch["filename"]=="a" and "default_hide_dependency_lines" in ch and "quest_links" in ch and "images" in ch
        converted=QuestBook(out); converted.load(); assert converted.quest_by_id["200"].title=="Engrenagem principal"
        back=root/"converted_snbt"; convert_json5_to_snbt(out,back,split_lang=True); assert detect_quest_format(back)=="snbt" and (back/"lang/pt_br/chapters/a.snbt").exists()
        # Split/merge compatibility on the original 1.21.1 tree.
        split_snbt_languages(src,keep_flat=True); assert (src/"lang/pt_br/chapters/a.snbt").exists(); merge_snbt_languages(src); merged=load_locale_tree(src,"pt_br","snbt"); assert merged["quest.200.title"]=="Engrenagem principal"
        # Translator helper mirrors Lang Splitter's common fill-missing workflow.
        fill_missing_snbt_translations(src,target_locale="pt_br",source_locale="en_us",keep_flat=True)
        filled=load_locale_tree(src,"pt_br","snbt"); assert filled["chapter.100.title"]=="Teste" and filled["quest.200.title"]=="Engrenagem principal"
        # Existing translations win; only a missing English-only key should be copied.
        en_path=src/"lang/en_us.snbt"; en_text=en_path.read_text(encoding="utf-8").rstrip()[:-1] + ' quest.999.title:"Fallback only"}'
        en_path.write_text(en_text,encoding="utf-8")
        fill_missing_snbt_translations(src,target_locale="pt_br",source_locale="en_us",keep_flat=True)
        filled=load_locale_tree(src,"pt_br","snbt"); assert filled["quest.999.title"]=="Fallback only" and filled["quest.200.title"]=="Engrenagem principal"
        merged_probe=src/"lang/pt_br/chapters/old.snbt_merged"; merged_probe.write_text('{x:"y"}',encoding="utf-8")
        cleanup=purge_merged_snbt_languages(src,locales=["pt_br"]); assert cleanup.stats["removidos"]==1 and not merged_probe.exists()



def test_translation_sync_and_qa():
    from alphaquest.core.translation_sync import analyze_translation_file, validate_locale_files
    from alphaquest.core.lang import load_locale_tree

    with tempfile.TemporaryDirectory() as td:
        root = Path(td); build_fixture(root); book = QuestBook(root); book.load()
        # Give QA a source string containing placeholders/numbers/line breaks.
        en = book.quest_root / "lang/en_us.snbt"
        en.write_text('''{
quest.200.title:"Main Gear %s 10"
quest.200.quest_desc:["Line 1" "Line 2"]
chapter.100.title:"Test"
}''', encoding="utf-8")
        book.load()

        updated = root / "pt_br.snbt"
        updated.write_text('''{
quest.200.title:"Engrenagem atualizada"
quest.200.quest_desc:["Linha 1" "Linha 2"]
quest.20.title:"ID digitado errado"
}''', encoding="utf-8")
        analysis = analyze_translation_file(book, updated, "pt_br", "en_us")
        assert analysis.source_format == "snbt" and len(analysis.rows) == 3
        title = next(r for r in analysis.rows if r.key == "quest.200.title")
        assert title.status == "ALTERADA"
        assert any(i.code == "PLACEHOLDER_MISMATCH" for i in title.issues)
        assert any(i.code == "NUMBER_MISMATCH" for i in title.issues)
        typo = next(r for r in analysis.rows if r.key == "quest.20.title")
        assert typo.status == "CHAVE_DESCONHECIDA"
        assert any("quest.200.title" in i.message for i in typo.issues)

        # Applying one imported key routes back through the QuestBook writer.
        book.save_translation_locale("pt_br", "quest.200.title", "Engrenagem revisada")
        reloaded = load_locale_tree(book.quest_root, "pt_br", book.storage_format)
        assert reloaded["quest.200.title"] == "Engrenagem revisada"

        # In a Lang Splitter layout the importer must route the same key to the
        # chapter-owned physical file instead of asking the user to place it.
        from alphaquest.core.format_conversion import split_snbt_languages
        split_snbt_languages(book.quest_root, keep_flat=True)
        book.load(); book.save_translation_locale("pt_br", "quest.200.title", "Revisada no split")
        split_file = book.quest_root / "lang/pt_br/chapters/a.snbt"
        assert parse_lang_snbt(split_file)["quest.200.title"] == "Revisada no split"

        # Broken syntax reports the exact line.
        broken = root / "broken_pt_br.snbt"
        broken.write_text('{\nquest.200.title "Sem dois pontos"\n}', encoding="utf-8")
        bad = analyze_translation_file(book, broken, "pt_br", "en_us")
        syntax = [i for i in bad.issues if i.code == "SYNTAX"]
        assert syntax and syntax[0].line == 2

        # A physical line break inside a quoted language string is also reported.
        broken_current = book.quest_root / "lang/pt_br.snbt"
        broken_current.write_text('{\nquest.200.title:"Linha quebrada\ncontinua aqui"\n}', encoding="utf-8")
        issues = validate_locale_files(book, "pt_br")
        assert any(i.code in ("RAW_NEWLINE_IN_STRING", "SYNTAX") and i.line >= 2 for i in issues)


def test_universal_assets_and_kubejs():
    import zipfile
    from alphaquest.core.mod_index import ModIndex

    with tempfile.TemporaryDirectory() as td:
        root=Path(td); mods=root/"random_jars"; mods.mkdir()
        jar=mods/"demo-any-version.jar"
        with zipfile.ZipFile(jar,"w") as z:
            z.writestr("assets/demo/lang/en_us.json", '{"item.demo.gear":"Demo Gear"}')
            z.writestr("assets/demo/models/item/gear.json", '{"parent":"item/generated","textures":{"layer0":"demo:item/gear"}}')
            z.writestr("assets/demo/textures/item/gear.png", b"png-gear")
            z.writestr("assets/demo/textures/gui/quest/banner.png", b"png-banner")
        kube=root/"my_kubejs"; (kube/"startup_scripts").mkdir(parents=True); (kube/"assets/kubejs/textures/item").mkdir(parents=True); (kube/"assets/kubejs/textures/gui/quests").mkdir(parents=True)
        (kube/"startup_scripts/items.js").write_text("""
StartupEvents.registry('item', event => {
  event.create('alpha_core').displayName('Alpha Core').texture('kubejs:item/alpha_core')
})
""",encoding="utf-8")
        (kube/"startup_scripts/legacy.js").write_text("""
onEvent('item.registry', event => { event.create('legacy_part').displayName('Legacy Part') })
""",encoding="utf-8")
        (kube/"assets/kubejs/textures/item/alpha_core.png").write_bytes(b"png-alpha")
        (kube/"assets/kubejs/textures/gui/quests/info.png").write_bytes(b"png-info")

        idx=ModIndex(); idx.scan_sources([mods],kube)
        assert "demo:gear" in idx.items and idx.items["demo:gear"].display_name=="Demo Gear"
        assert "kubejs:alpha_core" in idx.items and idx.items["kubejs:alpha_core"].display_name=="Alpha Core"
        assert "kubejs:legacy_part" in idx.items
        assert "demo:textures/gui/quest/banner" in idx.images
        assert "kubejs:textures/gui/quests/info" in idx.images
        assert idx.get_texture_bytes("demo:gear")==b"png-gear"
        assert idx.get_texture_bytes("kubejs:alpha_core")==b"png-alpha"
        assert idx.get_asset_bytes("kubejs:textures/gui/quests/info")==b"png-info"
        assert idx.minecraft_version=="auto"


if __name__=="__main__":
    test_fixture(); test_json5_and_conversion(); test_translation_sync_and_qa(); test_universal_assets_and_kubejs(); print("OK")
