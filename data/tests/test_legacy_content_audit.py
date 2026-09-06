import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]; SCRIPT=ROOT/"scripts"/"audit_legacy_content.py"

class LegacyContentAuditTests(unittest.TestCase):
    def test_outputs_internal_candidates_and_resolves_assets(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); one=base/"one"; two=base/"two"; out=base/"out"
            one.mkdir(); two.mkdir(); (one/"asset.png").write_bytes(b"image")
            (one/"index.html").write_text('<title>首页</title><h1>国家级项目</h1><p>介绍</p><img src="asset.png">',encoding="utf-8")
            (two/"shop.html").write_text('<title>商城</title><h1>商城</h1><img src="missing.jpg">',encoding="utf-8")
            subprocess.run([sys.executable,str(SCRIPT),"--tianma",str(one),"--zhixiu",str(two),"--output",str(out)],check=True,capture_output=True)
            report=json.loads((out/"content_audit_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["pages"],2); self.assertEqual(report["asset_resolution"],{"present":1,"missing":1})
            with (out/"text_candidates.csv").open(encoding="utf-8-sig") as handle: texts=list(csv.DictReader(handle))
            with (out/"asset_references.csv").open(encoding="utf-8-sig") as handle: refs=list(csv.DictReader(handle))
            self.assertTrue(all(row["visibility"]=="internal_only" and row["review_status"]=="draft" for row in texts))
            self.assertTrue(all(row["rights_status"]=="unverified" for row in refs))
            self.assertIn("claim_review_required",{row["risk"] for row in texts})

if __name__=="__main__": unittest.main()
