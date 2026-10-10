"""Fail-closed native-only policy. All destructive ORM work uses restored copies."""
import ast
import hashlib
import json
import re
from pathlib import Path
import secrets
import shutil

POLICY = {'target_version': 20, 'native_only': True, 'protocol': 2}
TECHNICAL = {'openupgrade_framework', 'openupgrade_scripts'}


def inventory(root):
    result = {}
    for path in Path(root).rglob('__manifest__.py'):
        if '.git' in path.parts:
            continue
        try:
            manifest = ast.literal_eval(path.read_text())
        except (ValueError, SyntaxError):
            continue
        if manifest.get('installable', True):
            result[path.parent.name] = {'depends': manifest.get('depends', [])}
    return result


def cleanup_plan(modules, native):
    installed = {m['name'] for m in modules if m['state'] == 'installed'}
    transitional = [m['name'] for m in modules if m['state'] not in ('installed', 'uninstalled', 'uninstallable')]
    if transitional:
        raise ValueError('Modules dans un état transitoire : ' + ', '.join(transitional))
    remove = installed - set(native)
    dependents = {name for name in installed & set(native)
                  if set(native[name]['depends']) & remove}
    if dependents:
        raise ValueError('La désinstallation toucherait des modules natifs : ' + ', '.join(sorted(dependents)))
    return sorted(remove)


def official_source(engine, version):
    path = engine.root / 'official' / str(version)
    path.parent.mkdir(parents=True, exist_ok=True)
    commit = engine.git_clone('https://github.com/odoo/odoo.git', str(version) + '.0', path)
    return path, commit, inventory(path)


def parse_coverage(text, evidence):
    rows = {}
    for line in text.splitlines():
        line = re.sub(r'\|(new|del)\|', '', line)
        cells = [part.strip() for part in line.split('|')]
        if len(cells) < 4 or not re.fullmatch(r'[a-z0-9_]+', cells[1]):
            continue
        status = {'Done':'done', 'Nothing to do':'nothing_to_do'}.get(cells[2])
        if status:
            rows[cells[1]] = {'status':status,'evidence':evidence + ' — ' + cells[2]}
    return rows


def check_coverage(engine, prepared):
    """Require a checked-in explicit coverage decision for every installed addon.

    Script existence alone is not evidence of completeness. A local reviewed
    manifest is bound to the exact OpenUpgrade commit, never inferred from success.
    """
    version = prepared['target']
    path = engine.root / 'coverage' / (str(version) + '.json')
    if not path.exists():
        root = Path(prepared['folder']) / 'OpenUpgrade'
        filename = 'modules' + str(version-1) + '0-' + str(version) + '0.rst'
        tables = sorted(root.rglob(filename))
        if not tables:
            raise ValueError('OpenUpgrade ne fournit pas de tableau de couverture pour ' + str(version-1) +
                             ' → ' + str(version) + '. Le palier ne peut pas être déclaré disponible.')
        rows = {}
        for table in tables:
            relative = table.relative_to(root).as_posix()
            rows.update(parse_coverage(table.read_text(),
                'https://github.com/OCA/OpenUpgrade/blob/' + prepared['commits']['OpenUpgrade'] + '/' + relative))
        path.parent.mkdir(parents=True, exist_ok=True)
        from migration import write_json
        write_json(path, {'commit':prepared['commits']['OpenUpgrade'], 'modules':rows})
    coverage = json.loads(path.read_text())
    if coverage.get('commit') != prepared['commits']['OpenUpgrade']:
        raise ValueError('La couverture ne correspond pas au commit OpenUpgrade utilisé.')
    absent = []
    for module in engine.state['modules']:
        if module['state'] != 'installed' or module['name'] in TECHNICAL:
            continue
        row = coverage.get('modules', {}).get(module['name'], {})
        if row.get('status') not in ('done', 'nothing_to_do', 'renamed', 'merged') or not row.get('evidence'):
            absent.append(module['name'])
    if absent:
        raise ValueError('Couverture non démontrée : ' + ', '.join(absent))
    prepared['coverage'] = coverage


def security_checks(engine, work):
    network = json.loads(engine.run(['docker', 'network', 'inspect', work['network']], quiet=True))[0]
    if not network.get('Internal'):
        raise ValueError('Le réseau de migration doit être interne.')
    inspected = []
    for name in [work['db'], work['prefix'] + '-upgrade']:
        info = engine.inspect(name)
        host = info['HostConfig']
        if host.get('Privileged') or host.get('NetworkMode') == 'host' or host.get('PidMode') == 'host':
            raise ValueError('Privilèges inattendus sur ' + name)
        if host.get('PortBindings'):
            raise ValueError('Port publié inattendu sur ' + name)
        if set(info['NetworkSettings']['Networks']) != {work['network']}:
            raise ValueError('Connexion réseau externe sur ' + name)
        if any(m['Type'] == 'bind' for m in info.get('Mounts', [])):
            raise ValueError('Montage hôte inattendu dans un conteneur de travail.')
        inspected.append(name)
    if engine.sql(work['db'], 'migration', 'SELECT count(*) FROM ir_cron WHERE active') != '0':
        raise ValueError('Des tâches planifiées restent actives.')
    return {'network_internal': True, 'no_published_ports': True,
            'no_host_mounts': True, 'no_privileged_containers': True,
            'cron_disabled': True, 'containers': inspected}


def cleanup(engine):
    """Uninstall third-party modules with Odoo 12 ORM, then promote a new copy."""
    if engine.state.get('native_cleanup'):
        return
    if engine.state['version'] != 12 or engine.state.get('pending'):
        raise ValueError('Le nettoyage natif exige une nouvelle copie Odoo 12 sans migration en attente.')
    source, commit, native = official_source(engine, 12)
    remove = cleanup_plan(engine.state['modules'], native)
    # Even no-op cleanup is recorded; originals and their manifest remain intact.
    if not remove:
        engine.state['native_cleanup'] = {'removed': [], 'odoo_commit': commit}
        engine.save()
        return
    folder = engine.root / 'native-cleanup'
    folder.mkdir(exist_ok=True)
    extras = folder / 'extra'
    extras.mkdir(exist_ok=True)
    # Originals are only read here. Never overlay a native module with third-party code.
    roots = [engine.root / 'extra' / '12']
    roots += list(Path(engine.state['backup']).glob('addons-*'))
    available = {}
    for root in roots:
        for path in root.rglob('__manifest__.py'):
            if path.parent.name not in native:
                available[path.parent.name] = path.parent
    missing = set(remove) - set(available)
    if missing:
        raise ValueError('Code Odoo 12 requis pour désinstaller proprement : ' + ', '.join(sorted(missing)) +
                         '. Fournir les modules dans extra/12; aucune suppression SQL forcée.')
    for name, path in available.items():
        shutil.copytree(path, extras / name, dirs_exist_ok=True)
    (folder / 'Dockerfile').write_text('FROM odoo:12\nUSER root\nCOPY extra /opt/cleanup-extra\nUSER odoo\n')
    image = 'odoo-native-cleanup:' + secrets.token_hex(6)
    engine.run(['docker', 'build', '-t', image, str(folder)])
    image = engine.run(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], quiet=True)
    previous = engine.state.get('prepared')
    engine.state['prepared'] = {'target': 12, 'image': image, 'inventory': {'paths':
        ['/usr/lib/python3/dist-packages/odoo/addons', '/opt/cleanup-extra']}}
    try:
        work = engine.start_pg(12, 'native-' + secrets.token_hex(6))
        engine.restore(work)
        engine.config(work)
        script = """import json
import re
names = NAMES
mods = env['ir.module.module'].search([('name', 'in', names), ('state', '=', 'installed')])
# Odoo computes the recursive uninstall set; protect native dependencies first.
protected = env['ir.module.module'].search([('name', 'in', NATIVE), ('state', '=', 'installed')])
deps = mods.downstream_dependencies()
if set(deps.mapped('name')) & set(protected.mapped('name')):
    raise RuntimeError('La cascade de désinstallation touche un module natif')
mods.button_immediate_uninstall()
env.cr.commit()
""".replace('NAMES', repr(remove)).replace('NATIVE', repr(sorted(native)))
        scriptpath = folder / 'cleanup.py'
        scriptpath.write_text(script)
        name = work['prefix'] + '-upgrade'
        launcher = "import os,pwd; u=pwd.getpwnam('odoo'); os.chown('/tmp/migration.conf',u.pw_uid,u.pw_gid); os.chmod('/tmp/cleanup.py',0o644); os.initgroups('odoo',u.pw_gid); os.setgid(u.pw_gid); os.setuid(u.pw_uid); os.execvp('sh',['sh','-c','exec odoo shell -c /tmp/migration.conf -d migration --no-http < /tmp/cleanup.py'])"
        engine.run(['docker', 'create', '--name', name, '--label', 'odoo.migration=local', '--network', work['network'],
                    '-v', work['data_volume'] + ':/var/lib/odoo', '--user', 'root', '--entrypoint', 'python3', image, '-c', launcher])
        engine.run(['docker', 'cp', work['config'], name + ':/tmp/migration.conf'])
        engine.run(['docker', 'cp', str(scriptpath), name + ':/tmp/cleanup.py'])
        # Launcher grants script read access before dropping privileges.
        engine.run(['docker', 'start', name])
        code = engine.run(['docker', 'wait', name], quiet=True)
        log = engine.run(['docker', 'logs', name], quiet=True)
        (folder / 'cleanup.log').write_text(log)
        if code != '0':
            raise ValueError('Désinstallation ORM Odoo 12 échouée. Voir native-cleanup/cleanup.log. Original conservé.')
        after_modules = engine.modules(work['db'], 'migration')
        remaining = cleanup_plan(after_modules, native)
        if remaining:
            raise ValueError('Modules tiers encore installés : ' + ', '.join(remaining))
        after = engine.metrics(work['db'], 'migration')
        protected_metrics = ('contacts', 'utilisateurs', 'societes', 'ventes', 'ecritures', 'debit', 'credit')
        differences = [k for k in protected_metrics if engine.state['metrics'].get(k) != after.get(k)]
        report = {'removed': remove, 'before': engine.state['metrics'], 'after': after,
                  'odoo_commit': commit, 'security': security_checks(engine, work), 'differences': differences}
        from migration import write_json
        write_json(folder / 'report.json', report)
        if differences:
            raise ValueError('Le nettoyage modifie des données protégées : ' + ', '.join(differences))
        engine.state['pending'] = {'version': 12, 'work': work, 'before': engine.state['metrics'],
            'metrics': after, 'modules': after_modules, 'decisions': {'native_cleanup': report},
            'commits': {'odoo': commit}, 'image': image}
        engine.validate({'_technical_auto': True, 'validation_note': 'Nettoyage natif sur copie; contrôles techniques réussis.'})
        engine.state['native_cleanup'] = report
        engine.save()
    finally:
        engine.state['prepared'] = previous
        engine.save()
