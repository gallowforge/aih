#!/usr/bin/env python3
"""Render the README scenes from the captures that scripts/readme-capture.sh saved.

  scripts/readme-visuals.py CAPTURE_DIR OUT_DIR [--only hero,stats,...] [--keep-html]

Every terminal shows a real command and exactly what it printed, ANSI colours included (aih
search emits them; output without colours gets a light, consistent tint). Diagrams and tiles
take their numbers from the same captures, never from this file. Each scene is an HTML page:
Chrome measures it, screenshots it at 1.6x (wide) or 1.35x (portrait), and ImageMagick
writes WebP. Needs google-chrome-stable (or $CHROME) and magick.
"""
import html, json, os, re, shutil, subprocess, sys, tempfile

CHROME = os.environ.get('CHROME', 'google-chrome-stable')
WIDE, NARROW = 1200, 800
esc = html.escape

# ------------------------------------------------------------------ captures
CAP = sys.argv[1] if len(sys.argv) > 1 else 'docs/readme/.capture'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'docs/readme'
ONLY = next((a[7:].split(',') for a in sys.argv if a.startswith('--only=')), None)
KEEP = '--keep-html' in sys.argv


def cap(name):
    """(command, output lines) of one capture."""
    lines = open(os.path.join(CAP, name + '.txt'), encoding='utf-8').read().rstrip('\n').split('\n')
    return lines[0], lines[1:]


BENCH = json.load(open(os.path.join(CAP, 'bench.json')))

# ------------------------------------------------------------------ text helpers
ANSI = re.compile(r'\x1b\[([0-9;]*)m')
ANSI_CLASS = {'36': 'a-cyan', '1': 'a-bold', '1;33': 'a-hit', '2': 'a-dim'}


def ansi(s):
    out, pos, opened = [], 0, False
    for m in ANSI.finditer(s):
        out.append(esc(s[pos:m.start()]))
        if opened:
            out.append('</span>')
            opened = False
        if m.group(1) not in ('', '0'):
            out.append(f'<span class="{ANSI_CLASS.get(m.group(1), "")}">')
            opened = True
        pos = m.end()
    out.append(esc(s[pos:]))
    if opened:
        out.append('</span>')
    return ''.join(out)


def command(cmd):
    """Light syntax colouring of a shell command line."""
    parts = re.findall(r"""'[^']*'|"[^"]*"|\$\([^)]*\)"?|\S+|\s+""", cmd)
    out, first, sub = [], True, False
    for p in parts:
        if p.isspace():
            out.append(p)
        elif first:
            out.append(f'<span class="c-prog">{esc(p)}</span>'); first = False; sub = p == 'aih'
        elif sub and not p.startswith('-'):
            out.append(f'<span class="c-sub">{esc(p)}</span>'); sub = False
        elif p.startswith('-'):
            out.append(f'<span class="c-flag">{esc(p)}</span>'); sub = False
        elif p[0] in '\'"':
            out.append(f'<span class="c-str">{esc(p)}</span>')
        else:
            out.append(f'<span class="c-arg">{esc(p)}</span>')
    return ''.join(out)


def prompt():
    return '<span class="ps">alex@server</span><span class="pc">:</span><span class="pw">~/aih</span><span class="pd">$</span> '


def lines_html(lines, tint=None):
    rows = []
    for l in lines:
        body = tint(l) if tint else ansi(l)
        ind = len(l) - len(l.lstrip(' '))
        rows.append(f'<div class="ln" style="--ind:{ind + 2}ch">{body or "&nbsp;"}</div>')
    return ''.join(rows)


def terminal(blocks, fs=14.5, title='alex@server: ~/aih', cursor=True, style='', tint=None):
    """blocks: [(command, output lines)]; output keeps its ANSI colours unless a tint function is given."""
    body = []
    for i, (cmd, out) in enumerate(blocks):
        if i:
            body.append('<div class="gap"></div>')
        body.append(f'<div class="ln cmd">{prompt()}{command(cmd)}</div>')
        body.append(lines_html(out, tint))
    if cursor:
        body.append(f'<div class="gap"></div><div class="ln cmd">{prompt()}<span class="cursor"></span></div>')
    return (f'<div class="term" style="--fs:{fs}px;{style}"><div class="bar"><i></i><i></i><i></i>'
            f'<span>{esc(title)}</span></div><div class="tbody">{"".join(body)}</div></div>')


MARK = '''<svg viewBox="0 0 64 64" width="{s}" height="{s}" aria-hidden="true"><defs>
<linearGradient id="mg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#c2b8ff"/><stop offset=".55" stop-color="#9b8cff"/><stop offset="1" stop-color="#6c58ea"/></linearGradient></defs>
<rect width="64" height="64" rx="17" fill="url(#mg)"/>
<path d="M18 17h28a5 5 0 0 1 5 5v15a5 5 0 0 1-5 5H31l-8.5 6.5V42H18a5 5 0 0 1-5-5V22a5 5 0 0 1 5-5z" fill="none" stroke="#fff" stroke-width="3.4" stroke-linejoin="round"/>
<circle cx="31" cy="29" r="5.6" fill="none" stroke="#fff" stroke-width="3.2"/><path d="M35.2 33.2l4.6 4.6" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/>
</svg>'''


def brand(size=26):
    return f'<div class="brand" style="font-size:{size}px">{MARK.format(s=round(size * 1.55))}<span>aih</span></div>'


# ------------------------------------------------------------------ CSS
CSS = r'''
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: transparent; }
body { font-family: Inter, system-ui, sans-serif; color: #f2f3f7; -webkit-font-smoothing: antialiased; font-feature-settings: 'cv11', 'ss01'; }
.card { position: relative; overflow: hidden; border-radius: 28px; isolation: isolate;
  background:
    radial-gradient(var(--gw, 1000px) var(--gh, 560px) at var(--gx, 50%) var(--gy, -10%), rgba(155, 140, 255, .29), transparent 70%),
    radial-gradient(720px 480px at var(--ax, 100%) var(--ay, 112%), rgba(155, 140, 255, .08), transparent 70%),
    linear-gradient(180deg, #0d0e15, #07080b); }
.card::before { content: ''; position: absolute; inset: 0; z-index: -1;
  background-image: radial-gradient(rgba(255, 255, 255, .075) 1.1px, transparent 1.5px); background-size: 26px 26px;
  -webkit-mask-image: radial-gradient(var(--gw, 1000px) var(--gh, 560px) at var(--gx, 50%) var(--gy, -10%), #000, transparent 75%); }
.card.square, .card.square::after { border-radius: 0; }
.card::after { content: ''; position: absolute; inset: 0; border-radius: 28px; pointer-events: none; z-index: 30;
  box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, .085), inset 0 1.5px 0 rgba(255, 255, 255, .06); }
.col { display: flex; flex-direction: column; }
.row { display: flex; }
.center { align-items: center; text-align: center; }

.brand { display: flex; align-items: center; gap: .55em; font-weight: 800; letter-spacing: -.035em; }
.brand svg { filter: drop-shadow(0 10px 26px rgba(155, 140, 255, .45)); }
h1 { font-weight: 800; letter-spacing: -.045em; line-height: 1.0; color: #f6f6fb; text-wrap: balance; }
.grad { background: linear-gradient(92deg, #d4ccff, #a597ff 45%, #8571f5); -webkit-background-clip: text; background-clip: text; color: transparent; }
.lede { color: #9ba1b3; font-weight: 500; line-height: 1.45; letter-spacing: -.01em; text-wrap: balance; }
.lede b { color: #e4e6ee; font-weight: 600; }
.eyebrow { font: 700 12.5px/1 Inter; letter-spacing: .14em; text-transform: uppercase; color: #a99cff; }

.chips { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.chip { display: inline-flex; align-items: center; gap: 9px; height: 36px; padding: 0 16px 0 14px; border-radius: 999px;
  font-weight: 600; font-size: 15px; color: #d9dce6; background: rgba(255, 255, 255, .035); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .1); }
.chip i { width: 8px; height: 8px; border-radius: 50%; background: var(--c); box-shadow: 0 0 12px var(--c); }
.chip em { font-style: normal; color: #7f8597; font-weight: 500; }

/* terminal */
.term { position: relative; border-radius: 14px; overflow: hidden; background: #0b0d13; text-align: left;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, .105), 0 40px 80px -34px rgba(0, 0, 0, .9), 0 24px 110px -44px rgba(155, 140, 255, .38); }
.term .bar { position: relative; height: 38px; display: flex; align-items: center; gap: 8px; padding: 0 16px;
  background: linear-gradient(#16181f, #111319); border-bottom: 1px solid rgba(255, 255, 255, .06); }
.term .bar i { width: 12px; height: 12px; border-radius: 50%; background: #ec6a5e; }
.term .bar i:nth-child(2) { background: #f2bf4f; } .term .bar i:nth-child(3) { background: #5fc454; }
.term .bar span { position: absolute; left: 0; right: 0; text-align: center; font: 500 13px Inter; color: #7d8394; letter-spacing: .01em; }
.tbody { padding: 18px 24px 22px; font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: var(--fs, 14.5px);
  line-height: 1.62; color: #d3d7e1; font-variant-ligatures: none; }
.ln { white-space: pre-wrap; overflow-wrap: break-word; padding-left: var(--ind, 0); text-indent: calc(-1 * var(--ind, 0)); }
.ln.cmd { color: #f1f2f6; }
.gap { height: .7em; }
.ps { color: #b2a6ff; font-weight: 600; } .pc { color: #5d6374; } .pw { color: #7fd6ee; font-weight: 600; } .pd { color: #5d6374; }
.c-prog { color: #fff; font-weight: 700; } .c-sub { color: #c4baff; font-weight: 600; } .c-flag { color: #8c94a8; }
.c-str { color: #ffd27a; } .c-arg { color: #e8eaf0; } .c-flag, .c-str { white-space: nowrap; }
.a-cyan { color: #7fd6ee; } .a-bold { color: #fff; font-weight: 700; } .a-dim { color: #5f6678; }
.a-hit { color: #ffd27a; font-weight: 700; background: rgba(255, 210, 122, .13); border-radius: 3px; box-shadow: 0 0 0 1.5px rgba(255, 210, 122, .13); }
.t-ok { color: #63e3a4; font-weight: 700; } .t-num { color: #c4baff; font-weight: 600; } .t-src { color: #fff; font-weight: 600; }
.t-mute { color: #6b7284; } .t-key { color: #8c94a8; } .t-val { color: #e8eaf0; } .t-str { color: #ffd27a; } .t-rule { color: #5d6374; }
.cursor { display: inline-block; width: .62em; height: 1.18em; vertical-align: -.24em; background: #9b8cff; border-radius: 1.5px;
  box-shadow: 0 0 14px rgba(155, 140, 255, .7); }

/* panels and tiles */
.panel { border-radius: 18px; background: linear-gradient(180deg, rgba(255, 255, 255, .045), rgba(255, 255, 255, .02));
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .09), 0 30px 60px -30px rgba(0, 0, 0, .7); backdrop-filter: blur(6px); }
.ph { font: 700 13px/1 Inter; letter-spacing: .13em; text-transform: uppercase; color: #a99cff; }
.pt { font-weight: 700; font-size: 20px; letter-spacing: -.02em; color: #f4f5f9; }
.ps2 { color: #8a90a2; font-weight: 500; font-size: 14px; line-height: 1.45; }
.flag { display: grid; grid-template-columns: 84px 1fr; align-items: baseline; gap: 14px; padding: 11px 0; border-top: 1px solid rgba(255, 255, 255, .06); }
.flag:first-of-type { border-top: 0; }
.flag code { font: 600 14px 'JetBrains Mono'; color: #c4baff; }
.flag span { font-size: 14.5px; color: #c9cdd8; font-weight: 500; line-height: 1.35; }
.flag span em { font-style: normal; color: #7d8394; }

.stat .n { font-weight: 800; letter-spacing: -.05em; line-height: 1; color: #f6f6fb; font-variant-numeric: tabular-nums; white-space: nowrap; }
.stat .n small { font-size: .5em; letter-spacing: -.02em; margin-left: .08em; color: #c8cbd6; font-weight: 700; }
.stat .n.grad { color: transparent; } .stat .n.grad small { color: transparent; }
.stat .l { margin-top: 12px; font-weight: 700; color: #e3e6ee; }
.stat .s { margin-top: 5px; font-weight: 500; color: #7f8697; line-height: 1.35; }

/* diagram */
.node { position: absolute; border-radius: 16px; padding: 16px 18px; background: linear-gradient(180deg, #151722, #0f1118);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .1), 0 24px 50px -28px rgba(0, 0, 0, .9); }
.node.hub { background: radial-gradient(120% 90% at 50% 0%, rgba(155, 140, 255, .22), transparent 70%), linear-gradient(180deg, #181a28, #10111a);
  box-shadow: inset 0 0 0 1.5px rgba(155, 140, 255, .55), 0 0 60px -10px rgba(155, 140, 255, .35), 0 30px 60px -30px rgba(0, 0, 0, .9); }
.node.dash { background: rgba(255, 255, 255, .02); box-shadow: none; border: 1.5px dashed rgba(155, 140, 255, .38); }
.node .k { font: 700 11.5px/1 Inter; letter-spacing: .13em; text-transform: uppercase; color: #8c84c9; }
.node .t { margin-top: 8px; font-weight: 700; font-size: 18px; letter-spacing: -.02em; color: #f4f5f9; display: flex; align-items: center; gap: 8px; }
.node .t code, .node code { font-family: 'JetBrains Mono'; font-weight: 600; }
.node .d { margin-top: 6px; font-size: 13.5px; line-height: 1.45; color: #9096a8; font-weight: 500; }
.node .d code { font-size: 12.5px; color: #c4baff; font-weight: 500; }
.node ul { margin-top: 10px; list-style: none; display: grid; gap: 7px; }
.node li { font-size: 13.5px; color: #c3c7d3; font-weight: 500; padding-left: 16px; position: relative; line-height: 1.35; }
.node li::before { content: ''; position: absolute; left: 2px; top: .52em; width: 6px; height: 6px; border-radius: 50%; background: #9b8cff; }
.pill { display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 9px; border-radius: 999px; font: 600 12px/1 Inter; }
.pill.ok { color: #63e3a4; background: rgba(99, 227, 164, .1); box-shadow: inset 0 0 0 1px rgba(99, 227, 164, .28); }
.pill.no { color: #ff8b8b; background: rgba(255, 120, 120, .08); box-shadow: inset 0 0 0 1px rgba(255, 120, 120, .25); }
.pill.vi { color: #c4baff; background: rgba(155, 140, 255, .12); box-shadow: inset 0 0 0 1px rgba(155, 140, 255, .3); }
.wire { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
.wire path { fill: none; stroke: rgba(155, 140, 255, .55); stroke-width: 1.6; }
.wire path.soft { stroke: rgba(255, 255, 255, .16); stroke-dasharray: 4 5; }
.wire text { font: 600 12px Inter; fill: #9a92d6; letter-spacing: .02em; }
.lbl { position: absolute; font: 600 12px/1 Inter; color: #a69de6; background: #0d0e15; padding: 5px 9px; border-radius: 999px;
  box-shadow: inset 0 0 0 1px rgba(155, 140, 255, .3); white-space: nowrap; }
.colh { position: absolute; font: 700 12px/1 Inter; letter-spacing: .16em; text-transform: uppercase; color: #6f6a99; }

/* document */
.doc { position: relative; border-radius: 14px; overflow: hidden; background: #0e1016; text-align: left;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, .105), 0 40px 80px -34px rgba(0, 0, 0, .9), 0 24px 110px -44px rgba(155, 140, 255, .32); }
.doc .tab { height: 42px; display: flex; align-items: center; gap: 10px; padding: 0 16px; background: linear-gradient(#16181f, #111319);
  border-bottom: 1px solid rgba(255, 255, 255, .06); font: 500 13px Inter; color: #9aa0b1; white-space: nowrap; overflow: hidden; }
.doc .tab b { color: #e6e8ef; font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
.doc .tab .pill { margin-left: auto; flex: none; }
.doc .page { padding: 22px 28px 0; font-size: 14.5px; line-height: 1.6; color: #c9cdd8; }
.doc .props { display: grid; grid-template-columns: 1fr 1fr; gap: 0 24px; padding: 12px 14px; border-radius: 10px; background: rgba(255, 255, 255, .03);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .07); margin-bottom: 18px; }
.doc .props div { display: flex; gap: 10px; padding: 4px 0; font-size: 12.5px; min-width: 0; }
.doc .props span { color: #737a8c; width: 70px; flex: none; }
.doc .props b { color: #dfe2ea; font-weight: 500; font-family: 'JetBrains Mono'; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.doc h1 { font-size: 25px; letter-spacing: -.03em; line-height: 1.15; margin: 4px 0 6px; padding-bottom: 12px; border-bottom: 1px solid rgba(255, 255, 255, .08); }
.doc h3 { display: flex; align-items: center; gap: 9px; margin: 18px 0 8px; font-size: 13.5px; font-weight: 700; color: #e8eaf0; letter-spacing: -.005em; }
.doc h3 i { width: 22px; height: 22px; border-radius: 7px; display: grid; place-items: center; font: 800 11px Inter; font-style: normal; color: #0b0c12; background: #9b8cff; }
.doc h3.as i { background: #e9e6dc; } .doc h3.tool i { background: #2a2e3a; color: #9aa0b1; }
.doc h3 small { color: #6f7688; font-weight: 500; font-size: 12.5px; }
.doc p { margin: 6px 0; }
.doc ol { margin: 6px 0 6px 20px; } .doc li { margin: 3px 0; padding-left: 4px; }
.doc code { font-family: 'JetBrains Mono'; font-size: .86em; padding: 1px 5px; border-radius: 5px; background: rgba(155, 140, 255, .12); color: #d6cfff; }
.doc pre { margin: 8px 0; padding: 12px 14px; border-radius: 9px; background: #090a0f; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .07);
  font: 12.5px/1.6 'JetBrains Mono'; color: #cfd3dd; white-space: pre-wrap; }
.doc pre code { background: none; padding: 0; color: inherit; font-size: inherit; }
.doc details { margin: 7px 0; border-radius: 9px; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .08); background: rgba(255, 255, 255, .022); }
.doc summary { list-style: none; display: flex; align-items: center; gap: 9px; padding: 8px 12px; font-size: 13px; color: #aeb3c2; font-weight: 600; }
.doc summary::before { content: ''; width: 0; height: 0; border-left: 5px solid #8c84c9; border-top: 4px solid transparent; border-bottom: 4px solid transparent; }
.doc details[open] summary::before { transform: rotate(90deg); }
.doc details pre { margin: 0 10px 10px; }
.doc .fade { position: absolute; left: 0; right: 0; bottom: 0; height: 120px; background: linear-gradient(180deg, transparent, #0e1016 85%); }
.kw { color: #c4baff; } .sq { color: #ffd27a; }

/* timeline */
.tl { position: relative; }
.tl .rowx { display: grid; grid-template-columns: 210px 1fr 150px; align-items: center; height: 46px; border-top: 1px solid rgba(255, 255, 255, .055); }
.tl .rowx:first-of-type { border-top: 0; }
.tl .src { font: 600 14px 'JetBrains Mono'; color: #eef0f5; display: flex; align-items: center; gap: 10px; }
.tl .src i { width: 9px; height: 9px; border-radius: 3px; background: var(--c); }
.tl .track { position: relative; height: 100%; }
.tl .seg { position: absolute; top: 50%; height: 10px; margin-top: -5px; border-radius: 99px; background: linear-gradient(90deg, var(--c), color-mix(in srgb, var(--c) 60%, #fff));
  box-shadow: 0 0 18px -2px var(--c); }
.tl .seg::before, .tl .seg::after { content: ''; position: absolute; top: 50%; width: 12px; height: 12px; margin-top: -6px; border-radius: 50%; background: #0d0e15; box-shadow: inset 0 0 0 2.5px var(--c); }
.tl .seg::before { left: -6px; } .tl .seg::after { right: -6px; }
.tl .num { text-align: right; font-size: 14px; color: #9aa0b1; font-weight: 500; }
.tl .num b { color: #f2f3f7; font-weight: 700; font-variant-numeric: tabular-nums; }
.tl .grid { position: absolute; top: 0; bottom: 0; width: 1px; background: rgba(255, 255, 255, .05); }
.tl .axis { display: grid; grid-template-columns: 210px 1fr 150px; margin-top: 8px; }
.tl .axis .ticks { position: relative; height: 16px; }
.tl .axis .ticks span { position: absolute; transform: translateX(-50%); font: 600 11.5px Inter; color: #6b7284; letter-spacing: .04em; text-transform: uppercase; }

.verdict { display: flex; gap: 16px; align-items: flex-start; padding: 20px 22px; }
.verdict .ic { flex: none; width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; background: rgba(99, 227, 164, .12);
  box-shadow: inset 0 0 0 1px rgba(99, 227, 164, .35), 0 0 26px -6px rgba(99, 227, 164, .5); }
.verdict .src { font: 600 15px 'JetBrains Mono'; color: #fff; }
.verdict .big { margin-top: 6px; font-size: 26px; font-weight: 800; letter-spacing: -.035em; color: #f4f5f9; }
.verdict .big b { color: #63e3a4; }
.verdict .sub { margin-top: 4px; font-size: 14px; color: #8a90a2; font-weight: 500; line-height: 1.4; }
'''

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=block" rel="stylesheet">')


def card(width, inner, pad='56px', vars_='', extra=''):
    return f'<div class="card" style="width:{width}px;padding:{pad};{vars_}{extra}">{inner}</div>'


# ------------------------------------------------------------------ tints for captures without colours
def tint_stats(l):
    s = esc(l)
    s = re.sub(r'^(\S+)', r'<span class="t-src">\1</span>', s)
    s = re.sub(r'(\w[\w-]*)=(\d+)', r'<span class="t-key">\1=</span><span class="t-num">\2</span>', s)
    s = re.sub(r'(\d{4}-\d{2}-\d{2})', r'<span class="a-cyan">\1</span>', s)
    s = s.replace('→', '<span class="t-mute">→</span>')
    s = re.sub(r'^(<span class="t-src">)flags:', r'<span class="t-key">flags:', s)
    return s


def tint_check(l):
    s = esc(l)
    if 'NOT SAFE:' in s:
        return s.replace('NOT SAFE:', '<span class="a-hit">NOT SAFE:</span>')
    if s.strip().startswith('SAFE:'):
        return s.replace('SAFE:', '<span class="t-ok">SAFE:</span>')
    s = re.sub(r'^(\s+)([\w-]+): export', r'\1<span class="t-src">\2</span>: export', s)
    s = re.sub(r'^(\s+)files:', r'\1<span class="t-key">files:</span>', s)
    s = re.sub(r'(\d+)( chats| days| referenced| without|;)', r'<span class="t-num">\1</span>\2', s)
    return s


def tint_collect(l):
    s = esc(l)
    s = re.sub(r'^(\s+)([\w-]+): (\d+)$', r'\1<span class="t-src">\2</span>: <span class="t-num">\3</span>', s)
    s = re.sub(r'^(\d+) changed, (\d+) removed, (\d+) unchanged',
               r'<span class="t-num">\1</span> changed, <span class="t-num">\2</span> removed, <span class="t-num">\3</span> unchanged', s)
    s = re.sub(r'pulled from (\S+)', r'pulled from <span class="t-ok">\1</span>', s)
    s = re.sub(r'^(claude-code|inbox)', r'<span class="t-key">\1</span>', s)
    s = re.sub(r'→ (.*)$', r'<span class="t-mute">→</span> <span class="t-val">\1</span>', s)
    return s


def tint_head(l):
    s = esc(l)
    if s == '---':
        return '<span class="t-rule">---</span>'
    m = re.match(r'^([\w_]+): (.*)$', s)
    if m:
        v = m.group(2)
        v = f'<span class="t-str">{v}</span>' if v.startswith('&quot;') else f'<span class="t-num">{v}</span>'
        return f'<span class="t-key">{m.group(1)}:</span> {v}'
    return s


def tint_plain(l):
    return f'<span class="t-val">{esc(l)}</span>'


# ------------------------------------------------------------------ Markdown -> document card
def inline(s):
    s = esc(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    return s


SQL_KW = r'\b(CREATE|VIRTUAL|TABLE|USING|SELECT|FROM|WHERE|JOIN|ON|ORDER|BY|LIMIT|MATCH|IF|NOT|EXISTS)\b'


def code_html(body, lang):
    s = esc(body)
    if lang in ('sql',):
        s = re.sub(r"(&#x27;[^&]*?&#x27;)", r'<span class="sq">\1</span>', s)
        s = re.sub(SQL_KW, r'<span class="kw">\1</span>', s)
    if lang == 'bash':
        s = re.sub(r'^(\w+)', r'<span class="kw">\1</span>', s)
    return f'<pre><code>{s}</code></pre>'


def markdown_doc(md, open_summaries=('Tool: Bash',)):
    """Render the subset aih writes: front matter, #/### headings, paragraphs, lists, fences, <details>."""
    fm, body = {}, md
    if md.startswith('---\n'):
        head, body = md[4:].split('\n---\n', 1)
        for line in head.split('\n'):
            k, _, v = line.partition(': ')
            fm[k] = json.loads(v) if v else ''
    lines, out, i = body.split('\n'), [], 0
    para = []

    def flush():
        if para:
            out.append(f'<p>{inline(" ".join(para))}</p>')
            para.clear()
    while i < len(lines):
        l = lines[i]
        if l.startswith('```'):
            flush()
            lang, buf = l[3:].strip(), []
            i += 1
            while not lines[i].startswith('```'):
                buf.append(lines[i]); i += 1
            out.append(code_html('\n'.join(buf), lang))
        elif l.startswith('<details><summary>'):
            flush()
            summary = re.match(r'<details><summary>(.*?)</summary>', l).group(1)
            buf = []
            i += 1
            while not lines[i].startswith('</details>'):
                buf.append(lines[i]); i += 1
            inner = markdown_doc('\n'.join(buf))[1] if summary in open_summaries else ''
            out.append(f'<details{" open" if inner else ""}><summary>{esc(summary)}</summary>{inner}</details>')
        elif l.startswith('# '):
            flush(); out.append(f'<h1>{inline(l[2:])}</h1>')
        elif l.startswith('### '):
            flush()
            who, _, when = l[4:].partition(' · ')
            cls = 'me' if who not in ('Assistant', 'Tool output', 'System') else ('as' if who == 'Assistant' else 'tool')
            badge = {'me': who[:1], 'as': 'AI', 'tool': '↳'}[cls]
            out.append(f'<h3 class="{cls}"><i>{badge}</i>{esc(who)} <small>{esc(when)}</small></h3>')
        elif re.match(r'^\d+\. ', l):
            flush()
            items = []
            while i < len(lines) and re.match(r'^\d+\. ', lines[i]):
                items.append(f'<li>{inline(re.sub(r"^\d+\. ", "", lines[i]))}</li>'); i += 1
            out.append(f'<ol>{"".join(items)}</ol>')
            continue
        elif not l.strip():
            flush()
        else:
            para.append(l)
        i += 1
    flush()
    return fm, ''.join(out)


def document(md, path, height, width=None):
    fm, body = markdown_doc(md)
    props = [('source', fm.get('source')), ('machine', fm.get('machine')), ('model', fm.get('model')),
             ('messages', fm.get('messages')), ('created', (fm.get('created') or '')[:16].replace('T', ' ')), ('branches', fm.get('branches'))]
    grid = ''.join(f'<div><span>{k}</span><b>{esc(str(v))}</b></div>' for k, v in props)
    name = os.path.basename(path)
    return (f'<div class="doc" style="height:{height}px;{f"width:{width}px;" if width else ""}"><div class="tab">'
            f'<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#8c84c9" stroke-width="1.5"><path d="M4 1.75h5.5L13 5.25v9H4z"/><path d="M9.5 1.75v3.5H13"/></svg>'
            f'<b>{esc(name)}</b><span class="pill vi">Markdown</span></div><div class="page"><div class="props">{grid}</div>{body}</div><div class="fade"></div></div>')


# ------------------------------------------------------------------ data from captures
def parse_stats():
    rows = []
    for l in cap('stats')[1]:
        m = re.match(r'(\S+)\s+chats=(\d+)\s+messages=(\d+)\s+with-branches=(\d+)\s+(\S+) → (\S+)', l)
        if m:
            rows.append(dict(src=m.group(1), chats=int(m.group(2)), msgs=int(m.group(3)), br=int(m.group(4)), a=m.group(5), b=m.group(6)))
    return rows


SRC_COLOR = {'claude-web': '#a597ff', 'claude-code-desktop': '#7fd6ee', 'claude-code-laptop': '#5fb8ea',
             'claude-code-server': '#58e0c8', 'chatgpt-alex': '#ffd27a'}


def month_index(d):
    y, m, day = map(int, d.split('-'))
    return y * 12 + (m - 1) + (day - 1) / 31


def timeline(rows, label_w=210, num_w=150, compact=False):
    lo = min(month_index(r['a']) for r in rows)
    hi = max(month_index(r['b']) for r in rows)
    lo, hi = int(lo), int(hi) + 1
    span = hi - lo
    pos = lambda v: (v - lo) / span * 100
    months = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
    ticks = ''.join(f'<span style="left:{pos(k):.2f}%">{months[k % 12]}{" ’" + str(k // 12)[2:] if k % 12 == 0 or k == lo else ""}</span>'
                    for k in range(lo, hi + 1))
    grid = ''.join(f'<i class="grid" style="left:{pos(k):.2f}%"></i>' for k in range(lo, hi + 1))
    cols = f'grid-template-columns:{label_w}px 1fr {num_w}px'
    body = ''
    for r in sorted(rows, key=lambda r: r['a']):
        c = SRC_COLOR.get(r['src'], '#9b8cff')
        a, b = pos(month_index(r['a'])), pos(month_index(r['b']))
        nums = f'<b>{r["chats"]}</b> chats · <b>{r["msgs"]}</b> msgs' if not compact else f'<b>{r["chats"]}</b> · <b>{r["msgs"]}</b>'
        body += (f'<div class="rowx" style="{cols};--c:{c}"><div class="src"><i></i>{r["src"]}</div>'
                 f'<div class="track">{grid}<div class="seg" style="left:{a:.2f}%;width:{max(b - a, .8):.2f}%"></div></div>'
                 f'<div class="num">{nums}</div></div>')
    return f'<div class="tl">{body}<div class="axis" style="{cols}"><span></span><div class="ticks">{ticks}</div><span></span></div></div>'


def stat(n, l, s, accent=False, sizes=(52, 16, 13.5)):
    return (f'<div class="stat"><div class="n{" grad" if accent else ""}" style="font-size:{sizes[0]}px">{n}</div>'
            f'<div class="l" style="font-size:{sizes[1]}px">{l}</div><div class="s" style="font-size:{sizes[2]}px">{s}</div></div>')


def numbers():
    rows = parse_stats()
    n_src = len({'claude-code' if r['src'].startswith('claude-code') else r['src'].split('-')[0] for r in rows})
    q = round(BENCH['query_ms_median'], 1)
    k = BENCH['messages'] // 1000
    return [
        (str(n_src), 'Sources', 'claude.ai, Claude Code, ChatGPT'),
        (f'{q:g}<small>ms</small>', 'Median search', f'over {k}k messages'),
        (f'{round(BENCH["build_s"], 1):g}<small>s</small>', 'Full rebuild', f'all {k}k messages'),
        ('1<small>h</small>', 'Collection cycle', 'on every machine'),
        ('0', 'Cloud calls', 'your disk only'),
    ]


# ------------------------------------------------------------------ scenes
def hero(mobile=False):
    blocks = [cap('hero-mobile' if mobile else 'hero')]
    chips = ('<div class="chips" style="margin-top:{m}px">'
             '<span class="chip" style="--c:#a597ff"><i></i>claude.ai</span>'
             '<span class="chip" style="--c:#7fd6ee"><i></i>Claude Code <em>· every machine</em></span>'
             '<span class="chip" style="--c:#ffd27a"><i></i>ChatGPT</span></div>')
    if not mobile:
        head = (f'<div class="col center">{brand(26)}'
                '<h1 style="margin-top:34px;font-size:68px">Every AI chat you’ve had,<br><span class="grad">one search away.</span></h1>'
                '<p class="lede" style="margin-top:22px;font-size:20.5px;max-width:880px">claude.ai, Claude Code on every machine and ChatGPT, in one SQLite '
                'database on your own disk. <b>Collected every hour. Searched in milliseconds. Nothing leaves your machine.</b></p>'
                + chips.format(m=26) + '</div>')
        return card(WIDE, head + f'<div style="margin-top:42px">{terminal(blocks, fs=14)}</div>', pad='56px 64px 60px',
                    vars_='--gx:50%;--gy:-14%;--gw:1300px;--gh:720px;')
    head = (f'<div class="col center">{brand(28)}'
            '<h1 style="margin-top:36px;font-size:62px">Every AI chat<br>you’ve had, <span class="grad">one<br>search away.</span></h1>'
            '<p class="lede" style="margin-top:24px;font-size:25px;max-width:640px">claude.ai, Claude Code and ChatGPT in one SQLite database on your own disk. '
            '<b>Nothing leaves your machine.</b></p>' + chips.format(m=26) + '</div>')
    return card(NARROW, head + f'<div style="margin-top:40px">{terminal(blocks, fs=17.5)}</div>', pad='60px 40px 48px',
                vars_='--gx:50%;--gy:-6%;--gw:900px;--gh:700px;')


def numbers_scene(mobile=False):
    st = numbers()
    if not mobile:
        cells = []
        for i, x in enumerate(st):
            sep = '' if i == 0 else 'padding-left:26px;border-left:1.5px solid rgba(255,255,255,.07);'
            cells.append(stat(*x, accent=i == len(st) - 1, sizes=(54, 16, 13.5)).replace('<div class="stat">', f'<div class="stat" style="{sep}">', 1))
        inner = f'<div style="display:grid;grid-template-columns:1.35fr 1.1fr 1fr 1fr .9fr;column-gap:26px;align-items:start">{"".join(cells)}</div>'
        return card(WIDE, inner, pad='62px 60px 60px', vars_='--gx:50%;--gy:-60%;--gw:1300px;--gh:380px;')
    cells = [stat(*x, accent=i == len(st) - 1, sizes=(74, 23, 18.5)) for i, x in enumerate(st)]
    cells[-1] = cells[-1].replace('<div class="stat">', '<div class="stat" style="grid-column:1/3;padding-top:44px;border-top:1.5px solid rgba(255,255,255,.07)">', 1)
    return card(NARROW, f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:54px 40px">{"".join(cells)}</div>', pad='64px 60px 64px',
                vars_='--gx:50%;--gy:-12%;--gw:900px;--gh:600px;')


FLAGS = [('--me', 'Your own words', ''), ('--claude', 'Only the answers', ''), ('--talk', 'No tools or thinking', ''),
         ('--source', 'One source', 'chatgpt, claude-web…'), ('--since', 'From a date', 'YYYY-MM-DD'),
         ('--newest', 'Newest first', 'instead of best match'), ('--raw', 'FTS5 syntax', 'NEAR(), prefix*, OR, NOT'), ('-n', 'Result count', 'default 20')]


def flags_panel(cols=1, pad='22px 24px 12px'):
    top = ' style="border-top:0"'  # the first row has no rule above it
    rows = ''.join(f'<div class="flag"{top if i < cols else ""}><code>{f}</code><span>{d}{f" <em>· {h}</em>" if h and cols == 1 else ""}</span></div>'
                   for i, (f, d, h) in enumerate(FLAGS))
    grid = f'display:grid;grid-template-columns:repeat({cols},1fr);column-gap:34px'
    return (f'<div class="panel" style="padding:{pad}"><div class="ph">Filters</div>'
            f'<div class="ps2" style="margin:8px 0 10px">Combine any of them. Results are ranked with BM25 and show the matching words.</div>'
            f'<div style="{grid}">{rows}</div></div>')


def search_scene(mobile=False):
    if not mobile:
        t = terminal([cap('search-me'), cap('search-near'), cap('search-src')], fs=13.6)
        return card(WIDE, f'{t}<div style="margin-top:24px">{flags_panel(cols=4, pad="22px 26px 10px")}</div>', pad='54px 56px', vars_='--gx:50%;--gy:-8%;')
    t = terminal([cap('search-me'), cap('search-near')], fs=16.5)
    return card(NARROW, f'{t}<div style="margin-top:28px">{flags_panel(cols=1, pad="24px 28px 12px")}</div>', pad='44px 40px',
                vars_='--gx:50%;--gy:-4%;--gw:900px;--gh:560px;')


def stats_scene(mobile=False):
    rows = parse_stats()
    total_c, total_m = sum(r['chats'] for r in rows), sum(r['msgs'] for r in rows)
    head = (f'<div class="row" style="align-items:baseline;justify-content:space-between;margin-bottom:12px"><div class="ph">Every source, one timeline</div>'
            f'<div class="ps2"><b style="color:#f2f3f7">{total_c}</b> chats · <b style="color:#f2f3f7">{total_m}</b> messages · from <code style="font:600 13px JetBrains Mono;color:#c4baff">aih stats</code></div></div>')
    if not mobile:
        t = terminal([cap('stats')], fs=14)
        panel = f'<div class="panel" style="padding:22px 26px 18px">{head}{timeline(rows)}</div>'
        return card(WIDE, f'{t}<div style="margin-top:26px">{panel}</div>', pad='54px 56px', vars_='--gx:50%;--gy:-8%;')
    t = terminal([cap('stats')], fs=12.1)
    head_m = (f'<div class="ph">Every source, one timeline</div><div class="ps2" style="margin:8px 0 10px"><b style="color:#f2f3f7">{total_c}</b> chats · '
              f'<b style="color:#f2f3f7">{total_m}</b> messages</div>')
    panel = f'<div class="panel" style="padding:24px 24px 18px">{head_m}{timeline(rows, label_w=208, num_w=64, compact=True)}</div>'
    return card(NARROW, f'{t}<div style="margin-top:26px">{panel}</div>', pad='44px 36px', vars_='--gx:50%;--gy:-4%;--gw:900px;--gh:560px;')


def markdown_scene(mobile=False):
    md = open(os.path.join(CAP, 'doc.md'), encoding='utf-8').read()
    path = cap('show')[1][0]
    if not mobile:
        t = terminal([(cap('ls')[0], cap('ls')[1]), cap('show'), (cap('head')[0], cap('head')[1])], fs=12.6, cursor=False, tint=tint_head)
        inner = (f'<div class="row" style="gap:26px;align-items:center"><div style="width:470px;flex:none">{t}</div>'
                 f'<div style="flex:1;min-width:0">{document(md, path, 724)}</div></div>')
        return card(WIDE, inner, pad='50px 52px', vars_='--gx:70%;--gy:-6%;--ax:0%;')
    t = terminal([cap('show')], fs=15.5, cursor=False, tint=tint_plain)
    return card(NARROW, f'{t}<div style="margin-top:26px">{document(md, path, 1020)}</div>', pad='44px 40px',
                vars_='--gx:50%;--gy:-4%;--gw:900px;--gh:560px;')


def collect_parse():
    out = cap('collect')[1]
    pulls = dict(re.findall(r'claude-code (\S+): pulled from (\S+)', '\n'.join(out)))
    counts = dict(re.findall(r'^\s+([\w-]+): (\d+)$', '\n'.join(out), re.M))
    return pulls, {k: int(v) for k, v in counts.items()}


ARROW = ('<defs><marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M0 0L10 5L0 10z" fill="rgba(155,140,255,.85)"/></marker></defs>')


def wires(w, h, paths):
    """SVG connectors: each path is 'd' or ('d', 'soft') for a dashed one; every solid path ends in an arrow."""
    body = ''.join(f'<path d="{p}" marker-end="url(#ar)"/>' if isinstance(p, str) else f'<path class="soft" d="{p[0]}"/>' for p in paths)
    return f'<svg class="wire" viewBox="0 0 {w} {h}" width="{w}" height="{h}">{ARROW}{body}</svg>'


def node(x, y, w, inner, cls='', h=None, extra=''):
    return f'<div class="node {cls}" style="left:{x}px;top:{y}px;width:{w}px;{f"height:{h}px;" if h else ""}{extra}">{inner}</div>'


def collect_diagram(mobile=False):
    pulls, counts = collect_parse()
    n_md = sum(counts.values())
    laptop_via = esc(pulls.get('laptop', ''))
    desktop_via = esc(pulls.get('desktop', ''))
    hub_k = '<div class="k" style="color:#b9afff">Hub · writes the archive</div><div class="t" style="font-size:22px">server</div>'
    if not mobile:
        W, H = 1088, 386
        html_ = (
            '<div class="colh" style="left:0;top:0">Your machines</div><div class="colh" style="left:440px;top:0">Hub</div>'
            '<div class="colh" style="left:812px;top:0">Archive</div>'
            + node(0, 26, 290, f'<div class="k">Claude Code</div><div class="t">desktop</div><div class="d"><code>{desktop_via}</code> <span class="pill ok">✓ pulled</span></div>', h=100)
            + node(0, 138, 290, f'<div class="k">Claude Code</div><div class="t">laptop</div><div class="d" style="line-height:1.9"><code>laptop-lan</code> <span class="pill no">✕ no answer</span><br>'
                               f'<code>{laptop_via}</code> <span class="pill ok">✓ pulled</span></div>', h=124)
            + node(0, 274, 290, '<div class="k">Website exports · inbox/</div><div class="t">claude.ai + ChatGPT</div>'
                               '<div class="d"><code>conversations-1.zip</code><br><code>chatgpt-export.zip</code></div>', h=112)
            + node(440, 78, 262, hub_k + '<div class="d" style="color:#b7bccb">Reads its own <code>~/.claude/projects</code> directly.</div>'
                   '<ul><li><code style="color:#e6e2ff">aih collect</code> every hour</li><li>rsync never deletes</li><li>Waits 2 min for a sync to finish</li>'
                   '<li>Re-imports only what changed</li></ul>', cls='hub')
            + node(812, 92, 276, '<div class="k">SQLite + FTS5</div><div class="t"><code>archive.db</code></div><div class="d">Ranked full-text search</div>')
            + node(812, 212, 276, f'<div class="k">Markdown</div><div class="t"><code>chats/</code></div><div class="d">{n_md} readable files, one per chat</div>')
            + '<div class="lbl" style="left:303px;top:126px">rsync over SSH</div><div class="lbl" style="left:338px;top:292px">inbox</div>')
        w = wires(W, H, ['M290 76 C 372 76, 360 166, 438 172', 'M290 200 C 360 200, 370 208, 438 208', 'M290 330 C 372 330, 360 250, 438 244',
                         'M702 186 C 752 186, 760 140, 810 140', 'M702 230 C 752 230, 760 260, 810 260'])
        return f'<div style="position:relative;width:{W}px;height:{H}px">{w}{html_}</div>'
    W, H = 720, 560
    html_ = (
        '<div class="colh" style="left:0;top:0">Your machines and exports</div>'
        + node(0, 26, 228, f'<div class="k">Claude Code</div><div class="t">desktop</div><div class="d"><code>{desktop_via}</code> <span class="pill ok">✓</span></div>', h=112)
        + node(246, 26, 228, f'<div class="k">Claude Code</div><div class="t">laptop</div><div class="d"><code>laptop-lan</code> <span class="pill no">✕</span><br>'
                             f'<code>{laptop_via}</code> <span class="pill ok">✓</span></div>', h=112)
        + node(492, 26, 228, '<div class="k">inbox/</div><div class="t">Exports</div><div class="d"><code>conversations-1.zip</code><br><code>chatgpt-export.zip</code></div>', h=112)
        + node(90, 214, 540, hub_k + '<ul><li><code style="color:#e6e2ff">aih collect</code> every hour, incremental</li><li>rsync over SSH, never deletes</li></ul>', cls='hub')
        + node(0, 440, 348, '<div class="k">SQLite + FTS5</div><div class="t"><code>archive.db</code></div><div class="d">Ranked full-text search</div>')
        + node(372, 440, 348, f'<div class="k">Markdown</div><div class="t"><code>chats/</code></div><div class="d">{n_md} readable files</div>'))
    w = wires(W, H, ['M114 138 C 114 176, 240 176, 250 210', 'M360 138 L360 210', 'M606 138 C 606 176, 480 176, 470 210',
                     'M250 372 C 250 404, 174 404, 174 436', 'M470 372 C 470 404, 546 404, 546 436'])
    return f'<div style="position:relative;width:{W}px;height:{H}px">{w}{html_}</div>'



def collect_scene(mobile=False):
    t = terminal([cap('collect'), cap('rebuild')], fs=14 if not mobile else 15.5, tint=tint_collect)
    if not mobile:
        return card(WIDE, f'{collect_diagram()}<div style="margin-top:34px">{t}</div>', pad='50px 56px 56px', vars_='--gx:50%;--gy:-10%;')
    return card(NARROW, f'{collect_diagram(True)}<div style="margin-top:30px">{t}</div>', pad='46px 40px', vars_='--gx:50%;--gy:-4%;--gw:900px;--gh:560px;')


def check_parse():
    res = []
    lines = cap('check')[1]
    for i, l in enumerate(lines):
        m = re.match(r'\s+([\w-]+): export has (\d+) chats, archive has (\d+); newest export is (\d+) days old', l)
        if m:
            verdict = lines[i + 2].strip()
            res.append(dict(src=m.group(1), exp=int(m.group(2)), have=int(m.group(3)), age=int(m.group(4)), safe=verdict.startswith('SAFE')))
    return res


def check_scene(mobile=False):
    t = terminal([cap('check')], fs=13.3 if not mobile else 13.6, tint=tint_check)
    tick = '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#63e3a4" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 10.5l3.5 3.5 7.5-8"/></svg>'
    tiles = ''.join(
        f'<div class="panel verdict"><div class="ic">{tick}</div><div><div class="src">{r["src"]}</div>'
        f'<div class="big">{r["have"]} of {r["exp"]} chats <b>{"safe" if r["safe"] else "missing"}</b></div>'
        f'<div class="sub">Every chat in the newest export is in the archive. Export age: {r["age"]} days.</div></div></div>' for r in check_parse())
    note = ('<div class="panel" style="padding:16px 22px"><div class="ps2"><b style="color:#e3e6ee">Older than two days?</b> '
            'The check asks for a fresh export first, because newer chats would not be covered.</div></div>')
    side = f'<div class="col" style="gap:14px">{tiles}{note}</div>'
    if not mobile:
        return card(WIDE, f'<div class="row" style="gap:26px;align-items:center"><div style="flex:1;min-width:0">{t}</div><div style="width:352px;flex:none">{side}</div></div>',
                    pad='54px 56px', vars_='--gx:72%;--gy:-20%;--ax:0%;')
    return card(NARROW, f'{t}<div style="margin-top:26px">{side}</div>', pad='44px 40px', vars_='--gx:50%;--gy:-4%;--gw:900px;--gh:560px;')


def architecture_scene(mobile=False):
    hub = ('<div class="k" style="color:#b9afff">aih collect · hourly</div><div class="t"><code>importers</code></div>'
           '<div class="d" style="color:#b7bccb">Every source becomes the same conversation, message and part rows.</div>')
    if not mobile:
        W, H = 1088, 610
        S, C, A, U = 0, 268, 604, 880
        html_ = (
            f'<div class="colh" style="left:{S}px;top:0">Sources</div><div class="colh" style="left:{C}px;top:0">Collect</div>'
            f'<div class="colh" style="left:{A}px;top:0">Archive</div><div class="colh" style="left:{U}px;top:0">Use</div>'
            + node(S, 28, 220, '<div class="t">claude.ai</div><div class="d">Official export, original uploads linked</div>', h=104)
            + node(S, 144, 220, '<div class="t">Claude Code</div><div class="d"><code>~/.claude/projects</code> on every machine</div>', h=104)
            + node(S, 260, 220, '<div class="t">ChatGPT</div><div class="d">Export zip, one folder per account</div>', h=104)
            + node(C, 28, 292, hub + '<ul><li>Only changed files re-import</li><li>Edited prompts kept as branches</li><li>Resumed sessions stored once</li>'
                   '<li>Chats deleted online never imported</li><li>System noise kept out of search</li><li>Half-synced exports wait their turn</li></ul>', cls='hub', h=336)
            + node(A, 28, 232, '<div class="k">Markdown</div><div class="t"><code>chats/*.md</code></div><div class="d">One file per chat; thinking and tool calls folded</div>', h=150)
            + node(A, 214, 232, '<div class="k">SQLite + FTS5</div><div class="t"><code>archive.db</code></div><div class="d"><code>unicode61</code>, diacritics folded, BM25 ranking</div>', h=150)
            + node(U, 28, 208, '<div class="t"><code>aih search</code></div><div class="d">Filters, snippets, FTS5 syntax</div>', h=106)
            + node(U, 143, 208, '<div class="t" style="font-size:13.5px"><code>stats · show · check</code></div><div class="d">Counts, paths, safe to delete</div>', h=106)
            + node(U, 258, 208, '<div class="t"><code>sqlite3</code> · agents</div><div class="d">Plain SQL; <code>CLAUDE.md</code> for agents</div>', h=106)
            + node(0, 412, 1088, '<div class="k" style="color:#a99cff">Optional · mine.py · nightly</div><div class="t" style="font-size:16px;font-weight:600;color:#c9cdd8">'
                   'Turn your own words into dated facts for a knowledge base, checked by a second model</div>', cls='dash', h=198, extra='padding:18px 22px;')
            + node(24, 494, 318, '<div class="k">1 · Extract</div><div class="t" style="font-size:16px">Fast model</div><div class="d">Reads only your own messages</div>')
            + node(385, 494, 318, '<div class="k">2 · Verify</div><div class="t" style="font-size:16px">Second, stronger model</div><div class="d">Checks every fact against your profile</div>')
            + node(746, 494, 318, '<div class="k">3 · Review</div><div class="t" style="font-size:16px">Notes for you</div><div class="d">The profile itself is never edited</div>')
            + f'<div class="lbl" style="left:{A + 128}px;top:376px">reads archive.db</div>')
        w = wires(W, H, ['M220 80 C 246 80, 242 150, 266 156', 'M220 196 L266 196', 'M220 312 C 246 312, 242 242, 266 236',
                         'M560 150 C 584 150, 580 104, 602 104', 'M560 250 C 584 250, 580 290, 602 290',
                         'M836 289 C 860 289, 852 81, 878 81', 'M836 289 C 860 289, 856 196, 878 196', 'M836 289 C 858 289, 856 311, 878 311',
                         ('M720 364 L720 410', 'soft'), 'M342 548 L383 548', 'M703 548 L744 548'])
        return card(WIDE, f'<div style="position:relative;width:{W}px;height:{H}px">{w}{html_}</div>', pad='50px 56px 56px', vars_='--gx:40%;--gy:-14%;')
    W, H = 720, 812
    html_ = (
        '<div class="colh" style="left:0;top:0">Sources</div>'
        + node(0, 26, 228, '<div class="t">claude.ai</div><div class="d">Official export</div>', h=96)
        + node(246, 26, 228, '<div class="t">Claude Code</div><div class="d">Every machine</div>', h=96)
        + node(492, 26, 228, '<div class="t">ChatGPT</div><div class="d">Every account</div>', h=96)
        + node(60, 178, 600, hub + '<div class="d">Only changed files re-import.</div>', cls='hub')
        + node(0, 370, 348, '<div class="k">SQLite + FTS5</div><div class="t"><code>archive.db</code></div><div class="d">Diacritics folded, BM25</div>', h=124)
        + node(372, 370, 348, '<div class="k">Markdown</div><div class="t"><code>chats/*.md</code></div><div class="d">One file per chat</div>', h=124)
        + node(0, 540, 720, '<div class="t"><code>aih search · stats · show · check</code></div><div class="d">Plus plain SQL with <code>sqlite3</code>, and <code>CLAUDE.md</code> for agents</div>')
        + node(0, 680, 720, '<div class="k" style="color:#a99cff">Optional · mine.py · nightly</div><div class="t" style="font-size:17px">Fast model extracts → second model verifies → notes</div>'
               '<div class="d">Your profile is never edited.</div>', cls='dash', extra='padding:18px 22px;'))
    w = wires(W, H, ['M114 122 C 114 150, 220 150, 230 174', 'M360 122 L360 174', 'M606 122 C 606 150, 500 150, 490 174',
                     'M250 318 C 250 344, 174 344, 174 366', 'M470 318 C 470 344, 546 344, 546 366',
                     'M174 494 L174 536', 'M546 494 L546 536', ('M360 636 L360 676', 'soft')])
    return card(NARROW, f'<div style="position:relative;width:{W}px;height:{H}px">{w}{html_}</div>', pad='46px 40px', vars_='--gx:50%;--gy:-4%;--gw:900px;--gh:560px;')


def social():
    t = terminal([cap('hero')], fs=14, cursor=False)
    inner = (f'<div class="col" style="position:absolute;left:76px;top:0;bottom:0;width:560px;justify-content:center">{brand(30)}'
             '<h1 style="margin-top:34px;font-size:66px;line-height:1.02">Every AI chat<br>you’ve had,<br><span class="grad">one search away.</span></h1>'
             '<p class="lede" style="margin-top:26px;font-size:26px;text-wrap:initial">claude.ai · Claude Code · ChatGPT<br><b>One local SQLite archive.</b></p></div>'
             f'<div style="position:absolute;left:676px;top:118px;width:900px">{t}</div>')
    return f'<div class="card square" style="width:1280px;height:640px;--gx:80%;--gy:-30%;--gw:1100px;--gh:760px">{inner}</div>'


SCENES = {
    'hero': (lambda: hero(), WIDE), 'hero-mobile': (lambda: hero(True), NARROW),
    'numbers': (lambda: numbers_scene(), WIDE), 'numbers-mobile': (lambda: numbers_scene(True), NARROW),
    'search': (lambda: search_scene(), WIDE), 'search-mobile': (lambda: search_scene(True), NARROW),
    'stats': (lambda: stats_scene(), WIDE), 'stats-mobile': (lambda: stats_scene(True), NARROW),
    'markdown': (lambda: markdown_scene(), WIDE), 'markdown-mobile': (lambda: markdown_scene(True), NARROW),
    'collect': (lambda: collect_scene(), WIDE), 'collect-mobile': (lambda: collect_scene(True), NARROW),
    'check': (lambda: check_scene(), WIDE), 'check-mobile': (lambda: check_scene(True), NARROW),
    'architecture': (lambda: architecture_scene(), WIDE), 'architecture-mobile': (lambda: architecture_scene(True), NARROW),
    'social': (social, 1280),
}


# ------------------------------------------------------------------ render
MEASURE_JS = ('<script>document.fonts.ready.then(()=>{const c=document.querySelector(".card");'
              'document.body.setAttribute("data-h",Math.ceil(c.getBoundingClientRect().height));});</script>')


def chrome(*args):
    env = {k: v for k, v in os.environ.items() if k != 'TMPDIR'}  # a long TMPDIR breaks Chrome's sockets
    return subprocess.run([CHROME, '--headless=new', '--hide-scrollbars', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                           '--virtual-time-budget=9000', *args], capture_output=True, text=True, timeout=120, env=env)


def render(name, html_body, width, tmp):
    page = os.path.join(tmp, name + '.html')
    doc = f'<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body>{html_body}{MEASURE_JS}</body></html>'
    open(page, 'w', encoding='utf-8').write(doc)
    if name == 'social':
        height = 640
    else:
        dom = chrome('--dump-dom', f'--window-size={width},3000', 'file://' + page).stdout
        height = int(re.search(r'data-h="(\d+)"', dom).group(1))
    scale = 1 if name == 'social' else (1.6 if width == WIDE else 1.35)
    png = os.path.join(tmp, name + '.png')
    chrome(f'--force-device-scale-factor={2 if name == "social" else scale}', '--default-background-color=00000000',
           f'--window-size={width},{height}', f'--screenshot={png}', 'file://' + page)
    if name == 'social':
        out = os.path.join(OUT, 'social.png')
        subprocess.run(['magick', png, '-resize', '1280x640!', '-strip', out], check=True)
    else:
        out = os.path.join(OUT, name + '.webp')
        subprocess.run(['magick', png, '-strip', '-quality', '86', '-define', 'webp:method=6', out], check=True)
    if KEEP:
        os.makedirs(os.path.join(OUT, '.html'), exist_ok=True)
        shutil.copy(page, os.path.join(OUT, '.html', name + '.html'))
    size = os.path.getsize(out) // 1024
    dims = subprocess.run(['magick', 'identify', '-format', '%wx%h', out], capture_output=True, text=True).stdout
    print(f'{os.path.basename(out):24} {dims:>10}  {size:4d} KB')


def main():
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, (build, width) in SCENES.items():
            if ONLY and name not in ONLY:
                continue
            render(name, build(), width, tmp)


if __name__ == '__main__':
    main()
