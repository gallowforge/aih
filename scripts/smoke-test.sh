#!/usr/bin/env bash
# End-to-end test: builds the synthetic setup from scripts/demo-data.py (three machines, a
# claude.ai export and a ChatGPT export), runs the real aih on it and checks the results.
#   scripts/smoke-test.sh
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
t="$(mktemp -d)"
trap 'rm -rf "$t"' EXIT
python3 "$repo/scripts/demo-data.py" "$t/alex" >/dev/null
export HOME="$t/alex" PATH="$t/alex/.demo/bin:$PATH"
cd "$t/alex/aih"

pass=0 fail=0
ok() { # ok "what is being checked" CONDITION...
  local what=$1; shift
  if "$@" >/dev/null 2>&1; then pass=$((pass + 1)); printf '  ok    %s\n' "$what"
  else fail=$((fail + 1)); printf '  FAIL  %s\n' "$what"; fi
}
has() { grep -qF -- "$2" <<<"$1"; }
only() { [ -n "$1" ] && ! grep -v -- "$2" <<<"$1" | grep -q .; }  # every line of $1 matches $2
sql() { python3 -c 'import sqlite3, sys; print(sqlite3.connect("archive.db").execute(sys.argv[1]).fetchone()[0])' "$1"; }
results() { grep -E '^\S+ \S+ · ' <<<"$1" || true; }  # the first line of each search result, colours removed
plain() { sed 's/\x1b\[[0-9;]*m//g'; }

echo "collect"
out=$(./aih collect)
ok "desktop is pulled over its LAN alias" has "$out" "claude-code desktop: pulled from desktop-lan"
ok "laptop falls back to its second alias" has "$out" "claude-code laptop: pulled from laptop"
ok "the hub reads its own transcripts" has "$out" "claude-code server: pulled from local"
ok "the ChatGPT export is routed to its account" has "$out" 'ChatGPT account "alex"'
ok "the claude.ai export is unpacked" has "$out" "conversations-1.zip → claude.ai export"
ok "every source file is imported" has "$out" "10 changed, 0 removed, 0 unchanged sources"
ok "the inbox is empty afterwards" test -z "$(ls inbox)"
ok "a second run re-imports nothing" has "$(./aih build)" "0 changed, 0 removed, 10 unchanged sources"
not_hub() {  # the same archive, seen from a machine that is not the hub
  python3 -c 'import json, sys; c = json.load(open("aih.config.json")); c["hub"] = "elsewhere"; json.dump(c, open(sys.argv[1], "w"))' "$t/other.json"
  ! AIH_CONFIG="$t/other.json" ./aih build >/dev/null 2>&1
}
ok "a machine that is not the hub refuses to write" not_hub

echo "import rules"
ok "17 conversations across 5 sources" test "$(sql 'SELECT count(*) || "/" || count(DISTINCT source) FROM conversations')" = 17/5
ok "the chat deleted on claude.ai is not imported" test "$(sql "SELECT count(*) FROM conversations WHERE source='claude-web'")" = 4
ok "its id is remembered" test -s sources/claude-web/deleted-chat-ids.txt
ok "a resumed session is stored once" test "$(sql "SELECT count(*) FROM conversations WHERE extra LIKE '%continues_from%'")" = 1
ok "system noise is kept in the database" test "$(sql "SELECT count(*) FROM parts WHERE kind='system'")" -gt 0
ok "the pasted screenshot is saved" has "$(./aih stats)" "claude-code-desktop    files=1 saved=1"
ok "edited and regenerated branches are counted" test "$(sql 'SELECT sum(n_branches) FROM conversations')" = 2
ok "subagent, archived and tool-error flags are set" has "$(./aih stats)" "{'archived': 1, 'subagent': 1, 'tool_errors': 2}"

echo "search"
r=$(./aih search "fts5 tokenizer" | plain)
three() { has "$1" ' claude-web · ' && has "$1" ' claude-code-laptop · ' && has "$1" ' chatgpt-alex · '; }
ok "one query finds all three sources" three "$r"
ok "--me returns only your own words" only "$(results "$(./aih search healthcheck --me | plain)")" '\[user/text\]$'
ok "--claude returns only answers" only "$(results "$(./aih search tokenizer --claude | plain)")" '\[assistant/text\]$'
ok "--source keeps to one source" only "$(results "$(./aih search lifetime --source chatgpt | plain)")" ' chatgpt-alex · '
ok "--raw takes FTS5 NEAR and prefix syntax" test "$(results "$(./aih search --raw 'NEAR(accent* fold*, 4)' --claude | plain)" | wc -l)" -eq 2
ok "accents are folded (resume finds résumé)" has "$(./aih search resume --claude | plain)" "résumé"
ok "system noise is kept out of results" test -z "$(./aih search ide_opened_file)"

echo "files"
md=$(./aih show 990035b6)
ok "show prints the chat's Markdown file" test -f "$md"
ok "the file has front matter" has "$(head -n 3 "$md")" 'source: "claude-code-laptop"'
ok "thinking is folded into <details>" grep -qF '<details><summary>Thinking</summary>' "$md"
ok "edited prompts are listed after the main line" grep -qF '## Other branches' chats/claude-web/2026/*Finding*.md
ok "INDEX.md lists every chat" test "$(grep -c '^| 20' INDEX.md)" -eq 17
ok "check says both exports are safe to delete" test "$(./aih check | grep -c 'SAFE: every chat')" -eq 2

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
