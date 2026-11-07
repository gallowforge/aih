#!/usr/bin/env python3
"""mine: turn the archive into dated facts for a personal knowledge base, checked by a second model.

  mine.py run [N]     extract facts from every message not mined yet (or only N batches), then reconcile
  mine.py status      what has been mined, what is waiting, what was written to the knowledge base inbox

The knowledge base is a folder of Markdown profile sections named NN-topic.md (01-identity.md,
03-devices.md, ...). mine.py never edits them. It writes review notes to an inbox folder instead.

Two stages, both resumable (a usage limit just stops the run; the next run continues):
  1. extract   the user's own words only (no assistant answers, no system noise, no subagent briefs), in
               chronological batches. A fast model turns each batch into dated candidate facts with the chat
               they came from. Output: mining/facts/<month>-<n>.jsonl
  2. reconcile per profile section, a stronger model compares the candidates with what the section already
               says. Order of trust: the profile > newer chats > older chats. Old chats only ADD what the
               profile lacks; contradictions are listed, never applied. Output: one note per section in the
               inbox folder, for a person (or an agent) to fold in.
Configure under "mining" in aih.config.json. Schedule nightly, for example with contrib/systemd/aih-mine.timer.
"""
import collections, datetime as dt, glob, hashlib, json, os, re, sqlite3, subprocess, sys, time

ROOT = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, ROOT)
from aih import CONFIG, DB  # noqa: E402  (shares aih's config file and database)

CFG = CONFIG.get('mining', {})
OUT = os.path.join(ROOT, 'mining')
FACTS = os.path.join(OUT, 'facts')
KB = os.path.expanduser(CFG.get('kb_dir', '~/kb'))
PROFILE_GLOB = CFG.get('profile_glob', 'profile/[0-9][0-9]-*.md')
INBOX = os.path.expanduser(CFG.get('inbox') or os.path.join(KB, 'inbox'))
CLAUDE = os.path.expanduser(CFG.get('claude', 'claude'))
WORKDIR = os.path.expanduser('~/.cache/aih-mining')  # neutral cwd; aih skips any transcript recorded here
EXTRACT_MODEL = CFG.get('extract_model', 'sonnet')
RECONCILE_MODEL = CFG.get('verify_model', 'opus')
HOST = CFG.get('host')  # optional: the only hostname allowed to run the miner (where the knowledge base is written)
USER = CFG.get('user_label', 'the user')
MAX_MSG = 1500        # long pastes (logs, code) are cut; the point is almost always in the first lines
MIN_MSG = 20          # "ok", "continue", "do it" carry no facts
BATCH_CHARS = 100_000
SLICE = 250           # candidates per reconcile call, so long lists are never skimmed


class LimitReached(Exception):
    pass


def log(msg):
    line = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M')} {msg}"
    print(line, flush=True)
    with open(os.path.join(OUT, 'mine.log'), 'a') as f:
        f.write(line + '\n')


def claude(prompt, model):
    """One headless Claude Code call with no tools and no saved session. Returns (text, (tokens_in, tokens_out))."""
    os.makedirs(WORKDIR, exist_ok=True)
    for attempt in range(3):
        r = subprocess.run([CLAUDE, '-p', '--model', model, '--tools', '', '--no-session-persistence',
                            '--strict-mcp-config', '--output-format', 'json'],
                           input=prompt, capture_output=True, text=True, cwd=WORKDIR, timeout=3600)
        try:
            d = json.loads(r.stdout)
        except ValueError:
            d = {'is_error': True, 'result': (r.stdout + r.stderr)[-500:]}
        text = d.get('result') or ''
        if not d.get('is_error'):
            u = d.get('usage') or {}
            return text, (u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0)
                          + u.get('cache_creation_input_tokens', 0), u.get('output_tokens', 0))
        if re.search(r'limit|quota|rate|overloaded|usage', text, re.I):
            if attempt < 2 and re.search(r'overloaded|529|rate', text, re.I):
                time.sleep(60 * (attempt + 1))
                continue
            raise LimitReached(text[:200])
        if attempt == 2:
            raise RuntimeError(text[:300])
        time.sleep(20)


def sections():
    """{'01': '01-identity.md', ...} from the knowledge base's profile folder."""
    return {os.path.basename(p)[:2]: os.path.relpath(p, KB) for p in sorted(glob.glob(os.path.join(KB, PROFILE_GLOB)))}


def fallback_section(secs):
    return str(CFG.get('fallback_section') or (max(secs) if secs else '00'))


def key_of(conv, msg, text):
    return hashlib.sha1(f'{conv}|{msg}|{text[:300]}'.encode()).hexdigest()[:16]


def load_set(name):
    p = os.path.join(OUT, name)
    return set(open(p).read().split()) if os.path.exists(p) else set()


def add_to_set(name, keys):
    with open(os.path.join(OUT, name), 'a') as f:
        f.write(''.join(k + '\n' for k in keys))


def pending_messages():
    db = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    rows = db.execute("""
        SELECT p.conv_id, p.msg_id, c.title, c.source, p.created, p.text
        FROM parts p JOIN conversations c ON c.id = p.conv_id
        JOIN messages m ON m.conv_id = p.conv_id AND m.id = p.msg_id
        WHERE p.role = 'user' AND p.kind = 'text' AND m.on_main = 1
          AND c.flags NOT LIKE '%subagent%' AND c.id NOT LIKE '%aih-mining%'
        ORDER BY p.created""").fetchall()
    mined = load_set('mined.txt')
    out = []
    for conv, msg, title, source, created, text in rows:
        t = (text or '').strip()
        if len(t) < MIN_MSG or not created:
            continue
        k = key_of(conv, msg, t)
        if k in mined:
            continue
        if len(t) > MAX_MSG:
            t = t[:MAX_MSG] + f' […{len(t) - MAX_MSG} more characters, cut]'
        out.append({'key': k, 'conv': conv, 'title': title or '(untitled)', 'source': source, 'date': created[:10], 'text': t})
    return out


EXTRACT_PROMPT = """You are helping maintain a personal knowledge base about {user}. Below are messages {user} typed
to AI assistants during {period}, each with its date and chat title. Only that side of the conversation is shown.

Extract durable facts ABOUT THIS PERSON that a future assistant should know: who they are, everyday facts about
their household, devices and accounts, their setup and how it is configured, decisions, preferences and dislikes,
how they want to be worked with, plans, purchases, health facts about themselves, habits, tastes, things they
said they never want again, corrections they made.

Rules:
- Only what the words actually show. No guessing, no general knowledge, no homework or exam content, no facts
  about the world. A question is not a fact about the person (unless it clearly reveals one, e.g. they own X).
- People change their minds. Record each fact with ITS date; do not resolve conflicts here.
- Speech-to-text slips are common ("cloud code" = Claude Code); write the real name.
- SKIP entirely: passwords, keys, tokens, card/ID/phone numbers, exact addresses; and anything about another
  person's legal status, court cases, disputes or other sensitive situations.
- One fact per item, short and specific, in English (the messages may be in any language).
- section = the best-fitting profile section number: {section_list}

Reply with ONLY a JSON array, no prose, like:
[{{"date":"2025-08-14","section":"12","kind":"preference","fact":"...","chat":"<chat title>","quote":"<their words, max 15>"}}]
kind is one of: fact, preference, decision, plan, purchase, dislike, correction, health, habit.
If nothing durable is there, reply [].

Messages:
{messages}
"""


def extract(limit_batches=None):
    os.makedirs(FACTS, exist_ok=True)
    msgs = pending_messages()
    if not msgs:
        log('extract: nothing new to mine')
        return 0
    secs = sections()
    fallback = fallback_section(secs)
    section_list = '; '.join(f'{k} {os.path.basename(v)[3:-3].replace("-", " ")}' for k, v in secs.items())
    # chronological batches; quiet months share a batch, busy months are split
    batches, cur, size = [], [], 0
    for m in msgs:
        line = f"[{m['date']} · {m['source']} · chat: {m['title']}] {m['text']}"
        if cur and size + len(line) > BATCH_CHARS:
            batches.append((cur[0][0]['date'][:7], cur)); cur, size = [], 0
        cur.append((m, line)); size += len(line)
    if cur:
        batches.append((cur[0][0]['date'][:7], cur))
    log(f'extract: {len(msgs)} messages waiting in {len(batches)} batches ({batches[0][0]} → {batches[-1][0]})')
    done = 0
    for month, batch in batches[:limit_batches]:
        period = f"{batch[0][0]['date']} to {batch[-1][0]['date']}"
        prompt = EXTRACT_PROMPT.format(user=USER, period=period, section_list=section_list,
                                       messages='\n\n'.join(line for _, line in batch))
        text, (tin, tout) = claude(prompt, EXTRACT_MODEL)
        m = re.search(r'\[.*\]', text, re.S)
        try:
            facts = json.loads(m.group(0)) if m else []
        except ValueError:
            log(f'extract {month}: reply was not valid JSON, will retry next run'); continue
        n = len(glob.glob(os.path.join(FACTS, f'{month}-*.jsonl'))) + 1
        path = os.path.join(FACTS, f'{month}-{n:02d}.jsonl')
        with open(path, 'w') as f:
            for x in facts:
                if not isinstance(x, dict) or not x.get('fact'):
                    continue
                x['id'] = hashlib.sha1(json.dumps(x, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
                x['section'] = str(x.get('section') or fallback).zfill(2)[:2]
                f.write(json.dumps(x, ensure_ascii=False) + '\n')
        add_to_set('mined.txt', [mm['key'] for mm, _ in batch])
        done += 1
        log(f'extract {month}: {len(batch)} messages → {len(facts)} candidate facts ({tin // 1000}k in, {tout // 1000}k out)')
    return done


RECONCILE_PROMPT = """You maintain a hand-corrected profile of {user}. Below is the CURRENT text of one profile section,
then candidate facts mined from years of old AI chats (dated, oldest first).

How to treat this history: it is messy, full of outdated, expired and sometimes wrong knowledge, and of
contradictions. The person said different things at different times. Newer statements, and what they fixed in
this profile, are the corrected ones. Order of trust: the profile > newer chats > older chats.

Your job, for this section only:
1. ADD: candidates that are durable, still plausibly true, and NOT already in the profile (in any wording).
   Among candidates that contradict each other, the newest wins; drop the older ones.
2. CONFLICT: candidates that contradict the profile. The profile wins and is not changed. List them only if a
   reasonable person might want to double-check (e.g. the chat is newer than the profile's own date for it).
3. Drop everything else silently: already known, outdated, trivial, one-off questions, guesses, other people's
   private matters, anything about legal status, courts or disputes, secrets.
Be strict: a short list of facts that matter beats a long list. Keep each line short.

Reply in this exact Markdown, nothing before or after:
### Add
- YYYY-MM-DD (chat "<title>"): <fact>
### Conflicts (the profile was kept)
- YYYY-MM-DD (chat "<title>"): history says <x>; profile says <y>
### Dropped
<one line: how many candidates were dropped and the main reasons>
(Write "- none" under a heading with nothing in it.)

=== PROFILE SECTION {name} ===
{profile}

=== CANDIDATE FACTS ({n}) ===
{facts}
"""


def reconcile():
    done_ids = load_set('reconciled.txt')
    pend = collections.defaultdict(list)
    for p in sorted(glob.glob(os.path.join(FACTS, '*.jsonl'))):
        for line in open(p):
            try:
                x = json.loads(line)
            except ValueError:
                continue
            if x.get('id') not in done_ids:
                pend[x['section']].append(x)
    secs = sections()
    if not pend:
        log('reconcile: nothing waiting')
        return 0
    os.makedirs(INBOX, exist_ok=True)
    today = dt.date.today().isoformat()
    n_notes = 0
    for sec in sorted(pend):
        facts = sorted(pend[sec], key=lambda x: x.get('date') or '')
        name = secs.get(sec, secs.get(fallback_section(secs)))
        profile = open(os.path.join(KB, name)).read()
        for i in range(0, len(facts), SLICE):
            chunk = facts[i:i + SLICE]
            lines = '\n'.join(f"- {x.get('date')} (chat \"{x.get('chat', '')}\") [{x.get('kind')}]: {x['fact']}"
                              + (f" — their words: \"{x['quote']}\"" if x.get('quote') else '') for x in chunk)
            text, (tin, tout) = claude(RECONCILE_PROMPT.format(user=USER, name=name, profile=profile, n=len(chunk), facts=lines),
                                       RECONCILE_MODEL)
            body = text.strip()
            adds = len(re.findall(r'^- \d{4}-\d{2}-\d{2}', body.split('### Conflicts')[0], re.M))
            if not re.search(r'^- \d{4}-\d{2}-\d{2}', body, re.M):  # nothing to add and no conflicts: no note
                add_to_set('reconciled.txt', [x['id'] for x in chunk])
                log(f'reconcile {name}: {len(chunk)} candidates, nothing new')
                continue
            note = (f"# From the AI history → {name} ({today}, part {i // SLICE + 1})\n\n"
                    f"Mined by `mine.py` from the user's own words in old chats, then checked against this section by a\n"
                    f"second model: only facts the profile lacks are under Add. Conflicts are listed for awareness; the\n"
                    f"profile was kept. Evidence for any line: `aih search \"<words>\"`.\n\n{body}\n")
            path = os.path.join(INBOX, f'{today}-history-{sec}-{i // SLICE + 1}.md')
            with open(path, 'w') as f:
                f.write(note)
            add_to_set('reconciled.txt', [x['id'] for x in chunk])
            n_notes += 1
            log(f'reconcile {name}: {len(chunk)} candidates → {adds} to add ({tin // 1000}k in, {tout // 1000}k out) → {os.path.basename(path)}')
    return n_notes


def status():
    msgs = pending_messages()
    facts = sum(1 for p in glob.glob(os.path.join(FACTS, '*.jsonl')) for _ in open(p))
    rec = len(load_set('reconciled.txt'))
    print(f'mined messages: {len(load_set("mined.txt"))}; waiting: {len(msgs)}'
          + (f' ({msgs[0]["date"]} → {msgs[-1]["date"]})' if msgs else ''))
    print(f'candidate facts: {facts}; reconciled: {rec}; waiting: {facts - rec}')
    print(f'notes in the inbox from history: {len(glob.glob(os.path.join(INBOX, "*-history-*.md")))}')


def main():
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'status':
        return status()
    if cmd != 'run':
        sys.exit(__doc__)
    if HOST and os.uname().nodename != HOST:
        sys.exit(f'mine.py is configured to run on {HOST} only (where the knowledge base is written).')
    if not sections():
        sys.exit(f'No profile sections match {os.path.join(KB, PROFILE_GLOB)}; set mining.kb_dir in aih.config.json.')
    try:
        extract(int(sys.argv[2]) if len(sys.argv) > 2 else None)
        if not pending_messages():
            reconcile()  # only once every message is mined, so each section sees all its candidates at once
        else:
            log('reconcile: waiting until extraction has caught up')
    except LimitReached as e:
        log(f'stopped: usage limit reached ({e}). The next run continues where this one stopped.')
    status()


if __name__ == '__main__':
    main()
