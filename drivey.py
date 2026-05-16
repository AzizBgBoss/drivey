#!/usr/bin/env python3
"""
drivey.py - Simple self-hosted file drive (Flask)
Home dir: ~/files
"""

import os, mimetypes, shutil, time
from flask import (Flask, request, send_file, redirect, url_for,
                   abort, render_template_string)
from werkzeug.utils import secure_filename
from auth import init_auth, login_required, login_route, logout_route, set_login_theme

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2 GB

init_auth(app, users_file='drivey_users.json', cookie_name='drivey_token')
set_login_theme('drivey', 'DRIVE', 'Y', 'personal file drive')

HOME = os.path.expanduser('~/files')
os.makedirs(HOME, exist_ok=True)

# ── MIME classification ───────────────────────────────────────────────────────

OPEN_MIME = ('audio/', 'video/', 'image/', 'application/pdf')
SHOW_EXTS = {'.txt', '.md', '.py', '.js', '.ts', '.json', '.html', '.htm',
             '.css', '.sh', '.bash', '.ini', '.cfg', '.conf', '.log',
             '.yaml', '.yml', '.toml', '.xml', '.csv', '.c', '.cpp',
             '.h', '.java', '.rs', '.go', '.rb', '.php', '.sql'}
DUAL_EXTS = {'.html', '.htm', '.shtml', '.xhtml', '.xhtm', '.xht', '.svg'}

def can_open(name):
    mime, _ = mimetypes.guess_type(name)
    ext = os.path.splitext(name)[1].lower()
    if ext in DUAL_EXTS:
        return True
    if mime:
        for prefix in OPEN_MIME:
            if mime.startswith(prefix):
                return True
    return False

def can_show(name):
    return os.path.splitext(name)[1].lower() in SHOW_EXTS or os.path.splitext(name)[1].lower() in DUAL_EXTS

def file_action(name):
    if can_open(name):
        return 'open'
    if can_show(name):
        return 'show'
    return 'dl'

# ── helpers ───────────────────────────────────────────────────────────────────

def safe_path(rel):
    target = os.path.realpath(os.path.join(HOME, rel))
    if not target.startswith(os.path.realpath(HOME)):
        abort(400)
    return target

def fmt_bytes(n):
    if n >= 1 << 30: return f'{n/(1<<30):.2f} GB'
    if n >= 1 << 20: return f'{n/(1<<20):.1f} MB'
    if n >= 1 << 10: return f'{n/(1<<10):.1f} KB'
    return f'{n} B'

def fmt_date(ts):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))

def fmt_items(n):
    return f'{n} item' if n == 1 else f'{n} items'

def dir_stats(abs_dir):
    total = 0
    count = 0
    for dp, dnames, fnames in os.walk(abs_dir):
        count += len(dnames) + len(fnames)
        for f in fnames:
            try: total += os.path.getsize(os.path.join(dp, f))
            except OSError: pass
    return total, count

def dir_entries(abs_dir, sort_by='type', sort_dir='asc'):
    entries = []
    for name in os.listdir(abs_dir):
        full = os.path.join(abs_dir, name)
        try:
            stat = os.stat(full)
        except OSError:
            continue
        is_dir = os.path.isdir(full)
        size = stat.st_size
        size_fmt = fmt_bytes(size)
        item_count = None
        item_count_fmt = ''
        if is_dir:
            size, item_count = dir_stats(full)
            item_count_fmt = fmt_items(item_count)
            size_fmt = item_count_fmt
        entries.append({
            'name':     name,
            'is_dir':   is_dir,
            'size':     size,
            'size_fmt': size_fmt,
            'item_count': item_count,
            'item_count_fmt': item_count_fmt,
            'mtime':    stat.st_mtime,
            'date_fmt': fmt_date(stat.st_mtime),
            'action':   'dir' if is_dir else file_action(name),
            'can_open': False if is_dir else can_open(name),
            'can_show': False if is_dir else can_show(name),
        })
    rev = (sort_dir == 'desc')
    if sort_by == 'name':
        entries.sort(key=lambda e: e['name'].lower(), reverse=rev)
    elif sort_by == 'size':
        entries.sort(key=lambda e: e['size'], reverse=rev)
    elif sort_by == 'date':
        entries.sort(key=lambda e: e['mtime'], reverse=rev)
    else:  # type
        if rev:
            entries.sort(key=lambda e: (e['is_dir'], e['name'].lower()))
        else:
            entries.sort(key=lambda e: (not e['is_dir'], e['name'].lower()))
    return entries

def dir_size(abs_dir):
    total, _ = dir_stats(abs_dir)
    return total

def search_files(query, rel_base, recursive):
    q = query.lower()
    results = []
    abs_base = safe_path(rel_base)
    if recursive:
        for dp, dirs, files in os.walk(abs_base):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in files:
                if q in name.lower():
                    full = os.path.join(dp, name)
                    rel  = os.path.relpath(full, HOME)
                    try:
                        stat = os.stat(full)
                        results.append({'name': name, 'rel': rel,
                                        'size_fmt': fmt_bytes(stat.st_size),
                                        'date_fmt': fmt_date(stat.st_mtime),
                                        'action': file_action(name),
                                        'can_open': can_open(name),
                                        'can_show': can_show(name)})
                    except OSError:
                        pass
    else:
        for name in os.listdir(abs_base):
            if q in name.lower():
                full = os.path.join(abs_base, name)
                if os.path.isfile(full):
                    try:
                        stat = os.stat(full)
                        rel  = os.path.relpath(full, HOME)
                        results.append({'name': name, 'rel': rel,
                                        'size_fmt': fmt_bytes(stat.st_size),
                                        'date_fmt': fmt_date(stat.st_mtime),
                                        'action': file_action(name),
                                        'can_open': can_open(name),
                                        'can_show': can_show(name)})
                    except OSError:
                        pass
    results.sort(key=lambda r: r['name'].lower())
    return results


# ── templates ─────────────────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>drivey / {{ breadcrumb_str }}</title>
<style>
* { -webkit-box-sizing: border-box; box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0a0a0f; color: #c8d8c8; font-family: monospace; font-size: 14px; padding: 20px 10px 60px; }
a { color: inherit; text-decoration: none; }
.header { max-width: 640px; margin: 0 auto 6px; }
h1 { font-size: 1.6rem; color: #00ff88; }
h1 span { color: #ff6b35; }
.sub { font-size: 11px; color: #4a5a4a; letter-spacing: 3px; text-transform: uppercase; max-width: 640px; margin: 0 auto 18px; }
.breadcrumb { max-width: 640px; margin: 0 auto 10px; font-size: 12px; color: #4a5a4a; text-transform: uppercase; letter-spacing: 1px; }
.breadcrumb a { color: #00ff88; }
.breadcrumb span { color: #4a5a4a; margin: 0 4px; }
.storageline { max-width: 640px; margin: 0 auto 14px; display: -webkit-box; display: -webkit-flex; display: flex; -webkit-box-pack: justify; -webkit-justify-content: space-between; justify-content: space-between; font-size: 11px; color: #4a5a4a; text-transform: uppercase; }
.card { background: #0f0f1a; border: 1px solid #1a1a2e; max-width: 640px; margin: 0 auto 12px; padding: 14px; }
.clbl { font-size: 11px; color: #4a5a4a; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; }
.search-row { display: -webkit-box; display: -webkit-flex; display: flex; }
.search-row input[type=text] { -webkit-box-flex: 1; -webkit-flex: 1; flex: 1; background: #0a0a0f; border: 1px solid #1a1a2e; border-right: none; color: #c8d8c8; font-family: monospace; font-size: 13px; padding: 7px 10px; outline: none; }
.search-row input[type=text]:focus { border-color: #00ff88; }
.rec-wrap { margin-top: 8px; font-size: 11px; color: #4a5a4a; text-transform: uppercase; }
.rec-wrap input { margin-right: 5px; }
.sortbar { max-width: 640px; width: 100%; margin: 0 auto; display: table; table-layout: fixed; border: 1px solid #1a1a2e; border-bottom: none; }
.sbtn { display: table-cell; width: 25%; background: transparent; border: none; border-right: 1px solid #1a1a2e; color: #4a5a4a; font-family: monospace; font-size: 11px; padding: 6px 4px; cursor: pointer; text-transform: uppercase; text-align: center; }
.sbtn:last-child { border-right: none; }
.sbtn.on { color: #00ff88; }
.upload-row { display: -webkit-box; display: -webkit-flex; display: flex; -webkit-box-align: center; -webkit-align-items: center; align-items: center; }
input[type=file] { -webkit-box-flex: 1; -webkit-flex: 1; flex: 1; background: #0a0a0f; border: 1px solid #1a1a2e; color: #c8d8c8; font-family: monospace; font-size: 12px; padding: 7px 8px; }
.upload-row .btn { margin-left: 8px; }
.mkdir-row { display: -webkit-box; display: -webkit-flex; display: flex; margin-top: 10px; }
input[type=text] { -webkit-box-flex: 1; -webkit-flex: 1; flex: 1; background: #0a0a0f; border: 1px solid #1a1a2e; border-right: none; color: #c8d8c8; font-family: monospace; font-size: 13px; padding: 7px 10px; outline: none; }
input[type=text]:focus { border-color: #00ff88; }
.btn { background: transparent; border: 1px solid #00ff88; color: #00ff88; font-family: monospace; font-size: 12px; padding: 7px 14px; cursor: pointer; text-transform: uppercase; white-space: nowrap; }
.shdr { max-width: 640px; margin: 0 auto; font-size: 11px; color: #4a5a4a; letter-spacing: 3px; text-transform: uppercase; border-bottom: 1px solid #1a1a2e; padding-bottom: 5px; }
.row { background: #0f0f1a; border: 1px solid #1a1a2e; border-top: none; max-width: 640px; width: 100%; margin: 0 auto; padding: 0; display: table; table-layout: fixed; }
.row:first-child { border-top: 1px solid #1a1a2e; }
.icon { display: table-cell; vertical-align: middle; font-size: 14px; width: 24px; padding: 9px 0 9px 8px; }
.fname { display: table-cell; vertical-align: middle; font-size: 13px; word-break: break-all; padding: 9px 6px; }
.fname a:hover { color: #00ff88; }
.fpath { font-size: 10px; color: #4a5a4a; display: block; margin-top: 2px; }
.fdate { display: table-cell; vertical-align: middle; font-size: 10px; color: #4a5a4a; width: 92px; padding: 9px 4px; text-align: right; }
.fsize { display: table-cell; vertical-align: middle; font-size: 11px; color: #4a5a4a; width: 74px; padding: 9px 4px; text-align: right; }
.itemcount { display: block; font-size: 10px; color: #4a5a4a; margin-top: 2px; }
.acts { display: table-cell; vertical-align: middle; width: 88px; padding: 6px 8px 6px 4px; text-align: right; }
.acts a, .acts button { display: inline-block; font-size: 11px; color: #00ff88; border: 1px solid #1a1a2e; padding: 3px 5px; margin: 1px 0 1px 2px; background: transparent; font-family: monospace; cursor: pointer; text-transform: uppercase; white-space: nowrap; }
.acts a.show { color: #ffe066; }
.acts button.del { color: #ff6b35; }
.empty { max-width: 640px; margin: 0 auto; background: #0f0f1a; border: 1px solid #1a1a2e; padding: 20px; text-align: center; font-size: 12px; color: #4a5a4a; }
.flash { max-width: 640px; margin: 0 auto 12px; padding: 8px 12px; font-size: 12px; border: 1px solid; }
.flash.ok  { border-color: #00ff88; color: #00ff88; }
.flash.err { border-color: #ff6b35; color: #ff6b35; }
#prog { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #0f0f1a; border-top: 1px solid #1a1a2e; padding: 10px 20px; font-size: 12px; color: #00ff88; text-transform: uppercase; }
#pbar { height: 3px; background: #1a1a2e; margin-top: 6px; }
#pfill { height: 100%; width: 0; background: #00ff88; }
</style>
</head>
<body>
<div class="header"><h1>DRIVE<span>Y</span></h1></div>
<div class="sub">personal file drive</div>

{% if msg %}<div class="flash {{ 'ok' if msg_ok else 'err' }}">{{ msg }}</div>{% endif %}

<div class="breadcrumb">
  <a href="/">~</a>
  {% for crumb in crumbs %}<span>/</span><a href="/browse/{{ crumb.path }}">{{ crumb.name }}</a>{% endfor %}
</div>
<div class="storageline"><span>{{ entry_count }} items</span><span>{{ total_size }}</span></div>

<div class="card">
  <div class="clbl">search</div>
  <form method="GET" action="/search" id="sform">
    <input type="hidden" name="base" value="{{ rel_path }}">
    <div class="search-row">
      <input type="text" name="q" id="sq" placeholder="filename..." value="{{ search_q }}" autocomplete="off">
      <button class="btn" type="submit">FIND</button>
    </div>
    <div class="rec-wrap">
      <input type="checkbox" name="r" id="rec" value="1" {{ 'checked' if search_recursive }}>
      <label for="rec">recursive</label>
    </div>
  </form>
</div>

{% if search_results is not none %}
<div class="shdr">results for "{{ search_q }}"{% if search_recursive %} (recursive){% endif %}</div>
{% if search_results %}
  {% for r in search_results %}
  <div class="row">
    <span class="icon">&#128196;</span>
    <span class="fname">
      <a href="/{{ r.action }}/{{ r.rel }}">{{ r.name }}</a>
      <span class="fpath">{{ r.rel }}</span>
    </span>
    <span class="fdate">{{ r.date_fmt }}</span>
    <span class="fsize">{{ r.size_fmt }}</span>
    <span class="acts">
      {% if r.can_open %}<a href="/open/{{ r.rel }}">OPEN</a>{% endif %}
      {% if r.can_show %}<a class="show" href="/show/{{ r.rel }}">SHOW</a>{% endif %}
      <a href="/dl/{{ r.rel }}">DL</a>
      <button class="del" onclick="delItem('{{ r.rel | urlencode }}', this)">X</button>
    </span>
  </div>
  {% endfor %}
{% else %}
  <div class="empty">no results</div>
{% endif %}

{% else %}
<div class="sortbar">
  {% for key, label in [('type','TYPE'),('name','NAME'),('size','SIZE'),('date','DATE')] %}
  <button class="sbtn {% if sort_by == key %}on{% endif %}" onclick="setSort('{{ key }}')">{{ label }}{% if sort_by == key %} {{ 'v' if sort_dir == 'desc' else '^' }}{% endif %}</button>
  {% endfor %}
</div>
<div class="shdr">name / date / size</div>

{% if rel_path %}
<div class="row">
  <span class="icon">&#128193;</span>
  <span class="fname"><a href="/browse/{{ parent_path }}">..</a></span>
  <span class="fdate">---</span>
  <span class="fsize">---</span>
  <span class="acts"></span>
</div>
{% endif %}

{% if entries %}
  {% for e in entries %}
  {% set fpath = (rel_path + '/' + e.name).strip('/') %}
  <div class="row">
    <span class="icon">{% if e.is_dir %}&#128193;{% else %}&#128196;{% endif %}</span>
    <span class="fname">
      {% if e.is_dir %}
        <a href="/browse/{{ fpath }}?sort={{ sort_by }}&dir={{ sort_dir }}">{{ e.name }}/</a>
      {% elif e.action == 'open' %}
        <a href="/open/{{ fpath }}">{{ e.name }}</a>
      {% elif e.action == 'show' %}
        <a href="/show/{{ fpath }}">{{ e.name }}</a>
      {% else %}
        <a href="/dl/{{ fpath }}">{{ e.name }}</a>
      {% endif %}
    </span>
    <span class="fdate">{{ e.date_fmt }}</span>
    <span class="fsize">
      {{ e.size_fmt }}
    </span>
    <span class="acts">
      {% if not e.is_dir %}
        {% if e.can_open %}<a href="/open/{{ fpath }}">OPEN</a>{% endif %}
        {% if e.can_show %}<a class="show" href="/show/{{ fpath }}">SHOW</a>{% endif %}
        <a href="/dl/{{ fpath }}">DL</a>
      {% endif %}
      <button class="del" onclick="delItem('{{ fpath | urlencode }}', this)">X</button>
    </span>
  </div>
  {% endfor %}
{% else %}
  <div class="empty">folder is empty</div>
{% endif %}
{% endif %}

<div class="card" style="margin-top:18px;">
  <div class="clbl">upload to current folder</div>
  <form method="POST" action="/upload/{{ rel_path }}" enctype="multipart/form-data" id="upform">
    <div class="upload-row">
      <input type="file" name="file" multiple id="fileinput">
      <button class="btn" type="submit">UPLOAD</button>
    </div>
  </form>
  <form method="POST" action="/mkdir/{{ rel_path }}" id="mkform" style="margin-top:10px;">
    <div class="mkdir-row">
      <input type="text" name="dirname" placeholder="new folder name" id="dname" autocomplete="off">
      <button class="btn" type="submit">MKDIR</button>
    </div>
  </form>
</div>

<div id="prog"><span id="pstat">uploading...</span><div id="pbar"><div id="pfill"></div></div></div>

<script>
function setSort(key) {
  var cur = '{{ sort_by }}', dir = '{{ sort_dir }}';
  var nd = (key === cur && dir === 'asc') ? 'desc' : 'asc';
  window.location = '/browse/{{ rel_path }}?sort=' + key + '&dir=' + nd;
}
document.getElementById('upform').onsubmit = function() {
  var f = document.getElementById('fileinput');
  if (!f || !f.value) { return false; }
  var p = document.getElementById('prog');
  if (p) { p.style.display = 'block'; }
  return true;
};
var pendingDel = '', pendingTimer = null;
function delItem(path, btn) {
  if (pendingDel !== path) {
    pendingDel = path; btn.innerHTML = 'sure?';
    if (pendingTimer) { clearTimeout(pendingTimer); }
    pendingTimer = setTimeout(function() { pendingDel = ''; window.location.reload(); }, 3000);
    return;
  }
  if (typeof XMLHttpRequest !== 'undefined') {
    var x = new XMLHttpRequest();
    x.onload = function() { window.location.reload(); };
    x.open('POST', '/delete/' + path); x.send();
  } else { window.location = '/delete/' + path; }
}
var dn = document.getElementById('dname');
if (dn) { dn.onkeydown = function(e) { if ((e||window.event).keyCode===13) document.getElementById('mkform').submit(); }; }
var sq = document.getElementById('sq');
if (sq) { sq.onkeydown = function(e) { if ((e||window.event).keyCode===13) document.getElementById('sform').submit(); }; }
</script>
</body>
</html>
"""

SHOW_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ name }}</title>
<style>
* { -webkit-box-sizing: border-box; box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0a0a0f; color: #c8d8c8; font-family: monospace; font-size: 14px; padding: 20px 10px 60px; }
a { color: #00ff88; text-decoration: none; }
h1 { font-size: 1.6rem; color: #00ff88; margin-bottom: 16px; }
h1 span { color: #ff6b35; }
.viewer { max-width: 640px; margin: 0 auto; background: #0f0f1a; border: 1px solid #1a1a2e; padding: 14px; }
.viewer-hdr { display: -webkit-box; display: -webkit-flex; display: flex; -webkit-box-pack: justify; -webkit-justify-content: space-between; justify-content: space-between; margin-bottom: 10px; font-size: 11px; color: #4a5a4a; text-transform: uppercase; }
pre { font-size: 12px; white-space: pre-wrap; word-break: break-all; color: #c8d8c8; line-height: 1.5; }
</style>
</head>
<body>
<h1>DRIVE<span>Y</span></h1>
<div class="viewer">
  <div class="viewer-hdr">
    <span>{{ name }}</span>
    <span><a href="/dl/{{ rel }}">DL</a> &nbsp; <a href="/browse/{{ parent }}">BACK</a></span>
  </div>
  <pre>{{ content }}</pre>
</div>
</body>
</html>
"""


# ── routes ────────────────────────────────────────────────────────────────────

def render_dir(rel, msg=None, msg_ok=True, sort_by='type', sort_dir='asc',
               search_q='', search_results=None, search_recursive=False):
    abs_dir = safe_path(rel)
    if not os.path.isdir(abs_dir):
        abort(404)
    entries = dir_entries(abs_dir, sort_by, sort_dir)
    total   = dir_size(abs_dir)
    parts   = [p for p in rel.split('/') if p]
    crumbs  = [{'name': p, 'path': '/'.join(parts[:i+1])} for i, p in enumerate(parts)]
    return render_template_string(
        TEMPLATE,
        rel_path=rel,
        entries=entries,
        crumbs=crumbs,
        parent_path='/'.join(parts[:-1]),
        breadcrumb_str='/' + rel if rel else '~',
        entry_count=len(entries),
        total_size=fmt_bytes(total),
        msg=msg, msg_ok=msg_ok,
        sort_by=sort_by, sort_dir=sort_dir,
        search_q=search_q,
        search_results=search_results,
        search_recursive=search_recursive,
    )

@app.route('/')
@login_required
def index():
    return redirect(url_for('browse', rel=''))

@app.route('/browse/', defaults={'rel': ''})
@app.route('/browse/<path:rel>')
@login_required
def browse(rel):
    sort_by  = request.args.get('sort', 'type')
    sort_dir = request.args.get('dir',  'asc')
    if sort_by  not in ('type','name','size','date'): sort_by  = 'type'
    if sort_dir not in ('asc','desc'):                sort_dir = 'asc'
    return render_dir(rel, sort_by=sort_by, sort_dir=sort_dir)

@app.route('/search')
@login_required
def search():
    q         = request.args.get('q', '').strip()
    base      = request.args.get('base', '')
    recursive = bool(request.args.get('r'))
    if not q:
        return redirect(url_for('browse', rel=base))
    results = search_files(q, base, recursive)
    return render_dir(base, search_q=q, search_results=results,
                      search_recursive=recursive)

@app.route('/upload/', defaults={'rel': ''}, methods=['GET', 'POST'])
@app.route('/upload/<path:rel>', methods=['GET', 'POST'])
@login_required
def upload(rel):
    if request.method == 'GET':
        return redirect(url_for('browse', rel=rel))
    abs_dir = safe_path(rel)
    os.makedirs(abs_dir, exist_ok=True)
    files = request.files.getlist('file')
    if not files or all(f.filename == '' for f in files):
        return render_dir(rel, 'no file selected', False)
    saved = []
    for f in files:
        if f.filename:
            name = secure_filename(f.filename)
            if name:
                f.save(os.path.join(abs_dir, name))
                saved.append(name)
    msg = f'uploaded: {", ".join(saved)}' if saved else 'nothing uploaded'
    return render_dir(rel, msg, bool(saved))

@app.route('/mkdir/', defaults={'rel': ''}, methods=['GET', 'POST'])
@app.route('/mkdir/<path:rel>', methods=['GET', 'POST'])
@login_required
def mkdir(rel):
    if request.method == 'GET':
        return redirect(url_for('browse', rel=rel))
    dirname = request.form.get('dirname', '').strip()
    if not dirname:
        return render_dir(rel, 'folder name required', False)
    name   = secure_filename(dirname)
    target = safe_path(os.path.join(rel, name))
    os.makedirs(target, exist_ok=True)
    return render_dir(rel, f'created: {name}')

@app.route('/dl/<path:rel>')
@login_required
def download(rel):
    abs_path = safe_path(rel)
    if not os.path.isfile(abs_path): abort(404)
    return send_file(abs_path, as_attachment=True,
                     download_name=os.path.basename(abs_path))

@app.route('/open/<path:rel>')
@login_required
def open_file(rel):
    abs_path = safe_path(rel)
    if not os.path.isfile(abs_path): abort(404)
    mime, _ = mimetypes.guess_type(abs_path)
    return send_file(abs_path, mimetype=mime or 'application/octet-stream')

@app.route('/show/<path:rel>')
@login_required
def show_file(rel):
    abs_path = safe_path(rel)
    if not os.path.isfile(abs_path): abort(404)
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read(512 * 1024)  # cap at 512 KB
    except Exception:
        abort(500)
    parts  = [p for p in rel.split('/') if p]
    parent = '/'.join(parts[:-1])
    return render_template_string(
        SHOW_TEMPLATE,
        name=os.path.basename(abs_path),
        rel=rel, parent=parent,
        content=content,
    )

@app.route('/delete/<path:rel>', methods=['GET', 'POST'])
@login_required
def delete(rel):
    abs_path = safe_path(rel)
    if os.path.isdir(abs_path):
        shutil.rmtree(abs_path)
    elif os.path.isfile(abs_path):
        os.remove(abs_path)
    else:
        abort(404)
    parent = '/'.join([p for p in rel.split('/') if p][:-1])
    return redirect(url_for('browse', rel=parent))

# ── auth routes ──────────────────────────────────────────────────────────────

app.add_url_rule('/login',  'login',  login_route,  methods=['GET', 'POST'])
app.add_url_rule('/logout', 'logout', logout_route, methods=['GET', 'POST'])

# ── run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=5050)
    args = parser.parse_args()
    print(f'[drivey] serving ~/files on http://{args.host}:{args.port}')
    app.run(host=args.host, port=args.port, debug=False)
