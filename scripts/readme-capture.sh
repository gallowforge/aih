#!/usr/bin/env bash
# Runs inside the namespace that scripts/readme-visuals.sh sets up. Do not run it directly.
set -euo pipefail
: "${WORK:?run scripts/readme-visuals.sh instead}"
hostname server
mount -t tmpfs tmpfs /home
export HOME=/home/alex LANG=C.UTF-8 PATH="/home/alex/aih:/home/alex/.demo/bin:/usr/bin:/bin"
out="$WORK/out"

python3 "$WORK/src/demo-data.py" /home/alex --aih "$WORK/src/aih.py" >/dev/null
cd /home/alex/aih

# cap NAME 'COMMAND': saves the command line, then exactly what it printed
cap() { { printf '%s\n' "$2"; eval "$2" 2>&1; } > "$out/$1.txt"; }

cap collect 'aih collect'
cap rebuild 'aih build'
cap stats 'aih stats'
cap hero 'aih search "fts5 tokenizer" --talk -n 4'
cap hero-mobile 'aih search "fts5 tokenizer" --talk -n 3'
cap search-me 'aih search healthcheck --me -n 3'
cap search-near "aih search --raw 'NEAR(accent* fold*, 4)' --claude -n 2"
cap search-src 'aih search lifetime --source chatgpt -n 1'
id=$(python3 -c 'import sqlite3; print(sqlite3.connect("archive.db").execute("SELECT substr(id, 8, 8) FROM conversations WHERE title LIKE ?", ("Add full-text search%",)).fetchone()[0])')
cap ls 'ls chats'
cap show "aih show $id"
cap head "head -n 14 \"\$(aih show $id)\""
cp "$(aih show "$id")" "$out/doc.md"
cap check 'aih check'

# Time searches on a larger synthetic archive: 2,000 sessions of 50 messages each.
python3 "$WORK/src/demo-data.py" /home/alex/bench --aih "$WORK/src/aih.py" --bench "${BENCH:-2000}" >/dev/null
cd /home/alex/bench/aih
start=$(date +%s.%N); ./aih build >/dev/null; end=$(date +%s.%N)
python3 - "$out/bench.json" "$start" "$end" <<'PY'
import json, os, sqlite3, statistics, subprocess, sys, time
queries = ['fts5 tokenizer', 'caddy certificate', 'docker healthcheck', 'rust lifetime', 'postgres index',
           'git rebase', 'asyncio gather', 'systemd timer', 'css grid', 'unicode accent']
db = sqlite3.connect('archive.db')
messages = db.execute('SELECT count(*) FROM messages').fetchone()[0]
sql = ('SELECT c.source, c.title, p.created, p.role, p.kind, snippet(parts_fts,0,"[","]","…",18), c.md_path '
       'FROM parts_fts JOIN parts p ON p.rowid=parts_fts.rowid JOIN conversations c ON c.id=p.conv_id '
       'WHERE parts_fts MATCH ? ORDER BY rank LIMIT 20')  # the query `aih search` runs
q_ms, cli_ms, hits = [], [], []
for q in queries:
    fts = ' '.join(f'"{w}"' for w in q.split())
    hits.append(db.execute('SELECT count(*) FROM parts_fts WHERE parts_fts MATCH ?', (fts,)).fetchone()[0])
    for _ in range(15):
        t = time.perf_counter(); db.execute(sql, (fts,)).fetchall(); q_ms.append((time.perf_counter() - t) * 1000)
    for _ in range(9):
        t = time.perf_counter(); subprocess.run(['./aih', 'search', q], stdout=subprocess.DEVNULL, check=True)
        cli_ms.append((time.perf_counter() - t) * 1000)
json.dump({'messages': messages, 'queries': queries, 'matches_per_query': hits,
           'query_ms_median': round(statistics.median(q_ms), 2), 'cli_ms_median': round(statistics.median(cli_ms), 1),
           'cli_ms_p90': round(sorted(cli_ms)[int(len(cli_ms) * .9)], 1),
           'build_s': round(float(sys.argv[3]) - float(sys.argv[2]), 1),
           'db_mb': round(os.path.getsize('archive.db') / 1e6, 1)}, open(sys.argv[1], 'w'), indent=2)
PY
