import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from migration import Engine
from ai_agent import latest_version, discover, source_path, apply_action, run_job, load_skills, Model

class AgentTests(unittest.TestCase):
    def test_latest_uses_stable_alias_not_highest_unreleased_branch(self):
        self.assertEqual(latest_version('Tags: 21.0-rc\nTags: 20.0, 20, latest\n'),20)
        with self.assertRaises(ValueError):latest_version('Tags: 21.0-rc, saas-21.1')

    def test_source_paths_never_read_credentials_or_escape_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            e=Engine(root)
            for path in ('../state.json','/etc/passwd','.git/config','scripts/../../state.json','config.json'):
                with self.assertRaises(ValueError):source_path(e,path)

    def test_patch_only_existing_migration_script_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as root:
            e=Engine(root)
            folder=Path(root)/'build/13/OpenUpgrade/addons/base/migrations/13.0.1.0'
            folder.mkdir(parents=True)
            script=folder/'post-migration.py'
            script.write_text('def migrate(cr, version):\n    pass\n')
            action={'action':'patch_script','reason':'Correction test','arguments':{'path':str(script.relative_to(Path(root)/'build/13/OpenUpgrade')),'content':'def migrate(cr, version):\n    return None\n'}}
            result=apply_action(e,action)
            self.assertEqual(result['syntax'],'passed')
            self.assertEqual(len(list((Path(root)/'ai-patches').rglob('before.py'))),1)
            e.state['pending']={'version':13}
            with self.assertRaisesRegex(ValueError,'validation'):apply_action(e,action)

    def test_model_cannot_patch_validation_or_coverage(self):
        with tempfile.TemporaryDirectory() as root:
            e=Engine(root)
            for path in ('docsource/modules120-130.rst','odoo/service/server.py','__manifest__.py'):
                with self.assertRaises(ValueError):apply_action(e,{'action':'patch_script','arguments':{'path':path,'content':'pass'}})

    def test_success_is_decided_by_engine_not_model(self):
        with tempfile.TemporaryDirectory() as root:
            e=Engine(root)
            e.state.update(source={},policy={'target_version':20})
            model=Mock()
            with patch.object(e,'autopilot'),patch('ai_agent.export_result',return_value={'version':20,'file':'result.zip'}):
                result=run_job(e,model,'skills',3)
            self.assertEqual(result['status'],'completed')
            model.decide.assert_not_called()

    def test_repeated_ai_retry_stops_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as root:
            e=Engine(root)
            e.state.update(source={},policy={'target_version':20})
            model=Mock()
            model.decide.return_value={'action':'retry','arguments':{},'reason':'transient'}
            with patch.object(e,'autopilot',side_effect=ValueError('same error')):
                result=run_job(e,model,'skills',8)
            self.assertEqual(result['status'],'blocked')
            self.assertEqual(model.decide.call_count,3)

    def test_multiple_odoo_databases_are_selected_without_guessing(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{},clear=True):
            e=Engine(root)
            infos={'odoo12':{'Id':'source-id','State':{'Running':True},'Config':{'Env':['HOST=db','PASSWORD=never-return-this']},'NetworkSettings':{'Networks':{'private':{'Aliases':['odoo12']}}}},
                   'pg':{'NetworkSettings':{'Networks':{'private':{'Aliases':['db'],'IPAddress':'172.1.1.2'}}}}}
            def command(args,**kw):
                return json.dumps({'db_host':'','db_name':'','dbfilter':'.*'}) if args[1]=='exec' else 'odoo12\npg'
            def sql(c,d,q):
                if d=='postgres':return 'one\ntwo\nother'
                if 'to_regclass' in q:return 'f' if d=='other' else 't'
                return '12.0.1.0'
            with patch.object(e,'inspect',side_effect=lambda n:infos[n]),patch.object(e,'run',side_effect=command),patch.object(e,'sql',side_effect=sql):
                result=discover(e,'odoo12')
            self.assertEqual(result['databases'],['one','two'])
            self.assertNotIn('never-return-this',json.dumps(result))

    def test_model_json_action_allowlist(self):
        response=Mock()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        response.read.return_value=json.dumps({'message':{'content':'{"action":"shell","arguments":{}}'}}).encode()
        with patch('urllib.request.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'autorisée'):Model().decide('skills',{},[])

    def test_third_party_reference_tampering_is_rejected(self):
        import shutil
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/'skills'
            shutil.copytree(Path(__file__).parent/'skills',target)
            path=target/'references/txampa-odoo-integration/SKILL.md'
            path.write_text(path.read_text()+'\nModified')
            with self.assertRaisesRegex(ValueError,'SHA-256'):load_skills(target)

    def test_third_party_reference_cannot_read_outside_skills(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/'00-main.md').write_text('main')
            (root/'reference-index.json').write_text(json.dumps({'references':[{'path':'../../secret.md'}]}))
            with self.assertRaisesRegex(ValueError,'périmètre'):load_skills(root)

    def test_skills_loaded_and_hashed(self):
        text,hashes=load_skills(Path(__file__).parent/'skills')
        self.assertEqual(len(hashes),8)
        self.assertIn('references/txampa-odoo-integration/SKILL.md',hashes)
        self.assertIn('class OdooClient',text)
        self.assertIn('REFERENCE_TECHNIQUE_NON_PRESCRIPTIVE',text)
        self.assertIn('patch_script',text)

if __name__=='__main__':unittest.main()
