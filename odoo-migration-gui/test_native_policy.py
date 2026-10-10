import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from migration import Engine
from native_policy import cleanup_plan, check_coverage, security_checks, parse_coverage

class NativeTests(unittest.TestCase):
    def test_coverage_never_promotes_blank_or_partial_status(self):
        rows=parse_coverage('| base |Done | |\n| web |Nothing to do | |\n| account | |No DB changes |\n| mail |Partial | |\n| |del| old |Done |Merged into new |', 'official')
        self.assertEqual(set(rows), {'base','web','old'})

    def test_unknown_module_removed_but_native_preserved(self):
        self.assertEqual(cleanup_plan([{'name':'base','state':'installed'}, {'name':'third','state':'installed'}], {'base':{'depends':[]}}), ['third'])

    def test_native_dependency_blocks_uninstall(self):
        with self.assertRaisesRegex(ValueError, 'natifs'):
            cleanup_plan([{'name':'base','state':'installed'}, {'name':'third','state':'installed'}], {'base':{'depends':['third']}})

    def test_coverage_is_commit_bound_and_complete(self):
        with tempfile.TemporaryDirectory() as root:
            engine=Engine(root)
            engine.state['modules']=[{'name':'base','state':'installed'}]
            prepared={'target':20,'folder':root,'commits':{'OpenUpgrade':'a'*40}}
            with self.assertRaisesRegex(ValueError,'tableau'):
                check_coverage(engine,prepared)
            (Path(root)/'coverage').mkdir()
            path=Path(root)/'coverage/20.json'
            path.write_text(json.dumps({'commit':'b'*40,'modules':{}}))
            with self.assertRaisesRegex(ValueError,'commit'):
                check_coverage(engine,prepared)
            path.write_text(json.dumps({'commit':'a'*40,'modules':{}}))
            with self.assertRaisesRegex(ValueError,'base'):
                check_coverage(engine,prepared)
            path.write_text(json.dumps({'commit':'a'*40,'modules':{'base':{'status':'done','evidence':'reviewed official source'}}}))
            check_coverage(engine,prepared)

    def test_public_port_and_host_mount_block_validation(self):
        with tempfile.TemporaryDirectory() as root:
            engine=Engine(root)
            work={'db':'db','prefix':'omig-test','network':'internal'}
            info={'HostConfig':{'PortBindings':{'5432/tcp':[{'HostIp':'0.0.0.0'}]}}, 'NetworkSettings':{'Networks':{'internal':{}}}, 'Mounts':[]}
            with patch.object(engine,'run',return_value='[{"Internal":true}]'), patch.object(engine,'inspect',return_value=info):
                with self.assertRaisesRegex(ValueError,'Port'):
                    security_checks(engine,work)
                info['HostConfig']['PortBindings']={}
                info['Mounts']=[{'Type':'bind'}]
                with self.assertRaisesRegex(ValueError,'Montage'):
                    security_checks(engine,work)

if __name__=='__main__':
    unittest.main()
