#!/usr/bin/env python3
"""Write the pages the README's glass windows show, from the captures of real aih runs.

  scripts/readme-tex.py [CAPTURE_DIR] [TEX_DIR]

Every line on these pages is copied from a capture that scripts/readme-capture.sh saved:
commands, results, counts and paths, with aih's own ANSI colours mapped to the README palette.
The chat document is the real Markdown file `aih show` pointed at, typeset as a page.
The element marked data-lift="key" is the line a scene lifts out of its window.
"""
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'docs', 'readme', '.capture')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'docs', 'readme', 'src', 'tex')
ACCENT = '--hi:#bcaaff;--hi-day:#5b3fc4;--ok:#c2b4ff'
esc = html.escape
ANSI = re.compile(r'\x1b\[([0-9;]*)m')


def cap(name):
    lines = open(os.path.join(CAP, name + '.txt'), encoding='utf-8').read().rstrip('\n').split('\n')
    return lines[0], lines[1:]


def ansi(s):
    """aih's colours: dates cyan, titles bold, hits bold yellow, paths dim."""
    cls = {'36': 'm', '1': 't', '1;33': 'hi', '2': 'f'}
    out, pos, opened = [], 0, False
    for m in ANSI.finditer(s):
        out.append(esc(s[pos:m.start()]))
        if opened:
            out.append('</span>'); opened = False
        if m.group(1) not in ('', '0'):
            out.append(f'<span class="{cls.get(m.group(1), "")}">'); opened = True
        pos = m.end()
    out.append(esc(s[pos:]))
    if opened:
        out.append('</span>')
    return ''.join(out)


def page(name, width, body, kind='term', theme='', size=None):
    style = f'width:{width}px;{ACCENT}' + (f';font-size:{size}px' if size else '')
    with open(os.path.join(OUT, name + '.html'), 'w', encoding='utf-8') as f:
        f.write(f'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="tex.css">'
                f'<body class="{kind} {theme}" style="{style}">\n{body}\n</body>\n')


def prompt(cmd):
    return f'<div class="l"><span class="p">$</span> <span class="c">{esc(cmd)}</span></div>'


def lines(ls, lift=None):
    return '\n'.join(f'<div class="l"{" data-lift=" + chr(34) + lift[1] + chr(34) if lift and i == lift[0] else ""}>{ansi(l) or " "}</div>'
                     for i, l in enumerate(ls))


def results(name, lift_first=False):
    """A search capture: the command, then each result as header, snippet and path."""
    cmd, ls = cap(name)
    out = [prompt(cmd)]
    for i in range(0, len(ls) - 2, 3):
        block = ''.join(f'<div class="l">{ansi(l)}</div>' for l in ls[i:i + 3])
        attr = ' data-lift="key"' if lift_first and i == 0 else ''
        out.append(f'<div class="gap"></div><div{attr}>{block}</div>')
    return '\n'.join(out)


def inline(s):
    s = esc(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    return re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)


def chat(theme):
    """The top of the real chat file: front matter, title and the first exchange."""
    md = open(os.path.join(CAP, 'doc.md'), encoding='utf-8').read().split('\n')
    assert md[0] == '---'
    end = md.index('---', 1)
    props = [l.split(': ', 1) for l in md[1:end]]
    keep = ('source', 'model', 'machine', 'messages', 'created')
    rows = ''.join(f'<span class="k">{esc(k)}</span><span>{esc(v.strip(chr(34)))}</span>' for k, v in props if k in keep)
    out = [f'<div class="kick">chats/claude-code-laptop/2026</div>', f'<div class="props" data-lift="key">{rows}</div>']
    i, para, inlist = end + 1, [], False
    shown_speakers = 0
    while i < len(md):
        l = md[i]
        if l.startswith('### '):
            shown_speakers += 1
            if shown_speakers > 2:
                break
            who, _, when = l[4:].partition(' · ')
            out.append(f'<h3>{esc(who)} <span>· {esc(when)}</span></h3>')
        elif l.startswith('# '):
            out.append(f'<h1>{esc(l[2:])}</h1>')
        elif l.startswith('<details><summary>'):
            label = re.match(r'<details><summary>(.*?)</summary>', l).group(1)
            out.append(f'<div class="fold">{esc(label)}</div>')
            while not md[i].startswith('</details>'):
                i += 1
        elif re.match(r'\d+\. ', l):
            if not inlist:
                out.append('<ol>'); inlist = True
            out.append(f'<li>{inline(l.split(". ", 1)[1])}</li>')
        elif l.strip():
            out.append(f'<p>{inline(l)}</p>')
        if inlist and not re.match(r'\d+\. ', md[i + 1] if i + 1 < len(md) else ''):
            out.append('</ol>'); inlist = False
        i += 1
    page('chat' if theme == 'dark' else 'chat-light', 560, '\n'.join(out), 'doc', theme)


def main():
    os.makedirs(OUT, exist_ok=True)
    # hero: the best match first
    page('search', 600, results('hero-mobile', lift_first=True))
    # aih stats
    cmd, ls = cap('stats')
    page('stats', 800, prompt(cmd) + '\n' + lines(ls), size=12.8)
    # filters: your own words, then FTS5 syntax through --raw
    me, near = results('search-me'), results('search-near', lift_first=True)
    page('me', 640, me)
    page('near', 600, near)
    page('source', 560, results('search-src'))
    # collect, then a second run that finds nothing to do
    cmd, ls = cap('collect')
    rcmd, rls = cap('rebuild')
    page('collect', 600, prompt(cmd) + '\n' + lines(ls) + '\n<div class="gap"></div>\n' + prompt(rcmd) + '\n' + lines(rls, (0, 'key')))
    # where a chat lives
    lcmd, lls = cap('ls')
    scmd, sls = cap('show')
    page('show', 560, prompt(lcmd) + '\n' + lines(lls) + '\n<div class="gap"></div>\n' + prompt(scmd) + '\n' + lines(sls))
    chat('dark'); chat('light')
    # the safe-to-delete check
    cmd, ls = cap('check')
    first = next(i for i, l in enumerate(ls) if 'SAFE' in l)
    body = []
    for i, l in enumerate(ls):
        t = ansi(l)
        if 'SAFE:' in l:
            t = re.sub(r'(SAFE)', r'<span class="ok">\1</span>', t)
        if i == first:   # lift the words, not the indent
            pre = len(t) - len(t.lstrip(' '))
            t = t[:pre] + f'<span data-lift="key">{t[pre:]}</span>'
        body.append(f'<div class="l{" lifted" if i == first else ""}">{t or " "}</div>')
    page('check', 600, prompt(cmd) + '\n' + '\n'.join(body))
    # the numbers the copy quotes, measured by the capture
    import json
    bench = json.load(open(os.path.join(CAP, 'bench.json')))
    smoke = open(os.path.join(ROOT, 'scripts', 'smoke-test.sh')).read()
    kinds = {'claude-web': 'claude.ai', 'claude-code': 'Claude Code', 'chatgpt': 'ChatGPT'}
    seen = {k for l in cap('stats')[1] if 'chats=' in l for k in kinds if l.startswith(k)}
    json.dump({'ms': f"{bench['query_ms_median']:.1f}", 'messages': f"{bench['messages']:,}", 'build_s': f"{bench['build_s']:.1f}",
               'cli_ms': round(bench['cli_ms_median']), 'sources': len(seen),
               'smoke': len(re.findall(r'^\s*ok "', smoke, re.M))}, open(os.path.join(OUT, 'facts.json'), 'w'), indent=1)
    print('tex pages ->', os.path.relpath(OUT, ROOT))


if __name__ == '__main__':
    main()
