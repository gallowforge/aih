#!/usr/bin/env python3
"""Render the README images from the captures that scripts/readme-capture.sh saved.

  scripts/readme-visuals.py CAPTURE_DIR OUT_DIR [--only=hero,stats,...]

The identity is a card catalogue (docs/readme/IDENTITY.md): every search result is typed on an
index card, the cabinet holds the numbers, the ledger keeps the stats. Every word on a card is
taken from a real capture: commands, results, counts, paths. Nothing here invents output.

Each scene becomes an HTML page in docs/readme/src/ (styled by src/aih.css), headless Chrome
screenshots it at 2x, and ImageMagick writes WebP (PNG for the social preview).
Needs google-chrome-stable (or $CHROME), ImageMagick and network access for Google Fonts.
"""
import hashlib, html, json, os, re, shutil, subprocess, sys, tempfile

CHROME = os.environ.get('CHROME', 'google-chrome-stable')
WIDE, NARROW = 1100, 540          # CSS px; rendered at 2x: 2200 and 1080 wide
esc = html.escape

CAP = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'docs/readme/.capture'
OUT = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else 'docs/readme'
SRC = os.path.join(OUT, 'src')
ONLY = next((a[7:].split(',') for a in sys.argv if a.startswith('--only=')), None)


# ------------------------------------------------------------------ captures
def cap(name):
    """(command, output lines) of one capture."""
    lines = open(os.path.join(CAP, name + '.txt'), encoding='utf-8').read().rstrip('\n').split('\n')
    return lines[0], lines[1:]


BENCH = json.load(open(os.path.join(CAP, 'bench.json')))
ANSI = re.compile(r'\x1b\[([0-9;]*)m')


def plain(s):
    return ANSI.sub('', s)


def ansi(s):
    """aih's colours on paper: hits in violet ribbon, paths in faded ink, the rest in black."""
    cls = {'1;33': 'hit', '2': 'dim', '1': 'b', '36': ''}
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


def results(name):
    """Search results of a capture: date, source, title, kind, snippet (HTML, hits marked) and path."""
    cmd, lines = cap(name)
    res = []
    for i in range(0, len(lines) - 2, 3):
        m = re.match(r'^(\S+) (\S+) · (.*) \[(\w+/\w+)\]$', plain(lines[i]))
        if not m:
            continue
        res.append(dict(date=m.group(1), src=m.group(2), title=m.group(3), kind=m.group(4),
                        snip=ansi(lines[i + 1].strip()), path=plain(lines[i + 2]).strip()))
    return cmd, res


def query_of(cmd):
    m = re.search(r"""search (?:--raw )?("[^"]*"|'[^']*'|\S+)""", cmd)
    return m.group(1).strip('"\'') if m else cmd


def parse_stats():
    rows = []
    for l in cap('stats')[1]:
        m = re.match(r'(\S+)\s+chats=(\d+)\s+messages=(\d+)\s+with-branches=(\d+)\s+(\S+) → (\S+)', l)
        if m:
            rows.append(dict(src=m.group(1), chats=int(m.group(2)), msgs=int(m.group(3)), br=int(m.group(4)), a=m.group(5), b=m.group(6)))
    return rows


# ------------------------------------------------------------------ small parts
def seed(*k):
    return int(hashlib.md5(repr(k).encode()).hexdigest()[:8], 16)


def mark(size=30, color='var(--ink)'):
    """The aih mark: the front of a catalogue drawer, label holder above the pull."""
    s = size * 1.05
    return (f'<div class="mark" style="font-size:{size}px"><svg width="{s:.0f}" height="{s:.0f}" viewBox="0 0 32 32" fill="none" stroke="{color}" stroke-width="1.9">'
            f'<rect x="2.5" y="4.5" width="27" height="23" rx="2"/><rect x="9.5" y="8.5" width="13" height="7" rx=".8"/>'
            f'<path d="M12 20.5h8a4 4 0 0 1-8 0z" fill="{color}" stroke-linejoin="round"/></svg><span>aih</span></div>')


STAMP_N = [0]


def stamp(center, ring, size=150, rot=-12, csize=None, cfont='var(--serif)', sub=None, seed_=3, cweight=400):
    """A violet rubber stamp: double ring, ring text, and one fact in the middle."""
    STAMP_N[0] += 1
    n = STAMP_N[0]
    r = size / 2
    rr = r - size * .1                      # radius of the ring text
    ri = r - size * .18                     # inner ring
    circ = 2 * 3.14159 * rr
    csize = csize or size * .27
    sub_svg = (f'<text x="{r}" y="{r + csize * .5 + size * .1:.1f}" text-anchor="middle" font-family="Courier Prime" font-weight="700" '
               f'font-size="{size * .085:.1f}" letter-spacing="2" stroke="none">{esc(sub)}</text>') if sub else ''
    cy = r + csize * .34 - (size * .07 if sub else 0)
    return f'''<svg class="stamp" width="{size}" height="{size}" viewBox="0 0 {size} {size}" style="transform:rotate({rot}deg)">
<defs><path id="sp{n}" d="M {r - rr},{r} a {rr},{rr} 0 1,1 {2 * rr},0 a {rr},{rr} 0 1,1 -{2 * rr},0"/>
<filter id="ink{n}" x="-8%" y="-8%" width="116%" height="116%">
<feTurbulence type="fractalNoise" baseFrequency=".045" numOctaves="2" seed="{seed_}" result="w"/>
<feDisplacementMap in="SourceGraphic" in2="w" scale="2.6" xChannelSelector="R" yChannelSelector="G" result="d"/>
<feTurbulence type="fractalNoise" baseFrequency=".95" numOctaves="2" seed="{seed_ + 5}" result="g"/>
<feColorMatrix in="g" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -3.1 0 0 0 2.45" result="m"/>
<feTurbulence type="fractalNoise" baseFrequency=".012" numOctaves="1" seed="{seed_ + 9}" result="p"/>
<feColorMatrix in="p" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -1.6 0 0 0 1.75" result="pm"/>
<feComposite in="d" in2="m" operator="in" result="s1"/><feComposite in="s1" in2="pm" operator="in"/></filter></defs>
<g filter="url(#ink{n})" fill="#5A3AA8" stroke="#5A3AA8">
<circle cx="{r}" cy="{r}" r="{r - 3}" fill="none" stroke-width="3.2"/>
<circle cx="{r}" cy="{r}" r="{ri:.1f}" fill="none" stroke-width="1.3"/>
<text font-family="Courier Prime" font-weight="700" font-size="{size * .082:.1f}" stroke="none"><textPath href="#sp{n}" textLength="{circ - 4:.1f}" lengthAdjust="spacing">{esc(ring)}</textPath></text>
<text x="{r}" y="{cy:.1f}" text-anchor="middle" font-family="{cfont.replace('var(--serif)', 'Libre Caslon Display')}" font-weight="{cweight}" font-size="{csize:.1f}" stroke="none">{center}</text>{sub_svg}
</g></svg>'''


def entry(r, fs=15, lh=1.42, band=False, clip=None):
    """One search result typed as a catalogue card: source and kind as the call number, the date,
    then the title, the snippet with its hits, and the path of the chat's Markdown file."""
    body = (f'<div class="top"><span>{esc(r["src"])} <span class="dim">[{esc(r["kind"])}]</span></span><span>{esc(r["date"])}</span></div>'
            f'<div class="title">{esc(r["title"])}</div>')
    if not band:
        body += f'<div class="snip">{r["snip"]}</div><div class="path">{esc(r["path"])}</div>'
    cl = f'height:{clip:.1f}px;overflow:hidden;' if clip else ''
    return f'<div class="entry" style="font-size:{fs}px;line-height:{lh};{cl}">{body}</div>'


def stacked(r, fs=13.2, lh=1.4, band=False, clip=None):
    """The same card for narrow drawers: date and kind on top, the source under them like a call number."""
    body = (f'<div class="top"><span>{esc(r["date"])}</span><span class="dim">[{esc(r["kind"])}]</span></div>'
            f'<div>{esc(r["src"])}</div><div class="title">{esc(r["title"])}</div>')
    if not band:
        body += (f'<div class="snip">{r["snip"]}</div>'
                 f'<div class="path" style="font-size:.9em;line-height:1.35">{esc(r["path"])}</div>')
    cl = f'height:{clip:.1f}px;overflow:hidden;' if clip else ''
    return f'<div class="entry" style="font-size:{fs}px;line-height:{lh};{cl}">{body}</div>'


def wrap_lines(text, cpl):
    """How many lines monospace text takes at cpl characters per line (greedy word wrap)."""
    n, cur = 1, 0
    for w in text.split(' '):
        while len(w) > cpl:
            if cur:
                n += 1
            w, cur = w[cpl:], 0
            n += 1 if w else 0
        if cur + len(w) + (1 if cur else 0) > cpl:
            n, cur = n + 1, len(w)
        else:
            cur += len(w) + (1 if cur else 0)
    return n


def stacked_height(r, w, fs=13.2, lh=1.4, pad=(16, 20)):
    cw = fs * .6
    usable = w - 2 * pad[1]
    t = wrap_lines(r['title'], int((usable - 2 * cw) / cw))
    sn = wrap_lines(plain(html.unescape(re.sub('<[^>]+>', '', r['snip']))), int((usable - 4 * cw) / cw))
    pa = wrap_lines(r['path'], int((usable - 2 * cw) / (cw * .9)))
    return pad[0] + fs * lh * (2 + t + sn) + fs * .9 * 1.35 * pa + fs * (.35 + .45 + .6) + 34


def icard(x, y, w, h, inner, pad='18px 24px 0', hole=True, hole_cls='', extra='', z=None):
    zs = f'z-index:{z};' if z is not None else ''
    return (f'<div class="icard" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{zs}{extra}"><div class="in" style="padding:{pad}">{inner}</div>'
            + (f'<i class="hole {hole_cls}"></i>' if hole else '') + '</div>')


def pencil_note(x, y, text, fs=17, w=None, rot=0, align='left'):
    ws = f'width:{w}px;' if w else ''
    return f'<div class="abs pencil" style="left:{x}px;top:{y}px;{ws}font-size:{fs}px;line-height:1.25;transform:rotate({rot}deg);text-align:{align}">{text}</div>'


def pencil_arrow(d, w, h, x=0, y=0, head=True):
    """A hand-drawn pencil leader; d is an SVG path in a w by h box placed at x, y."""
    hd = ('<marker id="pa" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
          '<path d="M1 1.5L8 5L1 8.5" fill="none" stroke="#8f8373" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></marker>')
    return (f'<svg class="abs" style="left:{x}px;top:{y}px;overflow:visible" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs>{hd}</defs>'
            f'<path d="{d}" fill="none" stroke="#8f8373" stroke-width="1.3" stroke-linecap="round" {"marker-end=\"url(#pa)\"" if head else ""}/></svg>')


def brass_label(x, y, w, h, inner, z=None):
    zs = f'z-index:{z};' if z is not None else ''
    return (f'<div class="brass-frame" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{zs}"><div class="label">{inner}</div>'
            f'<i class="rivet" style="left:-11px;top:{h / 2 - 3.5:.1f}px"></i><i class="rivet" style="right:-11px;top:{h / 2 - 3.5:.1f}px"></i></div>')


def cup_pull(cx, y, w=96, z=None):
    h = w * .34
    zs = f'z-index:{z};' if z is not None else ''
    return (f'<svg class="abs" style="left:{cx - w / 2:.1f}px;top:{y}px;{zs}overflow:visible" width="{w}" height="{h:.1f}" viewBox="0 0 100 34">'
            '<defs><linearGradient id="cpg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f3dc9e"/><stop offset=".35" stop-color="#c49a4c"/>'
            '<stop offset="1" stop-color="#6e5020"/></linearGradient><linearGradient id="cpi" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a2410"/>'
            '<stop offset="1" stop-color="#7a5a26"/></linearGradient></defs>'
            '<path d="M2 4 Q2 33 50 33 Q98 33 98 4 Z" fill="rgba(25,12,4,.35)" transform="translate(1.5,3)"/>'
            '<path d="M2 4 Q2 33 50 33 Q98 33 98 4 Z" fill="url(#cpg)"/>'
            '<path d="M10 5 Q12 25 50 25 Q88 25 90 5 Z" fill="url(#cpi)" opacity=".85"/>'
            '<rect x="0" y="1" width="100" height="5" rx="2" fill="url(#cpg)"/><rect x="0" y="1" width="100" height="1.4" rx=".7" fill="#fff4cf" opacity=".7"/>'
            '<circle cx="5" cy="3.5" r="1.6" fill="#6e5020"/><circle cx="95" cy="3.5" r="1.6" fill="#6e5020"/></svg>')


def knob(cx, cy, r=9, z=None):
    zs = f'z-index:{z};' if z is not None else ''
    return (f'<i class="abs" style="left:{cx - r}px;top:{cy - r}px;width:{2 * r}px;height:{2 * r}px;border-radius:50%;{zs}'
            f'background:radial-gradient(circle at 38% 32%,#fff1c4,#c99d4d 45%,#6e5020);box-shadow:0 2px 3px rgba(20,10,0,.5),0 0 0 1.5px rgba(60,35,10,.35)"></i>')


# ------------------------------------------------------------------ the drawer
def drawer(W, results_, label_html, fs=15, front_h=300, band=60, panel_h=190, tabs=(), back=56, z=0):
    """A catalogue drawer pulled toward you. The best match stands up front, typed in full; the
    next ones rise behind it, each showing its top lines. Returns (html, height)."""
    T = 15                                   # wall thickness at the front
    n_back = len(results_) - 1
    top0 = back + 34 + n_back * band         # top of the front card
    fy = top0 + front_h - 2                  # top edge of the front panel
    H = fy + panel_h
    by = back                                # top edge of the back panel
    inset_b = 34                             # how far the walls lean in at the back

    def inner_x(y):                          # left inner edge of the walls at height y
        return T + (inset_b + T * .7 - T) * (fy - y) / (fy - by)

    parts = []
    # walls and back panel, drawn behind the cards
    wl = f'0,{fy} {T},{fy} {inset_b + T * .7:.1f},{by} {inset_b:.1f},{by}'
    wr = f'{W},{fy} {W - T},{fy} {W - inset_b - T * .7:.1f},{by} {W - inset_b:.1f},{by}'
    parts.append(f'''<svg class="abs" style="left:0;top:0" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs><linearGradient id="wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7d5130"/><stop offset="1" stop-color="#a87444"/></linearGradient>
<linearGradient id="bk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5a371c"/><stop offset="1" stop-color="#3b2310"/></linearGradient></defs>
<rect x="{inset_b - 2:.1f}" y="{by - 9}" width="{W - 2 * inset_b + 4:.1f}" height="{fy - by + 9}" fill="url(#bk)"/>
<rect x="{inset_b - 2:.1f}" y="{by - 9}" width="{W - 2 * inset_b + 4:.1f}" height="9" fill="#a8744a"/>
<rect x="{inset_b - 2:.1f}" y="{by - 9}" width="{W - 2 * inset_b + 4:.1f}" height="1.5" fill="#d9a877" opacity=".8"/>
<polygon points="{wl}" fill="url(#wall)"/><polygon points="{wr}" fill="url(#wall)"/>
<polyline points="{T},{fy} {inset_b + T * .7:.1f},{by}" stroke="#d9a877" stroke-width="1.2" fill="none" opacity=".8"/>
<polyline points="{W - T},{fy} {W - inset_b - T * .7:.1f},{by}" stroke="#4a2d16" stroke-width="1.2" fill="none" opacity=".6"/>
</svg>''')
    # the pack: card tops at the back, behind the raised cards
    pack = []
    yb = top0 - n_back * band
    for k in range(9):
        y = by + 2 + k * (yb - by - 2) / 9 * (1 + k * .04)
        if y > yb - 2:
            break
        xl = inner_x(y) + 1
        pack.append(f'<rect x="{xl:.1f}" y="{y:.1f}" width="{W - 2 * xl:.1f}" height="{(yb - y):.1f}" fill="#f6f0e2"/>'
                    f'<rect x="{xl:.1f}" y="{y:.1f}" width="{W - 2 * xl:.1f}" height="1.1" fill="#b9a98d"/>')
    parts.append(f'<svg class="abs" style="left:0;top:0" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{"".join(pack)}</svg>')
    # guide tabs rising from the pack
    for (lbl, pos) in tabs:
        tw = 128
        y = by + 6
        xl = inner_x(y)
        x = xl + 8 + pos * (W - 2 * xl - tw - 16)
        parts.append(f'<div class="tab" style="left:{x:.1f}px;top:{y - 26}px;width:{tw}px;height:30px;font-size:12.5px;letter-spacing:.06em">{esc(lbl)}</div>')
    # raised cards, back to front
    for k in range(n_back, 0, -1):
        r = results_[k]
        y = top0 - k * band
        xl = inner_x(y + band) + 1
        s = (W - 2 * xl) / (W - 2 * T)
        parts.append(icard(xl, y, W - 2 * xl, front_h, entry(r, fs=fs * s, band=True, clip=band - 14 * s - 4), pad=f'{14 * s:.1f}px {22 * s:.1f}px 0', hole=False,
                           extra='box-shadow:0 0 0 .6px rgba(90,64,32,.16),0 -1px 0 rgba(255,255,255,.6) inset,0 -10px 14px -10px rgba(40,24,8,.35);'))
    parts.append(icard(T, top0, W - 2 * T, front_h, entry(results_[0], fs=fs), pad='20px 26px 0', hole=True,
                       extra='box-shadow:0 0 0 .6px rgba(90,64,32,.16),0 -12px 18px -12px rgba(40,24,8,.45);'))
    # front panel
    parts.append(f'<div class="abs oak" style="left:-6px;top:{fy}px;width:{W + 12}px;height:{panel_h + 200}px;border-radius:4px 4px 0 0;'
                 f'box-shadow:0 -1px 0 #d6a676 inset, 0 2px 0 rgba(255,225,180,.35) inset, 0 -16px 22px -14px rgba(30,15,5,.55)"></div>'
                 f'<div class="abs" style="left:10px;top:{fy + 14}px;width:{W - 20}px;height:{panel_h + 200}px;border-radius:3px;'
                 f'box-shadow:inset 0 0 0 1.5px rgba(60,32,12,.28), inset 2px 2px 0 rgba(255,220,170,.10)"></div>')
    parts.append(label_html(W, fy))
    shadow = 'filter:drop-shadow(-14px 22px 26px rgba(70,44,18,.30)) drop-shadow(-2px 4px 4px rgba(70,44,18,.18));'
    return f'<div class="abs" style="left:0;top:0;width:{W}px;height:{H}px;{shadow}">{"".join(parts)}</div>', H


# ------------------------------------------------------------------ CSS and fonts
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Courier+Prime:ital,wght@0,400;0,700;1,400&family=Libre+Caslon+Display'
         '&family=Libre+Caslon+Text:ital,wght@0,400;0,700;1,400&display=block" rel="stylesheet">')


def field(w, h, inner, extra=''):
    return f'<div class="field" style="width:{w}px;height:{h}px;{extra}">{inner}</div>'


# ------------------------------------------------------------------ scenes
def hero(mobile=False):
    cmd, res = results('hero-mobile' if mobile else 'hero')
    q = query_of(cmd)
    flags = cmd.split(f'"{q}"', 1)[1].strip()
    ms = f'{BENCH["query_ms_median"]:.1f}'
    ring = f'MEDIAN SEARCH · {BENCH["messages"]:,} MESSAGES · '

    def label(W, fy):
        lw, lh = (300, 74) if not mobile else (290, 72)
        x = (W - lw) / 2
        inner = (f'<div style="position:relative;width:100%;height:100%;display:flex;flex-direction:column;justify-content:center">'
                 f'<span class="abs typed faint" style="left:7px;top:4px;font-size:9.5px">006.3</span>'
                 f'<b class="typed" style="font-size:23px;letter-spacing:.01em">{esc(q)}</b>'
                 f'<span class="typed dim" style="font-size:11px;margin-top:3px">aih search … {esc(flags)}</span></div>')
        return brass_label(x, fy + 26, lw, lh, inner) + cup_pull(W / 2, fy + 26 + lh + 22, 104) + knob(W / 2, fy + 26 + lh + 86, 8)

    tabs = (('CHATGPT', .02), ('CLAUDE.AI', .5), ('CLAUDE CODE', .98))
    if not mobile:
        W, back, band, fh = 590, 64, 62, 344
        d, H = drawer(W, res, label, fs=16, front_h=fh, band=band, panel_h=200, tabs=tabs, back=back)
        top_front = back + 34 + (len(res) - 1) * band
        st = stamp(ms, ring, size=140, rot=-9, csize=50, sub='MS')
        left = (f'<div class="abs" style="left:68px;top:66px">{mark(30)}</div>'
                '<h1 class="abs display" style="left:66px;top:182px;width:440px;font-size:76px">Every AI chat you’ve had, <i>catalogued.</i></h1>'
                '<p class="abs lede" style="left:68px;top:462px;width:392px;font-size:19.5px">claude.ai, Claude Code on every machine and ChatGPT, '
                'word for word, in one SQLite file on your own disk. <b>Collected every hour, found in milliseconds.</b> <span style="white-space:nowrap">Nothing leaves</span> the building.</p>'
                + pencil_note(70, 706, 'best match up front,<br>the runners-up behind it', fs=17.5)
                + pencil_arrow('M4 178 C 84 184, 146 120, 184 8', 190, 190, 296, 562))
        right = (f'<div class="abs" style="left:478px;top:0;width:{W}px;height:{H}px">{d}'
                 f'<div class="abs" style="left:{W - 15 - 150}px;top:{top_front + fh - 150}px;z-index:5">{st}</div></div>')
        return field(WIDE, 840, left + right), WIDE, 840
    W, back, band, fh = 492, 34, 58, 318
    d, H = drawer(W, res, label, fs=14.2, front_h=fh, band=band, panel_h=190, tabs=tabs, back=back)
    top_front = back + 34 + (len(res) - 1) * band
    st = stamp(ms, ring, size=128, rot=-9, csize=46, sub='MS')
    head = (f'<div class="abs" style="left:26px;top:34px">{mark(26)}</div>'
            '<h1 class="abs display" style="left:24px;top:100px;width:490px;font-size:62px">Every AI chat you’ve had, <i>catalogued.</i></h1>'
            '<p class="abs lede" style="left:26px;top:262px;width:476px;font-size:18.5px">claude.ai, Claude Code on every machine and ChatGPT, word for word, '
            'in one SQLite file on your own disk. <b>Collected every hour, found in milliseconds.</b></p>')
    y0 = 370
    right = (f'<div class="abs" style="left:24px;top:{y0}px;width:{W}px;height:{H}px">{d}'
             f'<div class="abs" style="left:{W - 15 - 136}px;top:{top_front + fh - 142}px;z-index:5">{st}</div></div>')
    h = y0 + H - 30
    return field(NARROW, h, head + right), NARROW, h


def drawer_front(x, y, w, h, label, lw, lh, ajar=False, pull=64):
    """One drawer front of the cabinet: brass label holder with a typed label, cup pull, rod knob.
    An ajar drawer is pulled toward you: a dark gap with card tops opens above it."""
    lx, ly = (w - lw) / 2, 16
    if ajar:
        y, h, ly = y + 9, h - 9, ly - 6
    sh = ('box-shadow:0 1px 0 rgba(255,225,180,.30) inset,0 -1px 0 rgba(30,15,5,.35) inset,'
          + ('0 10px 12px -5px rgba(20,8,0,.6);transform:translate(0,2px) scale(1.01);z-index:3;' if ajar else '0 0 0 rgba(0,0,0,0);'))
    gap = (f'<div class="abs" style="left:{x + 3}px;top:{y - 9}px;width:{w - 6}px;height:11px;background:linear-gradient(#120a04,#2a170a);overflow:hidden;border-radius:1px">'
           f'<i class="abs" style="left:6px;right:6px;bottom:0;height:4px;background:repeating-linear-gradient(90deg,#e9e0cc 0 3px,#cbbd9f 3px 3.6px)"></i>'
           + ''.join(f'<i class="abs" style="left:{p * (w - 60) + 18:.1f}px;bottom:3px;width:26px;height:4px;background:#efe7d6;border-radius:2px 2px 0 0"></i>'
                     for p in (.08, .55, .9)) + '</div>') if ajar else ''
    return (gap + f'<div class="abs oak" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;border-radius:3px;{sh}">'
            f'<div class="abs" style="inset:7px;border-radius:2px;box-shadow:inset 0 0 0 1.2px rgba(55,28,10,.30),inset 1.5px 1.5px 0 rgba(255,220,170,.10)"></div>'
            + brass_label(lx, ly, lw, lh, label) + cup_pull(w / 2, ly + lh + 14, pull) + knob(w / 2, max(h - 15, ly + lh + 14 + pull * .34 + 13), 5.5) + '</div>')


def numbers():
    q = BENCH['query_ms_median']
    k = BENCH['messages'] // 1000
    n_src = len({'claude-code' if r['src'].startswith('claude-code') else r['src'].split('-')[0] for r in parse_stats()})
    return [
        (str(n_src), '', 'SOURCES', 'claude.ai, Claude Code, ChatGPT'),
        (f'{q:.1f}', 'ms', 'MEDIAN SEARCH', f'over {k}k messages'),
        (f'{BENCH["build_s"]:.1f}', 's', 'FULL REBUILD', f'all {k}k messages'),
        ('1', 'h', 'COLLECTION CYCLE', 'on every machine'),
        ('0', '', 'CLOUD CALLS', 'your disk only'),
    ]


def num_label(n, unit, lbl, cap_, fs=50, hot=False):
    col = 'color:var(--violet);' if hot else ''
    u = f'<span style="font-size:.46em;margin-left:.08em;font-family:var(--text);font-style:italic">{unit}</span>' if unit else ''
    return (f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-start;height:100%;width:100%;padding:{fs * .2:.0f}px 4px 0">'
            f'<div class="display" style="font-size:{fs}px;line-height:1;{col}">{n}{u}</div>'
            f'<b class="typed" style="font-size:{fs * .26:.1f}px;letter-spacing:.05em;margin-top:{fs * .15:.0f}px;white-space:nowrap">{lbl}</b>'
            f'<span class="typed dim" style="font-size:{fs * .25:.1f}px;margin-top:3px;line-height:1.25">{cap_}</span></div>')


def cabinet(x, y, w, h, inner):
    return (f'<div class="abs" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;filter:drop-shadow(0 18px 22px rgba(70,44,18,.32))">'
            f'<div class="abs oak" style="inset:0;border-radius:5px;background-color:#6f4527;box-shadow:inset 0 2px 0 rgba(255,220,170,.25),inset 0 0 0 1px rgba(30,14,4,.5)"></div>'
            f'<div class="abs" style="left:10px;right:10px;top:10px;bottom:10px;background:#24140a;border-radius:2px"></div>{inner}</div>')


def numbers_scene(mobile=False):
    st = numbers()
    if not mobile:
        W, H = WIDE, 300
        cw, chh = 1032, 236
        dw = (cw - 20 - 4 * 8) / 5
        fronts = ''.join(drawer_front(10 + i * (dw + 8), 10, dw, chh - 20, num_label(*x, fs=50, hot=i == 1),
                                      dw - 30, 134, ajar=i == 1, pull=60) for i, x in enumerate(st))
        return field(W, H, cabinet((W - cw) / 2, 30, cw, chh, fronts)), W, H
    W = NARROW
    cw = 500
    dw2 = (cw - 20 - 8) / 2
    big_h, small_h = 228, 214
    f = drawer_front(10, 10, cw - 20, big_h, num_label(*st[1], fs=62, hot=True), 300, 136, ajar=True, pull=70)
    for i, x in enumerate([st[0], st[2], st[3], st[4]]):
        col, row = i % 2, i // 2
        f += drawer_front(10 + col * (dw2 + 8), 10 + big_h + 8 + row * (small_h + 8), dw2, small_h, num_label(*x, fs=48), dw2 - 30, 128, pull=56)
    chh = 20 + big_h + 8 + 2 * small_h + 8
    H = chh + 64
    return field(W, H, cabinet((W - cw) / 2, 28, cw, chh, f)), W, H


KRAFT = 'background:#DCC69C;background-image:linear-gradient(180deg,rgba(255,250,235,.35),rgba(255,250,235,0) 40%,rgba(90,60,20,.06));'


def guide(x, y, w, h, tab, tab_pos, inner, tab_w=118):
    """A kraft guide card with its tab: the divider that starts each section of a drawer."""
    tx = x + 10 + tab_pos * (w - tab_w - 20)
    return (f'<div class="tab" style="left:{tx:.1f}px;top:{y - 27}px;width:{tab_w}px;height:30px;font-size:14px;{KRAFT}border-radius:6px 6px 0 0">{tab}</div>'
            f'<div class="icard" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{KRAFT}">'
            f'<div class="in" style="padding:14px 20px 0">{inner}</div></div>')


def nowrap_cmd(cmd):
    """A command that wraps only between its words, never inside a flag."""
    return ' '.join(f'<span style="white-space:nowrap">{esc(t)}</span>' for t in re.findall(r"""'[^']*'|"[^"]*"|\S+""", cmd))


def guide_band(cmd, w, fs):
    cpl = int((w - 40) / ((fs + .6) * .6))
    n, cur = 1, 0
    for t in re.findall(r"""'[^']*'|"[^"]*"|\S+""", cmd):   # the same units nowrap_cmd keeps together
        if cur and cur + 1 + len(t) > cpl:
            n, cur = n + 1, len(t)
        else:
            cur += len(t) + (1 if cur else 0)
    return 14 + n * (fs + .6) * 1.4 + 5 + 22 + 16


def section(x, y, w, cmd, res, tab, tab_pos, note, fs=13.2, gband=None, band=74):
    """One search as a drawer section: guide card at the back, runners-up rising, best match up front."""
    parts, cy = [], y
    gband = gband or guide_band(cmd, w, fs)
    full_h = stacked_height(res[0], w, fs)
    total_h = gband + band * (len(res) - 1) + full_h
    g_inner = (f'<div class="typed" style="font-size:{fs + .6:.1f}px;font-weight:700;line-height:1.4">{nowrap_cmd(cmd)}</div>'
               f'<div class="pencil" style="font-size:16px;margin-top:5px;color:#7d6f5c">{note}</div>')
    parts.append(guide(x, cy, w, total_h, tab, tab_pos, g_inner))
    cy += gband
    for r in reversed(res[1:]):
        parts.append(icard(x, cy, w, total_h - (cy - y), stacked(r, fs, band=True, clip=band - 16 - 3), pad='14px 20px 0', hole=False,
                           extra='box-shadow:0 0 0 .6px rgba(90,64,32,.16),0 -9px 12px -9px rgba(40,24,8,.32),0 18px 30px -18px rgba(60,38,16,.3);'))
        cy += band
    parts.append(icard(x, cy, w, full_h, stacked(res[0], fs), pad='16px 20px 0', hole=True, hole_cls='paper',
                       extra='box-shadow:0 0 0 .6px rgba(90,64,32,.16),0 -10px 14px -10px rgba(40,24,8,.38),0 22px 36px -18px rgba(60,38,16,.38);'))
    return ''.join(parts), cy + full_h - y


FLAGS = [('--me', 'your own words', ''), ('--claude', 'only the answers', ''), ('--talk', 'no tools or thinking', ''),
         ('--source', 'one source', 'chatgpt, claude-web…'), ('--since', 'from a date', 'YYYY-MM-DD'),
         ('--newest', 'newest first', 'instead of best match'), ('--raw', 'FTS5 syntax', 'NEAR(), prefix*, OR, NOT'), ('-n', 'how many', 'default 20')]


def placard(x, y, w, cols=4, fs=14.5, stack_title=False):
    """The printed notice every catalogue had: how to ask it."""
    if cols > 1:
        cells = ''.join(f'<div style="padding:10px 0 2px;border-top:1px solid var(--rule)"><b class="typed" style="font-size:{fs + .5}px">{f}</b>'
                        f'<div style="font-size:{fs + 1.5}px;margin-top:2px">{d}</div>'
                        f'<div class="dim" style="font-style:italic;font-size:{fs - .5}px;white-space:nowrap;min-height:1.3em">{esc(h)}</div></div>'
                        for f, d, h in FLAGS)
    else:
        cells = ''.join(f'<div style="display:grid;grid-template-columns:96px 1fr;align-items:baseline;padding:7px 0;border-top:1px solid var(--rule)">'
                        f'<b class="typed" style="font-size:{fs}px">{f}</b><span style="font-size:{fs + 1}px">{d}'
                        + (f' <span class="dim" style="font-style:italic;white-space:nowrap">· {esc(h)}</span>' if h else '') + '</span></div>'
                        for f, d, h in FLAGS)
    head = (f'<div class="display" style="font-size:27px">How to ask the catalogue</div>'
            f'<div class="it dim" style="font-size:15px;{"margin-top:4px" if stack_title else ""}">Combine any of them. Ranked by BM25.</div>')
    head = (f'<div>{head}</div>' if stack_title else
            f'<div style="display:flex;align-items:baseline;justify-content:space-between;gap:20px">{head}</div>')
    return (f'<div class="slip" style="left:{x}px;top:{y}px;width:{w}px;padding:22px 28px 16px;background:var(--card)">'
            f'<div class="abs" style="inset:7px;border:1px solid rgba(36,29,23,.55);box-shadow:0 0 0 2.5px var(--card),0 0 0 3.5px rgba(36,29,23,.35);pointer-events:none"></div>'
            f'{head}<div style="display:grid;grid-template-columns:repeat({cols},1fr);column-gap:26px;margin-top:12px;font-family:var(--text)">{cells}</div></div>')


def search_scene(mobile=False):
    specs = [('search-me', '--me', 0, 'only what you typed'),
             ('search-near', '--raw', .5, 'accents near folding, answers only'),
             ('search-src', '--source', 1, 'the ChatGPT shelf, and nothing else')]
    if not mobile:
        W, m, gap, top = WIDE, 44, 22, 70
        cw = (W - 2 * m - 2 * gap) / 3
        caps = [results(n) for n, *_ in specs]
        gb = max(guide_band(c, cw, 13.2) for c, _ in caps)
        out, hs = [], []
        for i, ((name, tab, pos, note), (cmd, res)) in enumerate(zip(specs, caps)):
            h_, hh = section(m + i * (cw + gap), top, cw, cmd, res, tab, pos, note, gband=gb)
            out.append(h_); hs.append(hh)
        x3 = m + 2 * (cw + gap)
        note = (pencil_note(x3 + 38, top + hs[2] + 40, 'Every section keeps its best<br>match up front. Ask for <span style="font-family:var(--type);font-style:normal">--newest</span><br>and they line up by date.', fs=17)
                + pencil_arrow('M30 34 C 16 22, 14 12, 20 2', 40, 40, x3 + 2, top + hs[2] + 2))
        py = top + max(hs) + 36
        pl = placard(m, py, W - 2 * m)
        H = py + 196 + 44
        return field(W, H, ''.join(out) + note + pl), W, H
    W, m = NARROW, 24
    out, y = [], 58
    for name, tab, pos, note in specs[:2]:
        cmd, res = results(name)
        h_, hh = section(m, y, W - 2 * m, cmd, res, tab, pos, note, fs=13.8, band=76)
        out.append(h_); y += hh + 62
    pl = placard(m, y - 22, W - 2 * m, cols=1, fs=14.5, stack_title=True)
    H = int(y - 22 + 432)
    return field(W, H, ''.join(out) + pl), W, H


def month_index(d):
    y, m, day = map(int, d.split('-'))
    return y * 12 + (m - 1) + (day - 1) / 31


def ledger_table(rows, fs=13.5, w=None):
    """aih stats as a ledger: one ruled row per source, totals double-underlined."""
    cols = '1.75fr .62fr .9fr .9fr'
    head = ''.join(f'<span class="sc" style="font-size:{fs + .5}px;{"text-align:right" if i else ""}">{h}</span>'
                   for i, h in enumerate(['Source', 'Chats', 'Messages', 'Branched']))
    body = ''.join(f'<div style="display:grid;grid-template-columns:{cols};align-items:end;height:{fs * 2.5:.0f}px;padding-bottom:5px;border-bottom:1px solid #cdbfa4" class="typed">'
                   f'<span style="font-size:{fs}px">{esc(r["src"])}</span><span style="text-align:right;font-size:{fs + 1}px">{r["chats"]}</span>'
                   f'<span style="text-align:right;font-size:{fs + 1}px">{r["msgs"]}</span><span style="text-align:right;font-size:{fs + 1}px">{r["br"]}</span></div>'
                   for r in rows)
    tc, tm, tb = sum(r['chats'] for r in rows), sum(r['msgs'] for r in rows), sum(r['br'] for r in rows)
    total = (f'<div style="display:grid;grid-template-columns:{cols};align-items:baseline;padding-top:9px" class="typed">'
             f'<span class="it" style="font-size:{fs + 3}px;font-family:var(--text)">Total</span>'
             + ''.join(f'<span style="text-align:right"><b style="font-size:{fs + 3}px;border-bottom:3.5px double var(--ink);padding:0 1px 1px">{v}</b></span>' for v in (tc, tm, tb))
             + '</div>')
    return (f'<div style="display:grid;grid-template-columns:{cols};padding-bottom:6px;border-bottom:1.5px solid var(--ink)">{head}</div>{body}{total}')


def timeline(rows, w, fs=12.5, row_h=58, label_w=0):
    """Each source as an inked bar from its first chat to its last, over ledger month columns."""
    lo = int(min(month_index(r['a']) for r in rows))
    hi = int(max(month_index(r['b']) for r in rows)) + 1
    span = hi - lo
    X = lambda v: label_w + (v - lo) / span * (w - label_w)
    months = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
    H = 30 + row_h * len(rows)
    svg = []
    for k in range(lo, hi + 1):
        x = X(k)
        svg.append(f'<line x1="{x:.1f}" y1="22" x2="{x:.1f}" y2="{H}" stroke="#cdbfa4" stroke-width="1"/>')
        if k < hi:
            lab = months[k % 12] + (f' ’{str(k // 12)[2:]}' if k % 12 == 0 or k == lo else '')
            svg.append(f'<text x="{X(k + .5):.1f}" y="14" text-anchor="middle" font-family="Libre Caslon Text" font-size="{fs + .5}" fill="#6B6053" '
                       f'style="font-variant:small-caps;letter-spacing:.06em">{lab.lower()}</text>')
    for i, r in enumerate(sorted(rows, key=lambda r: r['a'])):
        y = 30 + i * row_h
        a, b = X(month_index(r['a'])), X(month_index(r['b']))
        yb = y + row_h * .66
        da = f'{r["a"]} → {r["b"]}'
        tw_ = (len(r['src']) + 2) * fs * .6 + len(da) * (fs - 1) * .6
        tx = max(0, min(a, w - tw_))
        svg.append(f'<text x="{tx:.1f}" y="{y + row_h * .38:.1f}" font-family="Courier Prime" font-size="{fs}" fill="#241D17" stroke="#F7F1E3" stroke-width="6" stroke-linejoin="round" paint-order="stroke">'
                   f'<tspan font-weight="700">{esc(r["src"])}</tspan><tspan dx="{fs * .9:.1f}" font-size="{fs - 1}" fill="#6B6053">{esc(da)}</tspan></text>')
        svg.append(f'<path d="M{a:.1f} {yb:.1f} L{b:.1f} {yb:.1f}" stroke="#241D17" stroke-width="5.5" stroke-linecap="round"/>'
                   f'<line x1="{a:.1f}" y1="{yb - 8:.1f}" x2="{a:.1f}" y2="{yb + 8:.1f}" stroke="#241D17" stroke-width="1.6"/>'
                   f'<line x1="{b:.1f}" y1="{yb - 8:.1f}" x2="{b:.1f}" y2="{yb + 8:.1f}" stroke="#241D17" stroke-width="1.6"/>')
    return f'<svg width="{w}" height="{H}" viewBox="0 0 {w} {H}" style="overflow:visible;display:block">{"".join(svg)}</svg>', H


PAGE = 'background:#F7F1E3;'


def ribbon(x, y, h, w=15):
    return (f'<div class="abs" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;z-index:6;'
            f'background:linear-gradient(90deg,#3c2478,#52349c 35%,#6c50b4 55%,#52349c 75%,#38216f);'
            f'clip-path:polygon(0 0,100% 0,100% 100%,50% calc(100% - {w * .7:.0f}px),0 100%);'
            f'filter:drop-shadow(2px 3px 2px rgba(40,20,60,.35))"></div>')


def stats_scene(mobile=False):
    rows = parse_stats()
    cmd, out = cap('stats')
    notes = [l for l in out if not re.match(r'\S+\s+chats=', l)]
    note_html = ''.join(f'<div>{esc(l.replace("  ", "\u00a0 "))}</div>' for l in notes)
    if not mobile:
        W, H = WIDE, 700
        bx, by, bw, bh = 54, 60, 992, 580
        pw = bw / 2
        book = (f'<div class="abs" style="left:{bx - 12}px;top:{by - 8}px;width:{bw + 24}px;height:{bh + 22}px;border-radius:6px;'
                f'background:#3a2a20;box-shadow:0 30px 40px -18px rgba(50,30,10,.55),0 4px 8px rgba(50,30,10,.25)"></div>'
                + ''.join(f'<div class="abs" style="left:{bx - 6 + k * 1.3:.1f}px;top:{by + 2 + k * 1.6:.1f}px;width:{bw + 12 - k * 2.6:.1f}px;height:{bh}px;'
                          f'background:#efe6d3;border-radius:2px;box-shadow:0 0 0 .5px rgba(90,64,32,.25)"></div>' for k in range(3, 0, -1))
                + f'<div class="abs" style="left:{bx}px;top:{by}px;width:{pw}px;height:{bh}px;{PAGE}border-radius:3px 0 0 3px;'
                f'box-shadow:inset -38px 0 40px -26px rgba(80,55,25,.42)"></div>'
                f'<div class="abs" style="left:{bx + pw}px;top:{by}px;width:{pw}px;height:{bh}px;{PAGE}border-radius:0 3px 3px 0;'
                f'box-shadow:inset 38px 0 40px -26px rgba(80,55,25,.42)"></div>'
                f'<div class="abs" style="left:{bx + pw - 1}px;top:{by}px;width:2px;height:{bh}px;background:rgba(80,55,25,.35)"></div>')
        lp = (f'<div class="abs" style="left:{bx + 46}px;top:{by + 34}px;width:{pw - 86}px">'
              f'<div style="display:flex;align-items:baseline;justify-content:space-between"><div class="display" style="font-size:38px"><i>Circulation ledger</i></div>'
              f'<div class="typed dim" style="font-size:13px">$ {esc(cmd)}</div></div>'
              f'<div style="margin-top:26px">{ledger_table(rows)}</div>'
              f'<div class="sc dim" style="font-size:14px;margin-top:34px">Also on file</div>'
              f'<div class="typed" style="font-size:11.8px;line-height:1.6;margin-top:4px;color:var(--ink);white-space:nowrap">{note_html}</div></div>')
        tl, th = timeline(rows, pw - 92, fs=12.5, row_h=70)
        rp = (f'<div class="abs" style="left:{bx + pw + 46}px;top:{by + 34}px;width:{pw - 92}px">'
              f'<div class="display" style="font-size:38px"><i>First chat to last</i></div>'
              f'<div class="lede" style="font-size:15px;margin-top:4px">Every source, from its oldest chat to its newest.</div>'
              f'<div style="margin-top:28px">{tl}</div></div>')
        rib = ribbon(bx + pw + 9, by - 14, bh + 70, w=16)
        note = pencil_note(bx + 50, by + bh - 52, '17 chats, 80 messages: all present and accounted for.', fs=16.5)
        return field(W, H, book + lp + rp + rib + note), W, H
    W = NARROW
    pw, ph = 492, 878
    bx, by = 24, 40
    book = (f'<div class="abs" style="left:{bx - 9}px;top:{by - 8}px;width:{pw + 18}px;height:{ph + 18}px;border-radius:5px;background:#3a2a20;'
            f'box-shadow:0 26px 36px -18px rgba(50,30,10,.55)"></div>'
            + ''.join(f'<div class="abs" style="left:{bx + k * 1.4:.1f}px;top:{by + 2 + k * 1.6:.1f}px;width:{pw - k * 1.4:.1f}px;height:{ph}px;background:#efe6d3;'
                      f'border-radius:2px;box-shadow:0 0 0 .5px rgba(90,64,32,.25)"></div>' for k in range(3, 0, -1))
            + f'<div class="abs" style="left:{bx}px;top:{by}px;width:{pw}px;height:{ph}px;{PAGE}border-radius:0 3px 3px 0;box-shadow:inset 30px 0 32px -22px rgba(80,55,25,.4)"></div>')
    tl, th = timeline(rows, pw - 72, fs=12.5, row_h=62)
    inner = (f'<div class="abs" style="left:{bx + 38}px;top:{by + 30}px;width:{pw - 72}px">'
             f'<div class="display" style="font-size:36px"><i>Circulation ledger</i></div><div class="typed dim" style="font-size:13px;margin-top:4px">$ {esc(cmd)}</div>'
             f'<div style="margin-top:22px">{ledger_table(rows, fs=13)}</div>'
             f'<div class="display" style="font-size:26px;margin-top:40px"><i>First chat to last</i></div>'
             f'<div style="margin-top:16px">{tl}</div>'
             f'<div class="sc dim" style="font-size:14px;margin-top:26px">Also on file</div>'
             f'<div class="typed" style="font-size:11.2px;line-height:1.6;margin-top:4px;white-space:nowrap">{note_html}</div></div>')
    rib = ribbon(bx + pw - 27, by - 14, 190, w=14)
    H = by + ph + 50
    return field(W, H, book + inner + rib), W, H


# ------------------------------------------------------------------ Markdown, rendered the way aih writes it
def inline(s):
    s = esc(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    return re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)


SQL_KW = r'\b(CREATE|VIRTUAL|TABLE|USING|SELECT|FROM|WHERE|JOIN|ON|ORDER|BY|LIMIT|MATCH|IF|NOT|EXISTS)\b'


def code_html(body, lang):
    s = esc(body)
    if lang == 'sql':
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
    lines, out, i, para = body.split('\n'), [], 0, []

    def flush():
        if para:
            out.append(f'<p>{inline(" ".join(para))}</p>'); para.clear()
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
            cls = 'as' if who in ('Assistant', 'Tool output', 'System') else 'me'
            out.append(f'<h3 class="{cls}">{esc(who)} <small>{esc(when)}</small></h3>')
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


def folders(x, y, w, names, active, tab_w=150, step=24):
    """`ls chats` as a drawer of manila folders: one per source, the open one pulled to the front."""
    rest = [n for n in names if n != active]
    parts = []
    for k, n in enumerate(rest):                     # back to front
        depth = len(rest) - k
        fy = y + (len(rest) - depth) * step
        tx = x + 6 + k * (w - tab_w - 12) / max(1, len(rest))
        shade = 100 - depth * 4
        parts.append(f'<div class="ftab" style="left:{tx:.1f}px;top:{fy - 26}px;width:{tab_w}px;background:hsl(38 45% {shade - 26}%)">{esc(n)}</div>'
                     f'<div class="folder" style="left:{x}px;top:{fy}px;width:{w}px;height:900px;background:hsl(38 45% {shade - 26}%)"></div>')
    fy = y + len(rest) * step
    tx = x + w - tab_w - 6
    parts.append(f'<div class="ftab" style="left:{tx:.1f}px;top:{fy - 26}px;width:{tab_w}px;{KRAFT}">{esc(active)}</div>'
                 f'<div class="folder" style="left:{x}px;top:{fy}px;width:{w}px;height:900px;{KRAFT}"></div>')
    return ''.join(parts), fy


def front_matter_card(x, y, w, show_cmd, show_out, head_lines, fs=12.6):
    """The chat's catalogue card: its front matter typed verbatim, `aih show` and the path it printed."""
    fm = ''.join(f'<div>{esc(l) or "&nbsp;"}</div>' for l in head_lines if l.strip() or False)
    inner = (f'<div class="typed" style="font-size:{fs}px;line-height:1.5">'
             f'<div class="dim" style="font-size:{fs - .6}px">$ {esc(show_cmd)}</div>'
             f'<div class="dim" style="font-size:{fs - 1.4}px;line-height:1.4;overflow-wrap:anywhere;margin:2px 0 12px;padding-bottom:12px;border-bottom:1px solid var(--rule)">{esc(show_out)}</div>'
             f'{fm}</div>')
    n_path = wrap_lines(show_out, int((w - 44) / ((fs - 1.4) * .6)))
    h = 16 + fs * 1.5 + n_path * (fs - 1.4) * 1.4 + 26 + len([l for l in head_lines if l.strip()]) * fs * 1.5 + 44
    return icard(x, y, w, h, inner, pad='16px 22px 0', hole=True, hole_cls='paper'), h


def markdown_scene(mobile=False):
    md = open(os.path.join(CAP, 'doc.md'), encoding='utf-8').read()
    fm, body = markdown_doc(md)
    show_cmd, show_out = cap('show')
    _, ls = cap('ls')
    _, head = cap('head')
    active = fm.get('source', '')
    if not mobile:
        W, H = WIDE, 760
        cx, cy, cw = 44, 132, 464
        card, ch = front_matter_card(cx, cy, cw, show_cmd, show_out[0], head, fs=13.2)
        nx, nw = 556, 500
        fold, fy = folders(nx - 14, 84, nw + 28, ls, active, tab_w=156)
        note = (f'<div class="note" style="left:{nx}px;top:{fy + 18}px;width:{nw}px;height:{H - fy - 18 + 40}px;transform:rotate(.4deg)">'
                f'<div class="pg">{body}</div><div class="fade"></div></div>')
        lab = f'<div class="abs typed dim" style="left:{nx - 12}px;top:22px;font-size:13px">$ {esc(cap("ls")[0])}</div>'
        lab += pencil_note(nx + 300, 14, 'one folder per source', fs=17, rot=-2)
        arrow = (pencil_note(cx + 8, cy + ch + 34, 'Every card opens into a note:<br>one Markdown file per chat.', fs=18)
                 + pencil_arrow('M4 40 C 70 44, 150 20, 196 -36', 200, 50, cx + 300, cy + ch + 40))
        head_ = (f'<div class="abs typed dim" style="left:{cx + 2}px;top:96px;font-size:13px">$ {esc(cap("head")[0].replace(show_cmd.split()[-1], show_cmd.split()[-1]))}</div>')
        return field(W, H, lab + fold + note + head_ + card + arrow), W, H
    W = NARROW
    cx, cy, cw = 24, 62, 492
    card, ch = front_matter_card(cx, cy, cw, show_cmd, show_out[0], head, fs=13)
    head_ = f'<div class="abs typed dim" style="left:{cx + 2}px;top:30px;font-size:12.5px">$ {esc(cap("head")[0])}</div>'
    arrow = (pencil_note(cx + 6, cy + ch + 20, 'Every card opens into a note.', fs=17.5)
             + pencil_arrow('M4 2 C 40 10, 70 40, 84 92', 90, 96, cx + 262, cy + ch + 30))
    top = cy + ch + 136
    fold, fy = folders(cx - 4, top, cw + 8, ls, active, tab_w=150, step=22)
    nh = 760
    note = (f'<div class="note" style="left:{cx + 8}px;top:{fy + 16}px;width:{cw - 16}px;height:{nh}px">'
            f'<div class="pg" style="padding:22px 26px 0">{body}</div><div class="fade"></div></div>')
    H = int(fy + 16 + nh - 60)
    lab = f'<div class="abs typed dim" style="left:{cx}px;top:{top - 58}px;font-size:12.5px">$ {esc(cap("ls")[0])}</div>'
    return field(W, H, head_ + card + arrow + lab + fold + note), W, H


def collect_parse():
    out = cap('collect')[1]
    pulls = dict(re.findall(r'claude-code (\S+): pulled from (\S+)', '\n'.join(out)))
    counts = dict(re.findall(r'^\s+([\w-]+): (\d+)$', '\n'.join(out), re.M))
    inbox = re.findall(r'^inbox: (\S+) → (.*)$', '\n'.join(out), re.M)
    head = re.match(r'(\d+) changed, (\d+) removed, (\d+) unchanged', out[0])
    return pulls, {k: int(v) for k, v in counts.items()}, inbox, [int(g) for g in head.groups()]


def trolley(x, y, s=1.0):
    """A library book truck: oak sides, two shelves of cards, brass casters, a push handle."""
    cards = lambda yy, n, x0: ''.join(f'<rect x="{x0 + k * 9.5:.1f}" y="{yy - 26 + (k % 3) * 2}" width="8" height="{26 - (k % 3) * 2}" rx="1" fill="#FBF7EC" stroke="#241D17" stroke-width=".9"/>' for k in range(n))
    return (f'<g transform="translate({x},{y}) scale({s})" stroke-linejoin="round">'
            f'<path d="M150 6 L150 -8 Q150 -16 158 -16 L176 -16" fill="none" stroke="#241D17" stroke-width="3.2" stroke-linecap="round"/>'
            f'<rect x="0" y="0" width="156" height="104" rx="3" fill="#9C683B" stroke="#241D17" stroke-width="1.8"/>'
            f'<rect x="9" y="8" width="138" height="40" fill="#5a371c" stroke="#241D17" stroke-width="1.2"/>'
            f'<rect x="9" y="56" width="138" height="40" fill="#5a371c" stroke="#241D17" stroke-width="1.2"/>'
            + cards(48, 14, 12) + cards(96, 14, 12)
            + f'<rect x="9" y="46" width="138" height="5" fill="#BE8954" stroke="#241D17" stroke-width="1"/>'
            f'<rect x="9" y="94" width="138" height="5" fill="#BE8954" stroke="#241D17" stroke-width="1"/>'
            + ''.join(f'<g transform="translate({cx},116)"><line x1="0" y1="-12" x2="0" y2="-4" stroke="#241D17" stroke-width="2"/>'
                      f'<circle r="8.5" fill="#B48C45" stroke="#241D17" stroke-width="1.8"/><circle r="2.4" fill="#241D17"/></g>' for cx in (18, 138))
            + '</g>')


def station(x, y, kind='ok', r=9):
    if kind == 'hub':
        return f'<circle cx="{x}" cy="{y}" r="{r + 4}" fill="#FBF7EC" stroke="#241D17" stroke-width="3"/><circle cx="{x}" cy="{y}" r="{r - 3}" fill="#241D17"/>'
    if kind == 'no':
        return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="#FBF7EC" stroke="#241D17" stroke-width="2" stroke-dasharray="3 2.4"/>'
                f'<path d="M{x - 4} {y - 4} L{x + 4} {y + 4} M{x + 4} {y - 4} L{x - 4} {y + 4}" stroke="#241D17" stroke-width="1.8" stroke-linecap="round"/>')
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="#FBF7EC" stroke="#241D17" stroke-width="3"/>'


def chevrons(points):
    return ''.join(f'<path d="M{x - 5} {y - 6} L{x + 3} {y} L{x - 5} {y + 6}" transform="rotate({a} {x} {y})" fill="none" stroke="#241D17" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
                   for x, y, a in points)


def lbl(x, y, title, lines=(), anchor='start', fs=13.5, tfs=19):
    """A station name in the serif, with the real output beneath it, typed."""
    t = f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Libre Caslon Text" font-size="{tfs}" fill="#241D17">{title}</text>'
    for k, (txt, cls) in enumerate(lines):
        col = {'': '#241D17', 'dim': '#6B6053', 'b': '#241D17'}[cls]
        fw = ' font-weight="700"' if cls == 'b' else ''
        t += f'<text x="{x}" y="{y + 22 + k * (fs * 1.45):.1f}" text-anchor="{anchor}" font-family="Courier Prime" font-size="{fs}" fill="{col}"{fw}>{txt}</text>'
    return t


def docket(x, y, w, title, cmd, lines, fs=13.2, extra='', h=None, right=None):
    body = ''.join(f'<div style="padding-left:{(len(l) - len(l.lstrip())) * .6:.1f}em">{esc(l.strip()) or "&nbsp;"}</div>' for l in lines)
    hs = f'height:{h}px;' if h else ''
    return (f'<div class="slip" style="left:{x}px;top:{y}px;width:{w}px;{hs}padding:18px 24px 22px;{extra}">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;border-bottom:1.5px solid var(--ink);padding-bottom:7px;margin-bottom:10px">'
            f'<span class="sc" style="font-size:16px">{title}</span><span class="typed dim" style="font-size:12.5px">{esc(right) if right else "$ " + esc(cmd)}</span></div>'
            f'<div class="typed" style="font-size:{fs}px;line-height:1.55">{body}</div></div>')


def collect_scene(mobile=False):
    pulls, counts, inbox, (changed, removed, unchanged) = collect_parse()
    n_md = sum(counts.values())
    ccmd, cout = cap('collect')
    bcmd, bout = cap('rebuild')
    inbox_lines = [(f'{esc(f)} → {esc(t)}', '') for f, t in inbox]
    st = stamp(str(changed), f'RECEIVED · {removed} REMOVED · RECEIVED · {removed} REMOVED · ', size=124, rot=8, csize=48, sub='SOURCES', seed_=6)
    timer = [l for l in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'contrib', 'systemd', 'aih-collect.timer')).read().split('\n')
             if l.strip() and not l.startswith(('Description', '[Unit]', '[Install]', 'WantedBy'))]
    if not mobile:
        W, H = WIDE, 900
        L, R, T, B = 214, 1050, 150, 386              # the loop
        dx, lx, ix = 560, 830, 610
        loop = f'M{L} 268 L{L} {T + 22} Q{L} {T} {L + 22} {T} L{R - 22} {T} Q{R} {T} {R} {T + 22} L{R} {B - 22} Q{R} {B} {R - 22} {B} L{L + 22} {B} Q{L} {B} {L} {B - 22} L{L} 268'
        svg = (f'<svg class="abs" style="left:0;top:0;overflow:visible" width="{W}" height="480" viewBox="0 0 {W} 480">'
               f'<path d="{loop}" fill="none" stroke="#241D17" stroke-width="4" stroke-linecap="round"/>'
               f'<path d="M{lx - 50} {T} L{lx - 50} {T - 58}" stroke="#241D17" stroke-width="2" stroke-dasharray="5 4"/>'
               + chevrons([(440, T, 0), (700, T, 0), (960, T, 0), (R, 270, 90), (850, B, 180), (380, B, 180)])
               + station(L, 268, 'hub', 12) + station(dx, T) + station(lx - 50, T - 58, 'no') + station(lx, T) + station(ix, B)
               + lbl(dx, T + 40, 'desktop', [(f'pulled from {esc(pulls.get("desktop", ""))}', 'b')], 'middle')
               + lbl(lx - 66, T - 60, 'laptop-lan', [], 'end', tfs=17)
               + lbl(lx - 66, T - 60 + 2, '', [('no answer', 'dim')], 'end')
               + lbl(lx, T + 40, 'laptop', [(f'pulled from {esc(pulls.get("laptop", ""))}', 'b')], 'middle')
               + lbl(ix, B + 40, 'inbox/', inbox_lines, 'middle', fs=13)
               + trolley(300, T - 112, .84)
               + lbl(L - 22, 262, 'server', [(f'pulled from {esc(pulls.get("server", ""))}', 'b')], 'end', tfs=22)
               + '</svg>')
        notes = (pencil_note(44, 40, 'The trolley does its<br>round every hour.', fs=21)
                 + pencil_note(lx - 30, T - 104, 'away from home,<br>so it tries the next name', fs=16.5, rot=-2)
                 + pencil_note(L + 36, 292, f'the hub, and the only writer:<br>→ archive.db<br>→ chats/, {n_md} Markdown files', fs=16)
                 + pencil_note(R - 150, B - 74, 'never deletes', fs=16.5, rot=-3))
        d1 = docket(44, 520, 580, 'Collection docket', ccmd, cout)
        d2 = docket(656, 520, 400, 'The next round', bcmd, bout, extra='transform:rotate(-.6deg)', fs=12.6)
        n2 = pencil_note(670, 638, 'Run it again: only changed files<br>are read. Nothing had changed.', fs=16.5)
        d3 = docket(672, 716, 384, 'Timetable', '', timer, fs=12.6, extra='transform:rotate(.8deg)', right='contrib/systemd/aih-collect.timer')
        stp = f'<div class="abs" style="left:470px;top:578px;z-index:5">{st}</div>'
        return field(W, H, svg + notes + d1 + d2 + n2 + d3 + stp), W, H
    W = NARROW
    X, T0, B0 = 130, 210, 690
    sy = {'desktop': 300, 'laptop-lan': 392, 'laptop': 470, 'inbox': 580}
    svg = (f'<svg class="abs" style="left:0;top:0;overflow:visible" width="{W}" height="800" viewBox="0 0 {W} 800">'
           f'<path d="M{X} {T0} L{X} {B0 - 20} Q{X} {B0} {X - 20} {B0} L{48} {B0} Q{28} {B0} {28} {B0 - 20} L{28} {T0 + 20} Q{28} {T0} {48} {T0} L{X} {T0}" fill="none" stroke="#241D17" stroke-width="4" stroke-linecap="round"/>'
           f'<path d="M{X} {sy["laptop-lan"]} L{X + 44} {sy["laptop-lan"]}" stroke="#241D17" stroke-width="2" stroke-dasharray="5 4"/>'
           + chevrons([(X, 250, 90), (X, 530, 90), (28, 450, -90)])
           + station(X, T0, 'hub', 12) + station(X, sy['desktop']) + station(X + 44, sy['laptop-lan'], 'no') + station(X, sy['laptop']) + station(X, sy['inbox'])
           + lbl(X + 30, sy['desktop'] + 6, 'desktop', [(f'pulled from {esc(pulls.get("desktop", ""))}', 'b')])
           + lbl(X + 72, sy['laptop-lan'] + 6, 'laptop-lan', [('no answer', 'dim')], tfs=16)
           + lbl(X + 30, sy['laptop'] + 6, 'laptop', [(f'pulled from {esc(pulls.get("laptop", ""))}', 'b')])
           + lbl(X + 30, sy['inbox'] + 6, 'inbox/', [x for f, t in inbox for x in ((esc(f), ''), (f'  → {esc(t)}', 'dim'))], fs=12.4)
           + trolley(250, 92, .9)
           + lbl(X + 30, T0 + 6, 'server', [(f'pulled from {esc(pulls.get("server", ""))}', 'b')], tfs=22)
           + '</svg>')
    notes = pencil_note(26, 28, 'The trolley does its<br>round every hour.', fs=19)
    d1 = docket(24, 780, 492, 'Collection docket', ccmd, cout, fs=12)
    d2 = docket(24, 1118, 492, 'The next round', bcmd, bout, fs=12.4, extra='transform:rotate(-.5deg)')
    n2 = pencil_note(30, 1232, 'Run it again: only changed files are read.', fs=16.5)
    stp = f'<div class="abs" style="left:378px;top:836px;z-index:5">{stamp(str(changed), f"RECEIVED · {removed} REMOVED · RECEIVED · {removed} REMOVED · ", size=112, rot=8, csize=44, sub="SOURCES", seed_=6)}</div>'
    notes += n2
    H = 1290
    return field(W, H, svg + notes + d1 + d2 + stp), W, H


def check_parse():
    res, lines = [], cap('check')[1]
    for i, l in enumerate(lines):
        m = re.match(r'\s+([\w-]+): export has (\d+) chats, archive has (\d+); newest export is (\d+) days old', l)
        if m:
            res.append(dict(src=m.group(1), exp=int(m.group(2)), have=int(m.group(3)), age=int(m.group(4)),
                            lines=[l.strip(), lines[i + 1].strip(), lines[i + 2].strip()], safe=lines[i + 2].strip().startswith('SAFE')))
    return lines[0], res


def withdrawal_slip(x, y, w, r, cmd, fs=13.2, rot=0, n=1, stamp_size=132, text_w=None):
    """One account's verdict as a library withdrawal slip, typed from `aih check`, stamped when it is safe."""
    l1, l2, l3 = r['lines']
    text_w = text_w or w - stamp_size - 40
    verdict = esc(l3).replace('SAFE:', '<b>SAFE:</b>', 1) if r['safe'] else esc(l3)
    body = (f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
            f'<span class="display" style="font-size:25px">Withdrawal slip <span class="it dim" style="font-size:16px">no. {n}</span></span>'
            f'<span class="typed dim" style="font-size:12.5px">$ {esc(cmd)}</span></div>'
            f'<div style="border-top:1.5px solid var(--ink);margin:9px 0 12px"></div>'
            f'<div class="typed" style="width:{text_w}px;font-size:{fs}px;line-height:1.55"><div style="padding-left:4ch;text-indent:-4ch">{esc(l1)}</div>'
            f'<div style="padding-left:4ch;margin-top:3px">{esc(l2)}</div>'
            f'<div style="margin-top:12px;padding-top:9px;border-top:1px dashed var(--rule)"><span class="sc dim" style="font-size:14px;margin-right:10px">Verdict</span>'
            f'<span style="font-size:{fs + .6:.1f}px">{verdict}</span></div></div>')
    st = ''
    if r['safe']:
        st = (f'<div class="abs" style="right:24px;bottom:16px;width:{stamp_size}px;height:{stamp_size}px;z-index:4">'
              + stamp('SAFE', f'{r["have"]} OF {r["exp"]} CHATS ARCHIVED · {r["src"].upper()} · ', size=stamp_size, rot=-14 + n * 9, csize=stamp_size * .22,
                      cfont='Courier Prime', cweight=700, seed_=10 + n) + '</div>')
    return f'<div class="slip" style="left:{x}px;top:{y}px;width:{w}px;padding:20px 28px 22px;transform:rotate({rot}deg)">{body}{st}</div>'


def check_scene(mobile=False):
    head, res = check_parse()
    cmd = cap('check')[0]
    if not mobile:
        W, H = WIDE, 640
        out = f'<div class="abs typed dim" style="left:46px;top:38px;font-size:13px">{esc(head)}</div>'
        for i, r in enumerate(res):
            out += withdrawal_slip(44 + i * 30, 86 + i * 266, 640, r, cmd, rot=(-.6 if i == 0 else .5), n=i + 1, stamp_size=138)
        note = (pencil_note(770, 150, 'Before you delete anything online,<br>ask for a fresh export, drop it in<br>the inbox, then ask the librarian.', fs=18)
                + pencil_note(770, 382, 'An export older than two days?<br>The slip says to fetch a fresh one,<br>because newer chats are not on it.', fs=18))
        return field(W, H, out + note), W, H
    W = NARROW
    out, y = f'<div class="abs typed dim" style="left:26px;top:30px;font-size:12.2px;width:490px">{esc(head)}</div>', 92
    for i, r in enumerate(res):
        out += withdrawal_slip(20 + i * 6, y, 500, r, cmd, fs=12.4, rot=(-.6 if i == 0 else .5), n=i + 1, stamp_size=112, text_w=330)
        y += 300
    note = pencil_note(26, y + 2, 'An export older than two days? The slip<br>says to fetch a fresh one first.', fs=17.5)
    H = y + 76
    return field(W, H, out + note), W, H


# ------------------------------------------------------------------ the floor plan
INK = '#241D17'


def wall(x1, y1, x2, y2, w=6, dash=False):
    d = ' stroke-dasharray="14 7"' if dash else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{INK}" stroke-width="{w}" stroke-linecap="square"{d}/>'


def door(x, y, size, side):
    """A door in plan: the leaf and its swing. side is where the hinge sits and which way it opens."""
    hx, hy = x, y
    if side == 'v-down':      # opening in a vertical wall, hinge at top, swings right
        return (f'<line x1="{hx}" y1="{hy}" x2="{hx + size}" y2="{hy}" stroke="{INK}" stroke-width="2"/>'
                f'<path d="M{hx + size} {hy} A{size} {size} 0 0 1 {hx} {hy + size}" fill="none" stroke="{INK}" stroke-width="1" stroke-dasharray="3 3"/>')
    if side == 'h-right':     # opening in a horizontal wall, hinge at left, swings down
        return (f'<line x1="{hx}" y1="{hy}" x2="{hx}" y2="{hy + size}" stroke="{INK}" stroke-width="2"/>'
                f'<path d="M{hx} {hy + size} A{size} {size} 0 0 0 {hx + size} {hy}" fill="none" stroke="{INK}" stroke-width="1" stroke-dasharray="3 3"/>')
    return ''


def room(x, y, w, title, lines, fs=12.8, tfs=15.5):
    """A room label: name in small caps, then what happens there, typed. lines: (text, bold)."""
    body = ''.join(f'<div style="{"font-weight:700;margin-top:6px" if b else "color:var(--ink-2)"}">{t}</div>' for t, b in lines)
    return (f'<div class="abs" style="left:{x}px;top:{y}px;width:{w}px"><div class="sc" style="font-size:{tfs}px;letter-spacing:.12em">{title}</div>'
            f'<div class="typed" style="font-size:{fs}px;line-height:1.42;margin-top:3px">{body}</div></div>')


def shelves(x, y, w, n, gap=14):
    return ''.join(f'<rect x="{x}" y="{y + k * gap}" width="{w}" height="6" fill="#d9ccb0" stroke="{INK}" stroke-width="1.1"/>'
                   f'<line x1="{x}" y1="{y + k * gap + 3}" x2="{x + w}" y2="{y + k * gap + 3}" stroke="{INK}" stroke-width=".6"/>' for k in range(n))


def table(x, y, w, h, chairs=3):
    c = ''.join(f'<rect x="{x + (k + .5) * w / chairs - 5:.1f}" y="{y - 11}" width="10" height="8" rx="1.5" fill="none" stroke="{INK}" stroke-width="1"/>'
                f'<rect x="{x + (k + .5) * w / chairs - 5:.1f}" y="{y + h + 3}" width="10" height="8" rx="1.5" fill="none" stroke="{INK}" stroke-width="1"/>' for k in range(chairs))
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#efe5d0" stroke="{INK}" stroke-width="1.2"/>{c}'


def title_block(x, y, w, rows):
    cells = ''.join(f'<div style="display:flex;justify-content:space-between;gap:12px;padding:4px 10px;border-top:1px solid {INK}">'
                    f'<span class="sc" style="font-size:12px">{k}</span><span class="typed" style="font-size:12px">{v}</span></div>' for k, v in rows[1:])
    return (f'<div class="abs" style="left:{x}px;top:{y}px;width:{w}px;border:1.6px solid {INK};background:rgba(251,247,236,.6)">'
            f'<div class="display" style="font-size:19px;padding:6px 10px 5px">{rows[0]}</div>{cells}</div>')


def architecture_scene(mobile=False):
    ms = f'{BENCH["query_ms_median"]:.1f}'
    srcs = [('claude.ai', 'official export,<br>uploads linked'), ('Claude Code', '~/.claude/projects,<br>every machine'), ('ChatGPT', 'export zip, one<br>folder per account')]
    rules = ['only changed files re-import', 'edited prompts kept as branches', 'resumed sessions stored once',
             'chats deleted online never imported', 'system noise kept out of search', 'half-synced exports wait their turn']
    tb = title_block
    if not mobile:
        W, H = WIDE, 836
        X0, X1, Y0, Y1 = 196, 1056, 54, 470
        xa, xb, xc, ym = 350, 656, 862, 284
        sv = [wall(X0, Y0, X1, Y0), wall(X0, Y1, X1, Y1), wall(X1, Y0, X1, 330), wall(X1, 394, X1, Y1)]
        drops = [126, 258, 390]
        yy = Y0
        for d in drops:                                   # the left wall, with a book drop for each source
            sv.append(wall(X0, yy, X0, d - 16)); yy = d + 16
        sv.append(wall(X0, yy, X0, Y1))
        sv += [wall(xa, Y0, xa, 236), wall(xa, 286, xa, Y1),
               wall(xb, Y0, xb, 168), wall(xb, 214, xb, 376), wall(xb, 422, xb, Y1),
               wall(xc, Y0, xc, 214), wall(xc, 260, xc, 376), wall(xc, 422, xc, Y1),
               wall(xb, ym, xc, ym, 4)]
        sv += [door(xa, 236, 50, 'v-down'), door(xb, 168, 46, 'v-down'), door(xb, 376, 46, 'v-down'),
               door(xc, 214, 46, 'v-down'), door(xc, 376, 46, 'v-down'), door(X1 - 64, 330, 64, 'v-down')]
        for d in drops:
            sv.append(f'<path d="M{X0 - 50} {d} L{X0 + 14} {d}" stroke="{INK}" stroke-width="1.6" marker-end="url(#ah)"/>'
                      f'<rect x="{X0 - 4}" y="{d - 16}" width="8" height="32" fill="#E2D6BC" stroke="{INK}" stroke-width="1"/>')
        sv.append(shelves(680, 176, 156, 5, 18))
        sv.append(table(684, 412, 66, 24, 3) + table(768, 412, 66, 24, 3))
        # circulation desk: an L-shaped counter with the librarian's chair
        dx0, dy0 = xc + 62, 336
        sv.append(f'<path d="M{dx0} {dy0} L{dx0 + 112} {dy0} L{dx0 + 112} {dy0 + 62} L{dx0 + 96} {dy0 + 62} L{dx0 + 96} {dy0 + 16} L{dx0} {dy0 + 16} Z" fill="#efe5d0" stroke="{INK}" stroke-width="1.4"/>'
                  f'<rect x="{dx0 + 60}" y="{dy0 + 26}" width="14" height="14" rx="2" fill="none" stroke="{INK}" stroke-width="1"/>')
        # card cabinet in cataloguing
        sv.append(f'<rect x="{xa + 200}" y="{Y1 - 104}" width="88" height="60" fill="#efe5d0" stroke="{INK}" stroke-width="1.2"/>'
                  + ''.join(f'<line x1="{xa + 200 + k * 22}" y1="{Y1 - 104}" x2="{xa + 200 + k * 22}" y2="{Y1 - 44}" stroke="{INK}" stroke-width=".8"/>' for k in range(1, 4))
                  + ''.join(f'<line x1="{xa + 200}" y1="{Y1 - 104 + k * 15}" x2="{xa + 288}" y2="{Y1 - 104 + k * 15}" stroke="{INK}" stroke-width=".8"/>' for k in range(1, 4)))
        # the route a search takes, desk to stacks and back (violet: what aih finds)
        sv.append(f'<path d="M{dx0 + 40} {dy0 - 6} C {dx0 + 30} 280, {xc + 30} 232, {xc - 20} 232 L 800 232 C 770 232, 770 252, 800 252 L {xc - 20} 252 '
                  f'C {xc + 40} 252, {dx0 + 52} 290, {dx0 + 56} {dy0 - 8}" fill="none" stroke="#5A3AA8" stroke-width="2.4" stroke-dasharray=".5 6.5" stroke-linecap="round"/>'
                  f'<circle cx="784" cy="242" r="5" fill="#5A3AA8"/>')
        # the annex: optional, so drawn dashed, like a proposed wing
        A0, A1 = 594, 712
        sv += [wall(X0, A0, X1, A0, 4, True), wall(X0, A1, X1, A1, 4, True), wall(X0, A0, X0, A1, 4, True), wall(X1, A0, X1, A1, 4, True),
               wall(X0 + 287, A0, X0 + 287, A1, 3, True), wall(X0 + 574, A0, X0 + 574, A1, 3, True),
               wall(700, Y1, 700, A0, 3, True), wall(748, Y1, 748, A0, 3, True)]
        sv += [f'<path d="M{X0 + 262} {A0 + 92} L{X0 + 312} {A0 + 92}" stroke="{INK}" stroke-width="1.4" marker-end="url(#ah)"/>',
               f'<path d="M{X0 + 549} {A0 + 92} L{X0 + 599} {A0 + 92}" stroke="{INK}" stroke-width="1.4" marker-end="url(#ah)"/>']
        svg = (f'<svg class="abs" style="left:0;top:0;overflow:visible" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><defs>'
               f'<marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{INK}"/></marker></defs>'
               + ''.join(sv) + '</svg>')
        txt = ''.join(f'<div class="abs" style="left:12px;top:{d - 26}px;width:122px;text-align:right"><div style="font-family:var(--text);font-size:16px">{n}</div>'
                      f'<div class="typed dim" style="font-size:11.5px;line-height:1.3">{dsc}</div></div>' for (n, dsc), d in zip(srcs, drops))
        txt += room(X0 + 18, Y0 + 20, 128, 'Receiving', [('inbox/ holds exports until they stop changing', False),
                                                          ('rsync', True), ('brings Claude Code in, never deletes', False)], fs=12)
        txt += room(xa + 20, Y0 + 20, 280, 'Cataloguing', [('aih collect · hourly', True)] + [(r, False) for r in rules])
        txt += room(xb + 18, Y0 + 20, 190, 'The stacks', [('archive.db', True), ('SQLite + FTS5, BM25', False)], fs=12.6)
        txt += room(xb + 18, ym + 18, 190, 'Reading room', [('chats/*.md', True), ('one file per chat', False)], fs=12.6)
        txt += room(xc + 20, Y0 + 20, 180, 'Circulation', [('aih search', True), ('stats · show · check', True), ('sqlite3 · agents', True)], fs=12.6)
        txt += pencil_note(xc + 18, 412, f'<span style="color:#5A3AA8">a search: {ms} ms,<br>stacks and back</span>', fs=15)
        txt += pencil_note(X1 + 8, 338, 'you', fs=17)
        txt += f'<div class="abs" style="left:{X0}px;top:{A0 - 40}px"><span class="sc" style="font-size:16px;letter-spacing:.12em">The annex</span>' \
               f'<span class="it dim" style="font-size:16px;margin-left:10px">optional · mine.py · open nightly</span></div>'
        for k, (t, l1, l2) in enumerate([('1 · Extract', 'a fast model reads', 'only your own messages'), ('2 · Verify', 'a second, stronger model', 'checks every fact'),
                                         ('3 · Review', 'notes for you; your', 'profile is never edited')]):
            txt += room(X0 + 22 + k * 287, A0 + 22, 236, t, [(l1, False), (l2, False)], tfs=14.5)
        txt += pencil_note(758, 520, 'reads archive.db', fs=15)
        txt += tb(X1 - 300, A1 + 24, 300, ['aih · ground floor plan', ('drawn by', 'readme-visuals.py'), ('scale', 'one Python file')])
        txt += pencil_note(X0, A1 + 30, 'Dashed walls are optional, and only open at night.', fs=16.5)
        return field(W, H, svg + txt), W, H
    # phone: the same building, rooms stacked
    W = NARROW
    X0, X1 = 26, 514
    Y = [150, 252, 474, 664, 820]                      # receiving | cataloguing | reading + stacks | circulation | end
    D0, D1 = 418, 470                                  # door openings sit at the right, clear of the text
    sv = [wall(X0, Y[0], X1, Y[0]), wall(X0, Y[0], X0, Y[4]), wall(X1, Y[0], X1, Y[4]), wall(X0, Y[4], X1, Y[4])]
    for y in Y[1:4]:
        sv += [wall(X0, y, D0, y), wall(D1, y, X1, y)]
        sv.append(door(D0, y, D1 - D0, 'h-right'))
    sv.append(wall(270, Y[2], 270, Y[3], 4))
    xs = [110, 270, 430]
    for x in xs:
        sv.append(f'<path d="M{x} {Y[0] - 54} L{x} {Y[0] + 12}" stroke="{INK}" stroke-width="1.6" marker-end="url(#ah)"/>'
                  f'<rect x="{x - 16}" y="{Y[0] - 4}" width="32" height="8" fill="#E2D6BC" stroke="{INK}" stroke-width="1"/>')
    sv.append(shelves(296, Y[2] + 92, 150, 5, 16))
    dx0, dy0 = 300, Y[3] + 96
    sv.append(f'<path d="M{dx0} {dy0} L{dx0 + 120} {dy0} L{dx0 + 120} {dy0 + 16} L{dx0} {dy0 + 16} Z" fill="#efe5d0" stroke="{INK}" stroke-width="1.4"/>'
              f'<rect x="{dx0 + 54}" y="{dy0 + 24}" width="13" height="13" rx="2" fill="none" stroke="{INK}" stroke-width="1"/>')
    sv.append(f'<path d="M{dx0 + 100} {dy0 - 6} C {dx0 + 120} {Y[3] + 40}, {D0 + 30} {Y[3] + 30}, {D0 + 26} {Y[3] - 10} L {D0 + 20} {Y[2] + 150} '
              f'C {D0 + 16} {Y[2] + 120}, {D0 - 20} {Y[2] + 128}, 400 {Y[2] + 126}" fill="none" stroke="#5A3AA8" stroke-width="2.4" stroke-dasharray=".5 6.5" stroke-linecap="round"/>'
              f'<circle cx="398" cy="{Y[2] + 126}" r="5" fill="#5A3AA8"/>')
    A0, A1 = 880, 1010
    sv += [wall(X0, A0, X1, A0, 4, True), wall(X0, A1, X1, A1, 4, True), wall(X0, A0, X0, A1, 4, True), wall(X1, A0, X1, A1, 4, True),
           wall(250, Y[4], 250, A0, 3, True), wall(290, Y[4], 290, A0, 3, True)]
    svg = (f'<svg class="abs" style="left:0;top:0;overflow:visible" width="{W}" height="1250" viewBox="0 0 {W} 1250"><defs>'
           f'<marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{INK}"/></marker></defs>'
           + ''.join(sv) + '</svg>')
    txt = ''.join(f'<div class="abs" style="left:{x - 80}px;top:24px;width:160px;text-align:center"><div style="font-family:var(--text);font-size:16px">{n}</div>'
                  f'<div class="typed dim" style="font-size:11px;line-height:1.3">{dsc}</div></div>' for (n, dsc), x in zip(srcs, xs))
    txt += room(X0 + 18, Y[0] + 22, 440, 'Receiving', [('inbox/ holds exports until they stop changing;', False), ('rsync brings Claude Code in, never deletes', False)], fs=12)
    txt += room(X0 + 18, Y[1] + 18, 440, 'Cataloguing', [('aih collect · hourly', True)] + [(r, False) for r in rules], fs=12.4)
    txt += room(X0 + 18, Y[2] + 18, 220, 'Reading room', [('chats/*.md', True), ('one file per chat', False)], fs=12.4)
    txt += room(288, Y[2] + 18, 210, 'The stacks', [('archive.db', True), ('SQLite + FTS5', False)], fs=12.4)
    txt += room(X0 + 18, Y[3] + 18, 380, 'Circulation', [('aih search · stats', True), ('show · check', True), ('sqlite3 · agents · CLAUDE.md', True)], fs=12.4)
    txt += pencil_note(X0 + 20, Y[3] + 112, f'<span style="color:#5A3AA8">a search: {ms} ms</span>', fs=15.5)
    txt += pencil_note(302, Y[4] + 16, 'reads archive.db', fs=14.5)
    txt += room(X0 + 18, A0 + 16, 450, 'The annex <span class="it" style="font-variant:normal;letter-spacing:0;text-transform:none;font-size:14px">· optional · mine.py · nightly</span>',
                [('1 a fast model extracts facts from your words', False), ('2 a stronger model verifies them', False), ('3 notes for you; your profile is never edited', False)], fs=12)
    txt += tb(X1 - 270, A1 + 20, 270, ['aih · ground floor plan', ('drawn by', 'readme-visuals.py'), ('scale', 'one Python file')])
    H = A1 + 120
    return field(W, H, svg + txt), W, H


def social():
    cmd, res = results('hero-mobile')
    q = query_of(cmd)

    def label(W, fy):
        inner = (f'<div style="position:relative;width:100%;height:100%;display:flex;flex-direction:column;justify-content:center">'
                 f'<b class="typed" style="font-size:25px">{esc(q)}</b></div>')
        return brass_label((W - 290) / 2, fy + 26, 290, 66, inner) + cup_pull(W / 2, fy + 26 + 66 + 22, 104)

    W = 560
    d, H = drawer(W, res, label, fs=15.5, front_h=330, band=60, panel_h=170, tabs=(('CHATGPT', .02), ('CLAUDE.AI', .5), ('CLAUDE CODE', .98)), back=58)
    top_front = 58 + 34 + 2 * 60
    st = stamp(f'{BENCH["query_ms_median"]:.1f}', f'MEDIAN SEARCH · {BENCH["messages"]:,} MESSAGES · ', size=126, rot=-9, csize=48, sub='MS')
    left = (f'<div class="abs" style="left:64px;top:62px">{mark(38)}</div>'
            '<h1 class="abs display" style="left:62px;top:168px;width:600px;font-size:84px;line-height:.96">Every AI chat you’ve had, <i>catalogued.</i></h1>'
            '<p class="abs lede" style="left:65px;top:470px;width:560px;font-size:25px;line-height:1.4">claude.ai, Claude Code and ChatGPT, word for word, '
            'in one SQLite file on your own disk.</p>')
    right = (f'<div class="abs" style="left:680px;top:-6px;width:{W}px;height:{H}px">{d}'
             f'<div class="abs" style="left:{W - 15 - 140}px;top:{top_front + 330 - 134}px;z-index:5">{st}</div></div>')
    return field(1280, 640, left + right), 1280, 640


SCENES = {
    'hero': lambda: hero(), 'hero-mobile': lambda: hero(True),
    'numbers': lambda: numbers_scene(), 'numbers-mobile': lambda: numbers_scene(True),
    'search': lambda: search_scene(), 'search-mobile': lambda: search_scene(True),
    'stats': lambda: stats_scene(), 'stats-mobile': lambda: stats_scene(True),
    'markdown': lambda: markdown_scene(), 'markdown-mobile': lambda: markdown_scene(True),
    'collect': lambda: collect_scene(), 'collect-mobile': lambda: collect_scene(True),
    'check': lambda: check_scene(), 'check-mobile': lambda: check_scene(True),
    'architecture': lambda: architecture_scene(), 'architecture-mobile': lambda: architecture_scene(True),
    'social': social,
}


# ------------------------------------------------------------------ render
def chrome(*args, profile):
    env = {k: v for k, v in os.environ.items() if k != 'TMPDIR'}  # a long TMPDIR breaks Chrome's sockets
    return subprocess.run([CHROME, '--headless=new', '--no-sandbox', '--hide-scrollbars', '--disable-gpu', '--no-first-run',
                           '--no-default-browser-check', f'--user-data-dir={profile}', '--virtual-time-budget=9000', *args],
                          capture_output=True, text=True, timeout=180, env=env)


def render(name, body, w, h, tmp):
    w, h = int(round(w)), int(round(h))
    os.makedirs(SRC, exist_ok=True)
    page = os.path.join(SRC, name + '.html')
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>aih · {name}</title>{FONTS}'
           f'<link rel="stylesheet" href="aih.css"></head><body>{body}</body></html>\n')
    open(page, 'w', encoding='utf-8').write(doc)
    png = os.path.join(tmp, name + '.png')
    scale = 2
    chrome(f'--force-device-scale-factor={scale}', f'--window-size={w},{h}', f'--screenshot={png}', 'file://' + os.path.abspath(page),
           profile=os.path.join(tmp, 'chrome'))
    if not os.path.exists(png):
        sys.exit(f'Chrome wrote nothing for {name}')
    if name == 'social':
        out = os.path.join(OUT, 'social.png')
        subprocess.run(['magick', png, '-resize', '1280x640!', '-strip', out], check=True)
    else:
        out = os.path.join(OUT, name + '.webp')
        subprocess.run(['magick', png, '-strip', '-quality', '86', '-define', 'webp:method=6', out], check=True)
    size = os.path.getsize(out) // 1024
    dims = subprocess.run(['magick', 'identify', '-format', '%wx%h', out], capture_output=True, text=True).stdout
    print(f'{os.path.basename(out):24} {dims:>10}  {size:4d} KB')


def main():
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, build in SCENES.items():
            if ONLY and name not in ONLY:
                continue
            body, w, h = build()
            render(name, body, w, h, tmp)


if __name__ == '__main__':
    main()
