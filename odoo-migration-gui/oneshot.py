#!/usr/bin/env python3
"""One command: SQL + complete filestore -> validated Odoo backup, or clear blocker."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile
from migration import Engine, MAX_UPLOAD_BYTES, write_json


class ConsoleEngine(Engine):
    def log(self, message):
        super().log(message)
        print(message, flush=True)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def source_files(source):
    source = Path(source)
    dump = source / 'dump.sql'
    filestore = source / 'filestore'
    if dump.is_symlink() or not dump.is_file() or not dump.stat().st_size:
        raise ValueError('Déposer un dump SQL non vide dans /input/dump.sql.')
    if filestore.is_symlink() or not filestore.is_dir():
        raise ValueError('Déposer le dossier complet dans /input/filestore (sans le nom de base intermédiaire).')
    files = [(dump, 'dump.sql')]
    for path in sorted(filestore.rglob('*')):
        if path.is_symlink():
            raise ValueError('Lien symbolique refusé : ' + str(path))
        if path.is_file():
            files.append((path, path.relative_to(source).as_posix()))
        elif not path.is_dir():
            raise ValueError('Fichier spécial refusé : ' + str(path))
    if sum(path.stat().st_size for path, _ in files) > MAX_UPLOAD_BYTES:
        raise ValueError('Entrée supérieure à 10 Gio; ce moteur nécessite une adaptation de sa limite.')
    return files


def package_input(source, destination):
    files = source_files(source)
    manifest = {name: file_hash(path) for path, name in files}
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_STORED) as archive:
        for path, name in files:
            archive.write(path, name)
    if any(file_hash(path) != manifest[name] for path, name in files):
        raise ValueError('Entrée modifiée pendant la copie; utiliser une sauvegarde figée.')
    return manifest


def export_result(engine, output):
    """Export only a validated target. Never label a partial checkpoint as success."""
    target = engine.state['policy']['target_version']
    if engine.state['version'] != target or not engine.state['validated'] or engine.state.get('pending'):
        raise ValueError('Export refusé : la version cible n’est pas validée.')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Restore the final checkpoint once more before exporting standard Odoo SQL.
    work = engine.start_pg(target, 'export-' + os.urandom(6).hex())
    checkpoint = Path(engine.state['checkpoint'])
    expected = json.loads((checkpoint.parent / 'validation.json').read_text())['dump_sha256']
    if file_hash(checkpoint) != expected:
        raise ValueError('Le checkpoint final est corrompu.')
    engine.run(['docker','cp',str(checkpoint),work['db']+':/tmp/final.dump'])
    engine.run(['docker','exec',work['db'],'pg_restore','--exit-on-error','--no-owner','--no-acl','-U','odoo','-d','migration','/tmp/final.dump'])
    if engine.metrics(work['db'], 'migration') != engine.state['metrics']:
        raise ValueError('La restauration finale diffère du checkpoint.')
    sql = output / 'dump.sql.partial'
    engine.run(['docker','exec',work['db'],'pg_dump','-U','odoo','-d','migration','--no-owner','--no-acl'], out=sql, quiet=True)
    archive_path = output / ('odoo-' + str(target) + '-native.zip')
    partial = archive_path.with_suffix('.zip.partial')
    filestore = Path(engine.state['data']) / 'filestore' / 'migration'
    with zipfile.ZipFile(partial, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        archive.write(sql, 'dump.sql')
        for path in sorted(filestore.rglob('*')):
            if path.is_file():
                archive.write(path, 'filestore/' + path.relative_to(filestore).as_posix())
        archive.writestr('manifest.json', json.dumps({'odoo_dump':'1','db_name':'migration','version':str(target)+'.0',
            'major_version':str(target)+'.0','modules':{m['name']:m.get('latest_version') for m in engine.state['modules'] if m['state']=='installed'}}))
    partial.replace(archive_path)
    sql.unlink()
    engine.run(['docker','stop',work['db']], quiet=True)
    return {'file':archive_path.name,'sha256':file_hash(archive_path),'version':target}


def main():
    os.umask(0o077)
    root = Path(os.environ.get('ODOO_MIGRATION_HOME','/opt/odoo-migration-once'))
    output = root / 'output'
    output.mkdir(parents=True, exist_ok=True)
    lock = (root / 'oneshot.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    engine = ConsoleEngine(root / 'job')
    target = int(os.environ.get('TARGET_VERSION','20'))
    if not 13 <= target <= 20:
        raise ValueError('TARGET_VERSION doit être compris entre 13 et 20.')
    policy = {'target_version':target,'native_only':True,'protocol':2,'headless':True}
    if engine.state.get('policy') and engine.state['policy'] != policy:
        raise ValueError('Politique différente : utiliser un autre ODOO_MIGRATION_HOME.')
    engine.state['policy'] = policy
    engine.save()
    try:
        write_json(output / 'result.json', {'status':'running','target':target,'last_validated_version':engine.state['version']})
        engine.run(['docker','version'], quiet=True)
        source = Path('/input')
        if not engine.state.get('backup'):
            incoming = engine.root / 'incoming'
            incoming.mkdir(exist_ok=True)
            manifest = package_input(source, incoming / 'source.zip')
            write_json(engine.root / 'input-manifest.json', manifest)
            engine.import_backup({'file':str(incoming / 'source.zip')})
        else:
            manifest = json.loads((engine.root / 'input-manifest.json').read_text())
            current = {name:file_hash(path) for path,name in source_files(source)}
            if current != manifest:
                raise ValueError('La sauvegarde source a changé. Utiliser un nouveau dossier de travail.')
        # Optional original addons needed only for native ORM uninstallation.
        if (source / 'addons-12').is_symlink():
            raise ValueError('addons-12 doit être un dossier réel.')
        if (source / 'addons-12').is_dir():
            if any(p.is_symlink() for p in (source / 'addons-12').rglob('*')):
                raise ValueError('Liens symboliques refusés dans addons-12.')
            shutil.copytree(source / 'addons-12', engine.root / 'extra' / '12', dirs_exist_ok=True)
        engine.autopilot({'ack_auto':True})
        result = export_result(engine, output)
        write_json(output / 'result.json', {'status':'completed',**result,'metrics':engine.state['metrics'],
                                          'native_cleanup':engine.state.get('native_cleanup')})
        print('TERMINÉ : ' + str(output / result['file']), flush=True)
        return 0
    except Exception as exc:
        write_json(output / 'result.json', {'status':'blocked','target':target,'last_validated_version':engine.state['version'],
                                          'reason':str(exc),'checkpoint':engine.state.get('checkpoint')})
        print('BLOQUÉ : ' + str(exc) + '\nRapport : ' + str(output / 'result.json'), flush=True)
        return 2

if __name__ == '__main__':
    sys.exit(main())
