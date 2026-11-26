from pathlib import Path
import tempfile
import unittest

from demo import demo, save
from review import kappa, read_json, report
from triage import evaluate, examples, priority


class TestReview(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name)/"demo"
        self.page = demo(self.out)

    def test_paired_and_blind(self):
        summary = read_json(self.out/"simulated-report.json")
        self.assertEqual(summary["agreement"]["cue"]["matching"],3)
        self.assertAlmostEqual(summary["agreement"]["cue"]["kappa"],0.5)
        self.assertIsNone(summary["agreement"]["material"]["kappa"])
        self.assertIsNone(kappa([("pass","pass")]*4))
        self.assertEqual([row["wins"] for row in summary["paired_vs_base"]],[1,0,1])
        self.assertEqual(summary["paired_vs_base"][1]["unresolved_or_missing"],1)
        self.assertEqual(sorted(item["route"] for item in summary["investigation_queue"]),["reject","review"])
        html = self.page.read_text(encoding="utf-8")
        self.assertNotIn('"arm":',html)
        self.assertNotIn("base.gif",html)
        self.assertEqual(len(list((self.page.parent/"clips").glob("*.gif"))),4)

    def test_reject_duplicate_reviewer_and_incomplete_batch(self):
        key,a,b = [self.out/x for x in ["key.json","simulated-A.json","simulated-B.json"]]
        with self.assertRaises(ValueError):
            report(key,a,a)
        votes=read_json(b)
        votes["votes"].pop(next(iter(votes["votes"])))
        save(b,votes)
        with self.assertRaises(ValueError):
            report(key,a,b)

    def test_group_holdout_and_duplicate_protection(self):
        group={f"scene-{i}":False for i in range(10)}
        group["scene-9"]=True
        row=evaluate({("style","preview"):group})[0]
        self.assertEqual(row["held_out_routine_with_issue"],1)
        self.assertEqual(priority([False])["priority"],"standard review")
        key, rep=self.out/"key.json",self.out/"simulated-report.json"
        with self.assertRaises(ValueError):
            examples([(key,rep),(key,rep)])

    def test_existing_directory_is_preserved(self):
        with self.assertRaises(ValueError):
            demo(self.out)
        self.assertTrue(self.page.is_file())

