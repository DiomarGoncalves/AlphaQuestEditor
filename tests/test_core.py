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
   tasks: [{id:"300" type:"item" item:{count:1 id:"demo:gear"} consume_items:true}]
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
        assert ch.title=="Teste" and q.title=="Engrenagem principal" and q.description=="Primeira linha\n\nTerceira linha"; assert q.shape=="circle" and q.optional; assert q.primary_item_id=="demo:gear"; assert q.tasks[0].count==1 and "consume_items" in q.tasks[0].raw; assert q.rewards[0].amount==100
        assert book.save_position(q,4.25,3.5); book.load(); q=book.quest_by_id["200"]; assert (q.x,q.y)==(4.25,3.5)
        # Batch persistence used by the 0.5 visual multi-selection editor.
        assert book.save_positions([(q,5.0,4.0)]); book.load(); q=book.quest_by_id["200"]; assert (q.x,q.y)==(5.0,4.0)
        assert book.save_properties(q,{"shape":"circle","size":1.4,"optional":False,"invisible":True,"hide_dependent_lines":True,"hide_until_deps_complete":"true","hide_until_deps_visible":"default","hide_dependency_lines":"false","require_sequential_tasks":"true","can_repeat":"false","min_required_dependencies":1})
        book.load(); q=book.quest_by_id["200"]; assert abs(q.size-1.4)<.001 and q.invisible and not q.optional and q.min_required_dependencies==1
        new_id=book.create_quest(ch,"Nova Item Quest",1.0,2.0,"demo:gear","item",8); assert new_id; book.load(); nq=book.quest_by_id[new_id]; assert nq.title=="Nova Item Quest" and nq.primary_item_id=="demo:gear" and nq.tasks[0].count==8
        assert book.set_dependencies(nq,["200"]); book.load(); nq=book.quest_by_id[new_id]; assert nq.dependencies==["200"]
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

if __name__=="__main__": test_fixture(); print("OK")
