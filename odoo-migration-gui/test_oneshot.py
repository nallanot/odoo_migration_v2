import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from migration import Engine
from oneshot import package_input, source_files, export_result, file_hash

class OneShotTests(unittest.TestCase):
    def test_preserves_sql_and_nested_filestore(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'input'
            (source/'filestore/ab').mkdir(parents=True)
            sql=b'CREATE TABLE example (id integer);\n'
            attachment=b'attachment-content'
            (source/'dump.sql').write_bytes(sql)
            (source/'filestore/ab/abcdef').write_bytes(attachment)
            target=Path(root)/'backup.zip'
            result=package_input(source,target)
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(archive.read('dump.sql'),sql)
                self.assertEqual(archive.read('filestore/ab/abcdef'),attachment)
            self.assertEqual(result['dump.sql'],file_hash(source/'dump.sql'))
            self.assertEqual((source/'dump.sql').read_bytes(),sql)

    def test_missing_filestore_and_symlinks_block(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/'dump.sql').write_text('SQL')
            with self.assertRaises(ValueError): source_files(root)
            (root/'filestore').mkdir()
            (root/'filestore/bad').symlink_to(root/'dump.sql')
            with self.assertRaisesRegex(ValueError,'symbolique'): source_files(root)

    def test_partial_version_cannot_be_exported_as_target(self):
        with tempfile.TemporaryDirectory() as root:
            engine=Engine(root)
            engine.state['policy']={'target_version':20}
            with patch.object(engine,'start_pg') as start:
                with self.assertRaisesRegex(ValueError,'cible'):
                    export_result(engine,Path(root)/'output')
                start.assert_not_called()

    def test_export_restores_and_packages_sql_and_filestore(self):
        with tempfile.TemporaryDirectory() as root:
            engine=Engine(root)
            checkpoint=Path(root)/'checkpoint/database.dump'
            checkpoint.parent.mkdir()
            checkpoint.write_bytes(b'PGDMP-test')
            (checkpoint.parent/'validation.json').write_text(json.dumps({'dump_sha256':file_hash(checkpoint)}))
            data=Path(root)/'data/filestore/migration/ab'
            data.mkdir(parents=True)
            (data/'123').write_bytes(b'file')
            engine.state.update(policy={'target_version':20},version=20,checkpoint=str(checkpoint),data=str(Path(root)/'data'),metrics={'contacts':'1'},modules=[{'name':'base','state':'installed','latest_version':'20.0'}])
            def run(args,**kwargs):
                if kwargs.get('out'): Path(kwargs['out']).write_bytes(b'SQL-export')
                return ''
            with patch.object(engine,'start_pg',return_value={'db':'test-db'}),patch.object(engine,'run',side_effect=run),patch.object(engine,'metrics',return_value={'contacts':'1'}):
                result=export_result(engine,Path(root)/'output')
            with zipfile.ZipFile(Path(root)/'output'/result['file']) as archive:
                self.assertEqual(archive.read('dump.sql'),b'SQL-export')
                self.assertEqual(archive.read('filestore/ab/123'),b'file')

if __name__=='__main__': unittest.main()
