"""
Browser-measured page splitter (ADR 0002).

Loads each rendered sheet HTML in the shared Playwright browser, measures real
block heights against the sheet's content limit, elects each recipe's layout
(ADR 0009), and rebuilds overflowing sources into multi-sheet documents broken
only at safe boundaries:

- recipes: side-by-side only while everything fits ONE sheet; any overflow
  rebuilds the page as stacked vertical bands - ingredients streamed through
  two height-balanced columns first, instructions likewise directly below -
  so ingredients and instructions are never printed side by side on a
  multi-sheet recipe. Giants break out full-width across both columns.
- content pages: direct children of the prose container; tall tables are
  rebuilt into row-chunks (header row repeated) so a table starts right after
  its intro text and flows onto the next sheet instead of being moved there
  wholesale - no half-empty sheets before a table
- TOC pages: whole ``toc-section`` blocks

Continuation sheets repeat the title as an eyebrow strip unless their whole
content is sliced-diagram bands or other unbreakable giant blocks - pure
artwork pages print without the repeated title. Unbreakable
"giant" blocks (mermaid flowcharts, tall images) get their own sheet and
may overlap the footer band - the footer renders behind content - and are only
scaled down when they cannot physically fit on the paper.

Sliced diagrams carry a seam guarantee: every band is a true SVG slice (a
copy of the diagram svg whose viewBox shows exactly that band's row range),
sized against its clipping container after the verification pass, so
consecutive bands meet row-for-row with zero diagram rows lost. The shared
seam audit (``audit_page_seams``) re-checks this on any loaded page;
html_to_pdf runs it as a conversion gate before page.pdf().
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple

from html_to_pdf import (
    PAGE_LOAD_TIMEOUT,
    _get_browser,
    _path_to_uri,
    wait_for_render_settled,
)

# The measurement epsilon and the scale floor are consumed by the in-browser
# pass below (``EPS`` / ``MIN_SCALE``), not by Python.

_FOOTER_TOKEN_RE = re.compile(
    r'<div\s+data-page-footer(?:\s*=\s*"[^"]*")?\s*/?>'
)
# A sheet div's class list may carry extra classes on top of ``recipe-page``
# (e.g. the TODO watermark's ``notdone-watermark``), so match the class as a
# substring instead of the exact attribute value.
_SHEET_RE = re.compile(r'<div[^>]*class="[^"]*\brecipe-page\b[^"]*"[^>]*>')
# Legacy template shape the combiner still recognises
# (html_to_pdf.A4PageExtractor.PAGE_PATTERNS); current templates do not emit
# it, but the sheet diagnostics count both so they stay honest.
_SHEET_LEGACY_RE = re.compile(r'<main[^>]*class="[^"]*a4-page[^"]*"[^>]*>')


def count_sheets(html: str) -> int:
    """Number of page-container sheets (both template shapes) in ``html``."""
    return (len(_SHEET_RE.findall(html))
            + len(_SHEET_LEGACY_RE.findall(html)))


def _ensure_footer_tokens(html: str) -> str:
    """Re-inject missing footer tokens into .recipe-page sheets.

    Continuation sheets created by cloneNode(true) should preserve the
    ``<div data-page-footer>`` token, but if any sheet lost it the combiner
    will extract it without a token and ``inject_page_footer`` will silently
    skip it.  Walk each ``.recipe-page`` div, and append the token before its
    closing ``</div>`` when absent.
    """
    out: List[str] = []
    last = 0
    for m in _SHEET_RE.finditer(html):
        out.append(html[last:m.start()])
        start = m.end()
        depth = 1
        pos = start
        close_pos = -1
        while pos < len(html) and depth > 0:
            open_idx = html.find('<div', pos)
            close_idx = html.find('</div>', pos)
            if close_idx == -1:
                break
            if open_idx != -1 and open_idx < close_idx:
                depth += 1
                pos = open_idx + 4
            else:
                depth -= 1
                close_pos = close_idx
                pos = close_idx + 6

        if close_pos != -1:
            inner = html[start:close_pos]
            closing = html[close_pos:close_pos + 6]
        else:
            inner = html[start:]
            closing = ''

        if not _FOOTER_TOKEN_RE.search(inner):
            inner = inner + '<div data-page-footer></div>'

        out.append(m.group(0) + inner + closing)
        last = pos

    out.append(html[last:])
    return ''.join(out)


_JS_SPLITTER_TEMPLATE = r"""
() => {
  /*__SEAM_JS__*/
  // 14px (~3.7mm) safety margin absorbs sub-millimetre drift between this
  // measurement pass and the final print layout, keeping every sheet clear
  // of the content limit with room to spare above the footer band.
  const EPS = 14.0;
  const MIN_SCALE = 0.55;
  // ADR 0017: lowest scale still readable when shrinking a diagram so it can
  // join the text above it on the same sheet (the retired whole-page
  // scale-to-fit used the much lower 0.55 floor).
  const JOIN_FLOOR = 0.80;
  // Content-page tables taller than this are rebuilt into row-chunk tables
  // (header repeated per chunk) so they pack like ordinary units instead of
  // stranding as one unbreakable block.
  const TABLE_CHUNK_MAX = 420;
  // Minimum row count for a boundary band: band 0 smaller than this is
  // dropped, and the last band is padded up to this many rows so no
  // near-blank continuation sheet ever shows a hairline of diagram.
  const SLIVER_MIN = 80;

  const sheet = document.querySelector('.recipe-page');
  if (!sheet) return {changed: false, reason: 'no-sheet'};

  // Normalize the screen-only flex wrapper so sheets stack vertically at full
  // width while measuring (print CSS does the same at conversion time).
  const mainEl = sheet.closest('main');
  if (mainEl) {
    mainEl.style.display = 'block';
    mainEl.style.padding = '0';
    mainEl.style.minHeight = '0';
  }
  const scs = getComputedStyle(sheet);
  const padTop = parseFloat(scs.paddingTop) || 0;
  const padBot = parseFloat(scs.paddingBottom) || 0;
  const budget = sheet.clientHeight - padTop - padBot - EPS;

  const aside = sheet.querySelector('aside[data-purpose=ingredients-sidebar]');
  const article = sheet.querySelector('article[data-purpose=recipe-instructions]');
  // Recipes without an Ingredients section print with NO sidebar at all
  // (data-vertical-recipe marker on the article). They always elect the
  // vertical layout: side-by-side would need the ingredients panel that does
  // not exist, so the election never offers it.
  const forceVertical = !!(article && article.hasAttribute('data-vertical-recipe'));
  let kind = 'content';
  if (aside && article) kind = 'recipe';
  else if (forceVertical) kind = 'recipe';
  else if (sheet.querySelector('.toc-section')) kind = 'toc';

  // Header block = first direct sheet child containing an h1.
  let header = null;
  for (const c of sheet.children) {
    if (c.querySelector && c.querySelector('h1')) { header = c; break; }
  }
  // Margin-box height: the header's mb-* margin pushes the content column
  // down but border-box rects don't see it. Ignoring it over-allocated the
  // first band, whose bottom rows were then clipped at the sheet seam.
  const headerH = header
    ? header.getBoundingClientRect().height +
      (parseFloat(getComputedStyle(header).marginBottom) || 0)
    : 0;
  const titleText = header && header.querySelector('h1')
    ? header.querySelector('h1').textContent.trim() : '';

  let container;
  if (kind === 'recipe') {
    container = (aside && aside.closest('.grid')) || article.closest('.grid');
  } else {
    container = sheet.querySelector('.content-text') ||
                Array.from(sheet.children).find(c => c !== header);
  }
  const contMT = container ? (parseFloat(getComputedStyle(container).marginTop) || 0) : 0;

  // Column model: each column packs independently.
  const cols = [];
  if (kind === 'recipe') {
    const stepsWrap = article.querySelector('.space-y-2') || article;
    if (aside) {
      cols.push({key: 'aside', sel: 'aside[data-purpose=ingredients-sidebar]',
                 wrapInHost: false,
                 units: Array.from(aside.children).filter(n => n.nodeType === 1)});
    }
    cols.push({key: 'article', sel: 'article[data-purpose=recipe-instructions]',
               wrapInHost: true,
               units: Array.from(stepsWrap.children).filter(n => n.nodeType === 1)});
  } else {
    cols.push({key: 'main', sel: null, wrapInHost: false,
               units: Array.from(container.children).filter(n => n.nodeType === 1)});
  }
  cols.forEach(col => {
    if (col.key !== 'aside') return;
    // Split oversized sidebar sections (e.g. huge Ingredients lists) into
    // chunk sections of list items, so they can CONTINUE across sheets as
    // items instead of being treated as unbreakable giants and scaled down.
    const expanded = [];
    col.units.forEach(section => {
      const list = section.querySelector('ul,ol');
      const sectionH = section.getBoundingClientRect().height;
      if (!list || sectionH <= 520) { expanded.push(section); return; }
      const lis = Array.from(list.children);
      const chunks = [];
      let curList = null, curH = 0;
      const newChunk = () => {
        const s = document.createElement('section');
        s.className = section.className;
        const head = section.querySelector('h2,h3');
        if (head) s.appendChild(head.cloneNode(true));
        curList = document.createElement(list.tagName);
        curList.className = list.className;
        s.appendChild(curList);
        chunks.push(s);
        return curList;
      };
      lis.forEach(li => {
        const h = li.getBoundingClientRect().height;
        if (!curList || curH + h > 420) { newChunk(); curH = 0; }
        curList.appendChild(li);
        curH += h;
      });
      if (chunks.length) {
        // Keep every chunk in flow so the geometry pass measures real rects;
        // the packer moves the overflow chunks to continuation sheets later.
        section.replaceWith(...chunks);
        expanded.push(...chunks);
      } else {
        expanded.push(section);
      }
    });
    col.units = expanded.filter(n => n.nodeType === 1);
  });
  cols.forEach(col => {
    if (col.key !== 'main' || kind !== 'toc') return;
    // Split tall TOC sections into chunk sections at item level so a whole
    // chapter never becomes an unbreakable giant: the TOC should simply flow,
    // page count is irrelevant, and nothing may cross the footer band.
    const expanded = [];
    col.units.forEach(section => {
      const itemsWrap = section.querySelector('.toc-items');
      const sectionH = section.getBoundingClientRect().height;
      if (!itemsWrap || sectionH <= 640) { expanded.push(section); return; }
      const kids = Array.from(itemsWrap.children);
      const chunks = [];
      let cur = null, curH = 0;
      const newChunk = () => {
        const s = document.createElement('section');
        s.className = section.className;
        const head = section.querySelector('h2,h3');
        if (head) s.appendChild(head.cloneNode(true));
        const w = document.createElement('div');
        w.className = itemsWrap.className;
        s.appendChild(w);
        chunks.push(s);
        return w;
      };
      kids.forEach(k => {
        const kh = k.getBoundingClientRect().height;
        if (!cur || curH + kh > 560) { cur = newChunk(); curH = 0; }
        cur.appendChild(k);
        curH += kh;
      });
      if (chunks.length > 1) {
        section.replaceWith(...chunks);
        expanded.push(...chunks);
      } else {
        expanded.push(section);
      }
    });
    col.units = expanded.filter(n => n.nodeType === 1);
  });
  cols.forEach(col => {
    if (col.key !== 'main' || kind === 'recipe') return;
    // Content-page tables flow at row boundaries: a tall top-level table is
    // rebuilt into row-chunk tables (each repeating the header row) so it
    // packs like ordinary units - starting right after preceding prose and
    // continuing under the next sheet's strip - instead of being moved
    // wholesale onto a fresh sheet as an unbreakable giant.
    const expanded = [];
    col.units.forEach(unit => {
      if (unit.tagName !== 'TABLE') { expanded.push(unit); return; }
      if (unit.getBoundingClientRect().height <= TABLE_CHUNK_MAX) {
        expanded.push(unit);
        return;
      }
      const headEl = unit.querySelector('thead');
      const rows = Array.from(unit.querySelectorAll('tbody > tr'));
      if (!rows.length) { expanded.push(unit); return; }
      const headHTML = headEl ? headEl.outerHTML : '';
      const chunks = [];
      let cur = null, curH = 0;
      const newChunk = () => {
        cur = document.createElement('table');
        cur.setAttribute('data-table-chunk', '1');
        cur.innerHTML = headHTML + '<tbody></tbody>';
        chunks.push(cur);
        curH = 0;
      };
      rows.forEach(tr => {
        const h = tr.getBoundingClientRect().height;
        if (!cur || curH + h > TABLE_CHUNK_MAX) newChunk();
        cur.querySelector('tbody').appendChild(tr);
        curH += h;
      });
      unit.replaceWith(...chunks);
      expanded.push(...chunks);
    });
    col.units = expanded.filter(n => n.nodeType === 1);
  });
  cols.forEach(col => {
    if (col.key !== 'main' || kind === 'recipe') return;
    const expanded = [];
    col.units.forEach(unit => {
      if (!/^(ul|ol)$/i.test(unit.tagName)) { expanded.push(unit); return; }
      if (unit.getBoundingClientRect().height <= 380) { expanded.push(unit); return; }
      const lis = Array.from(unit.children).filter(n => n.nodeType === 1);
      if (!lis.length) { expanded.push(unit); return; }
      const chunks = [];
      let cur = null, curH = 0;
      const newChunk = () => {
        cur = document.createElement(unit.tagName);
        cur.className = unit.className;
        chunks.push(cur);
        curH = 0;
      };
      lis.forEach(li => {
        const h = li.getBoundingClientRect().height;
        if (!cur || curH + h > 380) newChunk();
        cur.appendChild(li);
        curH += h;
      });
      if (chunks.length > 1) {
        unit.replaceWith(...chunks);
        expanded.push(...chunks);
      } else {
        expanded.push(unit);
      }
    });
    col.units = expanded.filter(n => n.nodeType === 1);
  });
  cols.forEach(col => {
    col.units = col.units.filter(u => !u.hasAttribute('data-page-footer')
                                     && !u.classList.contains('page-footer'));
  });
  if (!cols.some(c => c.units.length)) return {changed: false, reason: 'empty',
                                               kind: kind};

  // Resolve the flowing host element of a column inside a given sheet.
  function colHost(sheetEl, col) {
    if (kind === 'recipe') {
      const host = sheetEl.querySelector(col.sel);
      if (!host) return null;
      return col.wrapInHost ? (host.querySelector('.space-y-2') || host) : host;
    }
    const direct = sheetEl.querySelector('.content-text');
    if (direct) return direct;
    const candidates = Array.from(sheetEl.children).filter(c =>
      !(c.querySelector && c.querySelector('h1'))
      && !c.hasAttribute('data-page-footer')
      && !c.classList.contains('cont-strip'));
    return candidates.length
      ? candidates.reduce((a, b) => b.children.length > a.children.length ? b : a)
      : null;
  }

  // Measure geometry while every unit sits in its original position.
  cols.forEach(col => {
    const host = colHost(sheet, col);
    if (!host || !col.units.length) { col.chrome = 0; col.tops = []; col.bots = []; return; }
    const hostTop = host.getBoundingClientRect().top + window.scrollY;
    col.chrome = col.units[0].getBoundingClientRect().top + window.scrollY - hostTop;
    col.tops = col.units.map(u => u.getBoundingClientRect().top + window.scrollY);
    col.bots = col.units.map(u => u.getBoundingClientRect().bottom + window.scrollY);
  });

  const overflowed = cols.some(col => col.units.length &&
    (col.chrome + (col.bots[col.bots.length - 1] - col.tops[0]))
      > budget - headerH - contMT + 0.5);
  if (!overflowed) {
    // No-ingredients recipes always elect vertical, even when everything
    // fits: side-by-side would need the ingredients panel that is absent.
    if (forceVertical) return {changed: false, reason: 'fits', kind: kind,
                               layout: 'vertical', sheets: 1};
    return {changed: false, reason: 'fits', kind: kind,
            layout: kind === 'recipe' ? 'side-by-side' : undefined,
            sheets: 1};
  }

  // Eyebrow strip probe for continuation sheets.
  const probe = document.createElement('div');
  probe.style.cssText = 'margin-bottom:1rem;';
  const spanEl = document.createElement('span');
  spanEl.className = 'section-heading';
  spanEl.textContent = titleText || '\u00a0';
  probe.appendChild(spanEl);
  sheet.appendChild(probe);
  const stripH = probe.getBoundingClientRect().height +
                 (parseFloat(getComputedStyle(probe).marginBottom) || 0);
  probe.remove();

  const availFirst = Math.max(60, budget - headerH - contMT);
  const availNext = Math.max(60, budget - stripH - contMT);

  // Layout election (ADR 0009): recipe pages print SIDE-BY-SIDE only while
  // everything fits ONE sheet. Any overflow rebuilds the page as stacked
  // vertical bands - ingredients streamed through two height-balanced
  // columns, instructions likewise directly below - so ingredients and
  // instructions are never printed side by side once a recipe needs more
  // than one sheet. Wide blocks break out across both columns at full size.
  // Recipes without an Ingredients section (data-vertical-recipe) never
  // elect side-by-side: fitting ones returned a vertical election above,
  // overflowing ones rebuild here with no ingredients band at all.
  const verticalRecipe = (kind === 'recipe');
  const giants = [];
  const scaledNames = [];
  const slicedNotes = [];
  const joinScaled = [];   // ADR 0017: diagrams scaled to join their text
  const joinDeferred = []; // ADR 0017: joins considered but the sheet was full
  const backfillNotes = [];
  let nextDiagramId = 0;

  // Shared band planning (ADR 0002/0017): how many full-size bands a diagram
  // of height h needs when its first band may occupy joinWin of the most
  // recently packed sheet's leftover space. A band smaller than SLIVER_MIN
  // is lifted away so no near-blank sheet ever shows a hairline of diagram.
  function planDiagramBands(h, joinWin, sheetAvail) {
    joinWin = Math.min(h, Math.max(0, joinWin));
    if (joinWin < SLIVER_MIN) joinWin = 0;   // a sliver helps nobody
    let restTotal = h - joinWin;
    let parts = Math.max(1, Math.ceil(restTotal / sheetAvail));
    // Hairline last-band guard: shift the first boundary so the last band
    // carries at least SLIVER_MIN rows (band 0 gives up the rows; the seam
    // pass re-checks it).
    while (joinWin > 0 && sheetAvail >= SLIVER_MIN &&
           restTotal - (parts - 1) * sheetAvail < SLIVER_MIN) {
      const lift = Math.min(
        SLIVER_MIN - (restTotal - (parts - 1) * sheetAvail), joinWin);
      joinWin -= lift;
      restTotal += lift;
      parts = Math.max(1, Math.ceil(restTotal / sheetAvail));
    }
    return {joinWin: joinWin, restTotal: restTotal, parts: parts};
  }

  if (!verticalRecipe) {
  // Greedy packing per column -> runs of unit indices per sheet.
  cols.forEach(col => {
    col.runs = [];
    let i = 0, avail = availFirst;
    while (i < col.units.length) {
      let end = i - 1;
      for (let k = i; k < col.units.length; k++) {
        if (col.chrome + (col.bots[k] - col.tops[i]) <= avail) end = k; else break;
      }
      if (end < i) {
        // Single block does not fit on the current sheet.
        const label = (col.units[i].textContent || '').trim().slice(0, 40) || ('#' + (i + 1));
        const h = col.bots[i] - col.tops[i];
        const prefixH = col.runs.length ? stripH : headerH;
        const room = sheet.clientHeight - padTop - prefixH - contMT;
        const sliceable = !!(col.units[i].querySelector &&
                             col.units[i].querySelector('svg'));
        if (sliceable && h > availNext) {
          // Diagrams slice at FULL size across consecutive sheets: print
          // readability beats keeping one on a page. The footer renders
          // behind every band. The FIRST band joins the most recently packed
          // sheet (title, intro text) using that sheet's leftover space, so
          // a diagram never strands its title on an otherwise empty sheet.
          const prev = col.runs[col.runs.length - 1];
          let joinWin = 0;
          if (prev && prev.part === undefined) {
            const budget = col.runs.length === 1 ? availFirst : availNext;
            const consumed = col.chrome
              + (col.bots[prev.end] - col.tops[prev.start]);
            joinWin = Math.max(0, budget - consumed);
          }
          const plan = planDiagramBands(h, joinWin, availNext);
          const diagId = 'dg' + Math.random().toString(36).slice(2, 10)
                       + '-' + nextDiagramId++;
          let off = plan.joinWin;
          for (let p = 0; p < plan.parts; p++) {
            const winH = Math.max(1, Math.min(availNext, plan.restTotal - p * availNext));
            col.runs.push({start: i, end: i, scale: 1, part: p + 1,
                           parts: plan.parts, winH: winH, off: off, diag: diagId});
            off += winH;
          }
          if (plan.joinWin > 0) {
            prev.bands = prev.bands || [];
            prev.bands.push({unitIdx: i, winH: plan.joinWin, off: 0, diag: diagId});
          }
          const sheetsUsed = plan.parts + (plan.joinWin > 0 ? 1 : 0);
          slicedNotes.push('diagram "' + label + '" sliced across ' +
                           sheetsUsed + ' sheets at 100% size');
          col.units[i].setAttribute('data-giant', '1');
          i += 1;
          avail = availNext;
          continue;
        }
        // Non-sliceable block: its own sheet, allowed to overlap the footer
        // band (footer renders behind content); scaled only when it cannot
        // physically fit on the paper.
        let scale = 1;
        if (h > room) {
          scale = Math.max(MIN_SCALE, room / h);
          scaledNames.push(label);
        }
        giants.push('unbreakable block "' + label + '"' +
                    (scale < 1 ? ' scaled ' + Math.round(scale * 100) + '%'
                               : ' overlaps footer band'));
        col.runs.push({start: i, end: i, scale: scale});
        col.units[i].setAttribute('data-giant', '1');
        i += 1;
        avail = availNext;
        continue;
      }
      // Diagram-joins-text election (ADR 0017): the scan above broke at a
      // sliceable diagram that would start the next sheet as an ordinary
      // unit - stranding the text above it on a short sheet. Prefer keeping
      // the two together: mildly scale the diagram into the leftover space
      // (never below JOIN_FLOOR), else slice it with band 0 joining the text
      // at 100% size. Only a genuinely full sheet defers the join.
      const d = end + 1;
      const dUnit = col.units[d];
      const dSliceable = !!(dUnit && dUnit.querySelector &&
                             dUnit.querySelector('svg'));
      if (dSliceable) {
        const hD = col.bots[d] - col.tops[d];
        if (hD <= availNext) {
          const consumed = col.chrome + (col.bots[end] - col.tops[i]);
          const leftover = Math.max(0, avail - consumed);
          const joinScale = hD > 0 ? leftover / hD : 1;
          const label = (dUnit.textContent || '').trim().slice(0, 40)
                        || ('#' + (d + 1));
          if (joinScale >= JOIN_FLOOR) {
            joinScaled.push('diagram "' + label + '" scaled ' +
                            Math.round(joinScale * 100) +
                            '% to join the text above it');
            const scales = {};
            scales[d] = joinScale;
            col.runs.push({start: i, end: d, scale: 1, unitScales: scales});
            col.units[d].setAttribute('data-giant', '1');
            i = d + 1;
            avail = availNext;
            continue;
          }
          if (leftover >= SLIVER_MIN) {
            const plan = planDiagramBands(hD, leftover, availNext);
            if (plan.joinWin > 0) {
              col.runs.push({start: i, end: end, scale: 1});
              const prev = col.runs[col.runs.length - 1];
              const diagId = 'dg' + Math.random().toString(36).slice(2, 10)
                           + '-' + nextDiagramId++;
              let off = plan.joinWin;
              for (let p = 0; p < plan.parts; p++) {
                const winH = Math.max(1, Math.min(availNext,
                                plan.restTotal - p * availNext));
                col.runs.push({start: d, end: d, scale: 1, part: p + 1,
                               parts: plan.parts, winH: winH, off: off,
                               diag: diagId});
                off += winH;
              }
              prev.bands = prev.bands || [];
              prev.bands.push({unitIdx: d, winH: plan.joinWin, off: 0,
                               diag: diagId});
              slicedNotes.push('diagram "' + label + '" sliced with band 0 ' +
                               'joining its text across ' +
                               (plan.parts + 1) + ' sheets at 100% size');
              col.units[d].setAttribute('data-giant', '1');
              i = d + 1;
              avail = availNext;
              continue;
            }
          } else {
            joinDeferred.push('diagram "' + label + '" starts the next ' +
                              'sheet: only ' + Math.round(leftover) +
                              'px slack under its text');
          }
        }
      }
      col.runs.push({start: i, end: end, scale: 1});
      i = end + 1;
      avail = availNext;
    }
  });
  } // end content/TOC per-column greedy packing

  let allSheets, adjusted = 0, extras = [], sheetIsBare = null;
  // Stream reference for the vertical-recipe path, stashed by that branch so
  // the outer-scope integrity audit can inspect planned instruction units.
  let verticalStreams = [];
  // Every flowing unit of a rebuilt sheet, in document order. Declared out here
  // because both the vertical branch (straggler shift, upward pull) and the
  // outer clip audit need it.
  function flowingNodesV(sh) {
    return Array.from(sh.querySelectorAll('[data-vunit]')).filter(n =>
      !n.hasAttribute('data-giant')
      && !(n.querySelector && n.querySelector('[data-giant]'))
      && !n.hasAttribute('data-page-footer'));
  }

  // Eyebrow strip builder shared by both layout paths.
  function makeStrip(label) {
    const d = document.createElement('div');
    d.className = 'cont-strip';
    d.style.cssText = 'margin-bottom:1rem;';
    const s = document.createElement('span');
    s.className = 'section-heading';
    s.textContent = label || titleText;
    d.appendChild(s);
    return d;
  }
  // On TOC continuations the strip names the chapter that continues here,
  // which orients far better than repeating the page title.
  function stripLabelFor(sheetIndex) {
    if (verticalRecipe || kind !== 'toc') return titleText;
    const col = cols[0];
    if (!col || !col.runs || !col.runs[sheetIndex]) return titleText;
    const firstUnit = col.units[col.runs[sheetIndex].start];
    const head = firstUnit && firstUnit.querySelector
      ? firstUnit.querySelector('h2,h3') : null;
    return (head && head.textContent.trim()) || titleText;
  }

  // Build one band window as a true SVG slice: a copy of the diagram svg
  // whose viewBox shows exactly this band's row range at the same scale.
  // The svg root clips its own viewport (paths AND foreignObject labels),
  // which survives printing; relying on the box's overflow:hidden does not -
  // at print Chromium lets foreignObject text escape ancestor clips, which
  // duplicated label text across sheet seams.
  // `m` carries SVG metrics precomputed while the source was still attached:
  // the vertical layout detaches originals before placement, and detached
  // nodes measure as zero rects, which once produced garbage viewBoxes
  // (blank bands that still passed the self-consistency audit).
  function buildBandBox(unit, diagId, off, winH, m) {
    const box = document.createElement('div');
    box.setAttribute('data-giant', '1');
    box.setAttribute('data-band-window', '1');
    box.setAttribute('data-band-diagram', String(diagId));
    box.setAttribute('data-band-off', String(off));
    box.style.cssText = 'height:' + winH + 'px;overflow:hidden;';
    const srcSvg = unit.querySelector('svg');
    if (!srcSvg) {
      box.appendChild(unit.cloneNode(true));
      return box;
    }
    let scale, vbW;
    if (m && m.__bandScale !== undefined) {
      scale = m.__bandScale;
      vbW = m.__bandVbW;
      box.setAttribute('data-band-total', String(m.__bandTotal));
    } else {
      if (unit.__bandScale === undefined) {
        const srcRect = srcSvg.getBoundingClientRect();
        const vb0 = srcSvg.viewBox && srcSvg.viewBox.baseVal;
        const vbW0 = vb0 && vb0.width ? vb0.width : srcRect.width;
        unit.__bandScale = vbW0 / (srcRect.width || 1);
        unit.__bandTotal = srcRect.height;
        unit.__bandVbW = vbW0;
      }
      scale = unit.__bandScale;
      vbW = unit.__bandVbW;
      box.setAttribute('data-band-total', String(unit.__bandTotal));
    }
    box.setAttribute('data-band-scale', String(scale));
    const bandSvg = srcSvg.cloneNode(true);
    bandSvg.setAttribute('viewBox', '0 ' + (off * scale).toFixed(2) + ' ' +
                         vbW + ' ' + (winH * scale).toFixed(2));
    bandSvg.style.height = winH + 'px';
    bandSvg.style.margin = '0';
    box.appendChild(bandSvg);
    if (off === 0 && !m) unit.remove();  // band 0 owns these rows
    return box;
  }

  if (!verticalRecipe) {
  const sheetCount = Math.max.apply(null,
    cols.map(c => Math.max(1, c.runs ? c.runs.length : 1)));
  if (sheetCount <= 1) return {changed: false, reason: 'fits-after-pack',
                               kind: kind, layout: 'side-by-side', sheets: 1};
  extras = [];
  for (let s = 1; s < sheetCount; s++) {
    const clone = sheet.cloneNode(true);
    clone.querySelectorAll('[id]').forEach(n => n.removeAttribute('id'));
    const cloneHeader = Array.from(clone.children).find(
      c => c.querySelector && c.querySelector('h1'));
    if (cloneHeader) cloneHeader.remove();
    // Strips are attached later (once units are placed and stragglers have
    // settled), so a sheet whose whole content turned out to be diagram
    // bands or giant blocks can be recognised and left bare.
    cols.forEach(col => {
      const host = colHost(clone, col);
      if (!host) return;
      Array.from(host.children).forEach(n => n.remove());
    });
    extras.push(clone);
  }
  let anchor = sheet;
  extras.forEach(ex => { anchor.parentNode.insertBefore(ex, anchor.nextSibling); anchor = ex; });
  allSheets = [sheet].concat(extras);

  // --- Move units into their packed positions ---
  cols.forEach(col => {
    (col.runs || []).forEach((run, rIdx) => {
      const host = colHost(allSheets[Math.min(rIdx, allSheets.length - 1)], col);
      if (!host) return;
      if (run.part !== undefined && run.parts) {
        // One band of a sliced diagram: a fixed-height clip window whose
        // inner copy of the diagram is shifted to show this band at 100%.
        // (Packing stores per-band winH/off; band 0 may be shorter than the
        // rest because it shares its sheet with the title/intro content.)
        const unit = col.units[run.start];
        const winH = run.winH || availNext;
        unit.style.margin = '0';
        host.appendChild(buildBandBox(unit, run.diag, run.off || 0, winH));
        return;
      }
      for (let u = run.start; u <= run.end; u++) {
        const unit = col.units[u];
        host.appendChild(unit);
        // Per-unit scale (ADR 0017 join elections) falls back to the run's
        // whole-run scale, which only ever applies to single-unit runs.
        const uScale = (run.unitScales && run.unitScales[u] !== undefined)
          ? run.unitScales[u]
          : (run.start === run.end ? run.scale : 1);
        if (uScale < 1) {
          const uh = unit.getBoundingClientRect().height || 1;
          const wrap = document.createElement('div');
          wrap.style.cssText = 'transform:scale(' + uScale + ');transform-origin:top left;'
            + 'width:' + (100 / uScale) + '%;height:' + (uh * uScale) + 'px;';
          host.insertBefore(wrap, unit);
          wrap.appendChild(unit);
        }
      }
      // Band(s) of a sliced diagram that share THIS sheet: clipped windows
      // under the sheet's own units (title/intro text).
      (run.bands || []).forEach(b => {
        const unit = col.units[b.unitIdx];
        if (!unit) return;
        unit.style.margin = '0';
        host.appendChild(buildBandBox(unit, b.diag, 0, b.winH));
      });
    });
  });

  // --- Verification pass: shift stragglers past the content limit ---
  function flowingNodes(sh) {
    const notGiant = n => !n.hasAttribute('data-giant');
    const c = sh.querySelector('.content-text') || sh.querySelector('.flex-grow.overflow-hidden');
    return c ? Array.from(c.children).filter(n => n.nodeType === 1
              && notGiant(n)
              && !n.hasAttribute('data-page-footer')
              && !n.classList.contains('page-footer')) : [];
  }

  let adjusted = 0;
  for (let iter = 0; iter < 4; iter++) {
    let movedAny = false;
    for (let s = 0; s < allSheets.length - 1; s++) {
      const limit = allSheets[s].getBoundingClientRect().bottom - padBot - EPS;
      const nodes = flowingNodes(allSheets[s]);
      if (!nodes.length) continue;
      const lastNode = nodes[nodes.length - 1];
      if (lastNode.getBoundingClientRect().bottom > limit) {
        const nh = colHost(allSheets[s + 1], cols[0]);
        if (nh) { nh.insertBefore(lastNode, nh.firstChild); adjusted++; movedAny = true; }
      }
    }
    if (!movedAny) break;
  }
  sheetIsBare = function(sh) {
    let sawUnit = false;
    for (const col of cols) {
      const host = colHost(sh, col);
      if (!host) continue;
      for (const child of Array.from(host.children)) {
        sawUnit = true;
        const giant = child.hasAttribute('data-giant')
          || !!(child.querySelector && child.querySelector('[data-giant]'));
        if (!giant) return false;
      }
    }
    return sawUnit;
  };
  } else {
    // ==== VERTICAL RECIPE BANDS (ADR 0009) ====
    // Streams at the finest SAFE granularity. The Ingredients section - the
    // one the band is named after - decomposes to list-item level (its
    // heading becomes an inline marker). So do its CONTINUATION CHUNKS: the
    // sidebar chunking pre-pass above splits oversized sections into
    // <=420px chunk sections, each with a CLONED heading, so chunk sections
    // whose heading matches the band label are still Ingredients, not new
    // sections. Genuinely different sections (Hardware, Sauces) stay whole:
    // their few items are meaningless detached from their short heading, and
    // item-level streaming let the balanced columns / verification passes
    // tear them apart and print the pieces at mismatched heights (Bibimbap's
    // hardware split). Instructions stay whole steps. Giants (svg diagrams)
    // stay whole and later break out full-width across both columns.
    const streams = [];
    const ingUnits = [];
    // The ingredients stream exists only when a sidebar was rendered; recipes
    // without an Ingredients section have no aside and no ingredients band.
    if (aside) {
      const sidebarSections = Array.from(aside.children)
        .filter(n => n.nodeType === 1);
      const firstHead = sidebarSections.length
        ? sidebarSections[0].querySelector('h2,h3') : null;
      const ingLabel = (firstHead && firstHead.textContent.trim())
        || 'Ingredients';
      sidebarSections.forEach((sec, secIdx) => {
        const headEl = sec.querySelector('h2,h3');
        const isPrimary = secIdx === 0
          || (!!headEl && headEl.textContent.trim() === ingLabel);
        if (!isPrimary) {
          ingUnits.push({
            el: sec, h: sec.getBoundingClientRect().height, primary: false});
          return;
        }
        if (headEl) ingUnits.push({
          heading: true, label: headEl.textContent.trim(),
          h: headEl.getBoundingClientRect().height || 16, primary: true});
        const list = sec.querySelector('ul,ol');
        if (!list) {
          ingUnits.push({el: sec, h: sec.getBoundingClientRect().height,
                         primary: true});
          return;
        }
        Array.from(list.children).forEach(li => {
          if (li.nodeType !== 1) return;
          ingUnits.push({el: li, h: li.getBoundingClientRect().height,
                         listTag: list.tagName, listClass: list.className,
                         primary: true});
        });
      });
      streams.push({key: 'ingredients', label: ingLabel, units: ingUnits});
    }
    // Instruction streams (ADR 0012 / version-block rendering): NON-versioned
    // recipes keep one stream over the legacy single Instructions block.
    // Versioned recipes get ONE stream per version <section>, so every version
    // prints in its own vertical band with its own two balanced columns.
    const insStreams = [];
    const instructionBlocks = Array.from(article.querySelectorAll('[data-instruction-block]'));
    // ADR 0012 invariant: every instruction element belongs to EXACTLY ONE
    // stream. The preamble owns 'ins:intro' (its own full-width band above the
    // first version/heading block) and is registered here and nowhere else.
    // Registering it twice does not duplicate the text - materialisation MOVES
    // nodes (appendChild, not clone) - it relocates the preamble onto a later
    // sheet, printing it after the very steps that precede it in the source.
    // Outermost markers only: a marker nested inside another (legacy shape)
    // must not open a second intro stream.
    const introEls = Array.from(article.querySelectorAll('[data-instruction-intro]'))
      .filter(el => !el.parentElement.closest('[data-instruction-intro]'));

    introEls.forEach(introEl => {
      const wrap = introEl.querySelector('.space-y-2') || introEl;
      const units = [];
      Array.from(wrap.children).forEach(st => {
        if (st.nodeType !== 1) return;
        units.push({el: st, h: st.getBoundingClientRect().height});
      });
      units.forEach((u, i) => u.el.setAttribute('data-seq', String(i)));
      if (units.length) {
        insStreams.push({key: 'ins:intro', label: '', units: units});
      }
    });
    if (instructionBlocks.length) {
      instructionBlocks.forEach((blk, bi) => {
        // A block carrying the intro marker is the headless preamble (legacy
        // variant shape); it belongs to the 'ins:intro' stream above, never
        // to an ins:<bi> band.
        if (blk.hasAttribute('data-instruction-intro')) return;
        const units = [];
        const headEl = blk.querySelector('.instruction-block-head h3');
        const label = (headEl && headEl.textContent.trim()) || '';
        const wrap = blk.querySelector('.space-y-2') || blk;
        Array.from(wrap.children).forEach(st => {
          if (st.nodeType !== 1 || st.tagName === 'H2' || st.tagName === 'H3') return;
          if (st.hasAttribute('data-instruction-intro')) return;
          units.push({el: st, h: st.getBoundingClientRect().height});
        });
        if (!units.length) return;   // an empty version block prints nothing
        units.forEach((u, i) => u.el.setAttribute('data-seq', String(i)));
        // Variant blocks carrying the classic Ingredients -> Instructions
        // sub-label pair (Pizza Al Taglio's ##### headings) print as two
        // FIXED half-columns: every unit before the "Instructions" label
        // goes left, the label and its steps go right. Height balancing
        // would otherwise mix ingredients and instruction steps across both
        // columns and print ingredient steps above instruction steps.
        let fixedSplit = null;
        let sawIngredients = false;
        units.forEach((u, i) => {
          const h4 = u.el.querySelector ? u.el.querySelector('h4') : null;
          if (!h4) return;
          const t = (h4.textContent || '').trim().toLowerCase();
          if (t === 'ingredients') { sawIngredients = true; return; }
          if (t === 'instructions' && sawIngredients && fixedSplit === null) {
            fixedSplit = i;
          }
        });
        insStreams.push({key: 'ins:' + bi, label: label, units: units,
                         fixedSplit: fixedSplit});
      });
    } else {
      const insUnits = [];
      const artHead = article.querySelector('h2,h3');
      let stepCandidates = Array.from(article.querySelectorAll('.space-y-2 > div, .space-y-2 > p'));
      if (!stepCandidates.length) {
        stepCandidates = Array.from(article.children).filter(c =>
          c.nodeType === 1 && c.tagName !== 'H2' && c.tagName !== 'H3'
            && !c.hasAttribute('data-instruction-intro')
        );
      }
      stepCandidates.forEach(st => {
        insUnits.push({el: st, h: st.getBoundingClientRect().height});
      });
      insUnits.forEach((u, i) => { if (u.el) u.el.setAttribute('data-seq', String(i)); });
      insStreams.push({key: 'instructions', label: 'Instructions', units: insUnits});
    }
    insStreams.forEach(st => streams.push(st));
    verticalStreams = streams;   // expose to the outer integrity audit

    const isGiantU = u => !!(!u.heading && u.el &&
      (u.el.hasAttribute('data-giant') ||
       (u.el.querySelector && u.el.querySelector('svg'))));

    // Rebuild the sheet as stacked bands FIRST (ADR 0011): probing needs the
    // destination geometry, so the two-band scaffold exists before anything
    // is measured. Tinted panel (classes carried over from the old sidebar)
    // for ingredients, plain white for instructions.
    sheet.setAttribute('data-layout', 'vertical');
    container.classList.remove('grid', 'grid-cols-12', 'gap-3');
    const asideClasses = aside
      ? (aside.className || '').split(/\s+/)
          .filter(c => c && !/^col-span-/.test(c)).join(' ')
      : '';
    if (aside) aside.remove();
    article.remove();
    function makeBand(key, cls) {
      const band = document.createElement('div');
      band.setAttribute('data-band', key);
      if (cls) band.className = cls;
      let bandStyle = 'margin-bottom:0.75rem;';
      if (key.startsWith('ins:')) {
        bandStyle += 'background:rgba(71,102,74,0.04);border-radius:0.375rem;padding:0.5rem 0.75rem;-webkit-print-color-adjust:exact;print-color-adjust:exact;';
      }
      band.style.cssText = bandStyle;
      const headRow = document.createElement('div');
      headRow.setAttribute('data-band-head', '');
      if (key.startsWith('ins:')) headRow.style.cssText = 'margin-bottom:0.5rem;';
      const colsWrap = document.createElement('div');
      if (key === 'ins:intro') {
        colsWrap.style.cssText = 'display:block;align-items:start;';
      } else {
        colsWrap.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;'
          + 'column-gap:0.75rem;align-items:start;';
      }
      const cL = document.createElement('div');
      cL.setAttribute('data-vcol', 'L');
      const cR = document.createElement('div');
      cR.setAttribute('data-vcol', 'R');
      colsWrap.appendChild(cL);
      if (key !== 'ins:intro') colsWrap.appendChild(cR);
      band.appendChild(headRow);
      band.appendChild(colsWrap);
      container.appendChild(band);
      return band;
    }
    streams.forEach(st => makeBand(st.key, st.key === 'ingredients' ? asideClasses : ''));

    // Measure where you place (ADR 0011): unit heights were historically
    // captured in the side-by-side geometry, but the vertical rebuild pours
    // the same elements into half-width columns where wrapping differs.
    // Attach every unit in its real band column, measure, then detach -
    // planning sees placement truth instead of stale sidebar numbers.
    function probeAttach(st) {
      const band = bandOf(sheet, st.key);
      const col = band.querySelector('[data-vcol="L"]');
      buildColumn(col, st.units, null);
    }
    function probeMeasureAndDetach(st) {
      const band = bandOf(sheet, st.key);
      const col = band.querySelector('[data-vcol="L"]');
      let ptr = 0;
      // Margin box: list gaps (space-y-*), step margins and heading margins
      // are part of what a column must fit - border-box alone undercounts.
      const marginBox = el => {
        const cs = getComputedStyle(el);
        return el.getBoundingClientRect().height
          + (parseFloat(cs.marginTop) || 0)
          + (parseFloat(cs.marginBottom) || 0);
      };
      const takeUnit = pred => {
        while (ptr < st.units.length && !pred(st.units[ptr])) ptr++;
        return ptr < st.units.length ? st.units[ptr++] : null;
      };
      Array.from(col.children).forEach(child => {
        if (child.tagName === 'H2') {
          const u = takeUnit(u2 => !!u2.heading);
          if (u) u.h = marginBox(child) || u.h;
          return;
        }
        if (child.tagName === 'UL' || child.tagName === 'OL') {
          Array.from(child.children).forEach(li => {
            const u = takeUnit(u2 => !u2.heading);
            if (u) u.h = marginBox(li) || u.h;
          });
          return;
        }
        const u = takeUnit(u2 => !u2.heading);
        if (u) u.h = marginBox(child) || u.h;
      });
      while (col.firstChild) col.removeChild(col.firstChild);
    }
    streams.forEach(probeAttach);
    // Precompute SVG band metrics NOW: the transform below detaches source
    // nodes from the document, and detached rects read zero.
    streams.forEach(st => st.units.forEach(u => {
      if (!isGiantU(u)) return;
      const svg = u.el.querySelector('svg');
      if (!svg) return;
      const srcRect = svg.getBoundingClientRect();
      const vb0 = svg.viewBox && svg.viewBox.baseVal;
      u.__bandVbW = vb0 && vb0.width ? vb0.width : srcRect.width;
      u.__bandScale = u.__bandVbW / (srcRect.width || 1);
      u.__bandTotal = srcRect.height;
    }));
    streams.forEach(probeMeasureAndDetach);

    // Per-band chrome (ADR 0011): a band joining a sheet costs its own box
    // (vertical padding + bottom margin) plus the filled head row - space the
    // planner must reserve before inviting a further stream onto the same
    // sheet. Leaving the padding out let the planner believe a sheet had room
    // for roughly one unit more than it had; that slack landed on the last
    // band's tail and pushed it past the content limit (Risotto's
    // impressive-date step 2 was clipped off sheet 1).
    function bandChrome(key) {
      const band = bandOf(sheet, key);
      if (!band) return 0;
      const bcs = getComputedStyle(band);
      const box = (parseFloat(bcs.paddingTop) || 0)
                + (parseFloat(bcs.paddingBottom) || 0)
                + (parseFloat(bcs.marginBottom) || 0);
      // The preamble band prints headless: no version label sits above it.
      const headRow = band.querySelector('[data-band-head]');
      if (key === 'ins:intro' || !headRow) return box;
      const probeH = document.createElement('h2');
      probeH.className = 'section-heading';
      probeH.textContent = 'X';
      headRow.appendChild(probeH);
      const headH = headRow.getBoundingClientRect().height;
      headRow.removeChild(probeH);
      return headH + box;
    }
    const chromeByKey = {};
    streams.forEach(st => { chromeByKey[st.key] = bandChrome(st.key); });

    // Fixed half-column split for variant blocks with Ingredients /
    // Instructions sub-labels (stream.fixedSplit): every unit before the
    // boundary goes left, the rest right. The boundary index is relative to
    // the stream; openPair.startUi translates it into this pair's item
    // range. Pairs that begin at or past the boundary (pure step
    // continuations) fall back to balanced packing.
    function pairSplit(st, openPair) {
      const forced = (st.fixedSplit != null)
        ? st.fixedSplit - openPair.startUi : -1;
      if (forced < 1) return balanceSplit(openPair.items);
      const splitAt = Math.min(forced, openPair.items.length);
      let colL = 0, colR = 0;
      openPair.items.forEach((it, idx) => {
        if (idx < splitAt) colL += it.h; else colR += it.h;
      });
      return {splitAt: splitAt, colMax: Math.max(colL, colR)};
    }
    // Prefix/suffix partition minimising the taller column; a split whose
    // left column would END on a heading marker takes a soft penalty so
    // headings lean forward into the following column instead of stranding.
    // Height ties resolve toward the LARGER split point: items prefer the
    // left column, so an optimal tie fills left first.
    function balanceSplit(items) {
      const n = items.length;
      const totals = new Array(n + 1).fill(0);
      for (let k = 0; k < n; k++) totals[k + 1] = totals[k] + items[k].h;
      const total = totals[n];
      const scores = new Array(n + 1);
      let minScore = Infinity;
      for (let k = 0; k <= n; k++) {
        const colMax = Math.max(totals[k], total - totals[k]);
        const strandPenalty = (k > 0 && items[k - 1].heading) ? 40 : 0;
        scores[k] = colMax + strandPenalty;
        if (scores[k] < minScore) minScore = scores[k];
      }
      let best = n;
      for (let k = n; k >= 0; k--) {
        if (scores[k] <= minScore + 0.25) { best = k; break; }
      }
      return {splitAt: best,
              colMax: Math.max(totals[best], total - totals[best])};
    }
    // --- Planning: sequential streams, one balanced column-pair per sheet ---
    const plans = [];
    let si = 0, ui = 0;
    while (si < streams.length) {
      const avail = plans.length ? availNext : availFirst;
      const rows = [];
      let used = 0, openPair = null, pushed = false;
      let bandedKey = null;
      let guard = 0;
      while (si < streams.length && guard++ < 10000) {
        const st = streams[si];
        if (ui >= st.units.length) {
          // Stream exhausted: flush its open column-pair before moving on -
          // otherwise a mid-sheet stream transition silently drops units.
          if (openPair) {
            rows.push(openPair);
            used += openPair.colMax;
            openPair = null;
          }
          si++;
          ui = 0;
          continue;
        }
        if (st.key === 'ins:intro') {
          // A band landing on this sheet pays its chrome first, exactly like
          // the branching path below: the preamble band carries a box of its
          // own (padding + margin) even though it prints without a heading.
          if (bandedKey !== st.key) {
            used += chromeByKey[st.key] || 0;
            bandedKey = st.key;
          }
          const room = avail - used;
          let curH = 0;
          const fitUnits = [];
          for (const u of st.units) {
            if (curH + u.h > room) break;
            fitUnits.push(u);
            curH += u.h;
          }
          if (fitUnits.length) {
            rows.push({type: 'fullWidth', stream: st.key, units: fitUnits});
            used += curH;
          }
          ui += fitUnits.length;
          if (ui >= st.units.length) {
            if (openPair) { rows.push(openPair); used += openPair.colMax; openPair = null; }
            si++;
            ui = 0;
          } else {
            break;  // sheet full; overflow goes to next sheet
          }
          continue;
        }
        const u = st.units[ui];
        // Remaining room, re-read after every reservation below: a band's
        // chrome is charged when its pair starts, and reading a stale room let
        // the sheet's last pair start one unit too deep (the straggler pass
        // then had to undo it).
        let room = avail - used;
        if (isGiantU(u)) {
          if (openPair) { rows.push(openPair); used += openPair.colMax; openPair = null; }
          const label40 = (u.el.textContent || '').trim().slice(0, 40) || '#';
          if (u.h <= room) {
            rows.push({type: 'full', stream: st.key, u: u, scale: 1});
            used += u.h;
            ui++;
            continue;
          }
          if (used > 0) break;  // give the giant a fresh sheet
          if (u.h > availNext) {
            // Slice at 100% size across consecutive sheets; the first window
            // joins THIS otherwise-empty sheet (the footer renders behind
            // every band). Hairline last-band guard as in the generic path.
            let firstWin = Math.min(u.h, Math.max(60, avail));
            let restTotal = u.h - firstWin;
            let parts = Math.ceil(restTotal / availNext) || 1;
            while (firstWin > 0 && parts > 1 && availNext >= SLIVER_MIN &&
                   restTotal - (parts - 1) * availNext < SLIVER_MIN) {
              firstWin -= Math.min(SLIVER_MIN - (restTotal - (parts - 1) * availNext),
                                   firstWin);
              restTotal = u.h - firstWin;
              parts = Math.ceil(restTotal / availNext);
            }
            const diagId = 'dg' + Math.random().toString(36).slice(2, 10)
                         + '-' + (nextDiagramId++);
            rows.push({type: 'band', stream: st.key, u: u,
                       off: 0, winH: firstWin, diag: diagId});
            plans.push({rows: rows});
            pushed = true;
            rows.length = 0;
            let off = firstWin;
            while (off < u.h - 0.5) {
              const winH = Math.max(1, Math.min(availNext, u.h - off));
              plans.push({rows: [{type: 'band', stream: st.key, u: u,
                                  off: off, winH: winH, diag: diagId}]});
              off += winH;
            }
            slicedNotes.push('diagram "' + label40 + '" sliced across ' +
                             plans.filter(p =>
                               p.rows.some(r => r.diag === diagId)).length +
                             ' sheets at 100% size');
            u.el.setAttribute('data-giant', '1');
            ui++;
            break;  // remaining streams continue after the diagram's last band
          }
          // Non-sliceable giant alone on this sheet; it may overlap the
          // footer band (footer renders behind content) and is scaled only
          // when it cannot physically fit on the paper.
          let scale = 1;
          const roomPaper = sheet.clientHeight - padTop - contMT;
          if (u.h > roomPaper) {
            scale = Math.max(MIN_SCALE, roomPaper / u.h);
            scaledNames.push(label40);
          }
          giants.push('unbreakable block "' + label40 + '"' +
                      (scale < 1 ? ' scaled ' + Math.round(scale * 100) + '%'
                                 : ' overlaps footer band'));
          rows.push({type: 'full', stream: st.key, u: u, scale: scale});
          u.el.setAttribute('data-giant', '1');
          used += u.h * scale;
          ui++;
          continue;
        }
        // Normal unit: tentatively extend this stream's pair row, keeping the
        // two columns height-balanced. Every band starting on this sheet -
        // including the first - pays its chrome up front (ADR 0011).
        if (!openPair && bandedKey !== st.key) {
          used += chromeByKey[st.key] || 0;
          bandedKey = st.key;
        }
        if (!openPair) {
          // Band atomicity for fixed-split bands (#### subheaders that carry
          // both ##### Ingredients and ##### Instructions): the whole band must
          // stay on one sheet, so check the entire remaining stream before
          // starting it here. Splitting a fixed-split band across sheets puts
          // the continuation's ingredients AND instructions into the left column
          // of the next sheet (the shift pass targets [data-vcol="L"]), which
          // breaks both the same-page rule and the right-column rule for
          // instructions. Pizza Al Taglio: Rosso: Pizza Rossa was the failing
          // case - its first 4 ingredients landed on sheet 2, the 5th plus all
          // instructions on sheet 3 in the left column.
          if (st.fixedSplit != null) {
            const remaining = st.units.slice(ui);
            const splitAt = Math.min(st.fixedSplit - ui, remaining.length);
            let colL = 0, colR = 0;
            for (let k = 0; k < remaining.length; k++) {
              if (k < splitAt) colL += remaining[k].h; else colR += remaining[k].h;
            }
            const bandColMax = Math.max(colL, colR);
            // Only enforce atomicity when there is a meaningful choice: if the
            // band is taller than a fresh sheet can hold it would never fit
            // anywhere and the check would trap the planner in a skip loop.
            // room here is (avail - used) with the band's chrome already charged
            // (charged at line ~1117 above) so the comparison is honest.
            if (bandColMax <= availFirst + 0.5 && bandColMax > (avail - used) + 0.5) {
              break;   // entire band → next sheet
            }
          }
          openPair = {type: 'pair', stream: st.key, label: st.label,
                      items: [], colMax: 0, startUi: ui};
        }
        room = avail - used;   // the band's chrome is now reserved
        openPair.items.push(u);
        const bal = pairSplit(st, openPair);
        openPair.splitAt = bal.splitAt;
        openPair.colMax = bal.colMax;
        if (openPair.colMax <= room + 0.5) { ui++; continue; }
        openPair.items.pop();
        const bal2 = pairSplit(st, openPair);
        openPair.splitAt = bal2.splitAt;
        openPair.colMax = bal2.colMax;
        // Only flush a pair that still carries items - an emptied pair would
        // print a bare band head and fake a stream's presence on this sheet.
        if (openPair.items.length) {
          rows.push(openPair);
          used += openPair.colMax;
        }
        openPair = null;
        break;  // sheet full for now
      }
      if (openPair && openPair.items.length) rows.push(openPair);
      if (rows.length) plans.push({rows: rows});
      else if (!pushed && !plans.length) plans.push({rows: []});
    }
    // --- Materialise: structural clones, then place planned rows ---
    extras = [];
    for (let s = 1; s < plans.length; s++) {
      const clone = sheet.cloneNode(true);
      clone.querySelectorAll('[id]').forEach(n => n.removeAttribute('id'));
      const cloneHeader = Array.from(clone.children).find(
        c => c.querySelector && c.querySelector('h1'));
      if (cloneHeader) cloneHeader.remove();
      extras.push(clone);
    }
    let anchorV = sheet;
    extras.forEach(ex => {
      anchorV.parentNode.insertBefore(ex, anchorV.nextSibling);
      anchorV = ex;
    });
    allSheets = [sheet].concat(extras);

    function bandOf(sh, key) {
      return sh.querySelector('[data-band="' + key + '"]');
    }
    function fillHead(band, label) {
      const headRow = band.querySelector('[data-band-head]');
      if (!headRow || headRow.childElementCount) return;
      if (!label) return;   // a headless band (e.g. intro block) prints no heading
      const h = document.createElement('h2');
      h.className = 'section-heading';
      h.textContent = label;
      headRow.appendChild(h);
    }
    function buildColumn(colEl, items, suppressLabel) {
      let curList = null;
      items.forEach(u => {
        if (u.heading) {
          // The band head already prints the stream label; an inline marker
          // repeating it verbatim is noise.
          if (suppressLabel && u.label === suppressLabel) return;
          curList = null;
          const h = document.createElement('h2');
          h.className = 'section-heading';
          h.style.cssText = 'margin-top:0.5rem;display:inline-block;';
          h.textContent = u.label;
          h.setAttribute('data-vunit', '1');
          colEl.appendChild(h);
          return;
        }
        if (u.listTag) {
          if (!curList || curList.tagName !== u.listTag ||
              curList.__srcClass !== (u.listClass || '')) {
            curList = document.createElement(u.listTag);
            curList.className = u.listClass || '';
            curList.__srcClass = u.listClass || '';
            colEl.appendChild(curList);
          }
          u.el.setAttribute('data-vunit', '1');
          curList.appendChild(u.el);
          return;
        }
        curList = null;
        u.el.setAttribute('data-vunit', '1');
        colEl.appendChild(u.el);
      });
    }
    const streamByKey = {};
    streams.forEach(st => { streamByKey[st.key] = st; });
    plans.forEach((plan, s) => {
      const sh = allSheets[Math.min(s, allSheets.length - 1)];
      plan.rows.forEach(row => {
        const band = bandOf(sh, row.stream);
        if (!band) return;
        const colsWrap = band.querySelector('[data-vcol="L"]').parentElement;
        // Band head: the stream label orients the reader, but on a
        // continuation sheet carrying only secondary sidebar sections (the
        // atomic Hardware/Sauces units) it would mislabel the content -
        // those sections carry their own h2 and print headless instead.
        const rowUnits = row.type === 'pair' ? row.items
                       : (row.type === 'fullWidth' ? row.units
                       : (row.u ? [row.u] : []));
        const streamLabel = row.label || streamByKey[row.stream].label;
        const headless = row.stream === 'ingredients'
                         && !rowUnits.some(u => u.primary);
        fillHead(band, headless ? '' : streamLabel);
        if (row.type === 'fullWidth') {
          const col = band.querySelector('[data-vcol="L"]');
          row.units.forEach(u => {
            u.el.setAttribute('data-vunit', '1');
            col.appendChild(u.el);
          });
          return;
        }
        if (row.type === 'pair') {
          buildColumn(band.querySelector('[data-vcol="L"]'),
                      row.items.slice(0, row.splitAt), row.label);
          buildColumn(band.querySelector('[data-vcol="R"]'),
                      row.items.slice(row.splitAt), row.label);
          return;
        }
        if (row.type === 'full') {
          row.u.el.setAttribute('data-vunit', '1');
          row.u.el.setAttribute('data-giant', '1');
          row.u.el.style.gridColumn = '1 / -1';
          if (row.scale >= 1) { colsWrap.appendChild(row.u.el); return; }
          const wrap = document.createElement('div');
          wrap.style.cssText = 'transform:scale(' + row.scale + ');'
            + 'transform-origin:top left;width:' + (100 / row.scale) + '%;'
            + 'height:' + (row.u.h * row.scale).toFixed(1) + 'px;'
            + 'grid-column:1 / -1;';
          colsWrap.appendChild(wrap);
          wrap.appendChild(row.u.el);
          return;
        }
        // type === 'band': one clipped window of a sliced diagram
        const box = buildBandBox(row.u.el, row.diag, row.off, row.winH, row.u);
        box.style.gridColumn = '1 / -1';
        colsWrap.appendChild(box);
      });
    });

    // --- Verification pass (vertical shape): shift stragglers ---
    // Every column's tail is checked, not just the sheet's last node: inside a
    // two-column band the DOM order is every left-column unit followed by
    // every right-column unit, so the sheet's last node can sit well inside
    // the limit while the LEFT column's tail is already past it (Risotto: the
    // impressive-date step 2 was placed there and quietly clipped away).
    // The correction moves a whole source-order SUFFIX - from the first
    // overflowing unit onward, across both columns - to the same band on the
    // next sheet, in order, at the top of its left column (every unit already
    // waiting there is later in source order). Shifting single nodes instead
    // would strand a later step above an earlier one.
    function firstOverflowingIndex(band, limit) {
      const units = Array.from(band.querySelectorAll('[data-vunit]'));
      for (let i = 0; i < units.length; i++) {
        if (units[i].getBoundingClientRect().bottom > limit) return i;
      }
      return -1;
    }
    // Inline labels (``#### Ingredients`` / ``##### Instructions``) and the
    // band-column heading markers are the units that introduce the ones below
    // them - the same shape the upward pull pairs with its first following
    // unit.
    function isHeadingUnit(el) {
      return el.tagName === 'H2'
        || !!(el.querySelector && el.querySelector('h3, h4'));
    }
    for (let iter = 0; iter < 4; iter++) {
      let movedAny = false;
      for (let s = 0; s < allSheets.length - 1; s++) {
        const limit = allSheets[s].getBoundingClientRect().bottom - padBot - EPS;
        const nextSheet = allSheets[s + 1];
        for (const band of Array.from(
               allSheets[s].querySelectorAll('[data-band]'))) {
          const at = firstOverflowingIndex(band, limit);
          if (at < 0) continue;
          const key = band.getAttribute('data-band');
          const nb = key ? bandOf(nextSheet, key) : null;
          const target = nb ? nb.querySelector('[data-vcol="L"]') : null;
          // No next sheet to carry the overflow: the clip audit reports it as
          // a warning instead of letting it vanish.
          if (!target) continue;
          const units = Array.from(band.querySelectorAll('[data-vunit]'));
          // A heading marker labels the units beneath it, so it travels with
          // its first moved unit instead of being stranded at the sheet foot.
          let from = at;
          while (from > 0 && isHeadingUnit(units[from - 1])) from--;
          // Fixed-split variants must travel whole without merging their
          // ingredient and instruction columns. Merging them makes the band
          // taller and can clip later variants on the destination sheet.
          const stForBand = streamByKey[key];
          if (stForBand && stForBand.fixedSplit != null) {
            for (const side of ['L', 'R']) {
              const source = band.querySelector('[data-vcol="' + side + '"]');
              const dest = nb.querySelector('[data-vcol="' + side + '"]');
              const ref = dest.firstChild;
              Array.from(source.children).forEach(n => dest.insertBefore(n, ref));
            }
          } else {
            const ref = target.firstChild;
            units.slice(from).forEach(n => target.insertBefore(n, ref));
          }
          adjusted++;
          movedAny = true;
        }
        // Stranded-label sweep: a heading unit that ends a band's share of this
        // sheet while its own units continue on the next one prints as a bare
        // label at the foot of the page (it fits, so the overflow sweep above
        // never sees it). Send it ahead, to the top of its units.
        for (const band of Array.from(
               allSheets[s].querySelectorAll('[data-band]'))) {
          const units = Array.from(band.querySelectorAll('[data-vunit]'));
          const lastUnit = units[units.length - 1];
          if (!lastUnit || !isHeadingUnit(lastUnit)) continue;
          const key = band.getAttribute('data-band');
          const nb = key ? bandOf(nextSheet, key) : null;
          const target = nb ? nb.querySelector('[data-vcol="L"]') : null;
          if (!target || !target.firstChild) continue;
          target.insertBefore(lastUnit, target.firstChild);
          adjusted++;
          movedAny = true;
        }
      }
      if (!movedAny) break;
    }
    // --- Upward pull (ADR 0011): back-fill genuine gaps from the next sheet ---
    // Mirror of the straggler shift: once overflows have settled, leading
    // flowing units of a following sheet move into remaining space of the
    // same band on this sheet. Never giants or diagram windows, never past
    // the content limit; a heading only moves together with its first
    // following unit so no lone heading is pulled up (or left behind).
    for (let iter = 0; iter < 4 && allSheets.length > 1; iter++) {
      let pulledAny = false;
      for (let s = 0; s < allSheets.length - 1; s++) {
        const cur = allSheets[s], nxt = allSheets[s + 1];
        const limit = cur.getBoundingClientRect().bottom - padBot - EPS;
        const streamRank = k => k === 'instructions' ? 1 : 0;
        for (let guard = 0; guard < 50; guard++) {
          const curNodes = flowingNodesV(cur);
          if (!curNodes.length) break;
          const nxtNodes = flowingNodesV(nxt);
          if (!nxtNodes.length) break;
          const group = [nxtNodes[0]];
          if (nxtNodes[0].tagName === 'H2') {
            if (!nxtNodes[1]) break;
            group.push(nxtNodes[1]);
          }
          const keyEl = group[0].closest('[data-band]');
          const key = keyEl ? keyEl.getAttribute('data-band') : null;
          if (!key) break;
          // Strict stacking: no unit of a later stream may already sit on
          // cur - pulling an earlier-stream unit above it would reorder.
          let laterHere = false;
          cur.querySelectorAll('[data-band]').forEach(b => {
            if (streamRank(b.getAttribute('data-band')) > streamRank(key)
                && b.querySelector('[data-vunit]:not([data-giant])')) {
              laterHere = true;
            }
          });
          if (laterHere) break;
          const targetBand = bandOf(cur, key);
          if (!targetBand) break;
          const colBottom = c => {
            const ns = Array.from(c.querySelectorAll('[data-vunit]'))
              .filter(n => !n.hasAttribute('data-giant'));
            return ns.length
              ? Math.max.apply(null, ns.map(n => n.getBoundingClientRect().bottom))
              : targetBand.getBoundingClientRect().top;
          };
          const cL = targetBand.querySelector('[data-vcol="L"]');
          const cR = targetBand.querySelector('[data-vcol="R"]');
          // Instruction bands must preserve left-first ordering: continuation
          // steps (always later in sequence) go to the RIGHT (suffix) column,
          // never the LEFT (prefix) column, so a later step never jumps ahead of
          // earlier steps that already spilled into the right column. Other bands
          // keep the height-balanced back-fill into the shorter column.
          const isInsBand = key === 'instructions' || key.indexOf('ins:') === 0;
          const srcCol = group[0].closest('[data-vcol]');
          const srcSide = srcCol ? srcCol.getAttribute('data-vcol') : null;
          const dest = isInsBand
            ? (srcSide === 'R' ? cR : null)
            : (colBottom(cL) <= colBottom(cR) ? cL : cR);
          if (!dest) break;
          const restores = group.map(n => ({
            n, parent: n.parentNode, before: n.nextSibling}));
          group.forEach(n => dest.appendChild(n));
          const newBottom = Math.max.apply(null,
            group.map(n => n.getBoundingClientRect().bottom));
          // The pulled units fitting is not enough: a pull grows an earlier
          // band, which pushes every later band on this sheet down. The whole
          // sheet must still end inside the content limit, or the pull would
          // hand the clip a fresh victim.
          const sheetBottom = flowingNodesV(cur).reduce(
            (low, n) => Math.max(low, n.getBoundingClientRect().bottom), 0);
          if (newBottom <= limit && sheetBottom <= limit) {
            adjusted++; pulledAny = true; continue;
          }
          restores.forEach(r => {
            if (r.parent) r.parent.insertBefore(r.n, r.before);
          });
          break;
        }
      }
      if (!pulledAny) break;
    }
    // Bands that received units only via the shift/pull passes have no
    // filled head yet - label every populated band now. fillHead keeps
    // existing labels, so this is idempotent.
    allSheets.forEach(sh => {
      streams.forEach(st => {
        const b = sh.querySelector('[data-band="' + st.key + '"]');
        if (b && b.querySelector('[data-vunit]')) fillHead(b, st.label);
      });
    });
    // Backfill notes (ADR 0011), read from the FINAL arrangement: a sheet
    // carrying both populated bands prints instructions starting beneath
    // ingredients - whether planned so, or delivered by the pull pass.
    // Instruction bands are the legacy single one ("instructions") or any
    // per-version band ("ins:<n>"); any populated one counts as backfill.
    allSheets.forEach((sh, idx) => {
      const ingBand = sh.querySelector('[data-band="ingredients"]');
      const insBand = sh.querySelector(
        '[data-band="instructions"],[data-band^="ins:"]');
      if (ingBand && insBand
          && ingBand.querySelector('[data-vunit]')
          && insBand.querySelector('[data-vunit]')) {
        backfillNotes.push('instructions start below ingredients on sheet '
                           + (idx + 1));
      }
    });
    // Drop band scaffolds left empty by the straggler pass: a lone repeated
    // heading above nothing reads as noise on the printed sheet. Also prune
    // TRAILING lone heading markers in each placed column - a heading whose
    // section items all continue on the next sheet is equally noise.
    allSheets.forEach(sh => {
      sh.querySelectorAll('[data-band]').forEach(b => {
        if (!b.querySelector('[data-vunit]')) b.remove();
      });
      sh.querySelectorAll('[data-vcol]').forEach(col => {
        const kids = Array.from(col.children);
        for (let i = kids.length - 1; i >= 0; i--) {
          const k = kids[i];
          if (k.tagName === 'H2' && k.hasAttribute('data-vunit')) {
            k.remove();
            continue;
          }
          break;
        }
      });
    });
    sheetIsBare = function(sh) {
      const units = sh.querySelectorAll('[data-vunit],[data-band-window]');
      if (!units.length) return false;
      return Array.from(units).every(n =>
        n.hasAttribute('data-giant') || n.hasAttribute('data-band-window'));
    };
    // Back-fill can evacuate a MIDDLE sheet completely (e.g. its whole content
    // was pulled up into the previous sheet) as well as a trailing one. Drop
    // every extra sheet that ended up carrying no flowing content at all, not
    // just the last. Runs before the eyebrow strips attach, so strip text
    // cannot mask emptiness here. Sheet 0 (the header sheet) is always kept.
    const keptSheets = allSheets.filter((sh, idx) => {
      if (idx === 0) return true;
      return !!sh.querySelector(
        '[data-vunit],[data-band-window],svg,img,[data-giant]');
    });
    allSheets.forEach(sh => { if (!keptSheets.includes(sh)) sh.remove(); });
    allSheets = keptSheets;
  }

  // --- Eyebrow strips: only where ordinary content continues ---
  // Attached now rather than at clone time: a continuation sheet whose every
  // unit ended up being a sliced-diagram band or an unbreakable giant block
  // prints bare - repeating the title above pure artwork adds nothing.
  // Sheets carrying flowing content (prose, steps, tables) keep the strip.
  // Bands are sized with the strip's height already reserved (availNext),
  // so re-adding a strip here cannot overflow anything, and omitting one
  // only frees space above the artwork.
  extras.forEach((ex, idx) => {
    if (!sheetIsBare(ex)) {
      ex.insertBefore(makeStrip(stripLabelFor(idx + 1)), ex.firstChild);
    }
  });

  // --- Seam pass: trim clipped bands, carry rows into the next band ---
  // The content column clips at the content limit, so a band whose box
  // passes that edge would silently lose its bottom rows at print time.
  // Trim the box and let the next band of the same diagram pick the rows
  // up (start earlier, window taller) - coverage stays exact end to end.
  const bandsByDiagram = {};
  Array.from(document.querySelectorAll('[data-band-window]')).forEach(b => {
    const d = b.getAttribute('data-band-diagram') || '0';
    (bandsByDiagram[d] = bandsByDiagram[d] || []).push(b);
  });
  Object.keys(bandsByDiagram).forEach(d => {
    let carry = 0;
    bandsByDiagram[d].forEach(box => {
      const off = parseFloat(box.getAttribute('data-band-off')) || 0;
      const scale = parseFloat(box.getAttribute('data-band-scale')) || 1;
      let effOff = off;
      let h = parseFloat(box.style.height);
      if (carry > 0) {
        effOff = Math.max(0, off - carry);
        h += (off - effOff);
        carry -= (off - effOff);
      }
      const cb = clipBottomFor(box);
      if (cb !== null) {
        const overflow = box.getBoundingClientRect().top + h - cb;
        if (overflow > 0.5) {
          h = Math.max(1, h - overflow);
          carry += overflow;
        }
      }
      box.style.height = h + 'px';
      box.setAttribute('data-band-off', String(effOff));
      const bandSvg = box.querySelector('svg');
      if (bandSvg && bandSvg.viewBox && bandSvg.viewBox.baseVal) {
        const vb = bandSvg.viewBox.baseVal;
        vb.y = effOff * scale;
        vb.height = h * scale;
      }
    });
  });

  // The final sheet must not force a trailing blank page.
  const lastSheet = allSheets[allSheets.length - 1];
  lastSheet.style.pageBreakAfter = 'auto';
  lastSheet.style.breakAfter = 'auto';

  // Drop trailing sheets that carry no meaningful content (e.g. a leftover
  // empty paragraph unit): they would print as near-blank pages.
  while (allSheets.length > 1) {
    const lastSh = allSheets[allSheets.length - 1];
    const txt = (lastSh.innerText || '').replace(/\u00a0/g, ' ').trim();
    const meaningful = txt.length > 0
      || lastSh.querySelector('svg, img, [data-giant]');
    if (!meaningful) { lastSh.remove(); allSheets.pop(); } else break;
  }

  // Column-order audit (regression tripwire): within every instruction band the
  // source-order sequence (data-seq) read across left then right column must keep
  // the left column as a prefix of the steps and the right column as the suffix -
  // i.e. every left index must be <= every right index. A later step landing in
  // the left column above an earlier one in the right column means the left-first
  // invariant was broken. Displayed step numbers reset per sub-section, so the
  // check uses data-seq (true source order), not the printed number.
  function bandStepOrderIssues() {
    const issues = [];
    const seqsOf = col => Array.from(col.querySelectorAll('[data-vunit]'))
      .map(n => n.getAttribute('data-seq'))
      .filter(s => s !== null && s !== undefined)
      .map(s => parseInt(s, 10));
    const shownOf = col => Array.from(col.querySelectorAll('[data-vunit]')).map(n => {
      const badge = n.children && n.children[0];
      const t = badge && badge.tagName === 'SPAN' ? (badge.textContent || '').trim() : '';
      const m = t.match(/^\d+/);
      return m ? m[0] : '?';
    });
    allSheets.forEach((sh, si) => {
      sh.querySelectorAll('[data-band="instructions"],[data-band^="ins:"]')
        .forEach(b => {
          const cL = b.querySelector('[data-vcol="L"]');
          const cR = b.querySelector('[data-vcol="R"]');
          if (!cL || !cR) return;
          const lSeq = seqsOf(cL), rSeq = seqsOf(cR);
          if (!lSeq.length || !rSeq.length) return;
          const maxL = Math.max.apply(null, lSeq);
          const minR = Math.min.apply(null, rSeq);
          if (maxL > minR) {
            issues.push('sheet ' + (si + 1) + ' band '
                        + b.getAttribute('data-band')
                        + ': steps not left-first (L=' + shownOf(cL).join(',')
                        + ' R=' + shownOf(cR).join(',') + ')');
          }
        });
    });
    return issues;
  }
  const colOrderIssues = bandStepOrderIssues();

  // Instruction integrity audit (regression tripwire): the probe pass detaches
  // units for measuring and materialisation MOVES them (appendChild, not
  // clone), so a stream registered twice does not duplicate text - it
  // relocates nodes onto a later sheet, printing the preamble after the steps
  // that precede it (the Aglio e Olio bug). Two signals: a meaningful unit
  // missing from the final DOM, and instruction units printing out of
  // source-stream order. Contentless units are skipped: the trailing
  // blank-sheet trim legitimately drops sheets whose only unit was an empty
  // paragraph.
  function instructionIntegrityIssues() {
    const issues = [];
    const isIns = k => k === 'ins:intro' || k.indexOf('ins:') === 0;
    const meaningful = el => ((el.textContent || '').replace(/\u00a0/g, ' ').trim().length > 0
      || !!(el.querySelector && el.querySelector('svg, img')));
    verticalStreams.filter(st => isIns(st.key)).forEach(st => {
      st.units.forEach((u, ui) => {
        if (!u.el || u.el.nodeType !== 1 || u.el.hasAttribute('data-giant')) return;
        if (u.el.isConnected) return;
        if (!meaningful(u.el)) return;   // trimmed near-blank sheet: benign
        issues.push("stream '" + st.key + "' unit " + ui
          + ' was planned but never printed: "'
          + (u.el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60) + '"');
      });
    });
    let prev = null;
    verticalStreams.filter(st => isIns(st.key)).forEach(st => {
      st.units.forEach((u, ui) => {
        if (!u.el || u.el.nodeType !== 1 || u.el.hasAttribute('data-giant')) return;
        if (!u.el.isConnected) return;
        if (prev && !(prev.el.compareDocumentPosition(u.el)
                      & Node.DOCUMENT_POSITION_FOLLOWING)) {
          issues.push("stream '" + st.key + "' unit " + ui
            + ' prints out of source order after stream ' + prev.key
            + ' (duplicate stream registration relocates nodes)');
        }
        prev = {key: st.key, el: u.el};
      });
    });
    return issues;
  }
  const integrityIssues = instructionIntegrityIssues();

  // Clip audit (regression tripwire): every sheet clips at its content limit,
  // so a unit whose box crosses that line loses its bottom - or all of itself -
  // at print time while staying attached to the DOM, which the detach-based
  // audit above cannot see (Risotto's impressive-date step 2 printed nowhere at
  // all this way). Report every crossing so the generation report names it.
  function clippedUnitIssues() {
    const issues = [];
    allSheets.forEach((sh, si) => {
      const limit = sh.getBoundingClientRect().bottom - padBot;
      flowingNodesV(sh).forEach(n => {
        const bottom = n.getBoundingClientRect().bottom;
        if (bottom <= limit + 0.5) return;
        const bandEl = n.closest('[data-band]');
        issues.push('sheet ' + (si + 1) + ' band '
          + (bandEl ? bandEl.getAttribute('data-band') : '?')
          + ': unit "'
          + (n.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 50)
          + '" crosses the content limit (bottom ' + Math.round(bottom)
          + 'px > ' + Math.round(limit) + 'px) and is clipped');
      });
    });
    return issues;
  }
  const clippedIssues = clippedUnitIssues();

  const seam = collectSeamReport();
  return {
    changed: true,
    kind: kind,
    layout: verticalRecipe ? 'vertical' : 'side-by-side',
    sheets: allSheets.length,
    giants: giants,
    scaled: scaledNames,
    sliced: slicedNotes,
    joinScaled: joinScaled,
    joinDeferred: joinDeferred,
    backfill: backfillNotes,
    colOrderIssues: colOrderIssues,
    unplaced: integrityIssues.concat(clippedIssues),
    seamNotes: seam.notes,
    seamErrors: seam.errors,
    adjusted: adjusted,
    html: '<!DOCTYPE html>\n' + document.documentElement.outerHTML
  };
}
"""


# Shared seam-integrity JS: injected into the splitter (after the trim pass)
# and usable standalone on any loaded page - html_to_pdf runs it right before
# page.pdf() as the conversion gate for sliced diagrams.
_SEAM_JS = r"""
function clipBottomFor(box) {
  let el = box.parentElement;
  while (el && el !== document.body) {
    const cs = getComputedStyle(el);
    if (cs.overflowY === 'hidden' || cs.overflowY === 'clip') {
      return el.getBoundingClientRect().bottom;
    }
    el = el.parentElement;
  }
  const sheet = box.closest('.recipe-page, .a4-page');
  return sheet ? sheet.getBoundingClientRect().bottom : null;
}
function collectSeamReport() {
  const groups = {};
  Array.from(document.querySelectorAll('[data-band-window]')).forEach(b => {
    const d = b.getAttribute('data-band-diagram') || '0';
    (groups[d] = groups[d] || []).push(b);
  });
  const notes = [];
  const errors = [];
  let totalBands = 0;
  Object.keys(groups).forEach(d => {
    const boxes = groups[d];
    totalBands += boxes.length;
    const totalH = boxes[0]
      ? (parseFloat(boxes[0].getAttribute('data-band-total')) || 0) : 0;
    let coverTo = 0;
    boxes.forEach((box, k) => {
      const br = box.getBoundingClientRect();
      const covStart = parseFloat(box.getAttribute('data-band-off')) || 0;
      const covEnd = covStart + br.height;
      if (k === 0 && Math.abs(covStart) > 0.5) {
        errors.push('band 1 starts at diagram row ' + covStart.toFixed(1) +
                    ' (expected 0)');
      }
      if (k > 0 && Math.abs(covStart - coverTo) > 1) {
        errors.push('seam ' + k + ': band starts at row ' + covStart.toFixed(1) +
                    ' after coverage to ' + coverTo.toFixed(1) + ' (' +
                    (covStart - coverTo).toFixed(1) + 'px ' +
                    (covStart > coverTo ? 'lost' : 'duplicated') + ')');
      }
      coverTo = covEnd;
      const scale = parseFloat(box.getAttribute('data-band-scale')) || 1;
      const svg = box.querySelector('svg');
      if (svg && svg.viewBox && svg.viewBox.baseVal) {
        const vb = svg.viewBox.baseVal;
        if (Math.abs(vb.y / scale - covStart) > 0.5 ||
            Math.abs(vb.height / scale - br.height) > 0.5) {
          errors.push('band ' + (k + 1) + ' viewBox does not match rows [' +
                      covStart.toFixed(1) + ', ' + covEnd.toFixed(1) + ']');
        }
        const renderedW = svg.getBoundingClientRect().width;
        if (renderedW && Math.abs(vb.width / scale - renderedW) > 1) {
          errors.push('band ' + (k + 1) + ' viewBox width ' + vb.width +
                      ' does not match rendered width ' +
                      renderedW.toFixed(1) + ' at scale ' + scale.toFixed(3));
        }
      }
      const cb = clipBottomFor(box);
      if (cb !== null && br.bottom > cb + 0.5) {
        errors.push('band ' + (k + 1) + ' extends ' +
                    (br.bottom - cb).toFixed(1) + 'px past its clip edge');
      }
    });
    if (totalH && Math.abs(coverTo - totalH) > 1.5) {
      errors.push('coverage ends at row ' + coverTo.toFixed(1) + ' of ' +
                  totalH.toFixed(1) + ' (' + (totalH - coverTo).toFixed(1) +
                  'px of diagram lost)');
    }
    notes.push(boxes.length + ' band(s), seams verified, coverage ' +
               Math.round(coverTo) + '/' + Math.round(totalH) + 'px');
  });
  return {bands: totalBands, notes: notes, errors: errors};
}
"""

_JS_SPLITTER = _JS_SPLITTER_TEMPLATE.replace('/*__SEAM_JS__*/', _SEAM_JS)

# Standalone seam audit for the conversion gate: same checks, read-only.
_JS_SEAM_AUDIT = "() => {" + _SEAM_JS + "\nreturn collectSeamReport(); }"


def audit_page_seams(page) -> List[str]:
    """Re-verify band seam integrity on a loaded page (conversion gate)."""
    result = page.evaluate(_JS_SEAM_AUDIT)
    return list((result or {}).get("errors") or [])


def split_page_file(html_path: str) -> Optional[List[Tuple[str, str]]]:
    """Split one rendered sheet file if its content exceeds the content limit.

    Returns ``(level, message)`` diagnostics when the file was rewritten with
    more than one sheet; recipe pages additionally report their elected layout
    (ADR 0009) - ``side-by-side`` (or ``vertical`` for recipes without an
    Ingredients section, which never offer side-by-side) when nothing changed,
    ``vertical`` ahead of the rewrite notes - and a ``backfill`` line per sheet
    where instructions start below ingredients (ADR 0011). ``join-scaled`` lines
    record ADR 0017
    elections (a diagram mildly scaled so it starts below its text); ``info``
    lines carry joins deferred because the sheet was genuinely full. ``warn``
    lines carry the column-order audit, the instruction-integrity audit (a
    planned instruction unit that never printed, or prints out of source order)
    and the clip audit (a unit crossing its sheet's content limit, so it would
    print with its bottom - or all of itself - cut off at the sheet seam).
    Non-recipe pages that fit return ``None``.
    """
    path = Path(html_path)
    browser = _get_browser()
    page = browser.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=1)
    # Measure under print media: the templates' screen styles wrap sheets in a
    # horizontal flex row, which squeezes them and corrupts every measurement.
    page.emulate_media(media="print")
    try:
        page.goto(_path_to_uri(str(path.resolve())),
                  timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")
        wait_for_render_settled(page)
        # Grace period so the Tailwind CDN JIT settles after font load.
        page.wait_for_timeout(150)
        result = page.evaluate(_JS_SPLITTER)
    finally:
        page.close()

    name = path.name
    kind = (result or {}).get("kind")
    layout = (result or {}).get("layout")
    sheets = int((result or {}).get("sheets", 1))

    if not result or not result.get("changed"):
        # Layout election reporting (ADR 0009): a recipe page records which
        # layout won even when no continuation was needed. Recipes without an
        # Ingredients section always elect vertical - their sidebar is never
        # written - so a fitting page can report a vertical election too.
        if kind == "recipe" and layout in ("side-by-side", "vertical"):
            return [(layout,
                     f"{name}: {layout} layout elected (1 sheet)")]
        return None

    with open(path, "w", encoding="utf-8") as f:
        f.write(result["html"])

    html = result["html"]
    token_count = html.count('<div data-page-footer')
    sheet_count = count_sheets(html)
    diags: List[Tuple[str, str]] = []
    if token_count < sheet_count:
        html = _ensure_footer_tokens(html)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        diags.append(("info", f"{name}: footer token re-injected into "
                              f"{sheet_count - token_count} continuation sheet(s)"))
    if kind == "recipe":
        diags.append(("vertical",
                      f"{name}: vertical layout elected ({sheets} sheet(s))"))
    if sheets > 1:
        diags.append(("split", f"{name}: rebuilt as {sheets} sheets "
                               f"(kind={kind or '?'})"))
    for msg in result.get("giants") or []:
        diags.append(("giant", f"{name}: {msg}"))
    for msg in result.get("scaled") or []:
        diags.append(("scaled", f"{name}: scaled block '{msg}'"))
    for msg in result.get("sliced") or []:
        diags.append(("sliced", f"{name}: {msg}"))
    for msg in result.get("joinScaled") or []:
        diags.append(("join-scaled", f"{name}: {msg}"))
    for msg in result.get("joinDeferred") or []:
        diags.append(("info", f"{name}: {msg}"))
    for msg in result.get("backfill") or []:
        diags.append(("backfill", f"{name}: {msg}"))
    for msg in result.get("seamNotes") or []:
        diags.append(("info", f"{name}: {msg}"))
    for msg in result.get("seamErrors") or []:
        diags.append(("error", f"{name}: seam integrity: {msg}"))
    for msg in result.get("colOrderIssues") or []:
        diags.append(("warn", f"{name}: {msg}"))
    for msg in result.get("unplaced") or []:
        diags.append(("warn", f"{name}: {msg}"))
    adjusted = int(result.get("adjusted", 0))
    if adjusted:
        diags.append(("info", f"{name}: verification pass moved {adjusted} block(s)"))
    return diags
