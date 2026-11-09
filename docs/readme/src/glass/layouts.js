// aih in Glass: every composition of the README. The windows show real aih output (see
// scripts/readme-tex.py); the accent light is violet, the colour aih's search hits take.
import { lights, term, doc, lift, hero, heroPhone, panel, panelPhone, band, bandPhone, social } from './grammar.js';

const A = { ray: '#b9b0ec', pool: '#5a43c8', deep: '#2c2560', lift: '#6a52d8', top: '#0b0b15', haze: '#1c1b30', fog: '#0c0c14',
  mote: '#e4dcff', day: '#f1f0f6', shade: '#ecebf3', dayFog: '#f1f0f6' };
const L = lights(A);

export function build(M) {
  const F = M.facts;
  const HERO = {
    name: 'aih', h: 600, hp: 640,
    line: 'Every AI conversation, from every machine, searchable on your own disk.',
    linePhone: 'Every AI conversation, from every machine,<br>searchable on your own disk.',
    win: (n, ph) => {
      const P = ph
        ? { s: { x: 86, y: 262, w: 150, z: -420, rot: [4, 28, 0] }, d: { x: 298, y: 262, w: 120, z: -420, rot: [4, -28, 0] }, m: { x: 190.5, y: 400, w: 316, z: 0, rot: [3, 0, 0] } }
        : { s: { x: 170, y: 322, w: 270, z: -420, rot: [4, 28, 0] }, d: { x: 674, y: 326, w: 210, z: -420, rot: [4, -28, 0] }, m: { x: 420, y: 378, w: 380, z: 0, rot: [3, 0, 0] } };
      const far = { fog: n ? 0.42 : 0.30, lod: 0.8, defocus: 1.6, breathe: [14, 0.15] };
      return [
        term(M, 'stats', P.s, n, A, { ...far }),
        doc(M, 'chat', P.d, n, A, { ...far, breathe: [14, 0.7] }),
        term(M, 'search', P.m, n, A, { breathe: [10, 0.4], bezel: 10, glow: 0.75 }),
        lift(M, 2, 'search', 'key', n, A, { lift: ph ? 60 : 90, grow: ph ? 0.98 : 1.0, breathe: [12, 0.85] }),
      ];
    },
  };
  const SEARCH = {
    kick: 'Search', head: 'Find it in milliseconds',
    body: 'Type the words you remember. Every source is searched at once and ranked with BM25. Keep only your own words with <code>--me</code>, or pass FTS5 syntax with <code>--raw</code>.',
    win: (n, ph) => {
      const P = ph ? { a: { x: 168, y: 350, w: 280, z: -80, rot: [2, -14, 0] }, b: { x: 214, y: 464, w: 270, z: 60, rot: [0, -12, 0] } }
        : { a: { x: 548, y: 190, w: 330, z: -90, rot: [2, -18, 0] }, b: { x: 640, y: 306, w: 290, z: 50, rot: [0, -12, 0] } };
      return [
        term(M, 'me', P.a, n, A, { breathe: [8, 0.0] }),
        term(M, 'near', P.b, n, A, { breathe: [8, 0.45] }),
        lift(M, 1, 'near', 'key', n, A, { lift: 80, shift: [ph ? 0 : -24, 0] }),
      ];
    },
  };
  const COLLECT = {
    kick: 'Collect', head: 'Every machine, every hour',
    body: '<code>aih collect</code> pulls Claude Code transcripts over SSH, LAN first, and imports website exports from an inbox. It never deletes, and a second run re-imports nothing.',
    win: (n, ph) => {
      const P = ph ? { a: { x: 184, y: 348, w: 310, z: -110, rot: [2, -12, 0] }, b: { x: 206, y: 462, w: 280, z: 60, rot: [0, -10, 0] } }
        : { a: { x: 574, y: 176, w: 360, z: -140, rot: [2, -18, 0] }, b: { x: 628, y: 300, w: 300, z: 50, rot: [0, -12, 0] } };
      return [
        term(M, 'stats', P.a, n, A, { breathe: [8, 0.0] }),
        term(M, 'collect', P.b, n, A, { breathe: [8, 0.45] }),
        lift(M, 1, 'collect', 'key', n, A, { lift: 90 }),
      ];
    },
  };
  const MARKDOWN = {
    kick: 'Markdown', head: 'Read any chat like a document', hw: 320,
    body: 'Every chat is also a Markdown file with its source, model and machine up front. Thinking and tool calls fold away, so it reads cleanly in any editor.',
    win: (n, ph) => {
      const P = ph ? { a: { x: 162, y: 392, w: 240, z: -80, rot: [2, -12, 0] }, b: { x: 252, y: 470, w: 230, z: 70, rot: [0, -12, 0] } }
        : { a: { x: 552, y: 212, w: 270, z: -90, rot: [2, -18, 0] }, b: { x: 680, y: 320, w: 250, z: 70, rot: [0, -12, 0] } };
      return [
        doc(M, 'chat', P.a, n, A, { breathe: [8, 0.0] }),
        term(M, 'show', P.b, n, A, { breathe: [8, 0.45] }),
        lift(M, 0, n ? 'chat' : 'chat-light', 'key', n, A, { lift: 90, pad: 0, radius: 14, key: n ? '#0B0E14' : '#F7F7F5', keyAmt: n ? 0.7 : 0.8, shift: [ph ? 0 : -30, 0] }),
      ];
    },
  };
  const CHECK = {
    kick: 'Check', head: 'Delete online with proof, not hope', hw: 320,
    body: 'Before you delete chats from a website, <code>aih check</code> compares its newest export with the archive. It says SAFE only when every chat is already there.',
    win: (n, ph) => {
      const P = ph ? { a: { x: 190, y: 420, w: 340, z: -40, rot: [2, -10, 0] } } : { a: { x: 584, y: 218, w: 390, z: -60, rot: [2, -18, 0] } };
      return [
        term(M, 'check', P.a, n, A, { breathe: [8, 0.0] }),
        lift(M, 0, 'check', 'key', n, A, { lift: ph ? 70 : 100, grow: ph ? 1.0 : 1.04, shift: [ph ? 0 : -36, 0] }),
      ];
    },
  };
  const FACTS = { glow: A.deep, hi: '#c9b9ff', hiDay: '#5b3fc4', facts: [
    [`${F.ms} ms`, `median search over ${F.messages} messages`, true],
    [String(F.sources), 'sources: claude.ai, Claude Code and ChatGPT'],
    ['1 file', 'of standard-library Python, no dependencies'],
    [String(F.smoke), 'end-to-end checks in CI'],
  ] };
  // social preview: the hero's main window and its lifted line at the right, one page behind it
  const socialWin = (n) => { const w = HERO.win(n, false); return [
    { ...w[1], x: 590, y: 150, w: 128, z: -320, rot: [3, -26, 0] },
    { ...w[2], x: 456, y: 162, w: 236, z: 0, rot: [2, -12, 0] },
    { ...w[3], parent: 1, lift: 70, shift: [-10, 0] }]; };
  return {
    hero: hero(HERO, L), 'hero-phone': heroPhone(HERO, L),
    numbers: band(FACTS, L), 'numbers-phone': bandPhone(FACTS, L),
    search: panel(SEARCH, L), 'search-phone': panelPhone(SEARCH, L),
    collect: panel(COLLECT, L), 'collect-phone': panelPhone(COLLECT, L),
    markdown: panel(MARKDOWN, L), 'markdown-phone': panelPhone(MARKDOWN, L),
    check: panel(CHECK, L), 'check-phone': panelPhone(CHECK, L),
    social: social({ kick: 'CLI · Python', name: 'aih', line: 'Every AI conversation, from every machine, searchable on your own disk.',
      win: socialWin }, L),
  };
}
