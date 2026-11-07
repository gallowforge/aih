# Working with an aih archive

Instructions for Claude Code, or any agent, running in a folder that holds an aih archive. Copy this file next to your archive, or reference it from your own `CLAUDE.md`.

The archive holds every AI conversation the owner has had, word for word: claude.ai (official export, original uploads, every saved artifact version), Claude Code sessions from each machine, and ChatGPT exports. `aih collect` keeps it current.

## Treat it as evidence, not truth

Order of trust: the live system > the owner's maintained notes > newer chats > older chats.

The history spans years. It holds outdated, expired and wrong information, and the owner said different things at different times. Newer statements are usually the corrected ones. Old chats may add facts the notes lack; they never overwrite them. When chats disagree, the newest wins; record the conflict with both dates. If it is still unclear, flag it instead of guessing.

- Assistant answers can be wrong. The owner's own statements can be out of date. Quote facts with their date and chat title.
- `parts.kind = 'system'` is text the owner never typed: claude.ai memory snapshots, Claude Code system reminders, task notices, command output, interruption markers and continuation summaries. It is kept in the database but left out of the Markdown and the search index.
- Flags on a conversation: `tool_errors`, `truncated`, `subagent` (a Claude Code subagent transcript, not the owner talking), `deleted_or_hidden`, `archived`. `branches > 0` means a prompt was edited or an answer regenerated; the main line is the version that was kept.
- Resumed Claude Code sessions re-copy earlier messages. Each message is stored once, in the session where it first appeared (`extra.continues_from` names that session).
- Chats deleted on claude.ai are never imported, even though exports still list them as empty shells. Their IDs are kept in `sources/claude-web/deleted-chat-ids.txt`.

## How to use it

- Search: `./aih search "words"`. Filters: `--me` (only the owner's words), `--claude` (only answers), `--talk` (no tool output or thinking), `--source claude-web|claude-code-<machine>|chatgpt-<account>`, `--since YYYY-MM-DD`, `--newest`, `-n 50`. `--raw` passes FTS5 syntax through, for example `'NEAR(caddy certificate, 8)'`, `'tokeni*'` or `'docker NOT compose'`.
- Read: `chats/<source>/<year>/<date> <title> [id].md`. `INDEX.md` lists every chat.
- SQL: `archive.db`, tables `conversations`, `messages`, `parts`, `files` and the FTS5 index `parts_fts`.
- Update: `./aih collect` pulls new sessions, imports the inbox and rebuilds what changed. `./aih build --full` rebuilds from scratch.

## Never

- Never edit or "fix" anything under `sources/`. It is the raw record. Move removals to the trash, never `rm`.
- Never publish, upload or paste the archive anywhere. It holds private conversations.
