#!/usr/bin/env python3
"""
drive.py - Simple self-hosted file drive (Flask)
Home dir: ~/files
"""

import os, math, mimetypes
from flask import (Flask, request, send_file, redirect, url_for,
                   abort, render_template_string, jsonify)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2 GB

HOME = os.path.expanduser('~/files')
os.makedirs(HOME, exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────

def safe_path(rel):
    """Resolve rel path inside HOME; abort 400 if escaping."""
    target = os.path.realpath(os.path.join(HOME, rel))
    if not target.startswith(os.path.realpath(HOME)):
        abort(400)
    return target

def fmt_bytes(n):
    if n >= 1 << 30: return f'{n/(1<<30):.2f} GB'
    if n >= 1 << 20: return f'{n/(1<<20):.1f} MB'
    if n >= 1 << 10: return f'{n/(1<<10):.1f} KB'
    return f'{n} B'

def dir_entries(abs_dir):
    entries = []
    for name in sorted(os.listdir(abs_dir)):
        full = os.path.join(abs_dir, name)
        stat = os.stat(full)
        entries.append({
            'name': name,
            'is_dir': os.path.isdir(full),
            'size': stat.st_size,
            'size_fmt': fmt_bytes(stat.st_size) if not os.path.isdir(full) else '—',
            'mtime': stat.st_mtime,
        })
    entries.sort(key=lambda e: (not e['is_dir'], e['name'].lower()))
    return entries

def dir_size(abs_dir):
    total = 0
    for dp, _, fnames in os.walk(abs_dir):
        for f in fnames:
            try: total += os.path.getsize(os.path.join(dp, f))
            except: pass
    return total

# ── HTML template ─────────────────────────────────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>drive / {{ breadcrumb_str }}</title>
<style>
* { -webkit-box-sizing: border-box; box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0a0a0f;
  color: #c8d8c8;
  font-family: monospace;
  font-size: 14px;
  padding: 20px 10px 60px;
}
a { color: inherit; text-decoration: none; }

/* header */
.header { max-width: 640px; margin: 0 auto 6px; display: -webkit-box; display: -webkit-flex; display: flex; -webkit-box-align: center; -webkit-align-items: center; align-items: center; -webkit-box-pack: justify; -webkit-justify-content: space-between; justify-content: space-between; }
h1 { font-size: 1.6rem; color: #00ff88; letter-spacing: 0; }
h1 span { color: #ff6b35; }
.sub { font-size: 11px; color: #4a5a4a; letter-spacing: 3px; text-transform: uppercase; max-width: 640px; margin: 0 auto 18px; }

/* breadcrumb */
.breadcrumb { max-width: 640px; margin: 0 auto 10px; font-size: 12px; color: #4a5a4a; text-transform: uppercase; letter-spacing: 1px; }
.breadcrumb a { color: #00ff88; }
.breadcrumb span { color: #4a5a4a; margin: 0 4px; }

/* storage bar */
.storageline { max-width: 640px; margin: 0 auto 14px; display: -webkit-box; display: -webkit-flex; display: flex; -webkit-box-pack: justify; -webkit-justify-content: space-between; justify-content: space-between; font-size: 11px; color: #4a5a4a; text-transform: uppercase; letter-spacing: 1px; }

/* upload card */
.card { background: #0f0f1a; border: 1px solid #1a1a2e; max-width: 640px; margin: 0 auto 18px; padding: 14px; }
.clbl { font-size: 11px; color: #4a5a4a; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; }
.upload-row { display: -webkit-box; display: -webkit-flex; display: flex; -webkit-box-align: center; -webkit-align-items: center; align-items: center; gap: 8px; }
input[type=file] { -webkit-box-flex: 1; -webkit-flex: 1; flex: 1; background: #0a0a0f; border: 1px solid #1a1a2e; color: #c8d8c8; font-family: monospace; font-size: 12px; padding: 7px 8px; }
.btn { background: transparent; border: 1px solid #00ff88; color: #00ff88; font-family: monospace; font-size: 12px; padding: 7px 14px; cursor: pointer; text-transform: uppercase; white-space: nowrap; }
.btn:disabled { opacity: 0.4; cursor: default; }
.btn.warn { border-color: #ff6b35; color: #ff6b35; }
.btn.muted { border-color: #1a1a2e; color: #4a5a4a; }
.mkdir-row { display: -webkit-box; display: -webkit-flex; display: flex; margin-top: 10px; }
input[type=text] { -webkit-box-flex: 1; -webkit-flex: 1; flex: 1; background: #0a0a0f; border: 1px solid #1a1a2e; border-right: none; color: #c8d8c8; font-family: monospace; font-size: 13px; padding: 7px 10px; outline: none; }
input[type=text]:focus { border-color: #00ff88; }

/* file list */
.shdr { max-width: 640px; margin: 0 auto; font-size: 11px; color: #4a5a4a; letter-spacing: 3px; text-transform: uppercase; border-bottom: 1px solid #1a1a2e; padding-bottom: 5px; margin-bottom: 0; }
.row {
  background: #0f0f1a;
  border: 1px solid #1a1a2e;
  border-top: none;
  max-width: 640px;
  margin: 0 auto;
  padding: 9px 12px;
  display: -webkit-box; display: -webkit-flex; display: flex;
  -webkit-box-align: center; -webkit-align-items: center; align-items: center;
  gap: 8px;
}
.row:first-child { border-top: 1px solid #1a1a2e; }
.icon { font-size: 14px; width: 18px; -webkit-flex-shrink: 0; flex-shrink: 0; }
.fname { -webkit-box-flex: 1; -webkit-flex: 1; flex: 1; font-size: 13px; word-break: break-all; }
.fname a:hover { color: #00ff88; }
.fsize { font-size: 11px; color: #4a5a4a; -webkit-flex-shrink: 0; flex-shrink: 0; min-width: 60px; text-align: right; }
.acts { display: -webkit-box; display: -webkit-flex; display: flex; gap: 6px; -webkit-flex-shrink: 0; flex-shrink: 0; }
.acts a, .acts button { font-size: 11px; color: #00ff88; border: 1px solid #1a1a2e; padding: 3px 7px; background: transparent; font-family: monospace; cursor: pointer; text-transform: uppercase; white-space: nowrap; }
.acts button.del { color: #ff6b35; }
.empty { max-width: 640px; margin: 0 auto; background: #0f0f1a; border: 1px solid #1a1a2e; padding: 20px; text-align: center; font-size: 12px; color: #4a5a4a; }

/* flash */
.flash { max-width: 640px; margin: 0 auto 12px; padding: 8px 12px; font-size: 12px; border: 1px solid; }
.flash.ok  { border-color: #00ff88; color: #00ff88; }
.flash.err { border-color: #ff6b35; color: #ff6b35; }

/* progress overlay */
#prog { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #0f0f1a; border-top: 1px solid #1a1a2e; padding: 10px 20px; font-size: 12px; color: #00ff88; text-transform: uppercase; }
#pbar { height: 3px; background: #1a1a2e; margin-top: 6px; }
#pfill { height: 100%; width: 0; background: #00ff88; }
</style>
</head>
<body>

<div class="header">
  <h1>DRIVE<span>Y</span></h1>
</div>
<div class="sub">personal file drive</div>

{% if msg %}
<div class="flash {{ 'ok' if msg_ok else 'err' }}">{{ msg }}</div>
{% endif %}

<!-- breadcrumb -->
<div class="breadcrumb">
  <a href="/">~</a>
  {% for crumb in crumbs %}
    <span>/</span><a href="/browse/{{ crumb.path }}">{{ crumb.name }}</a>
  {% endfor %}
</div>

<!-- storage info -->
<div class="storageline">
  <span>{{ entry_count }} items</span>
  <span>{{ total_size }}</span>
</div>

<!-- upload + mkdir -->
<div class="card">
  <div class="clbl">upload to current folder</div>
  <form method="POST" action="/upload/{{ rel_path }}" enctype="multipart/form-data" id="upform">
    <div class="upload-row">
      <input type="file" name="file" multiple id="fileinput">
      <button class="btn" type="submit" id="upbtn">UPLOAD</button>
    </div>
  </form>
  <form method="POST" action="/mkdir/{{ rel_path }}" id="mkform" style="margin-top:10px;">
    <div class="mkdir-row">
      <input type="text" name="dirname" placeholder="new folder name" id="dname" autocomplete="off">
      <button class="btn" type="submit">MKDIR</button>
    </div>
  </form>
</div>

<!-- file list -->
<div class="shdr">name</div>

{% if rel_path %}
<div class="row">
  <span class="icon">&#128193;</span>
  <span class="fname"><a href="/browse/{{ parent_path }}">..</a></span>
  <span class="fsize">—</span>
  <span class="acts"></span>
</div>
{% endif %}

{% if entries %}
  {% for e in entries %}
  <div class="row">
    <span class="icon">{% if e.is_dir %}&#128193;{% else %}&#128196;{% endif %}</span>
    <span class="fname">
      {% if e.is_dir %}
        <a href="/browse/{{ (rel_path + '/' + e.name).strip('/') }}">{{ e.name }}/</a>
      {% else %}
        <a href="/open/{{ (rel_path + '/' + e.name).strip('/') }}">{{ e.name }}</a>
      {% endif %}
    </span>
    <span class="fsize">{{ e.size_fmt }}</span>
    <span class="acts">
      {% if not e.is_dir %}
        <a href="/dl/{{ (rel_path + '/' + e.name).strip('/') }}">DL</a>
      {% endif %}
      <button class="del" onclick="delItem('{{ (rel_path + '/' + e.name).strip('/') | urlencode }}', this)">X</button>
    </span>
  </div>
  {% endfor %}
{% else %}
  <div class="empty">folder is empty</div>
{% endif %}

<div id="prog"><span id="pstat">uploading...</span><div id="pbar"><div id="pfill"></div></div></div>

<script>
/* Native multipart POST — no XHR/FormData.
   BB OS 6 WebKit bug: FormData silently drops file inputs even when a file
   is selected, so the upload body arrives empty. Plain native POST works. */
document.getElementById('upform').onsubmit = function() {
  var f = document.getElementById('fileinput');
  if (!f || !f.value) { return false; }
  var prog = document.getElementById('prog');
  if (prog) { prog.style.display = 'block'; }
  return true;
};

/* confirm-delete pattern */
var pendingDel = '', pendingTimer = null;
function delItem(path, btn) {
  if (pendingDel !== path) {
    pendingDel = path;
    btn.innerHTML = 'sure?';
    if (pendingTimer) { clearTimeout(pendingTimer); }
    pendingTimer = setTimeout(function() { pendingDel = ''; window.location.reload(); }, 3000);
    return;
  }
  var xhr2 = new XMLHttpRequest();
  xhr2.onload = function() { window.location.reload(); };
  xhr2.open('POST', '/delete/' + path);
  xhr2.send();
}

/* mkdir enter key */
document.getElementById('dname').onkeydown = function(e) {
  if ((e || window.event).keyCode === 13) { document.getElementById('mkform').submit(); }
};
</script>
</body>
</html>
"""

# ── routes ────────────────────────────────────────────────────────────────────

def render_dir(rel, msg=None, msg_ok=True):
    abs_dir = safe_path(rel)
    if not os.path.isdir(abs_dir):
        abort(404)

    entries = dir_entries(abs_dir)
    total   = dir_size(abs_dir)

    # breadcrumb parts
    parts = [p for p in rel.split('/') if p]
    crumbs = []
    for i, part in enumerate(parts):
        crumbs.append({'name': part, 'path': '/'.join(parts[:i+1])})

    parent_parts = parts[:-1]
    parent_path  = '/'.join(parent_parts)
    breadcrumb_str = '/' + rel if rel else '~'

    return render_template_string(
        TEMPLATE,
        rel_path=rel,
        entries=entries,
        crumbs=crumbs,
        parent_path=parent_path,
        breadcrumb_str=breadcrumb_str,
        entry_count=len(entries),
        total_size=fmt_bytes(total),
        msg=msg,
        msg_ok=msg_ok,
    )

@app.route('/')
def index():
    return redirect(url_for('browse', rel=''))

@app.route('/browse/', defaults={'rel': ''})
@app.route('/browse/<path:rel>')
def browse(rel):
    return render_dir(rel)

@app.route('/upload/', defaults={'rel': ''}, methods=['POST'])
@app.route('/upload/<path:rel>', methods=['POST'])
def upload(rel):
    abs_dir = safe_path(rel)
    os.makedirs(abs_dir, exist_ok=True)
    files = request.files.getlist('file')
    if not files or all(f.filename == '' for f in files):
        return render_dir(rel, 'no file selected', False)
    saved = []
    for f in files:
        if f.filename:
            name = secure_filename(f.filename)
            f.save(os.path.join(abs_dir, name))
            saved.append(name)
    msg = f'uploaded: {", ".join(saved)}' if saved else 'nothing uploaded'
    return render_dir(rel, msg, bool(saved))

@app.route('/mkdir/', defaults={'rel': ''}, methods=['POST'])
@app.route('/mkdir/<path:rel>', methods=['POST'])
def mkdir(rel):
    dirname = request.form.get('dirname', '').strip()
    if not dirname:
        return render_dir(rel, 'folder name required', False)
    name = secure_filename(dirname)
    target = safe_path(os.path.join(rel, name))
    os.makedirs(target, exist_ok=True)
    return render_dir(rel, f'created: {name}')

@app.route('/dl/<path:rel>')
def download(rel):
    abs_path = safe_path(rel)
    if not os.path.isfile(abs_path):
        abort(404)
    return send_file(abs_path, as_attachment=True,
                     download_name=os.path.basename(abs_path))

@app.route('/open/<path:rel>')
def open_file(rel):
    abs_path = safe_path(rel)
    if not os.path.isfile(abs_path):
        abort(404)
    mime, _ = mimetypes.guess_type(abs_path)
    return send_file(abs_path, mimetype=mime or 'application/octet-stream')

@app.route('/delete/<path:rel>', methods=['POST'])
def delete(rel):
    import shutil
    abs_path = safe_path(rel)
    if os.path.isdir(abs_path):
        shutil.rmtree(abs_path)
    elif os.path.isfile(abs_path):
        os.remove(abs_path)
    else:
        abort(404)
    parent = '/'.join([p for p in rel.split('/') if p][:-1])
    return redirect(url_for('browse', rel=parent))

# ── run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=5050)
    args = parser.parse_args()
    print(f'[drive] serving ~/files on http://{args.host}:{args.port}')
    app.run(host=args.host, port=args.port, debug=False)
