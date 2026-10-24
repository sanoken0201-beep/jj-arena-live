"""Compile caller markers and stop signed-out background quiz refreshes."""
import hashlib
from pathlib import Path

MARKER = 'quiz caller diagnostics v89'


def transform_app_js(source):
    if MARKER in source:
        return source
    anchor = '  function jjV203DayCheck(){'
    if source.count(anchor) != 1:
        raise RuntimeError('quiz day-check anchor drift')
    source = source.replace(anchor, anchor + '\n    if(!me || document.hidden)return; // ' + MARKER)
    target = "api('/quiz/question')"
    count = source.count(target)
    if not 1 <= count < 20:
        raise RuntimeError('quiz request callsite drift')
    for i in range(1, count + 1):
        source = source.replace(target, "api('/quiz/question',{headers:{'X-JJ-Quiz-Source':'browser-call-%d'}})" % i, 1)
    return source


def apply_to_build(output_root, manifest):
    path = Path(output_root) / 'static/app.js'
    content = transform_app_js(path.read_text(encoding='utf-8'))
    path.write_text(content, encoding='utf-8')
    manifest['outputs']['static/app.js'] = hashlib.sha256(content.encode()).hexdigest()
    manifest.setdefault('post_transforms', {})['quiz_request_diagnostics'] = MARKER
    return manifest
