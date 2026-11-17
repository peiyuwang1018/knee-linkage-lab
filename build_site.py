#!/usr/bin/env python3
"""Build a GitHub Pages artifact from reviewed public assets and shared Python code."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build(destination=None):
    out = Path(destination) if destination else ROOT / '_site'
    out.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / 'static').iterdir():
        if source.suffix not in {'.html', '.css', '.js', '.mjs'}:
            continue
        content = source.read_text()
        if source.name in {'index.html', 'chain.html'}:
            content = content.replace('<html lang="en">', '<html lang="en" data-solver="browser">')
        (out / source.name).write_text(content)
    sources = {source.name: source.read_text() for source in sorted((ROOT / 'kneelab').glob('*.py'))}
    sources['chains.json'] = (ROOT / 'kneelab/chains.json').read_text()
    (out / 'kneelab-sources.json').write_text(json.dumps(sources, ensure_ascii=False))
    for name, source in {'model.md': 'docs/Model.md', 'findings.md': 'docs/Initial-findings.en.md',
                         'readme.md': 'README.md'}.items():
        (out / name).write_bytes((ROOT / source).read_bytes())
    (out / '.nojekyll').touch()
    return out


if __name__ == '__main__':
    print(f'Built browser app: {build()}')
