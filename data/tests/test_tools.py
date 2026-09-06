import base64, csv, hashlib, json, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path

ROOT=Path(__file__).parents[1]; SCRIPTS=ROOT/"scripts"
sys.path.insert(0,str(SCRIPTS))
from asset_inventory import normalized_zip_name

class ToolTests(unittest.TestCase):
    def test_repairs_utf8_zip_name_without_language_flag(self):
        broken="藏羌绣".encode("utf-8").decode("cp437")
        self.assertEqual(normalized_zip_name(broken),"藏羌绣")
    def test_inventory_filters_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); archive=td/"a.zip"; out=td/"out"
            with zipfile.ZipFile(archive,"w") as z:
                z.writestr("藏羌绣/a.png",b"same"); z.writestr("藏羌绣/b.png",b"same")
                z.writestr("__MACOSX/._a.png",b"noise"); z.writestr("藏羌绣/.DS_Store",b"noise")
            subprocess.run([sys.executable,str(SCRIPTS/"asset_inventory.py"),str(archive),"--output",str(out)],check=True,capture_output=True)
            s=json.loads((out/"summary.json").read_text(encoding="utf-8"))
            self.assertEqual((s["business_files"],s["unique_sha256"],s["exact_duplicate_groups"]),(2,1,1))

    def test_legacy_extract_and_clean(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); out=td/"legacy"; clean=td/"clean"
            html=td/"library.html"; js=td/"manifest.js"
            html.write_text('<article class="pattern-record" data-tags="animal"><div class="source-crop" data-x="1" data-y="2" data-w="3" data-h="4"></div><h3>1. 天马</h3><p>说明</p></article>',encoding="utf-8")
            js.write_text('window.X=[{name:"纹样.png",url:"assets/generated/纹样.png",type:"动物",meaning:"吉祥",color:"红",craft:"平针"},{name:"别名.png",url:"assets/generated/纹样.png",type:"动物"}];',encoding="utf-8")
            subprocess.run([sys.executable,str(SCRIPTS/"extract_legacy.py"),"--tianma",str(html),"--zhixiu",str(js),"--output",str(out)],check=True,capture_output=True)
            report=json.loads((out/"legacy_report.json").read_text(encoding="utf-8")); self.assertEqual(report["total_candidates"],3)
            subprocess.run([sys.executable,str(SCRIPTS/"clean_candidates.py"),str(out/"legacy_candidates.csv"),"--output",str(clean)],check=True,capture_output=True)
            with (clean/"normalized_candidates.csv").open(encoding="utf-8-sig") as f: rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]["candidate_name"],"天马"); self.assertEqual(rows[1]["origin_claim"],"generated")
            self.assertIn("shared_asset_reference",rows[1]["review_issues"])

    def test_mvd_is_unique_balanced_and_locked_down(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); inventory=td/"assets.csv"; duplicates=td/"duplicates.json"; out=td/"mvd"
            fields=["source_path","byte_size","sha256","mime_type","width","height"]
            rows=[
              {"source_path":"藏羌绣/纹样分类/植物纹样/a.png","byte_size":"10","sha256":"a"*64,"mime_type":"image/png","width":"10","height":"10"},
              {"source_path":"藏羌绣/纹样分类/植物纹样/a-copy.png","byte_size":"10","sha256":"a"*64,"mime_type":"image/png","width":"10","height":"10"},
              {"source_path":"藏羌绣/纹样分类/动物纹样/b.jpg","byte_size":"20","sha256":"b"*64,"mime_type":"image/jpeg","width":"20","height":"20"},
              {"source_path":"藏羌绣/纹样分类/几何纹/c.pdf","byte_size":"30","sha256":"c"*64,"mime_type":"application/pdf","width":"","height":""},
            ]
            with inventory.open("w",encoding="utf-8-sig",newline="") as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
            duplicates.write_text(json.dumps([{"sha256":"a"*64,"count":2,"paths":[]}]),encoding="utf-8")
            subprocess.run([sys.executable,str(SCRIPTS/"select_mvd_candidates.py"),str(inventory),"--duplicates",str(duplicates),"--output",str(out)],check=True,capture_output=True)
            seed=json.loads((out/"catalog_seed.json").read_text(encoding="utf-8"))["records"]
            self.assertEqual(len(seed),2); self.assertEqual(len({x["sha256"] for x in seed}),2)
            self.assertTrue(all(x["status"]=="draft" and x["visibility"]=="internal_only" for x in seed))
            self.assertTrue(all(not x["allow_display"] and not x["allow_ai_training"] for x in seed))
            self.assertEqual({x["legacy_category"] for x in seed},{"植物纹样","动物纹样"})

    def test_materialize_verifies_hash_and_blocks_traversal(self):
        png=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFElEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg==")
        digest=hashlib.sha256(png).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); archive=td/"a.zip"; seed=td/"seed.csv"; out=td/"out"
            with zipfile.ZipFile(archive,"w") as z: z.writestr("藏羌绣/纹样分类/几何纹/a.png",png)
            fields=["pattern_id","asset_id","candidate_name","original_path","sha256","status","visibility"]
            row={"pattern_id":"p","asset_id":"a","candidate_name":"候选","original_path":"藏羌绣/纹样分类/几何纹/a.png","sha256":digest,"status":"draft","visibility":"internal_only"}
            with seed.open("w",encoding="utf-8-sig",newline="") as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow(row)
            subprocess.run([sys.executable,str(SCRIPTS/"materialize_mvd_assets.py"),str(archive),str(seed),"--output",str(out)],check=True,capture_output=True)
            manifest=json.loads((out/"asset_manifest.json").read_text(encoding="utf-8"))["records"][0]
            self.assertEqual(manifest["original_sha256"],digest); self.assertEqual(manifest["visibility"],"internal_only")
            self.assertTrue((out/manifest["thumbnail_relative_path"]).is_file())
            row["original_path"]="../escape.png"
            with seed.open("w",encoding="utf-8-sig",newline="") as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow(row)
            failed=subprocess.run([sys.executable,str(SCRIPTS/"materialize_mvd_assets.py"),str(archive),str(seed),"--output",str(td/"unsafe")],capture_output=True)
            self.assertEqual(failed.returncode,2)
            error=json.loads((td/"unsafe"/"asset_manifest.json").read_text(encoding="utf-8"))["records"][0]["processing_error"]
            self.assertIn("unsafe_original_path",error); self.assertFalse((td/"escape.png").exists())

if __name__=="__main__": unittest.main()
