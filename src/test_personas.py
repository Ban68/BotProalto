"""
Loader de personas para el modo automático del panel /admin/test.

Cada persona vive en context/test_personas/<slug>.md con un frontmatter YAML
mínimo (slug, nombre, descripcion) y un cuerpo markdown que se usa como
instrucción para el LLM-cliente. Cargamos todo a memoria al primer uso.
"""
import os
import re

_PERSONAS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'context',
    'test_personas',
)

_cache = None


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Parse a minimal YAML frontmatter (clave: valor por línea).
    Devuelve (meta_dict, body)."""
    if not raw.startswith('---'):
        return {}, raw
    try:
        _, fm, body = raw.split('---', 2)
    except ValueError:
        return {}, raw
    meta = {}
    for line in fm.strip().splitlines():
        if ':' not in line:
            continue
        k, v = line.split(':', 1)
        meta[k.strip()] = v.strip()
    return meta, body.lstrip('\n')


def load_personas(force_reload: bool = False) -> dict:
    """Devuelve {slug: {slug, nombre, descripcion, prompt_body}} cacheado."""
    global _cache
    if _cache is not None and not force_reload:
        return _cache

    personas = {}
    if not os.path.isdir(_PERSONAS_DIR):
        _cache = personas
        return personas

    for fname in sorted(os.listdir(_PERSONAS_DIR)):
        if not fname.endswith('.md'):
            continue
        path = os.path.join(_PERSONAS_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            print(f"[test_personas] could not read {fname}: {e}")
            continue
        meta, body = _parse_frontmatter(raw)
        slug = meta.get('slug') or os.path.splitext(fname)[0]
        personas[slug] = {
            'slug': slug,
            'nombre': meta.get('nombre') or slug,
            'descripcion': meta.get('descripcion') or '',
            'prompt_body': body.strip(),
        }

    _cache = personas
    return personas


def get_persona(slug: str) -> dict | None:
    return load_personas().get(slug)


def list_personas() -> list:
    """Devuelve lista resumida para el dropdown del frontend."""
    return [
        {'slug': p['slug'], 'nombre': p['nombre'], 'descripcion': p['descripcion']}
        for p in load_personas().values()
    ]
