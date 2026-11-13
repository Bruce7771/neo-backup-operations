import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('audit_diag',Path(__file__).with_name('retention-audit.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Diagnostics(unittest.TestCase):
    def test_fixed_enum_and_caller_frame_exclude_private_path(self):
        value=m.nested_planner_failure('Traceback:\n  File "/private/synthetic/retention-plan.py", line 155, in build\n'
            '  File "/private/synthetic/retention-plan.py", line 36, in require\n'
            'ValueError: Every retained configuration delta needs its exact full-parent dependency\n')
        self.assertEqual(value,{'nested_failure_code':'CONFIG_DEPENDENCY_COVERAGE_MISMATCH',
                               'nested_source_module':'retention-plan.py','nested_source_line':155})
        self.assertNotIn('private',str(value))
    def test_unreviewed_text_is_not_forwarded(self):
        self.assertEqual(m.nested_planner_failure('ValueError: synthetic-private-value\n'),
                         {'nested_failure_code':'NESTED_PLANNER_FAILURE_UNCLASSIFIED'})

if __name__=='__main__':unittest.main()
