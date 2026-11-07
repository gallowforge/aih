#!/usr/bin/env python3
"""Build a synthetic aih setup: fake exports and transcripts for a made-up user, "alex".

Everything here is invented. The chats are about neutral engineering topics, the hosts are
placeholders and every address is from a documentation range. It exists so the README visuals,
the smoke test and the benchmark run the real aih on data that belongs to nobody.

  scripts/demo-data.py DEST              build DEST, a fake home folder (see the layout below)
  scripts/demo-data.py DEST --bench N    also add N long generated sessions, for timing searches

Layout of DEST (it plays the part of /home/alex on the hub machine, "server"):
  aih/                  a copy of aih.py, its `aih` symlink and aih.config.json
  aih/inbox/            a claude.ai export zip and a ChatGPT export zip, waiting to be imported
  .claude/projects/     this machine's Claude Code transcripts
  .demo/machines/NAME/  the home folders of the other two machines, "desktop" and "laptop"
  .demo/bin/ssh         a stand-in for ssh that maps each host alias to one of those folders.
                        "laptop-lan" never answers, so aih falls back to the "laptop" alias.

Then run the real thing:
  HOME=DEST PATH=DEST/.demo/bin:$PATH DEST/aih/aih collect
"""
import argparse, base64, datetime as dt, json, os, random, shutil, stat, struct, uuid, zipfile, zlib

NS = uuid.UUID('f63090ed-d01a-4c1e-ad74-20aa5431cfdb')
HOME_IN_PATHS = '/home/alex'


def uid(label):
    return str(uuid.uuid5(NS, label))


def at(stamp, plus=0):
    """'2026-02-11 19:03' + seconds -> ISO 8601 with milliseconds, the way the exports write it."""
    t = dt.datetime.strptime(stamp, '%Y-%m-%d %H:%M') + dt.timedelta(seconds=plus)
    return t.strftime('%Y-%m-%dT%H:%M:%S.') + f'{(plus * 37) % 1000:03d}Z'


def epoch(iso_s):
    return dt.datetime.strptime(iso_s[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=dt.timezone.utc).timestamp()


def png(w, h):
    """A small, valid PNG: a dark card grid, standing in for a pasted screenshot."""
    def px(x, y):
        edge = x % 22 < 2 or y % 18 < 2
        return (34, 38, 48) if edge else (18 + x // 4, 20 + y // 4, 28 + x // 6)
    raw = b''.join(b'\x00' + bytes(c for x in range(w) for c in px(x, y)) for y in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


# ------------------------------------------------------------------ claude.ai (official export)
def web_msg(conv, n, sender, text, when, parent=None, attachments=None):
    return {'uuid': uid(f'{conv}/{n}'), 'text': text, 'sender': sender, 'created_at': when, 'updated_at': when,
            'content': [{'type': 'text', 'text': text, 'start_timestamp': when, 'stop_timestamp': when, 'citations': []}],
            'attachments': attachments or [], 'files': [],
            'parent_message_uuid': parent or '00000000-0000-4000-8000-000000000000'}


def web_chat(key, name, start, turns):
    """turns: (sender, text) or (sender, text, options). Options: branch=True starts again from the top
    (an edited first prompt), attachments=[...] adds pasted files."""
    msgs, prev = [], None
    for i, t in enumerate(turns):
        sender, text, opt = t[0], t[1], (t[2] if len(t) > 2 else {})
        parent = None if opt.get('branch') else prev
        m = web_msg(key, i, sender, text, at(start, 40 + i * 95), parent, opt.get('attachments'))
        msgs.append(m)
        prev = m['uuid']
    return {'uuid': uid(key), 'name': name, 'summary': '', 'created_at': at(start), 'updated_at': msgs[-1]['created_at'],
            'account': {'uuid': uid('account')}, 'chat_messages': msgs}


def claude_web_export():
    chats = [
        web_chat('web-fts5', 'Finding José when searching for jose', '2026-01-18 20:41', [
            ('human', "I'm searching contacts with LIKE '%jose%' and it misses José. What's the cleanest fix?"),
            ('assistant', "LIKE compares characters one by one, so 'e' never equals 'é'. You could store a folded copy "
                          "of each name, but an FTS5 index does the folding for you and ranks results too."),
            # the prompt was edited: a second version starts from the same point, and that line is kept
            ('human', "I have a notes table and want full-text search where 'jose' also finds 'José'. Which FTS5 "
                      "tokenizer should I use?", {'branch': True}),
            ('assistant', "Use the built-in unicode61 tokenizer with diacritics removed:\n\n```sql\nCREATE VIRTUAL TABLE "
                          "notes_fts USING fts5(\n  title, body,\n  tokenize = 'unicode61 remove_diacritics 2'\n);\n```\n\n"
                          "The tokenizer folds é to e both when it indexes and when it parses your query, so 'jose' and "
                          "'José' are the same token. Level 2 also folds a few characters that level 1 misses.\n\n"
                          "Two other options: the trigram tokenizer if you need substring matches, and porter if you "
                          "want 'running' to find 'run'."),
            ('human', "Does porter still fold the accents?"),
            ('assistant', "Yes. Porter wraps another tokenizer and stems what it returns, so chain them: "
                          "`tokenize = 'porter unicode61 remove_diacritics 2'`. Accents are folded first, then each "
                          "English word is reduced to its stem."),
        ]),
        web_chat('web-caddy', 'Caddy reverse proxy with automatic HTTPS', '2025-11-02 18:15', [
            ('human', "I want Caddy in front of three services on one box: git.example.com, notes.example.com and a "
                      "status page, on ports 3000, 5230 and 8080. What's the smallest Caddyfile?"),
            ('assistant', "Three site blocks are all you need:\n\n```caddy\ngit.example.com {\n    reverse_proxy "
                          "localhost:3000\n}\n\nnotes.example.com {\n    reverse_proxy localhost:5230\n}\n\n"
                          "status.example.com {\n    reverse_proxy localhost:8080\n}\n```\n\nCaddy obtains and renews a "
                          "certificate for each name on its own, as long as ports 80 and 443 reach the box and the DNS "
                          "records point at it."),
            ('human', "The box is behind NAT and only 443 is forwarded. Will the certificate still renew?"),
            ('assistant', "The TLS-ALPN challenge works over 443, so Caddy can still renew. If you ever close 443 too, "
                          "switch to the DNS challenge: build Caddy with your DNS provider's module and add a `tls` block "
                          "with `dns <provider> {env.DNS_API_TOKEN}`. Caddy renews each certificate about 30 days "
                          "before it expires."),
        ]),
        web_chat('web-asyncio', 'asyncio.gather vs TaskGroup', '2025-12-09 22:07', [
            ('human', "When should I use asyncio.TaskGroup instead of gather? I fetch 20 URLs and want to stop "
                      "everything if one fails."),
            ('assistant', "That is exactly what TaskGroup (Python 3.11+) is for. When one task raises, the group "
                          "cancels the others and re-raises the errors together as an ExceptionGroup:\n\n```python\n"
                          "async with asyncio.TaskGroup() as tg:\n    tasks = [tg.create_task(fetch(u)) for u in urls]\n"
                          "pages = [t.result() for t in tasks]\n```\n\n`gather` keeps the other tasks running after a "
                          "failure unless you cancel them yourself. Use it when you want every result, with "
                          "`return_exceptions=True`."),
        ]),
        web_chat('web-explain', 'Reading a slow EXPLAIN ANALYZE', '2026-02-21 10:32', [
            ('human', "Why is this query so slow? The plan is attached.", {'attachments': [
                {'file_name': 'plan.txt', 'file_type': 'txt', 'file_size': 311, 'extracted_content':
                 "Seq Scan on events  (cost=0.00..18334.00 rows=412 width=72) (actual time=0.031..211.402 rows=398 loops=1)\n"
                 "  Filter: ((user_id = 42) AND (created_at > (now() - '7 days'::interval)))\n"
                 "  Rows Removed by Filter: 999602\nPlanning Time: 0.118 ms\nExecution Time: 211.488 ms"}]}),
            ('assistant', "Postgres reads all million rows and throws away 999,602 of them: there is no index it can "
                          "use for `user_id` and `created_at` together. Add one, in that order, since you filter on "
                          "equality first and a range second:\n\n```sql\nCREATE INDEX CONCURRENTLY events_user_created\n"
                          "  ON events (user_id, created_at);\n```\n\nThe plan should turn into an Index Scan that "
                          "touches about 400 rows."),
        ]),
    ]
    # A chat deleted on claude.ai: exports still list it, as an empty shell. aih must never import it.
    shell = web_chat('web-deleted', '', '2026-01-05 09:12', [('human', ''), ('assistant', '')])
    for m in shell['chat_messages']:
        m['content'] = []
    return chats + [shell]


# ------------------------------------------------------------------ Claude Code (JSONL transcripts)
class Session:
    def __init__(self, machine, project_cwd, key, start, model='claude-sonnet-4-5', title=None, sidechain=False):
        self.machine, self.cwd, self.key, self.start, self.model = machine, project_cwd, key, start, model
        self.sid = uid(f'cc/{key}')
        self.lines, self.t, self.prev, self.n, self.sidechain = [], 0, None, 0, sidechain
        if title:
            self.lines.append({'type': 'summary', 'summary': title, 'leafUuid': uid(f'cc/{key}/leaf')})

    def _emit(self, kind, message, step, meta=False, fixed_id=None):
        self.t += step
        self.n += 1
        u = fixed_id or uid(f'cc/{self.key}/{self.n}')
        line = {'parentUuid': self.prev, 'isSidechain': self.sidechain, 'userType': 'external', 'cwd': self.cwd,
                'sessionId': self.sid, 'version': '2.0.14', 'gitBranch': 'main', 'type': kind, 'message': message,
                'uuid': u, 'timestamp': at(self.start, self.t)}
        if meta:
            line['isMeta'] = True
        self.lines.append(line)
        self.prev = u
        return u

    def user(self, *blocks, step=75):
        """A typed prompt is a plain string; a prompt with an image or IDE context is a list of blocks."""
        if len(blocks) == 1 and isinstance(blocks[0], str):
            content = blocks[0]
        else:
            content = [{'type': 'text', 'text': b} if isinstance(b, str) else b for b in blocks]
        return self._emit('user', {'role': 'user', 'content': content}, step)

    def assistant(self, *blocks, step=31):
        content = []
        for b in blocks:
            if isinstance(b, str):
                content.append({'type': 'text', 'text': b})
            else:
                content.append(b)
        self._tool_ids = [b['id'] for b in content if b.get('type') == 'tool_use']
        return self._emit('assistant', {'id': 'msg_' + uid(f'cc/{self.key}/m{self.n}').replace('-', '')[:24], 'type': 'message',
                                        'role': 'assistant', 'model': self.model, 'content': content,
                                        'stop_reason': 'tool_use' if self._tool_ids else 'end_turn',
                                        'usage': {'input_tokens': 1200 + self.n * 310, 'output_tokens': 180 + self.n * 22}}, step)

    def result(self, text, error=False, step=3):
        tid = self._tool_ids.pop(0)
        return self._emit('user', {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': tid,
                                                                  'content': text, 'is_error': error}]}, step)

    def tool(self, name, **inp):
        return {'type': 'tool_use', 'id': 'toolu_' + uid(f'cc/{self.key}/t{self.n}/{name}/{len(self.lines)}').replace('-', '')[:24],
                'name': name, 'input': inp}

    def write(self, home, subpath=None):
        project = self.cwd.replace('/', '-').replace('.', '-')
        folder = os.path.join(home, '.claude', 'projects', project)
        path = os.path.join(folder, subpath) if subpath else os.path.join(folder, self.sid + '.jsonl')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in self.lines))
        stamp = epoch(at(self.start, self.t))
        os.utime(path, (stamp, stamp))
        return path


def thinking(text):
    return {'type': 'thinking', 'thinking': text, 'signature': 'synthetic'}


def claude_code(base, machines_dir):
    homes = {'server': base, 'desktop': os.path.join(machines_dir, 'desktop'), 'laptop': os.path.join(machines_dir, 'laptop')}
    stack = f'{HOME_IN_PATHS}/srv/stack'

    # server: compose healthchecks, then a resumed session that re-copies the start of the first one
    s1 = Session('server', stack, 'server-health', '2026-02-02 21:10', title='Add a Postgres healthcheck to the compose stack')
    s1.user({'type': 'text', 'text': f'<ide_opened_file>The user opened the file {stack}/compose.yaml in the IDE.</ide_opened_file>'},
            {'type': 'text', 'text': 'Add a healthcheck to Postgres in the compose stack so the app only starts once the '
                                     'database is ready. Keep it minimal.'})
    s1.assistant(thinking('The app depends on db but starts as soon as the container exists. pg_isready in a '
                          'healthcheck plus depends_on with condition service_healthy fixes the race.'),
                 "I'll read the compose file first.", s1.tool('Read', file_path=f'{stack}/compose.yaml'))
    s1.result('services:\n  db:\n    image: postgres:17\n    environment:\n      POSTGRES_USER: app\n  app:\n    build: .\n'
              '    depends_on:\n      - db\n    ports:\n      - "8000:8000"\n')
    s1.assistant(s1.tool('Edit', file_path=f'{stack}/compose.yaml', old_string='    depends_on:\n      - db',
                         new_string='    depends_on:\n      db:\n        condition: service_healthy'))
    s1.result(f'The file {stack}/compose.yaml has been updated.')
    s1.assistant(s1.tool('Bash', command='docker compose up -d && docker compose ps', description='Restart the stack and show health'))
    s1.result('dependency failed to start: container stack-db-1 is unhealthy', error=True, step=19)
    s1.assistant('The check ran before Postgres finished initialising. A `start_period` gives it time.',
                 s1.tool('Edit', file_path=f'{stack}/compose.yaml', old_string='      retries: 5',
                         new_string='      retries: 5\n      start_period: 10s'))
    s1.result(f'The file {stack}/compose.yaml has been updated.')
    s1.assistant(s1.tool('Bash', command='docker compose up -d && docker compose ps', description='Restart the stack and show health'))
    s1.result('NAME          IMAGE         STATUS\nstack-app-1   stack-app     Up 4 seconds\nstack-db-1    postgres:17   '
              'Up 16 seconds (healthy)', step=24)
    s1.assistant("Done. `db` reports healthy after about ten seconds, and `app` waits for it:\n\n```yaml\n  db:\n"
                 "    healthcheck:\n      test: [\"CMD-SHELL\", \"pg_isready -U app\"]\n      interval: 5s\n      timeout: 3s\n"
                 "      retries: 5\n      start_period: 10s\n  app:\n    depends_on:\n      db:\n        condition: service_healthy\n```")
    s1.write(homes['server'])

    s2 = Session('server', stack, 'server-health-2', '2026-02-03 09:02', title='Healthcheck for the app container')
    for line in s1.lines[1:4]:  # a resumed session starts with copies of earlier messages
        copy = dict(line, sessionId=s2.sid)
        s2.lines.append(copy)
        s2.prev = copy['uuid']
    s2.t = 60
    s2.user('Now give the app container a healthcheck too. It serves /healthz on port 8000, and the image has wget '
            'but not curl.')
    s2.assistant("BusyBox wget is enough. Add this under `app`:\n\n```yaml\n    healthcheck:\n      test: [\"CMD\", \"wget\", "
                 "\"-qO-\", \"http://localhost:8000/healthz\"]\n      interval: 10s\n      timeout: 3s\n      retries: 3\n```\n\n"
                 "`docker compose ps` will show `(healthy)` next to it within twenty seconds.")
    s2.write(homes['server'])

    s3 = Session('server', stack, 'server-caddy', '2026-03-12 08:47', title='Caddy certificate renewal failing')
    s3.user('Caddy logs say the certificate for status.example.com failed to renew. Can you look?')
    s3.assistant(s3.tool('Bash', command='docker compose logs caddy --since 24h | grep -m2 error', description='Find renewal errors'))
    s3.result('{"level":"error","logger":"tls.obtain","msg":"could not get certificate from issuer","identifier":'
              '"status.example.com","challenge":"tls-alpn-01","error":"HTTP 400 urn:ietf:params:acme:error:connection - '
              '203.0.113.10: Timeout during connect (likely firewall problem)"}')
    s3.assistant("Let's Encrypt can't reach this box on 443, so the TLS-ALPN challenge times out. The router forward "
                 "points at 192.168.1.20, but the server is 192.168.1.40 now. Fix the forward, or move status.example.com "
                 "to the DNS challenge so the certificate never depends on an open port.")
    s3.user('Fixed the forward. Check again.')
    s3.assistant(s3.tool('Bash', command='docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile && '
                                         'docker compose logs caddy --since 5m | grep -m1 obtained', description='Reload Caddy and watch the retry'))
    s3.result('{"level":"info","logger":"tls.obtain","msg":"certificate obtained successfully","identifier":"status.example.com"}', step=41)
    s3.assistant('Caddy retried on its own after the reload and obtained the certificate for status.example.com. '
                 'Renewal will now work the same way.')
    s3.write(homes['server'])

    # desktop: a CSS grid fix with a pasted screenshot and a subagent, and a systemd timer
    dash = f'{HOME_IN_PATHS}/src/dashboard'
    d1 = Session('desktop', dash, 'desktop-grid', '2026-01-09 17:26', model='claude-opus-4-1', title='CSS grid for the status dashboard')
    d1.user({'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': base64.b64encode(png(176, 108)).decode()}},
            {'type': 'text', 'text': 'The cards overlap below 900px, screenshot attached. I want three columns on a desktop and '
                                     'one on a phone, without a pile of media queries.'})
    d1.assistant(thinking('auto-fit with minmax collapses columns on its own. min(100%, 280px) stops a single card '
                          'overflowing on very narrow screens. Check for other breakpoints first.'),
                 'Let me find every breakpoint first.', d1.tool('Task', description='Find grid breakpoints', subagent_type='Explore',
                                                                 prompt='Find every place grid breakpoints are defined in src/ and report file:line.'))
    d1.result('Breakpoints are defined in two places: src/styles.css:41 and src/components/Card.css:12.', step=30)
    d1.assistant("One rule replaces both breakpoints:\n\n```css\n.grid {\n  display: grid;\n  grid-template-columns: "
                 "repeat(auto-fit, minmax(min(100%, 280px), 1fr));\n  gap: 16px;\n}\n```\n\nThe browser fits as many "
                 "280px columns as it can and stretches them, so the layout goes from three columns to one with no "
                 "media query.", d1.tool('Edit', file_path=f'{dash}/src/styles.css', old_string='grid-template-columns: repeat(3, 1fr);',
                                         new_string='grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));'))
    d1.result(f'The file {dash}/src/styles.css has been updated.')
    d1.write(homes['desktop'])
    sub = Session('desktop', dash, 'desktop-grid-sub', '2026-01-09 17:27', model='claude-haiku-4-5', sidechain=True)
    sub.user('Find every place grid breakpoints are defined in src/ and report file:line.')
    sub.assistant(sub.tool('Grep', pattern='@media|grid-template-columns', path='src', output_mode='content', **{'-n': True}))
    sub.result('src/styles.css:41:  grid-template-columns: repeat(3, 1fr);\nsrc/styles.css:58:@media (max-width: 900px) {\n'
               'src/components/Card.css:12:@media (max-width: 600px) {')
    sub.assistant('Breakpoints are defined in two places: src/styles.css:41 and src/components/Card.css:12.')
    sub.write(homes['desktop'], os.path.join(d1.sid, 'subagents', 'agent-a7c1d2e9.jsonl'))

    d2 = Session('desktop', f'{HOME_IN_PATHS}', 'desktop-timer', '2025-12-15 23:18', title='systemd timer instead of cron for backups')
    d2.user('Replace my cron line `0 3 * * * ~/bin/backup.sh` with a systemd user timer that catches up if the PC '
            'was off at 3am.')
    d2.assistant('Two small units. `Persistent=true` is what makes it catch up after the PC was off.',
                 d2.tool('Write', file_path=f'{HOME_IN_PATHS}/.config/systemd/user/backup.timer',
                         content='[Unit]\nDescription=Nightly backup\n\n[Timer]\nOnCalendar=*-*-* 03:00\nPersistent=true\n\n'
                                 '[Install]\nWantedBy=timers.target\n'))
    d2.result(f'File created successfully at: {HOME_IN_PATHS}/.config/systemd/user/backup.timer')
    d2.assistant(d2.tool('Bash', command='systemctl --user daemon-reload && systemctl --user enable --now backup.timer && '
                                         'systemctl --user list-timers backup.timer', description='Enable the timer'))
    d2.result('NEXT                        LEFT     LAST  PASSED  UNIT          ACTIVATES\n'
              'Tue 2025-12-16 03:00:00 +03 3h 41min -     -       backup.timer  backup.service\n\n1 timers listed.')
    d2.assistant('The timer is live and runs at 03:00. If the PC is off then, it runs once at the next boot. You can '
                 'remove the cron line with `crontab -e`.')
    d2.write(homes['desktop'])

    # laptop: full-text search for a notes CLI, and a Rust lifetime error
    notes = f'{HOME_IN_PATHS}/src/notes'
    l1 = Session('laptop', notes, 'laptop-search', '2026-02-11 19:03', model='claude-opus-4-1', title='Add full-text search to the notes CLI')
    l1.user("Add a `notes search` command. Storage is already SQLite. Rank results by relevance, and searching 'cafe' "
            "should also find 'café'.")
    l1.assistant(thinking('FTS5 ships with Python\'s sqlite3, so no new dependency. An external-content table over '
                          'notes keeps one copy of the text; triggers keep it in sync. The unicode61 tokenizer with '
                          'remove_diacritics 2 folds café to cafe. bm25() ranks, snippet() gives context.'),
                 "SQLite's FTS5 does all of this with no new dependency:\n\n1. An FTS5 index over `notes(title, body)` "
                 "with the `unicode61 remove_diacritics 2` tokenizer, so accents fold.\n2. Triggers keep the index in "
                 "sync with the table.\n3. `notes search` ranks with `bm25()` and prints a `snippet()` of each match.",
                 l1.tool('Write', file_path=f'{notes}/notes/search.py',
                         content='import sqlite3\n\nSCHEMA = """\nCREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(\n'
                                 "  title, body, content='notes', content_rowid='id',\n  tokenize='unicode61 remove_diacritics 2'\n);\n"
                                 '"""\n\n\ndef search(db, query, limit=10):\n    return db.execute(\n        "SELECT n.created, n.title, '
                                 'snippet(notes_fts, 1, \'[\', \']\', \'…\', 12) "\n        "FROM notes_fts JOIN notes n ON n.id = '
                                 'notes_fts.rowid "\n        "WHERE notes_fts MATCH ? ORDER BY bm25(notes_fts) LIMIT ?", (query, limit))\n'))
    l1.result(f'File created successfully at: {notes}/notes/search.py')
    l1.assistant(l1.tool('Bash', command='python -m notes search cafe', description='Try an accent-folded search'))
    l1.result('2026-01-30  Coffee notes\n    …the [café] on 5th roasts on Tuesdays…\n2026-02-04  Weekend plan\n'
              '    …meet at the [cafe] near the station…')
    l1.assistant("It works: `cafe` finds both spellings, best match first. The index is created with:\n\n```sql\nCREATE "
                 "VIRTUAL TABLE notes_fts USING fts5(\n  title, body,\n  content='notes', content_rowid='id',\n  "
                 "tokenize='unicode61 remove_diacritics 2'\n);\n```\n\nI also added triggers for insert, update and "
                 "delete, and a `--limit` flag (default 10).")
    l1.user('Why not the trigram tokenizer?')
    l1.assistant('Trigram matches any substring (`afe` finds café), but the index is about three times larger, '
                 'queries need at least three characters, and ranking by whole words gets worse. For a notes CLI, '
                 'the unicode61 tokenizer is the better default.')
    l1.write(homes['laptop'])

    lex = f'{HOME_IN_PATHS}/src/lexer'
    l2 = Session('laptop', lex, 'laptop-rust', '2026-03-05 21:40', title='Rust lifetimes: a struct holding a &str')
    l2.user('cargo build fails with E0106 on my Token struct. Fix it without cloning strings.')
    l2.assistant(l2.tool('Bash', command='cargo build 2>&1 | head -8', description='Reproduce the error'))
    l2.result("error[E0106]: missing lifetime specifier\n --> src/lexer.rs:3:11\n  |\n3 |     text: &str,\n  |           ^ "
              "expected named lifetime parameter", error=True)
    l2.assistant("`Token` borrows its text from the source string, so it needs a lifetime that ties the two "
                 "together:\n\n```rust\npub struct Token<'a> {\n    pub kind: Kind,\n    pub text: &'a str,\n}\n\npub fn "
                 "tokens<'a>(src: &'a str) -> Vec<Token<'a>> { ... }\n```\n\nNo clones: every token points into `src`, "
                 "and the compiler checks that `src` outlives them.",
                 l2.tool('Edit', file_path=f'{lex}/src/lexer.rs', old_string='pub struct Token {', new_string="pub struct Token<'a> {"))
    l2.result(f'The file {lex}/src/lexer.rs has been updated.')
    l2.assistant(l2.tool('Bash', command='cargo build', description='Build again'))
    l2.result('   Compiling lexer v0.1.0 (/home/alex/src/lexer)\n    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.84s', step=9)
    l2.assistant('It builds. The lifetime is the only change; the function bodies stay as they were.')
    l2.write(homes['laptop'])


# ------------------------------------------------------------------ ChatGPT (export zip)
def gpt_chat(key, title, start, turns, archived=False, model='gpt-4o'):
    """turns: (role, text) in order, or (role, text, 'regen') for an answer generated again from the same prompt."""
    mapping = {}
    root = uid(f'{key}/root')
    mapping[root] = {'id': root, 'message': None, 'parent': None, 'children': []}
    sysid = uid(f'{key}/system')
    mapping[sysid] = {'id': sysid, 'parent': root, 'children': [], 'message': {
        'id': sysid, 'author': {'role': 'system', 'name': None, 'metadata': {}}, 'create_time': None,
        'content': {'content_type': 'text', 'parts': ['']}, 'status': 'finished_successfully', 'metadata': {}, 'recipient': 'all'}}
    mapping[root]['children'].append(sysid)
    prev, before = sysid, sysid
    t0 = epoch(at(start))
    for i, t in enumerate(turns):
        role, text = t[0], t[1]
        parent = before if len(t) > 2 and t[2] == 'regen' else prev
        nid = uid(f'{key}/{i}')
        mapping[nid] = {'id': nid, 'parent': parent, 'children': [], 'message': {
            'id': nid, 'author': {'role': role, 'name': None, 'metadata': {}}, 'create_time': t0 + 30 + i * 70,
            'update_time': None, 'content': {'content_type': 'text', 'parts': [text]}, 'status': 'finished_successfully',
            'end_turn': role == 'assistant', 'weight': 1.0, 'metadata': {'model_slug': model} if role == 'assistant' else {},
            'recipient': 'all'}}
        mapping[parent]['children'].append(nid)
        before, prev = parent, nid
    cid = uid(key)
    return {'title': title, 'create_time': t0, 'update_time': t0 + 30 + len(turns) * 70, 'mapping': mapping,
            'moderation_results': [], 'current_node': prev, 'plugin_ids': None, 'conversation_id': cid, 'id': cid,
            'default_model_slug': model, 'is_archived': archived}


def chatgpt_export():
    return [
        gpt_chat('gpt-accents', 'Accent-insensitive search in SQLite', '2025-10-30 19:55', [
            ('user', 'In SQLite, how do I make a search ignore accents, so resume matches résumé?'),
            ('assistant', "SQLite's LIKE folds case only for ASCII letters, so it can't do this alone. Store a "
                          "normalised copy of the column and search that instead."),
            ('assistant', "The simplest way is an FTS5 table whose tokenizer removes diacritics:\n\n```sql\nCREATE "
                          "VIRTUAL TABLE docs USING fts5(body, tokenize='unicode61 remove_diacritics 2');\n```\n\nThe "
                          "tokenizer folds é to e when it indexes and when it reads your query, so 'resume' matches "
                          "'résumé'. You also get ranking with bm25() for free.", 'regen'),
            ('user', 'Which tokenizer handles Japanese?'),
            ('assistant', "Neither unicode61 nor porter splits Japanese into words. Use the trigram tokenizer for "
                          "substring matching, or load an ICU-based tokenizer extension."),
        ]),
        gpt_chat('gpt-elision', 'Rust lifetime elision rules', '2025-10-21 16:20', [
            ('user', "Explain Rust's lifetime elision rules with one example each."),
            ('assistant', "Three rules let you leave lifetimes out:\n\n1. Each reference parameter gets its own "
                          "lifetime: `fn f(a: &str, b: &str)` is `fn f<'a, 'b>(a: &'a str, b: &'b str)`.\n2. With exactly "
                          "one input lifetime, the output gets it: `fn first(s: &str) -> &str`.\n3. In a method with "
                          "`&self`, the output gets the lifetime of `self`: `fn name(&self) -> &str`.\n\nIf none of them "
                          "applies, the compiler asks you to write the lifetime yourself."),
        ]),
        gpt_chat('gpt-wget', 'Docker healthcheck: curl or wget?', '2025-11-14 12:02', [
            ('user', "Alpine-based image, no curl. What's the smallest healthcheck for a web app on port 8000?"),
            ('assistant', "Alpine ships BusyBox wget, so no extra package:\n\n```dockerfile\nHEALTHCHECK --interval=10s "
                          "--timeout=3s \\\n  CMD wget -qO- http://localhost:8000/healthz || exit 1\n```\n\n`-q` keeps the "
                          "log quiet and `-O-` writes the body to stdout, which is discarded."),
        ]),
        gpt_chat('gpt-partial', 'Postgres partial index', '2025-12-01 09:44', [
            ('user', "Can I index only the rows where status = 'pending'? The table has 40 million rows and almost "
                     "none are pending."),
            ('assistant', "Yes, with a partial index:\n\n```sql\nCREATE INDEX jobs_pending ON jobs (created_at)\n  WHERE "
                          "status = 'pending';\n```\n\nIt stays tiny because it holds only the pending rows, and Postgres "
                          "uses it for any query whose WHERE clause implies `status = 'pending'`."),
        ], archived=True),
        gpt_chat('gpt-rebase', 'Rebase a feature branch onto main', '2026-01-27 14:31', [
            ('user', 'My branch is 14 commits behind main. Rebase or merge?'),
            ('assistant', "Rebase if the branch is yours alone; it keeps history linear:\n\n```bash\ngit fetch origin\n"
                          "git rebase origin/main\ngit push --force-with-lease\n```\n\n`--force-with-lease` refuses to "
                          "overwrite commits someone else pushed in the meantime. If others build on the branch, merge "
                          "instead."),
        ]),
    ]


def zip_json(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))


SSH_SHIM = r'''#!/usr/bin/env bash
# Demo stand-in for ssh: every "host" is a folder under .demo/machines. rsync calls it as
#   ssh [-o option]... HOST COMMAND...
# "laptop-lan" never answers, like a laptop that is away from home, so aih tries the next alias.
machines="$(cd "$(dirname "$0")/../machines" && pwd)"
while [ $# -gt 0 ]; do
  case "$1" in -o|-p|-l|-i|-F) shift 2 ;; -*) shift ;; *) break ;; esac
done
host=$1; shift
case "$host" in
  desktop-lan|desktop) m=desktop ;;
  laptop) m=laptop ;;
  *) echo "ssh: connect to host $host port 22: Connection timed out" >&2; exit 255 ;;
esac
cd "$machines/$m" && HOME="$machines/$m" exec sh -c "$*"
'''


# ------------------------------------------------------------------ benchmark sessions
def bench(dest_sources, n_sessions, seed=7):
    """N generated sessions of 50 messages each, straight into sources/ (no collect needed)."""
    rnd = random.Random(seed)
    words = (
        'the a to and of in is it for that you with on this be as are can if not use your or but at from by an '
        'will so when what all one have more which then there would only file run need just like time add each '
        'make way want new same should first set work data value error code line test list name case build start '
        'change check call return output input query index table row column search token tokenizer fts5 sqlite '
        'database schema migration backup restore server client proxy caddy nginx certificate renewal tls dns port '
        'docker compose container image volume network healthcheck restart service timer systemd cron journal log '
        'rust lifetime borrow struct trait async await future python asyncio task group gather exception typescript '
        'react component state hook css grid flex layout breakpoint media query git rebase merge branch commit push '
        'postgres explain analyze partial btree vacuum cache latency throughput memory cpu thread process signal '
        'kernel linux shell bash script variable path config yaml json toml parse format regex unicode accent '
        'diacritics ranking bm25 snippet highlight prefix phrase near match prompt model answer context window'
    ).split()
    weights = [1 / (i + 1) ** 0.9 for i in range(len(words))]
    base = os.path.join(dest_sources, 'claude-code', 'bench', '-home-alex-bench')
    os.makedirs(base, exist_ok=True)
    t0 = epoch('2024-01-01T00:00:00')
    for s in range(n_sessions):
        sid = uid(f'bench/{s}')
        prev, lines = None, []
        for m in range(50):
            text = ' '.join(rnd.choices(words, weights, k=rnd.randint(25, 140)))
            u = uid(f'bench/{s}/{m}')
            role = 'user' if m % 2 == 0 else 'assistant'
            stamp = dt.datetime.fromtimestamp(t0 + s * 3600 + m * 40, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            msg = {'role': role, 'content': text if role == 'user' else [{'type': 'text', 'text': text}]}
            lines.append(json.dumps({'parentUuid': prev, 'type': role, 'message': msg, 'uuid': u, 'timestamp': stamp,
                                     'sessionId': sid, 'cwd': '/home/alex/bench'}))
            prev = u
        p = os.path.join(base, sid + '.jsonl')
        with open(p, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        os.utime(p, (t0 + s * 3600, t0 + s * 3600))
    return words


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dest')
    ap.add_argument('--aih', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'aih.py'))
    ap.add_argument('--bench', type=int, default=0, metavar='N')
    a = ap.parse_args()
    base = os.path.abspath(a.dest)
    if os.path.exists(base) and os.listdir(base):
        raise SystemExit(f'{base} is not empty')
    app = os.path.join(base, 'aih')
    os.makedirs(os.path.join(app, 'inbox'), exist_ok=True)
    shutil.copy2(a.aih, os.path.join(app, 'aih.py'))
    os.symlink('aih.py', os.path.join(app, 'aih'))
    json.dump({'user_name': 'Alex',
               'machines': {'desktop': ['desktop-lan', 'desktop'], 'laptop': ['laptop-lan', 'laptop'], 'server': ['server']},
               'hostnames': {os.uname().nodename: 'server'},
               'hub': 'server'}, open(os.path.join(app, 'aih.config.json'), 'w'), indent=2)

    machines = os.path.join(base, '.demo', 'machines')
    claude_code(base, machines)

    old = dt.datetime.now().timestamp() - 600  # dropped ten minutes ago, so collect treats them as complete
    web = os.path.join(app, 'inbox', 'conversations-1.zip')
    zip_json(web, {'conversations.json': claude_web_export(),
                   'users.json': [{'uuid': uid('account'), 'full_name': 'Alex', 'email_address': 'alex@example.com'}]})
    gpt = os.path.join(app, 'inbox', 'chatgpt-export.zip')
    zip_json(gpt, {'conversations.json': chatgpt_export(), 'message_feedback.json': [],
                   'user.json': {'id': 'user-' + uid('gpt-user')[:24], 'email': 'alex@example.com'},
                   'chat.html': '<!doctype html><title>ChatGPT Data Export</title>'})
    for p in (web, gpt):
        os.utime(p, (old, old))

    shim = os.path.join(base, '.demo', 'bin', 'ssh')
    os.makedirs(os.path.dirname(shim), exist_ok=True)
    open(shim, 'w').write(SSH_SHIM)
    os.chmod(shim, os.stat(shim).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if a.bench:
        bench(os.path.join(app, 'sources'), a.bench)
    print(f'demo ready: HOME={base} PATH={os.path.dirname(shim)}:$PATH {app}/aih collect')


if __name__ == '__main__':
    main()
