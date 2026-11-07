#!/usr/bin/env python3
"""aih: one searchable archive of your AI conversations.

Every conversation (claude.ai, Claude Code, ChatGPT), kept exactly as it was said. Nothing is
corrected or summarised: the archive is evidence, not truth.

  aih build               re-import every source and rebuild archive.db + chats/
  aih collect             pull Claude Code transcripts from every machine, import the inbox, rebuild
  aih search "words"      full-text search (add --me, --claude, --source, --since, -n)
  aih show <id-prefix>    print the path of a chat's Markdown file
  aih stats               counts per source, gaps, flags
  aih check               is every chat in the newest website export also in the archive?

Layout (relative to this file):
  sources/claude-web/     official export folders + files/ (original uploads)
  sources/claude-code/    copies of ~/.claude/projects, one folder per machine
  sources/chatgpt/        ChatGPT export .zip files (or unzipped folders), one folder per account
  archive.db              SQLite: conversations, messages, parts, files, FTS index
  chats/<source>/<year>/  one Markdown file per conversation
  aih.config.json         optional: machines, hub, inbox, display name (see aih.config.example.json)
"""
import argparse, base64, collections, datetime as dt, glob, hashlib, json, mimetypes, os, re, shutil, sqlite3, sys, zipfile

ROOT = os.path.dirname(os.path.realpath(__file__))
SRC = os.path.join(ROOT, 'sources')
DB = os.path.join(ROOT, 'archive.db')
CHATS = os.path.join(ROOT, 'chats')
CLAUDE_ROOT_PARENT = '00000000-0000-4000-8000-000000000000'
CONFIG_PATH = os.path.expanduser(os.environ.get('AIH_CONFIG', os.path.join(ROOT, 'aih.config.json')))


def load_config():
    """Optional JSON config. Every key has a default, so aih runs without one."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


CONFIG = load_config()
USER_NAME = CONFIG.get('user_name', 'You')  # heading for your own messages in the Markdown copies

# ---------------------------------------------------------------- normalised model
# conversation: dict(id, source, title, created, updated, model, url, flags{}, messages[])
# message: dict(id, parent, role, created, parts[], files[], raw)
# part: dict(kind, text, meta{})   kind in text|thinking|tool_use|tool_result|attachment|image|system
# file: dict(id, name, path(rel to ROOT) or None, kind)


def iso(t):
    if t is None or t == '':
        return None
    if isinstance(t, (int, float)):
        return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat().replace('+00:00', 'Z')
    return str(t)


def slug(s, n=60):
    s = re.sub(r'[\\/:*?"<>|\n\r\t]+', ' ', s or '').strip()
    s = re.sub(r'\s+', ' ', s)
    return (s[:n].rstrip(' .') or 'untitled')


def fence(body, lang=''):
    body = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2)
    ticks = max([3] + [len(m) + 1 for m in re.findall(r'`{3,}', body)])
    return f"{'`' * ticks}{lang}\n{body.rstrip()}\n{'`' * ticks}"


def as_text(v):
    """Flatten tool inputs / results of any shape into searchable text."""
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return '\n'.join(as_text(x) for x in v)
    if isinstance(v, dict):
        if v.get('type') == 'text' and 'text' in v:
            return v['text'] or ''
        if v.get('type') == 'image':
            return '[image]'
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def main_path(msgs, leaf=None):
    """Return the ids on the conversation's main line: walk back from the chosen leaf."""
    by = {m['id']: m for m in msgs}
    kids = collections.defaultdict(list)
    for m in msgs:
        kids[m['parent']].append(m)
    if leaf not in by:
        leaves = [m for m in msgs if not kids.get(m['id'])]
        leaf = max(leaves, key=lambda m: (m['created'] or '', m.get('index', 0)))['id'] if leaves else None
    path, cur, seen = [], leaf, set()
    while cur in by and cur not in seen:
        seen.add(cur); path.append(cur); cur = by[cur]['parent']
    return list(reversed(path))


# ---------------------------------------------------------------- importer: claude.ai
def load_claude_web():
    base = os.path.join(SRC, 'claude-web')
    exports = sorted(glob.glob(os.path.join(base, 'official-export-*', 'conversations', 'conversations.json')))
    files_dir = os.path.join(base, 'files')
    file_map = {}
    for p in glob.glob(os.path.join(files_dir, '*')):
        file_map[os.path.basename(p).split('.')[0]] = os.path.relpath(p, ROOT)
    live = {}
    lp = os.path.join(base, 'live-metadata.json')
    if os.path.exists(lp):
        for c in json.load(open(lp)):
            live[c['uuid']] = c
    fidx = {}
    for p in glob.glob(os.path.join(base, 'files-index-*.json')):
        fidx.update(json.load(open(p)).get('index', {}))
    convs = {}
    for ep in exports:  # later exports win, but keep conversations only seen earlier
        for c in json.load(open(ep)):
            convs[c['uuid']] = c
    # Chats deleted on claude.ai come back in exports as empty shells (IDs, timestamps, sometimes leftover
    # pastes and files). They were deleted on purpose, so they are never imported and their IDs are remembered.
    deny_path = os.path.join(base, 'deleted-chat-ids.txt')
    deny = {l.strip() for l in open(deny_path) if l.strip() and not l.startswith('#')} if os.path.exists(deny_path) else set()
    new_dead = [u for u, c in convs.items() if u not in deny and c.get('chat_messages')
                and all(not m.get('text') and not m.get('content') for m in c['chat_messages'])]
    if new_dead:
        with open(deny_path, 'a') as f:
            f.write(''.join(u + '\n' for u in new_dead))
        deny.update(new_dead)
    for c in convs.values():
        if c['uuid'] in deny:
            continue
        lv = live.get(c['uuid'], {})
        msgs = []
        for i, m in enumerate(c.get('chat_messages') or []):
            parts, files = [], []
            for b in m.get('content') or []:
                t = b.get('type')
                if t == 'text':
                    parts.append({'kind': 'text', 'text': b.get('text') or ''})
                elif t == 'thinking':
                    parts.append({'kind': 'thinking', 'text': b.get('thinking') or '',
                                  'meta': {'truncated': b.get('truncated') or b.get('cut_off')}})
                elif t == 'tool_use':
                    parts.append({'kind': 'tool_use', 'text': as_text(b.get('input')),
                                  'meta': {'name': b.get('name'), 'input': b.get('input'), 'message': b.get('message'), 'id': b.get('id')}})
                elif t == 'tool_result':
                    parts.append({'kind': 'tool_result', 'text': as_text(b.get('content')),
                                  'meta': {'name': b.get('name'), 'is_error': bool(b.get('is_error')), 'id': b.get('tool_use_id')}})
                elif t in ('image', 'document'):
                    fu = b.get('file_uuid')
                    if fu:
                        files.append({'id': fu, 'name': b.get('title') or fidx.get(fu, {}).get('name') or fu, 'kind': t})
                elif t == 'injected_prompt_block':
                    parts.append({'kind': 'system', 'text': b.get('prompt') or '', 'meta': {'source': b.get('injection_source')}})
            for a in m.get('attachments') or []:
                parts.append({'kind': 'attachment', 'text': a.get('extracted_content') or '',
                              'meta': {'name': a.get('file_name') or f"pasted.{a.get('file_type') or 'txt'}", 'size': a.get('file_size')}})
            for f in m.get('files') or []:
                if f['file_uuid'] not in {x['id'] for x in files}:
                    files.append({'id': f['file_uuid'], 'name': f.get('file_name') or f['file_uuid'], 'kind': 'file'})
            if not parts and m.get('text'):
                parts.append({'kind': 'text', 'text': m['text']})
            for f in files:
                f['path'] = file_map.get(f['id'])
            msgs.append({'id': m['uuid'], 'parent': m.get('parent_message_uuid') or CLAUDE_ROOT_PARENT,
                         'role': 'user' if m['sender'] == 'human' else 'assistant', 'created': m.get('created_at'),
                         'index': i, 'parts': parts, 'files': files})
        flags = {}
        if live and c['uuid'] not in live:
            flags['deleted_or_hidden'] = True  # in Anthropic's export, gone from the live account
        yield {'id': c['uuid'], 'source': 'claude-web', 'title': c.get('name') or '',
               'created': c.get('created_at'), 'updated': c.get('updated_at'),
               'model': lv.get('model'), 'url': f"https://claude.ai/chat/{c['uuid']}",
               'leaf': lv.get('current_leaf_message_uuid'), 'flags': flags,
               'extra': {k: lv.get(k) for k in ('is_starred', 'platform', 'project_uuid', 'summary') if lv.get(k)},
               'messages': msgs}


# ---------------------------------------------------------------- importer: Claude Code
# Things Claude Code writes into the "user" side that the user never typed.
NOISE = re.compile(r'\s*(<(system-reminder|task-notification|command-name|command-message|command-args|local-command-stdout|'
                   r'local-command-stderr|local-command-caveat|bash-input|bash-stdout|bash-stderr|user-prompt-submit-hook|'
                   r'ide_opened_file|ide_selection|teammate-message)[ >]|\[Request interrupted|Caveat: |'
                   r'This session is being continued|\[SYSTEM)')


def cc_units():
    base = os.path.join(SRC, 'claude-code')
    for machine in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        mdir = os.path.join(base, machine)
        if machine.startswith('_') or not os.path.isdir(mdir):
            continue
        for path in sorted(glob.glob(os.path.join(mdir, '**', '*.jsonl'), recursive=True)):
            if 'aih-mining' in path:
                continue  # the miner's own prompts are not conversations
            yield 'cc:' + os.path.relpath(path, base), file_fp(path), (lambda m=machine, d=mdir, p=path: [c for c in [cc_file(m, d, p)] if c])


def cc_file(machine, mdir, path):
    media = os.path.join(SRC, 'claude-code', '_media')
    sid = os.path.splitext(os.path.basename(path))[0]
    project = os.path.relpath(os.path.dirname(path), mdir)
    sidechain = '/subagents/' in path or os.path.basename(os.path.dirname(path)) == 'subagents'
    msgs, title, cwd, model, first_user = [], None, None, None, None
    last_prompt = None
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return None
    for ln in lines:
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        t = o.get('type')
        if t == 'custom-title':
            title = o.get('customTitle') or title
        elif t == 'summary' and not title:
            title = o.get('summary')
        elif t == 'last-prompt':
            last_prompt = o.get('lastPrompt')
        if t not in ('user', 'assistant') or not isinstance(o.get('message'), dict):
            continue
        cwd = cwd or o.get('cwd')
        m = o['message']
        model = model or m.get('model')
        content = m.get('content')
        parts, files = [], []
        if isinstance(content, str):
            content = [{'type': 'text', 'text': content}]
        for b in content or []:
            bt = b.get('type')
            if bt == 'text':
                parts.append({'kind': 'text', 'text': b.get('text') or ''})
            elif bt == 'thinking':
                parts.append({'kind': 'thinking', 'text': b.get('thinking') or ''})
            elif bt == 'tool_use':
                parts.append({'kind': 'tool_use', 'text': as_text(b.get('input')),
                              'meta': {'name': b.get('name'), 'input': b.get('input'), 'id': b.get('id')}})
            elif bt == 'tool_result':
                c2 = b.get('content')
                for sub in c2 if isinstance(c2, list) else []:
                    if isinstance(sub, dict) and sub.get('type') == 'image':
                        files.append(save_b64(media, sub))
                parts.append({'kind': 'tool_result', 'text': as_text(c2),
                              'meta': {'is_error': bool(b.get('is_error')), 'id': b.get('tool_use_id')}})
            elif bt == 'image':
                files.append(save_b64(media, b))
        files = [f for f in files if f]
        role = m.get('role') or t
        if role == 'user':
            for p in parts:
                if p['kind'] == 'text' and (o.get('isMeta') or NOISE.match(p['text'])):
                    p['kind'] = 'system'
        is_tool_return = role == 'user' and parts and all(p['kind'] == 'tool_result' for p in parts)
        if role == 'user' and not is_tool_return and not o.get('isMeta') and first_user is None:
            txt = ' '.join(p['text'] for p in parts if p['kind'] == 'text').strip()
            if txt and not NOISE.match(txt):
                first_user = txt
        msgs.append({'id': o.get('uuid') or hashlib.sha1(ln.encode()).hexdigest(),
                     'parent': o.get('parentUuid') or CLAUDE_ROOT_PARENT,
                     'role': 'tool' if is_tool_return else ('meta' if o.get('isMeta') else role),
                     'created': o.get('timestamp'), 'index': len(msgs), 'parts': parts, 'files': files})
    if not msgs:
        return None
    flags = {'subagent': True} if sidechain else {}
    return {'id': f'{machine}:{sid}', 'source': f'claude-code-{machine}',
           'title': title or (first_user or last_prompt or sid)[:90],
           'created': msgs[0]['created'], 'updated': msgs[-1]['created'], 'model': model,
           'url': None, 'leaf': None, 'flags': flags,
           'extra': {'project_dir': project, 'cwd': cwd, 'machine': machine}, 'messages': msgs,
           'linear': True}


def save_b64(media, block):
    src = block.get('source') or {}
    if src.get('type') != 'base64' or not src.get('data'):
        return None
    raw = base64.b64decode(src['data'])
    h = hashlib.sha1(raw).hexdigest()[:20]
    ext = mimetypes.guess_extension(src.get('media_type') or '') or '.bin'
    os.makedirs(media, exist_ok=True)
    p = os.path.join(media, h + ext)
    if not os.path.exists(p):
        open(p, 'wb').write(raw)
    return {'id': h, 'name': h + ext, 'kind': 'image', 'path': os.path.relpath(p, ROOT)}


# ---------------------------------------------------------------- importer: ChatGPT
def load_chatgpt(only=None):
    base = os.path.join(SRC, 'chatgpt')
    for z in glob.glob(os.path.join(base, '*.zip')):
        out = z[:-4]
        if not os.path.isdir(out):
            with zipfile.ZipFile(z) as zf:
                zf.extractall(out)
    for cj in [only] if only else sorted(glob.glob(os.path.join(base, '**', 'conversations*.json'), recursive=True)):
        folder = os.path.dirname(cj)
        account = os.path.relpath(cj, base).split(os.sep)[0]  # one top-level folder per ChatGPT account
        account = re.sub(r'[^a-z0-9]+', '-', account.lower()).strip('-')
        assets = {}
        for p in glob.glob(os.path.join(folder, '**', '*'), recursive=True):
            m = re.match(r'(file[-_][A-Za-z0-9]+)', os.path.basename(p))
            if m and os.path.isfile(p):
                assets[m.group(1)] = os.path.relpath(p, ROOT)
        data = json.load(open(cj))
        for c in data if isinstance(data, list) else []:
            mapping = c.get('mapping') or {}
            msgs = []
            for nid, node in mapping.items():
                m = node.get('message')
                if not m:
                    continue
                role = (m.get('author') or {}).get('role')
                ct = m.get('content') or {}
                parts, files = [], []
                kind = ct.get('content_type')
                for p in ct.get('parts') or []:
                    if isinstance(p, str):
                        if p:
                            parts.append({'kind': 'text' if role != 'tool' else 'tool_result', 'text': p})
                    elif isinstance(p, dict):
                        ptr = p.get('asset_pointer') or ''
                        fid = re.sub(r'^[a-z-]+://', '', ptr)
                        if fid:
                            key = re.match(r'(file[-_][A-Za-z0-9]+)', fid)
                            files.append({'id': fid, 'name': fid, 'kind': 'image',
                                          'path': assets.get(key.group(1)) if key else None})
                        elif p.get('text'):
                            parts.append({'kind': 'text', 'text': p['text']})
                if kind in ('code', 'execution_output') and ct.get('text'):
                    parts.append({'kind': 'tool_use' if kind == 'code' else 'tool_result', 'text': ct['text'],
                                  'meta': {'name': m.get('recipient') or kind}})
                if kind in ('thoughts',):
                    parts.append({'kind': 'thinking', 'text': as_text([t.get('content') for t in ct.get('thoughts') or []])})
                if kind == 'user_editable_context' or (role == 'system' and not parts and not files):
                    continue
                for a in (m.get('metadata') or {}).get('attachments') or []:
                    aid = a.get('id') or ''
                    same = [f for f in files if f['id'].replace('file_', 'file-') == aid.replace('file_', 'file-')]
                    if same:  # the image pointer and the attachment are one file: keep one entry, with its real name
                        same[0]['name'] = a.get('name') or same[0]['name']
                        continue
                    files.append({'id': aid, 'name': a.get('name') or aid, 'kind': 'file',
                                  'path': assets.get(aid.replace('file_', 'file-'), assets.get(aid))})
                if not parts and not files:
                    continue
                msgs.append({'id': nid, 'parent': node.get('parent') or CLAUDE_ROOT_PARENT,
                             'role': {'user': 'user', 'assistant': 'assistant', 'tool': 'tool'}.get(role, role),
                             'created': iso(m.get('create_time')), 'index': len(msgs), 'parts': parts, 'files': files})
            # re-parent across skipped nodes so the tree stays connected
            kept = {m['id'] for m in msgs}
            for m in msgs:
                p = m['parent']
                while p not in kept and p in mapping:
                    p = mapping[p].get('parent')
                m['parent'] = p if p in kept else CLAUDE_ROOT_PARENT
            cid = c.get('conversation_id') or c.get('id')
            yield {'id': cid, 'source': f'chatgpt-{account}', 'title': c.get('title') or '',
                   'created': iso(c.get('create_time')), 'updated': iso(c.get('update_time')),
                   'model': c.get('default_model_slug'), 'url': f'https://chatgpt.com/c/{cid}',
                   'leaf': c.get('current_node'), 'flags': {'archived': True} if c.get('is_archived') else {},
                   'extra': {}, 'messages': msgs}


# ---------------------------------------------------------------- render
ROLE_HEAD = {'user': USER_NAME, 'assistant': 'Assistant', 'tool': 'Tool output', 'meta': 'System'}


def render_msg(m, rel_root):
    if not m['files'] and all(p['kind'] == 'system' or not (p['text'] or '').strip() for p in m['parts']):
        return ''  # nothing the user or the assistant actually said (system noise stays searchable in the database)
    who = ROLE_HEAD.get(m['role'], m['role'])
    out = [f"### {who} · {(m['created'] or '')[:16].replace('T', ' ')}"]
    for p in m['parts']:
        k, meta = p['kind'], p.get('meta') or {}
        if k == 'text':
            out.append(p['text'])
        elif k == 'thinking' and p['text'].strip():
            out.append(f"<details><summary>Thinking</summary>\n\n{fence(p['text'])}\n</details>")
        elif k == 'tool_use':
            name = meta.get('name') or 'tool'
            inp = meta.get('input') if meta.get('input') is not None else p['text']
            body = ''
            if isinstance(inp, dict) and isinstance(inp.get('file_text'), str):
                ext = os.path.splitext(inp.get('path') or '')[1].lstrip('.')
                body = f"`{inp.get('path')}`\n\n" + fence(inp['file_text'], ext)
            elif isinstance(inp, dict) and isinstance(inp.get('command'), str) and len(inp) <= 3:
                body = fence(inp['command'], 'bash')
            else:
                body = fence(inp, 'json')
            label = f"Tool: {name}" + (f" — {meta['message']}" if meta.get('message') else '')
            out.append(f"<details><summary>{label}</summary>\n\n{body}\n</details>")
        elif k == 'tool_result':
            err = ' (error)' if meta.get('is_error') else ''
            out.append(f"<details><summary>↳ result{(' · ' + meta['name']) if meta.get('name') else ''}{err}</summary>\n\n{fence(p['text'])}\n</details>")
        elif k == 'attachment':
            out.append(f"<details><summary>Attachment: {meta.get('name')} ({meta.get('size') or '?'} bytes)</summary>\n\n{fence(p['text'])}\n</details>")
        # 'system' parts (memory injections) stay in the database only
    for f in m['files']:
        if f.get('path'):
            link = os.path.relpath(os.path.join(ROOT, f['path']), rel_root).replace(' ', '%20')
            is_img = re.search(r'\.(png|jpe?g|gif|webp|heic|bmp|svg)$', f['path'], re.I)
            out.append(f"{'!' if is_img else ''}[{f['name']}]({link})")
        else:
            out.append(f"*{f['name']}* (file not available)")
    return '\n\n'.join(out)


def render(conv, path_ids):
    by = {m['id']: m for m in conv['messages']}
    on = set(path_ids)
    rel_root = os.path.dirname(os.path.join(ROOT, conv['md_path']))
    fm = {'title': conv['title'] or '(untitled)', 'source': conv['source'], 'id': conv['id'],
          'created': conv['created'], 'updated': conv['updated'], 'model': conv['model'], 'url': conv['url'],
          'messages': len(conv['messages']), 'branches': conv['n_branches'],
          'flags': sorted(k for k, v in conv['flags'].items() if v)}
    fm.update({k: v for k, v in conv['extra'].items() if isinstance(v, (str, int, float, bool))})
    head = '---\n' + '\n'.join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items() if v not in (None, '', [])) + '\n---\n'
    body = [f"# {conv['title'] or '(untitled)'}"]
    if conv['flags'].get('deleted_or_hidden'):
        body.append('> Note: this chat is in Anthropic\'s export but no longer in your live account (deleted or hidden).')
    body += [x for x in (render_msg(by[i], rel_root) for i in path_ids) if x]
    off = [m for m in conv['messages'] if m['id'] not in on]
    if off:
        body.append('---\n\n## Other branches\n\n*Edited prompts and regenerated answers that are not on the main line above.*')
        kids = collections.defaultdict(list)
        for m in off:
            kids[m['parent']].append(m)
        starts = [m for m in off if m['parent'] not in {x['id'] for x in off}]
        for n, s in enumerate(sorted(starts, key=lambda m: m['created'] or ''), 1):
            par = by.get(s['parent'])
            ctx = ''
            if par:
                t = ' '.join(p['text'] for p in par['parts'] if p['kind'] == 'text')[:120].replace('\n', ' ')
                ctx = f" (after: “{t}…”)"
            body.append(f"### ↪ Branch {n}{ctx}")
            stack = [s]
            while stack:
                m = stack.pop(0)
                x = render_msg(m, rel_root)
                if x:
                    body.append(x)
                stack = sorted(kids.get(m['id'], []), key=lambda x: x['created'] or '') + stack
    return head + '\n' + '\n\n'.join(body) + '\n'


# ---------------------------------------------------------------- build
SCHEMA = '''
CREATE TABLE conversations(id TEXT PRIMARY KEY, source TEXT, title TEXT, created TEXT, updated TEXT, model TEXT,
  url TEXT, md_path TEXT, n_messages INT, n_branches INT, flags TEXT, extra TEXT, unit TEXT);
CREATE TABLE units(key TEXT PRIMARY KEY, fp TEXT);
CREATE TABLE owners(msg_id TEXT PRIMARY KEY, conv_id TEXT);
CREATE INDEX conv_unit ON conversations(unit); CREATE INDEX conv_md ON conversations(md_path);
CREATE TABLE messages(id TEXT, conv_id TEXT, parent_id TEXT, role TEXT, created TEXT, on_main INT, PRIMARY KEY(conv_id, id));
CREATE TABLE parts(rowid INTEGER PRIMARY KEY, conv_id TEXT, msg_id TEXT, seq INT, kind TEXT, role TEXT, created TEXT,
  text TEXT, meta TEXT);
CREATE TABLE files(conv_id TEXT, msg_id TEXT, file_id TEXT, name TEXT, kind TEXT, path TEXT);
CREATE VIEW parts_v AS SELECT p.rowid AS rowid, p.text AS text, c.title AS title FROM parts p JOIN conversations c ON c.id = p.conv_id;
CREATE VIRTUAL TABLE parts_fts USING fts5(text, title, content='parts_v', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');
CREATE INDEX parts_conv ON parts(conv_id); CREATE INDEX msg_conv ON messages(conv_id);
'''


def file_fp(path):
    st = os.stat(path)
    return f'{st.st_size}:{int(st.st_mtime)}'


def units():
    """Every independent piece of source data, with a fingerprint: only changed pieces are re-imported."""
    base = os.path.join(SRC, 'claude-web')
    inputs = sorted(glob.glob(os.path.join(base, 'official-export-*', 'conversations', 'conversations.json'))
                    + glob.glob(os.path.join(base, 'files-index-*.json'))
                    + [os.path.join(base, n) for n in ('live-metadata.json', 'deleted-chat-ids.txt') if os.path.exists(os.path.join(base, n))])
    if inputs:
        fdir = os.path.join(base, 'files')
        nfiles = len(os.listdir(fdir)) if os.path.isdir(fdir) else 0
        fp = hashlib.sha1(('|'.join(f'{p}:{file_fp(p)}' for p in inputs) + f'|files:{nfiles}').encode()).hexdigest()
        yield 'claude-web', fp, lambda: list(load_claude_web())
    yield from cc_units()
    gbase = os.path.join(SRC, 'chatgpt')
    for z in glob.glob(os.path.join(gbase, '**', '*.zip'), recursive=True):
        out = z[:-4]
        if not os.path.isdir(out):
            with zipfile.ZipFile(z) as zf:
                zf.extractall(out)
    for cj in sorted(glob.glob(os.path.join(gbase, '**', 'conversations*.json'), recursive=True)):
        yield 'gpt:' + os.path.relpath(cj, gbase), file_fp(cj), (lambda cj=cj: list(load_chatgpt(cj)))


def write_if_changed(path, text):
    try:
        if open(path, encoding='utf-8').read() == text:
            return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    open(tmp, 'w', encoding='utf-8').write(text)
    os.replace(tmp, path)
    return True


def open_db():
    fresh = not os.path.exists(DB)
    db = sqlite3.connect(DB)
    if not fresh and not db.execute("SELECT 1 FROM sqlite_master WHERE name='units'").fetchone():
        db.close(); os.remove(DB); fresh = True; db = sqlite3.connect(DB)  # old one-shot layout: start over
    if fresh:
        db.executescript(SCHEMA)
    return db


def drop_unit(db, key):
    """Remove everything a unit produced; returns the Markdown paths it owned."""
    ids = [r[0] for r in db.execute('SELECT id FROM conversations WHERE unit=?', (key,))]
    paths = set()
    for cid in ids:
        db.execute("INSERT INTO parts_fts(parts_fts, rowid, text, title) SELECT 'delete', v.rowid, v.text, v.title "
                   "FROM parts_v v JOIN parts p ON p.rowid = v.rowid WHERE p.conv_id=? AND p.kind != 'system'", (cid,))
        paths.update(r[0] for r in db.execute('SELECT md_path FROM conversations WHERE id=?', (cid,)))
        for t in ('parts', 'messages', 'files'):
            db.execute(f'DELETE FROM {t} WHERE conv_id=?', (cid,))
        db.execute('DELETE FROM owners WHERE conv_id=?', (cid,))
        db.execute('DELETE FROM conversations WHERE id=?', (cid,))
    db.execute('DELETE FROM units WHERE key=?', (key,))
    return paths


def insert_conv(db, conv, unit, stats):
    msgs = conv['messages']
    if conv['source'].startswith('claude-code'):
        # A resumed session re-copies earlier messages: keep each message once, in the session that had it first.
        kept, dup_of = [], collections.Counter()
        for m in msgs:
            r = db.execute('SELECT conv_id FROM owners WHERE msg_id=?', (m['id'],)).fetchone()
            if r and r[0] != conv['id']:
                dup_of[r[0]] += 1
            else:
                kept.append(m)
        if dup_of:
            conv['extra']['continues_from'] = dup_of.most_common(1)[0][0]
            conv['extra']['repeated_messages_skipped'] = sum(dup_of.values())
        msgs = conv['messages'] = kept
        if not msgs:
            stats['skipped: fully repeated session'] += 1
            return None
        ids = set()
        for m in msgs:
            if m['id'] in ids:
                continue
            ids.add(m['id'])
            db.execute('INSERT OR IGNORE INTO owners VALUES(?,?)', (m['id'], conv['id']))
    if db.execute('SELECT 1 FROM conversations WHERE id=?', (conv['id'],)).fetchone():
        conv['id'] += '#' + hashlib.sha1(unit.encode()).hexdigest()[:6]  # same session id seen twice
    path_ids = [m['id'] for m in msgs] if conv.get('linear') else main_path(msgs, conv.get('leaf'))
    kids = collections.Counter(m['parent'] for m in msgs)
    conv['n_branches'] = 0 if conv.get('linear') else sum(v - 1 for v in kids.values() if v > 1)
    if any((p.get('meta') or {}).get('is_error') for m in msgs for p in m['parts']):
        conv['flags']['tool_errors'] = True
    if any((p.get('meta') or {}).get('truncated') for m in msgs for p in m['parts']):
        conv['flags']['truncated'] = True
    year = (conv['created'] or '0000')[:4]
    day = (conv['created'] or '0000-00-00')[:10]
    short = re.sub(r'[^0-9a-zA-Z]', '', conv['id'].split(':')[-1])[:8]
    rel = os.path.join('chats', conv['source'], year, f"{day} {slug(conv['title'])} [{short}].md")
    while db.execute('SELECT 1 FROM conversations WHERE md_path=?', (rel,)).fetchone():
        rel = rel[:-3] + '_.md'
    conv['md_path'] = rel
    on = set(path_ids)
    db.execute('INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (conv['id'], conv['source'], conv['title'], conv['created'], conv['updated'], conv['model'], conv['url'],
                rel, len(msgs), conv['n_branches'], json.dumps(conv['flags']), json.dumps(conv['extra'], default=str), unit))
    for m in msgs:
        db.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?)',
                   (m['id'], conv['id'], m['parent'], m['role'], m['created'], int(m['id'] in on)))
        for n, p in enumerate(m['parts']):
            meta = dict(p.get('meta') or {})
            meta.pop('input', None)
            cur = db.execute('INSERT INTO parts(conv_id,msg_id,seq,kind,role,created,text,meta) VALUES(?,?,?,?,?,?,?,?)',
                             (conv['id'], m['id'], n, p['kind'], m['role'], m['created'], p['text'], json.dumps(meta, ensure_ascii=False, default=str)))
            if p['kind'] != 'system':
                db.execute('INSERT INTO parts_fts(rowid,text,title) VALUES(?,?,?)', (cur.lastrowid, p['text'], conv['title']))
        for f in m['files']:
            db.execute('INSERT INTO files VALUES(?,?,?,?,?,?)', (conv['id'], m['id'], f['id'], f['name'], f['kind'], f.get('path')))
    write_if_changed(os.path.join(ROOT, rel), render(conv, path_ids))
    return rel


def build(full=False, quiet=False):
    if full and os.path.exists(DB):
        os.remove(DB)
    db = open_db()
    known = dict(db.execute('SELECT key, fp FROM units'))
    stats = collections.Counter()
    seen, changed = set(), []
    for key, fp, load in units():
        seen.add(key)
        if known.get(key) != fp:
            changed.append((key, fp, load))
    gone = [k for k in known if k not in seen]
    # oldest sessions first, so a message is owned by the session where it first appeared
    changed.sort(key=lambda u: (u[0].startswith('cc:'), os.path.getmtime(os.path.join(SRC, 'claude-code', u[0][3:])) if u[0].startswith('cc:') else 0))
    old_paths, new_paths = set(), set()
    for key in gone:
        old_paths |= drop_unit(db, key)
    for key, fp, load in changed:
        old_paths |= drop_unit(db, key)
        try:
            convs = load()
        except Exception as e:  # one broken source must never stop the rest
            stats[f'error in {key}: {type(e).__name__}: {e}'] += 1
            continue
        for conv in sorted(convs, key=lambda c: c['created'] or ''):
            rel = insert_conv(db, conv, key, stats)
            if rel:
                new_paths.add(rel)
                stats[conv['source']] += 1
        db.execute('INSERT OR REPLACE INTO units VALUES(?,?)', (key, fp))
        db.commit()
    for rel in old_paths - new_paths:
        if not db.execute('SELECT 1 FROM conversations WHERE md_path=?', (rel,)).fetchone():
            try:
                os.remove(os.path.join(ROOT, rel))
            except FileNotFoundError:
                pass
    db.commit(); db.close()
    if changed or gone or not os.path.exists(os.path.join(ROOT, 'INDEX.md')):
        write_index()
    if not quiet or changed or gone:
        print(f'{len(changed)} changed, {len(gone)} removed, {len(seen) - len(changed)} unchanged sources')
        for k in sorted(stats):
            print(f'  {k}: {stats[k]}')


def write_index():
    db = sqlite3.connect(DB)
    rows = db.execute('SELECT source,title,created,md_path,n_messages,n_branches,flags,model FROM conversations ORDER BY created DESC').fetchall()
    out = ['# AI history', '', 'Search: `./aih search "words"` (see CLAUDE.md).',
           '', '> These chats are a record of what was said, not of what is true. Answers can be wrong, and later chats may correct earlier ones.', '']
    by = collections.defaultdict(list)
    for r in rows:
        by[r[0]].append(r)
    for src, rs in sorted(by.items()):
        out += [f'## {src} ({len(rs)})', '', '| date | chat | msgs | notes |', '|---|---|---|---|']
        for s, t, c, p, n, b, fl, mo in rs:
            notes = [k.replace('_', ' ') for k, v in json.loads(fl).items() if v]
            if b:
                notes.append(f'{b} branch' + ('es' if b > 1 else ''))
            title = (t or '(untitled)').replace('|', '/').replace('[', '(').replace(']', ')')
            out.append(f"| {(c or '')[:10]} | [{title}]({p.replace(' ', '%20')}) | {n} | {', '.join(notes)} |")
        out.append('')
    write_if_changed(os.path.join(ROOT, 'INDEX.md'), '\n'.join(out) + '\n')


# ---------------------------------------------------------------- ingest browser downloads
MAGIC = [(b'\x89PNG', '.png'), (b'\xff\xd8\xff', '.jpg'), (b'GIF8', '.gif'), (b'%PDF', '.pdf'), (b'PK\x03\x04', '.zip'),
         (b'RIFF', '.webp'), (b'\x1a\x45\xdf\xa3', '.webm'), (b'ID3', '.mp3'), (b'OggS', '.ogg'), (b'{', '.json'), (b'<svg', '.svg'), (b'<', '.html')]


def sniff(path):
    head = open(path, 'rb').read(64)
    if head[4:8] == b'ftyp':
        return '.heic' if head[8:12] in (b'heic', b'heix', b'mif1') else '.mp4'
    for sig, ext in MAGIC:
        if head.startswith(sig):
            return ext
    try:
        head.decode('utf-8')
        return '.txt'
    except UnicodeDecodeError:
        return '.bin'


def fix_bins(dest):
    for p in glob.glob(os.path.join(dest, '*.bin')):
        ext = sniff(p)
        if ext != '.bin':
            os.replace(p, p[:-4] + ext)


def ingest(a):
    """Unpack claude-files-NN.tar bundles (original uploads fetched from claude.ai) into sources/claude-web/files."""
    import tarfile
    dest = os.path.join(SRC, 'claude-web', 'files')
    os.makedirs(dest, exist_ok=True)
    for tp in sorted(glob.glob(os.path.join(os.path.expanduser(a.dir), 'claude-files-*.tar'))):
        n = 0
        with tarfile.open(tp) as tf:
            members = tf.getmembers()
            idx = {}
            for m in members:
                if m.name.startswith('index/'):
                    idx.update(json.load(tf.extractfile(m)))
            for m in members:
                if not m.name.startswith('files/') or not m.isfile():
                    continue
                u = os.path.basename(m.name)
                if not re.fullmatch(r'[0-9a-f-]{36}', u):
                    continue
                info = idx.get(u, {})
                ct = (info.get('content_type') or '').split(';')[0].strip()
                ext = os.path.splitext(info.get('name') or '')[1].lower()
                if not ext or len(ext) > 6:
                    ext = mimetypes.guess_extension(ct) or '.bin'
                if info.get('variant') == 'preview':
                    ext = mimetypes.guess_extension(ct) or ext
                for old in glob.glob(os.path.join(dest, u + '.*')):
                    os.remove(old)
                with open(os.path.join(dest, u + ext), 'wb') as f:
                    shutil.copyfileobj(tf.extractfile(m), f)
                n += 1
        part = re.search(r'claude-files-([\w-]+)', tp).group(1)
        json.dump({'index': idx}, open(os.path.join(SRC, 'claude-web', f'files-index-{part}.json'), 'w'))
        os.remove(tp)  # everything in it is now under files/
        print(f'{os.path.basename(tp)}: {n} files')
    fix_bins(dest)


# ---------------------------------------------------------------- collect (runs on a timer)
# machine name -> ssh names to try, in order (LAN first). The machine running collect reads its own folder directly.
MACHINES = CONFIG.get('machines', {})
HOSTNAMES = {k.lower(): v for k, v in CONFIG.get('hostnames', {}).items()}  # OS hostname -> machine name
INBOX = os.path.expanduser(os.environ.get('AIH_INBOX', CONFIG.get('inbox') or os.path.join(ROOT, 'inbox')))
HUB = CONFIG.get('hub')  # the one machine that writes the archive (the others hold synced copies); None: any machine


def this_machine():
    h = os.uname().nodename.lower()
    return HOSTNAMES.get(h, h.split('.')[0])


def pull_claude_code(log):
    """Copy every machine's Claude Code transcripts in. Never deletes: if a machine prunes, the archive keeps them."""
    import subprocess
    me = this_machine()
    machines = dict(MACHINES)
    machines.setdefault(me, [])  # this machine is always collected, even with no config
    for name, hosts in machines.items():
        dest = os.path.join(SRC, 'claude-code', name) + '/'
        os.makedirs(dest, exist_ok=True)
        filt = ['--include=*/', '--include=*.jsonl', '--exclude=*']
        if name == me:
            srcs = [os.path.expanduser('~/.claude/projects/')]
        else:
            srcs = [f'{h}:.claude/projects/' for h in hosts]
        for src in srcs:
            cmd = ['rsync', '-a', '--timeout=60', '-e', 'ssh -o BatchMode=yes -o ConnectTimeout=6'] + filt + [src, dest]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                log.append(f'claude-code {name}: pulled from {src.split(":")[0] if ":" in src else "local"}')
                break
        else:
            log.append(f'claude-code {name}: not reachable, will retry next run')


def route_inbox(log):
    """Import whatever was dropped in inbox/: claude.ai export zips, ChatGPT export zips, claude-files bundles."""
    if not os.path.isdir(INBOX):
        os.makedirs(INBOX, exist_ok=True)
        return
    done = os.path.join(INBOX, '.imported')
    for f in sorted(os.listdir(INBOX)):
        path = os.path.join(INBOX, f)
        if f.startswith('.') or not os.path.isfile(path) or f.endswith(('.tmp', '.part', '.crdownload')):
            continue
        if time_since_modified(path) < 120:
            continue  # still arriving (a file sync may be mid-copy)
        try:
            kind = route_one(path, log)
        except Exception as e:
            log.append(f'inbox: could not import {f}: {type(e).__name__}: {e}')
            continue
        if kind and os.path.exists(path):
            os.makedirs(done, exist_ok=True)
            shutil.move(path, os.path.join(done, f))  # kept for 30 days, then removed by collect


def time_since_modified(path):
    import time
    return time.time() - os.path.getmtime(path)


def route_one(path, log):
    name = os.path.basename(path)
    if re.match(r'claude-files-.*\.tar$', name):
        ingest(argparse.Namespace(dir=os.path.dirname(path)))
        log.append(f'inbox: {name} (claude.ai original files)')
        return 'tar'
    if re.match(r'manifest-[0-9a-f-]+-\d+-[0-9a-f]+-(\d{4}-\d{2}-\d{2})-(\d{2})-(\d{2})', name):
        return 'manifest' if stash_claude(path, name, log) else None
    if not zipfile.is_zipfile(path):
        log.append(f'inbox: left {name} alone (not a known export)')
        return None
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if any(n.endswith('conversations.json') for n in names) and any(n.endswith(('user.json', 'chat.html', 'message_feedback.json')) for n in names):
            acct = 'account'
            for n in names:
                if n.endswith('user.json'):
                    try:
                        u = json.loads(zf.read(n))
                        acct = (u.get('email') or u.get('id') or acct).split('@')[0]
                    except ValueError:
                        pass
            acct = re.sub(r'[^a-z0-9]+', '-', acct.lower()).strip('-') or 'account'
            dest = os.path.join(SRC, 'chatgpt', acct)
            os.makedirs(dest, exist_ok=True)
            shutil.copy2(path, os.path.join(dest, name))
            log.append(f'inbox: {name} → ChatGPT account "{acct}"')
            return 'chatgpt'
    if re.match(r'(conversations|frames|projects|memories|artifact_data|claude_code_cloud|light_metadata)-\d+\.zip$', name):
        return 'claude' if stash_claude(path, name, log) else None
    log.append(f'inbox: left {name} alone (zip, but not a known export)')
    return None


def stash_claude(path, name, log):
    """Group a claude.ai official export by its manifest date; unpack conversations and frames."""
    base = os.path.join(SRC, 'claude-web')
    mans = sorted(glob.glob(os.path.join(INBOX, 'manifest-*.json')) + [path if name.startswith('manifest-') else ''])
    stamp = None
    for m in filter(None, mans):
        g = re.search(r'-(\d{4}-\d{2}-\d{2})-(\d{2})-(\d{2})\.json$', m)
        if g:
            stamp = f'{g.group(1)}-{g.group(2)}{g.group(3)}'
    stamp = stamp or dt.datetime.now().strftime('%Y-%m-%d-%H%M')
    dest = os.path.join(base, f'official-export-{stamp}')
    os.makedirs(os.path.join(dest, 'zips'), exist_ok=True)
    shutil.copy2(path, os.path.join(dest, 'zips', name))
    cat = name.split('-')[0]
    if cat in ('conversations', 'frames', 'projects', 'memories', 'artifact_data', 'claude_code_cloud', 'light_metadata'):
        with zipfile.ZipFile(path) as zf:
            zf.extractall(os.path.join(dest, cat))
        if cat == 'conversations':
            # Strip deleted chats before they ever land in the archive (same rule as the importer).
            cj = glob.glob(os.path.join(dest, cat, '**', 'conversations.json'), recursive=True)
            for c in cj:
                data = json.load(open(c))
                live = [x for x in data if not (x.get('chat_messages') and all(not m.get('text') and not m.get('content') for m in x['chat_messages']))]
                dead = [x['uuid'] for x in data if x not in live]
                if dead:
                    with open(os.path.join(base, 'deleted-chat-ids.txt'), 'a') as fh:
                        fh.write(''.join(u + '\n' for u in dead))
                    json.dump(live, open(c, 'w'), ensure_ascii=False)
            os.remove(os.path.join(dest, 'zips', name))  # the zip would still hold the deleted shells
    log.append(f'inbox: {name} → claude.ai export {stamp}')
    return True


def hub_only(a):
    if HUB and this_machine() != HUB and not getattr(a, 'force', False):
        sys.exit(f'This copy is read-only here: the archive is updated on "{HUB}" and synced to this machine.\n'
                 f'Search works anywhere. To update now, run "aih collect" on {HUB}, or pass --force.')


def collect(a):
    hub_only(a)
    log = []
    pull_claude_code(log)
    route_inbox(log)
    done = os.path.join(INBOX, '.imported')
    for f in glob.glob(os.path.join(done, '*')):
        if time_since_modified(f) > 30 * 86400:
            os.remove(f)
    build(quiet=True)
    stamp = dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    with open(os.path.join(ROOT, 'collect.log'), 'a') as fh:
        fh.write(''.join(f'{stamp} {l}\n' for l in log))
    if not a.quiet:
        print('\n'.join(log))


# ---------------------------------------------------------------- search / stats
def search(a):
    db = sqlite3.connect(DB)
    q = a.query if a.raw else ' '.join('"' + w.replace('"', '') + '"' for w in a.query.split())
    sql = ['SELECT c.source, c.title, p.created, p.role, p.kind, snippet(parts_fts,0,"\x1b[1;33m","\x1b[0m","…",18), c.md_path',
           'FROM parts_fts JOIN parts p ON p.rowid=parts_fts.rowid JOIN conversations c ON c.id=p.conv_id WHERE parts_fts MATCH ?']
    args = [q]
    if a.me:  # only what the user typed: subagent transcripts are one Claude briefing another, not him
        sql.append("AND p.role='user' AND p.kind IN ('text','attachment') AND c.flags NOT LIKE '%subagent%'")
    if a.claude:
        sql.append("AND p.role='assistant' AND p.kind='text'")
    if a.talk:
        sql.append("AND p.kind IN ('text','attachment')")
    if a.source:
        sql.append('AND c.source LIKE ?'); args.append(a.source + '%')
    if a.since:
        sql.append('AND p.created >= ?'); args.append(a.since)
    sql.append('ORDER BY ' + ('p.created DESC' if a.newest else 'rank') + ' LIMIT ?'); args.append(a.n)
    for src, title, created, role, kind, snip, path in db.execute(' '.join(sql), args):
        print(f"\x1b[36m{(created or '')[:10]}\x1b[0m {src} · \x1b[1m{title or '(untitled)'}\x1b[0m [{role}/{kind}]")
        print('   ' + (snip or '').replace('\n', ' '))
        print(f'   \x1b[2m{path}\x1b[0m')


def stats_cmd(_):
    db = sqlite3.connect(DB)
    for r in db.execute('SELECT source, count(*), sum(n_messages), sum(n_branches>0), min(created), max(created) FROM conversations GROUP BY source'):
        print('%-22s chats=%-5s messages=%-6s with-branches=%-4s %s → %s' % (r[0], r[1], r[2], r[3], (r[4] or '')[:10], (r[5] or '')[:10]))
    for r in db.execute("SELECT c.source, count(*), sum(f.path IS NOT NULL) FROM files f JOIN conversations c ON c.id=f.conv_id GROUP BY c.source"):
        print('%-22s files=%s saved=%s' % r)
    fl = collections.Counter()
    for (f,) in db.execute('SELECT flags FROM conversations'):
        fl.update(k for k, v in json.loads(f).items() if v)
    print('flags:', dict(fl))


def check(a):
    """Is it safe to delete my data on a website? Compares the newest export of each account with the archive."""
    db = sqlite3.connect(DB)
    print('Safe-to-delete check (newest export vs what the archive holds):\n')
    exports = {}
    for cj in sorted(glob.glob(os.path.join(SRC, 'chatgpt', '**', 'conversations*.json'), recursive=True)):
        acct = re.sub(r'[^a-z0-9]+', '-', os.path.relpath(cj, os.path.join(SRC, 'chatgpt')).split(os.sep)[0].lower()).strip('-')
        exports.setdefault(f'chatgpt-{acct}', []).append(cj)
    web = sorted(glob.glob(os.path.join(SRC, 'claude-web', 'official-export-*', 'conversations', 'conversations.json')))
    if web:
        exports['claude-web'] = [web[-1]]
    if not exports:
        print('  no website exports yet'); return
    for src, files in sorted(exports.items()):
        ids, newest = set(), 0
        for f in files:
            data = json.load(open(f))
            ids |= {c.get('conversation_id') or c.get('id') or c.get('uuid') for c in data if c.get('mapping') or c.get('chat_messages')}
            newest = max(newest, os.path.getmtime(f))
        have = {r[0].split('#')[0] for r in db.execute('SELECT id FROM conversations WHERE source=?', (src,))}
        missing = ids - have
        age = (dt.datetime.now() - dt.datetime.fromtimestamp(newest)).days
        verdict = 'SAFE: every chat in the export is in the archive' if not missing else f'NOT SAFE: {len(missing)} chats from the export are missing'
        nf = db.execute('SELECT count(*), sum(f.path IS NULL) FROM files f JOIN conversations c ON c.id=f.conv_id WHERE c.source=?', (src,)).fetchone()
        print(f'  {src}: export has {len(ids)} chats, archive has {len(have)}; newest export is {age} days old')
        print(f'      files: {nf[0] or 0} referenced, {nf[1] or 0} without the original file')
        print(f'      {verdict}' + ('' if age <= 2 else ' (but request a fresh export first: chats newer than it are not covered)'))


def show(a):
    db = sqlite3.connect(DB)
    for (p,) in db.execute('SELECT md_path FROM conversations WHERE id LIKE ? OR id LIKE ?', (a.id + '%', '%:' + a.id + '%')):
        print(os.path.join(ROOT, p))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(prog='aih', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    bp = sp.add_parser('build'); bp.add_argument('--full', action='store_true', help='rebuild everything from scratch'); bp.add_argument('--force', action='store_true')
    s = sp.add_parser('search'); s.add_argument('query'); s.add_argument('-n', type=int, default=20)
    s.add_argument('--me', action='store_true', help='only what you typed'); s.add_argument('--claude', action='store_true', help='only assistant answers')
    s.add_argument('--talk', action='store_true', help='skip tool calls, tool output and thinking')
    s.add_argument('--source'); s.add_argument('--since', help='YYYY-MM-DD'); s.add_argument('--newest', action='store_true')
    s.add_argument('--raw', action='store_true', help='pass FTS5 syntax through (AND/OR/NEAR/prefix*)')
    sp.add_parser('stats'); sh = sp.add_parser('show'); sh.add_argument('id')
    sp.add_parser('check', help='is it safe to delete my data on ChatGPT / claude.ai?')
    cp = sp.add_parser('collect', help='pull Claude Code from all machines, import the inbox, rebuild'); cp.add_argument('--quiet', action='store_true'); cp.add_argument('--force', action='store_true')
    ig = sp.add_parser('ingest', help='unpack claude-files-*.tar bundles from a folder'); ig.add_argument('dir', nargs='?', default='~/Downloads'); ig.add_argument('--force', action='store_true')
    a = ap.parse_args()
    {'build': lambda a: (hub_only(a), build(a.full)), 'search': search, 'stats': stats_cmd, 'show': show, 'ingest': lambda a: (hub_only(a), ingest(a)), 'collect': collect, 'check': check}[a.cmd](a)
