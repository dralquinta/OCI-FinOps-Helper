"""Copy allowlisted suite assets without notebook results or customer OCIDs."""
import copy
import json
from importlib import metadata
from pathlib import Path
import re
import shutil
import sys


def redact(text):
    return re.sub(r"ocid1\.[A-Za-z0-9_.-]+", '<resource-ocid>', text)


def sanitize_notebook(notebook):
    clean = copy.deepcopy(notebook)
    clean['metadata'] = {}
    for cell in clean.get('cells', []):
        cell['metadata'] = {}
        if cell.get('cell_type') == 'code':
            cell['outputs'] = []
            cell['execution_count'] = None
        source = cell.get('source', [])
        cell['source'] = [redact(line) for line in source] if isinstance(source, list) else redact(source)
        cell.pop('attachments', None)
    return clean


def asset_sources(root):
    return [root / name for name in ['README.md', 'LICENSE', 'collector.sh', 'requirements.txt']] + sorted((root / 'docs').glob('*.md')) + sorted((root / 'jupe-note').glob('*.ipynb')) + sorted((root / 'src').rglob('*.py'))


def prepare(root, destination):
    if destination.exists():
        shutil.rmtree(destination)
    for source in asset_sources(root):
        target = destination / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == '.ipynb':
            target.write_text(json.dumps(sanitize_notebook(json.loads(source.read_text())), indent=1))
        elif source.suffix == '.py':
            # Production source must retain OCID type prefixes and parser semantics.
            target.write_bytes(source.read_bytes())
        else:
            target.write_text(redact(source.read_text()))
    notices = ['# Bundled third-party dependencies', '',
               'Python runtime: Python Software Foundation License (https://docs.python.org/3/license.html).', '']
    license_directory = destination / 'third-party-licenses'
    for package in sorted(metadata.distributions(), key=lambda item: item.metadata['Name']):
        name = package.metadata['Name']
        notices.append(name + ' ' + package.version + ': ' + package.metadata.get('License-Expression', package.metadata.get('License', 'See package license files.')).split('\n')[0])
        for file in package.files or []:
            if 'license' in file.name.lower() and package.locate_file(file).is_file():
                license_directory.mkdir(parents=True, exist_ok=True)
                (license_directory / (name + '-' + file.name)).write_bytes(package.locate_file(file).read_bytes())
    (destination / 'THIRD_PARTY_NOTICES.md').write_text('\n'.join(notices) + '\n')


if __name__ == '__main__':
    prepare(Path(__file__).resolve().parents[1], Path(sys.argv[1]))
