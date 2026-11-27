import {
  CHINESE_RE,
  DROP_SIGNATURE,
  EMOJI_RE,
} from './constants.js';
import { getStrings, isEn } from './i18n.js';

const MARKER_LINE_RE = /^(?<prefix>[ ]{0,3}>[ ]?(?:\[poop:(?<legacy>[a-z0-9_-]+)\])?[^\r\n\u2028\u2029]*?)(?<sig><!--\s*block-poop-everywhere:drop(?::(?<kind>[a-z0-9_-]+))?(?::(?<meta>[a-z0-9_=,-]+))?\s*-->)[ \t]*(?:\r\n|\r|\n)?$/;
const MARKER_COMMENT_RE = /<!--\s*block-poop-everywhere:drop(?::[a-z0-9_-]+)?(?::[a-z0-9_=,-]+)?\s*-->/g;

const FENCE_OPEN_RE = /^[ ]{0,3}(`{3,}|~{3,})(.*)$/;
const FENCE_CLOSE_RE = /^(`{3,}|~{3,})[ \t]*$/;
const HTML_TYPE1_OPEN_RE = /^[ ]{0,3}<(pre|script|style|textarea)(?:[ \t>]|$)/i;
const HTML_TYPE1_CLOSE_RE = /<\/(?:pre|script|style|textarea)>/i;
const HTML_TYPE6_OPEN_RE = /^[ ]{0,3}<\/?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)(?:[ \t\/>]|$)/i;
const HTML_TYPE7_OPEN_RE = /^[ ]{0,3}(?:<[A-Za-z][A-Za-z0-9-]*(?:[ \t]+[A-Za-z_:][A-Za-z0-9_.:-]*(?:[ \t]*=[ \t]*(?:[^ \t\r\n"'=<>`]+|'[^']*'|"[^"]*"))?)*[ \t]*\/?>|<\/[A-Za-z][A-Za-z0-9-]*[ \t]*>)[ \t]*$/;
const LIST_ITEM_RE = /^([ ]{0,3})([-*+]|\d{1,9}[.)])([ \t]+|$)/;
const ATX_HEADING_RE = /^[ ]{0,3}#{1,6}(?:[ \t]|$)/;
const THEMATIC_BREAK_RE = /^[ ]{0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$/;
const SETEXT_UNDERLINE_RE = /^[ ]{0,3}(?:=+|-+)[ \t]*$/;

function stripTrailingNewlines(s) {
  return s.replace(/[\r\n]+$/, '');
}

function stripSpacesTabs(s) {
  return s.replace(/^[ \t]+|[ \t]+$/g, '');
}

function rstripSpacesTabs(s) {
  return s.replace(/[ \t]+$/, '');
}

function lstripSpaces(s) {
  return s.replace(/^ +/, '');
}

function isBlankText(s) {
  return stripSpacesTabs(s) === '';
}

function isBareNewline(s) {
  return s === '\n' || s === '\r\n' || s === '\r';
}

function endsWithAnyNewline(s) {
  return s.endsWith('\n') || s.endsWith('\r');
}

export function matchMarkerLine(line) {
  const m = MARKER_LINE_RE.exec(line);
  if (!m) return null;
  const sigPos = m.groups.prefix.length;
  let bs = 0;
  let j = sigPos - 1;
  while (j >= 0 && line[j] === '\\') {
    bs += 1;
    j -= 1;
  }
  if (bs % 2 === 1) return null;
  return m;
}

export function dropSig(kind, meta = '') {
  if (meta) {
    return `<!-- block-poop-everywhere:drop:${kind}:${meta} -->`;
  }
  return `<!-- block-poop-everywhere:drop:${kind} -->`;
}

/**
 * Split strictly on CommonMark line endings (CRLF, LF, CR), preserving bytes in O(N) time.
 */
export function splitMdLines(content) {
  if (!content) return [];
  const lines = [];
  let pos = 0;
  const n = content.length;
  let nlR = content.indexOf('\r', 0);
  let nlN = content.indexOf('\n', 0);
  while (pos < n) {
    if (nlR !== -1 && nlR < pos) {
      nlR = content.indexOf('\r', pos);
    }
    if (nlN !== -1 && nlN < pos) {
      nlN = content.indexOf('\n', pos);
    }
    if (nlR === -1 && nlN === -1) {
      lines.push(content.slice(pos));
      break;
    }
    let end;
    if (nlR !== -1 && (nlN === -1 || nlR < nlN)) {
      end = (nlR + 1 < n && content[nlR + 1] === '\n') ? nlR + 2 : nlR + 1;
    } else {
      end = nlN + 1;
    }
    lines.push(content.slice(pos, end));
    pos = end;
  }
  return lines;
}

export function leadingColumns(text, startCol = 0) {
  let col = startCol;
  let idx = 0;
  const n = text.length;
  while (idx < n) {
    const ch = text[idx];
    if (ch === ' ') {
      col += 1;
      idx += 1;
    } else if (ch === '\t') {
      col += 4 - (col % 4);
      idx += 1;
    } else {
      break;
    }
  }
  return [col - startCol, idx];
}

export function stripSingleBqPrefix(text, startCol = 0) {
  const [cols, idx] = leadingColumns(text, startCol);
  if (cols > 3 || idx >= text.length || text[idx] !== '>') {
    return [null, startCol];
  }
  const colAfterGt = startCol + cols + 1;
  const rest = text.slice(idx + 1);
  if (rest.startsWith(' ')) {
    return [rest.slice(1), colAfterGt + 1];
  }
  if (rest.startsWith('\t')) {
    const tabW = 4 - (colAfterGt % 4);
    return [' '.repeat(tabW - 1) + rest.slice(1), colAfterGt + 1];
  }
  return [rest, colAfterGt];
}

export function htmlBlockEndKind(strippedNl, allowType7 = false) {
  if (HTML_TYPE1_OPEN_RE.test(strippedNl)) {
    return 'type1';
  }
  const s = lstripSpaces(strippedNl);
  if (strippedNl.length - s.length > 3) {
    return null;
  }
  if (s.startsWith('<!--')) return 'comment';
  if (s.startsWith('<?')) return 'pi';
  if (s.length >= 3 && s.startsWith('<!')) {
    const c = s[2].toUpperCase();
    if (c >= 'A' && c <= 'Z') return 'decl';
  }
  if (s.startsWith('<![CDATA[')) return 'cdata';
  if (HTML_TYPE6_OPEN_RE.test(strippedNl)) return 'blank';
  if (allowType7 && HTML_TYPE7_OPEN_RE.test(strippedNl)) return 'blank';
  return null;
}

export function htmlBlockCloses(kind, strippedNl) {
  if (kind === 'type1') return HTML_TYPE1_CLOSE_RE.test(strippedNl);
  if (kind === 'comment') return strippedNl.includes('-->');
  if (kind === 'pi') return strippedNl.includes('?>');
  if (kind === 'decl') return strippedNl.includes('>');
  if (kind === 'cdata') return strippedNl.includes(']]>');
  return false;
}

function listItemContentIndent(line, startCol, mList) {
  const [leadCols] = leadingColumns(mList[1], startCol);
  const markerEndCol = startCol + leadCols + mList[2].length;
  const after = line.slice(mList[1].length + mList[2].length);
  const [wsCols, wsIdx] = leadingColumns(after, markerEndCol);
  const rest = after.slice(wsIdx);
  if (rest === '' || wsCols >= 5) {
    return (markerEndCol - startCol) + 1;
  }
  return (markerEndCol - startCol) + Math.max(wsCols, 1);
}

function isBareBqSep(rawLine) {
  const strippedNl = stripTrailingNewlines(rawLine);
  const [cols, idx] = leadingColumns(strippedNl, 0);
  return cols <= 3 && rstripSpacesTabs(strippedNl.slice(idx)) === '>';
}

function canListInterruptParagraph(mList, line) {
  const marker = mList[2];
  const after = line.slice(mList[0].length);
  if (isBlankText(after)) return false;
  if (marker.endsWith('.') || marker.endsWith(')')) {
    return parseInt(marker.slice(0, -1), 10) === 1;
  }
  return true;
}

function lineInterruptsBqParagraph(strippedNl, cols) {
  if (isBlankText(strippedNl)) return true;
  if (cols <= 3) {
    const mOpen = FENCE_OPEN_RE.exec(strippedNl);
    if (mOpen && !(mOpen[1][0] === '`' && mOpen[2].includes('`'))) {
      return true;
    }
    if (htmlBlockEndKind(strippedNl, false) !== null) {
      return true;
    }
    if (ATX_HEADING_RE.test(strippedNl) || THEMATIC_BREAK_RE.test(strippedNl)) {
      return true;
    }
    const mList = LIST_ITEM_RE.exec(strippedNl);
    if (mList && canListInterruptParagraph(mList, strippedNl)) {
      return true;
    }
  }
  return false;
}

function lineInterruptsParaText(line) {
  if (isBlankText(line)) return true;
  if (stripSingleBqPrefix(line, 0)[0] !== null) return true;
  const [cols] = leadingColumns(line, 0);
  return lineInterruptsBqParagraph(line, cols);
}

function parseLinkRefDef(textLines, startIdx, bqMode = false) {
  const nLines = textLines.length;
  if (startIdx >= nLines) return 0;
  const bqCache = new Map();

  function getLine(liIdx) {
    if (!bqMode) return textLines[liIdx];
    if (bqCache.has(liIdx)) return bqCache.get(liIdx);
    const s = textLines[liIdx];
    const [inn] = stripSingleBqPrefix(s, 0);
    const cand = inn !== null ? inn : s;
    bqCache.set(liIdx, cand);
    return cand;
  }

  const first = getLine(startIdx);
  const [cols, idx] = leadingColumns(first, 0);
  if (cols > 3 || idx >= first.length || first[idx] !== '[') {
    return 0;
  }

  function lineOk(liIdx) {
    if (liIdx >= nLines) return false;
    if (liIdx === startIdx) return true;
    return !lineInterruptsParaText(getLine(liIdx));
  }

  let li = startIdx;
  let ci = idx + 1;
  let labelLen = 0;
  let hasNonWs = false;
  let foundClose = false;
  while (lineOk(li)) {
    const ln = getLine(li);
    const lnLen = ln.length;
    while (ci < lnLen) {
      const ch = ln[ci];
      if (ch === '\\' && ci + 1 < lnLen) {
        labelLen += 2;
        if (labelLen > 999) return 0;
        hasNonWs = true;
        ci += 2;
        continue;
      }
      if (ch === '[') return 0;
      if (ch === ']') {
        foundClose = true;
        ci += 1;
        break;
      }
      labelLen += 1;
      if (labelLen > 999) return 0;
      if (ch !== ' ' && ch !== '\t') {
        hasNonWs = true;
      }
      ci += 1;
    }
    if (foundClose) break;
    labelLen += 1;
    if (labelLen > 999) return 0;
    li += 1;
    ci = 0;
  }

  if (!foundClose || !hasNonWs) return 0;
  let ln = getLine(li);
  if (ci >= ln.length || ln[ci] !== ':') return 0;
  ci += 1;

  while (ci < ln.length && (ln[ci] === ' ' || ln[ci] === '\t')) ci += 1;
  if (ci >= ln.length) {
    li += 1;
    if (!lineOk(li)) return 0;
    ln = getLine(li);
    ci = 0;
    while (ci < ln.length && (ln[ci] === ' ' || ln[ci] === '\t')) ci += 1;
    if (ci >= ln.length) return 0;
  }

  if (ln[ci] === '<') {
    ci += 1;
    let closedAngle = false;
    while (ci < ln.length) {
      const ch = ln[ci];
      if (ch === '\\' && ci + 1 < ln.length) {
        ci += 2;
        continue;
      }
      if (ch === '<') return 0;
      if (ch === '>') {
        closedAngle = true;
        ci += 1;
        break;
      }
      ci += 1;
    }
    if (!closedAngle) return 0;
  } else {
    const destStart = ci;
    let parenDepth = 0;
    while (ci < ln.length) {
      const ch = ln[ci];
      const oc = ch.charCodeAt(0);
      if (oc <= 0x20 || oc === 0x7f) break;
      if (ch === '\\' && ci + 1 < ln.length) {
        ci += 2;
        continue;
      }
      if (ch === '(') {
        parenDepth += 1;
        if (parenDepth > 32) return 0;
      } else if (ch === ')') {
        if (parenDepth === 0) return 0;
        parenDepth -= 1;
      }
      ci += 1;
    }
    if (ci === destStart || parenDepth !== 0) return 0;
  }

  const destLineIdx = li;

  function parseTitle(tLi, tCi) {
    const tLn = getLine(tLi);
    if (tCi >= tLn.length) return 0;
    const opener = tLn[tCi];
    let closer;
    if (opener === '"') closer = '"';
    else if (opener === "'") closer = "'";
    else if (opener === '(') closer = ')';
    else return 0;
    tCi += 1;
    let curLi = tLi;
    while (curLi < nLines) {
      if (curLi > tLi && !lineOk(curLi)) return 0;
      const curLn = getLine(curLi);
      const curLen = curLn.length;
      while (tCi < curLen) {
        const ch = curLn[tCi];
        if (ch === '\\' && tCi + 1 < curLen) {
          tCi += 2;
          continue;
        }
        if (opener === '(' && ch === '(') return 0;
        if (ch === closer) {
          tCi += 1;
          if (!isBlankText(curLn.slice(tCi))) return 0;
          return curLi + 1;
        }
        tCi += 1;
      }
      curLi += 1;
      tCi = 0;
    }
    return 0;
  }

  const wsStart = ci;
  while (ci < ln.length && (ln[ci] === ' ' || ln[ci] === '\t')) ci += 1;
  if (ci < ln.length) {
    if (ci === wsStart) return 0;
    const titleEnd = parseTitle(li, ci);
    if (titleEnd === 0) return 0;
    return titleEnd - startIdx;
  }

  const baseConsumed = (destLineIdx + 1) - startIdx;
  const nextLi = destLineIdx + 1;
  if (lineOk(nextLi)) {
    const nextLn = getLine(nextLi);
    let nci = 0;
    while (nci < nextLn.length && (nextLn[nci] === ' ' || nextLn[nci] === '\t')) nci += 1;
    if (nci < nextLn.length && (nextLn[nci] === '"' || nextLn[nci] === "'" || nextLn[nci] === '(')) {
      const titleEnd = parseTitle(nextLi, nci);
      if (titleEnd > 0) return titleEnd - startIdx;
    }
  }
  return baseConsumed;
}

function listItemBody(line, startCol, mList) {
  const [leadCols] = leadingColumns(mList[1], startCol);
  const markerEndCol = startCol + leadCols + mList[2].length;
  const after = line.slice(mList[1].length + mList[2].length);
  const [wsCols, wsIdx] = leadingColumns(after, markerEndCol);
  const rest = after.slice(wsIdx);
  if (rest === '') return ['', markerEndCol + 1];
  if (wsCols >= 5) return [' '.repeat(wsCols - 1) + rest, markerEndCol + 1];
  return [rest, markerEndCol + Math.max(wsCols, 1)];
}

function nestedLineOpensOrContinuesPara(text, startCol, prevInPara) {
  if (isBlankText(text)) return false;
  const [cols, idx] = leadingColumns(text, startCol);
  if (!prevInPara && cols >= 4) return false;
  if (cols <= 3) {
    const norm = ' '.repeat(cols) + text.slice(idx);
    const mF = FENCE_OPEN_RE.exec(norm);
    if (mF && !(mF[1][0] === '`' && mF[2].includes('`'))) return false;
    if (htmlBlockEndKind(norm, !prevInPara) !== null) return false;
    if (ATX_HEADING_RE.test(norm) || THEMATIC_BREAK_RE.test(norm)) return false;
    if (prevInPara && SETEXT_UNDERLINE_RE.test(norm)) return false;
    const [innerBq, innerCol] = stripSingleBqPrefix(text, startCol);
    if (innerBq !== null) {
      return nestedLineOpensOrContinuesPara(innerBq, innerCol, false);
    }
    const mList = LIST_ITEM_RE.exec(norm);
    if (mList) {
      if (!prevInPara || canListInterruptParagraph(mList, norm)) {
        const [body, bodyCol] = listItemBody(norm, startCol, mList);
        return nestedLineOpensOrContinuesPara(body, bodyCol, false);
      }
      return true;
    }
  }
  return true;
}

function stripExactBqLayers(text, startCol, depth) {
  let cur = text;
  let col = startCol;
  for (let i = 0; i < depth; i += 1) {
    const [nxt, nxtCol] = stripSingleBqPrefix(cur, col);
    if (nxt === null) return [null, startCol];
    cur = nxt;
    col = nxtCol;
  }
  return [cur, col];
}

function tryParseInlineLinkTail(s, pos, unclosedTitle) {
  const n = s.length;
  let p = pos;
  while (p < n && (s[p] === ' ' || s[p] === '\t' || s[p] === '\n')) p += 1;
  if (p >= n) return -1;
  if (s[p] === ')') return p;

  if (s[p] === '<') {
    p += 1;
    let closed = false;
    while (p < n) {
      const ch = s[p];
      if (ch === '\\' && p + 1 < n && s[p + 1] !== '\n') {
        p += 2;
        continue;
      }
      if (ch === '<' || ch === '\n') return -1;
      if (ch === '>') {
        closed = true;
        p += 1;
        break;
      }
      p += 1;
    }
    if (!closed) return -1;
  } else {
    const destStart = p;
    let parenDepth = 0;
    while (p < n) {
      const ch = s[p];
      const oc = ch.charCodeAt(0);
      if (oc <= 0x20 || oc === 0x7f) break;
      if (ch === '\\' && p + 1 < n) {
        p += 2;
        continue;
      }
      if (ch === '(') {
        parenDepth += 1;
        if (parenDepth > 32) return -1;
      } else if (ch === ')') {
        if (parenDepth === 0) break;
        parenDepth -= 1;
      }
      p += 1;
    }
    if (p === destStart || parenDepth !== 0) return -1;
  }

  const wsStart = p;
  while (p < n && (s[p] === ' ' || s[p] === '\t' || s[p] === '\n')) p += 1;
  if (p >= n) return -1;
  if (s[p] === ')') return p;
  if (p === wsStart || (s[p] !== '"' && s[p] !== "'" && s[p] !== '(')) return -1;

  const opener = s[p];
  const closer = opener === '(' ? ')' : opener;
  const failFloor = unclosedTitle[closer];
  if (failFloor !== undefined && p >= failFloor) return -1;

  const titleStart = p;
  p += 1;
  let closedTitle = false;
  while (p < n) {
    const ch = s[p];
    if (ch === '\\' && p + 1 < n) {
      p += 2;
      continue;
    }
    if (opener === '(' && ch === '(') return -1;
    if (ch === closer) {
      closedTitle = true;
      p += 1;
      break;
    }
    p += 1;
  }
  if (!closedTitle) {
    unclosedTitle[closer] = titleStart;
    return -1;
  }
  while (p < n && (s[p] === ' ' || s[p] === '\t' || s[p] === '\n')) p += 1;
  if (p < n && s[p] === ')') return p;
  return -1;
}

function commonmarkProtectedInlineRanges(paraText) {
  const ranges = [];
  const n = paraText.length;
  const tickRuns = new Map();
  const tickCursor = new Map();
  if (paraText.includes('`')) {
    let k = 0;
    while (k < n) {
      if (paraText[k] === '`') {
        let r = 1;
        while (k + r < n && paraText[k + r] === '`') r += 1;
        let arr = tickRuns.get(r);
        if (!arr) {
          arr = [];
          tickRuns.set(r, arr);
        }
        arr.push(k);
        k += r;
      } else {
        k += 1;
      }
    }
  }
  const unclosedTitle = {};
  let openBrackets = 0;
  let i = 0;
  while (i < n) {
    const ch = paraText[i];
    if (ch === '\\' && i + 1 < n) {
      i += 2;
      continue;
    }
    if (ch === '`') {
      let ticks = 1;
      while (i + ticks < n && paraText[i + ticks] === '`') ticks += 1;
      const positions = tickRuns.get(ticks) || [];
      let cur = tickCursor.get(ticks) || 0;
      while (cur < positions.length && positions[cur] <= i) cur += 1;
      tickCursor.set(ticks, cur);
      if (cur < positions.length) {
        const closePos = positions[cur];
        ranges.push([i, closePos + ticks]);
        i = closePos + ticks;
      } else {
        i += ticks;
      }
      continue;
    }
    if (ch === '[') {
      openBrackets += 1;
      i += 1;
      continue;
    }
    if (ch === ']') {
      if (openBrackets > 0) {
        if (i + 1 < n && paraText[i + 1] === '(') {
          const closeParen = tryParseInlineLinkTail(paraText, i + 2, unclosedTitle);
          if (closeParen >= 0) {
            ranges.push([i + 1, closeParen + 1]);
            openBrackets -= 1;
            i = closeParen + 1;
            continue;
          }
        }
        openBrackets -= 1;
      }
      i += 1;
      continue;
    }
    i += 1;
  }
  return ranges;
}

function commentInCodeSpan(lineOffset, innerText, spanRanges) {
  if (!spanRanges || spanRanges.length === 0) return false;
  MARKER_COMMENT_RE.lastIndex = 0;
  let lastMatch = null;
  let m;
  while ((m = MARKER_COMMENT_RE.exec(innerText)) !== null) {
    lastMatch = m;
  }
  if (!lastMatch) return false;
  const absPos = lineOffset + lastMatch.index;
  for (let i = 0; i < spanRanges.length; i += 1) {
    const [lo, hi] = spanRanges[i];
    if (absPos >= lo && absPos < hi) return true;
  }
  return false;
}

export function iterMarkdownRecords(content) {
  const rawLines = splitMdLines(content);
  const strippedLines = rawLines.map((rl, idxS) => {
    let sn = stripTrailingNewlines(rl);
    if (idxS === 0 && sn.startsWith('\ufeff')) {
      sn = sn.slice(1);
    }
    return sn;
  });

  let inFence = false;
  let fenceChar = '';
  let fenceLen = 0;
  let fenceListIndent = null;
  let inIndented = false;
  let htmlKind = null;
  let htmlListIndent = null;
  let inParagraph = false;
  let skipRefDefLines = 0;
  const listIndents = [];
  let listInPara = false;

  let bqFenceChar = '';
  let bqFenceLen = 0;
  let bqFenceListIndent = null;
  let bqHtmlKind = null;
  let bqHtmlListIndent = null;
  let bqInParagraph = false;
  let bqInNestedPara = false;
  let bqInIndented = false;
  let bqListIndents = [];
  let bqSkipRefDefLines = 0;
  let bqNestedFenceChar = '';
  let bqNestedFenceLen = 0;
  let bqNestedHtmlKind = null;
  let bqNestedDepth = 0;

  function resetBqNestedBlocks() {
    bqNestedFenceChar = '';
    bqNestedFenceLen = 0;
    bqNestedHtmlKind = null;
    bqNestedDepth = 0;
  }

  const records = [];

  for (let lineIdx = 0; lineIdx < rawLines.length; lineIdx += 1) {
    const rawLine = rawLines[lineIdx];
    const strippedNl = strippedLines[lineIdx];
    const isBlank = isBlankText(strippedNl);
    const [cols, idx] = leadingColumns(strippedNl, 0);

    if (skipRefDefLines > 0) {
      skipRefDefLines -= 1;
      inParagraph = false;
      records.push([rawLine, false, null, false, false]);
      continue;
    }
    if (bqSkipRefDefLines > 0) {
      bqSkipRefDefLines -= 1;
      bqInParagraph = false;
      bqInNestedPara = false;
      inParagraph = false;
      records.push([rawLine, false, null, false, false]);
      continue;
    }

    if (inFence) {
      if (fenceListIndent !== null && !isBlank && cols < fenceListIndent) {
        inFence = false;
        fenceChar = '';
        fenceLen = 0;
        fenceListIndent = null;
      } else {
        records.push([rawLine, false, null, false, false]);
        const maxCloseCol = fenceListIndent === null ? 3 : fenceListIndent + 3;
        if (!isBlank && cols <= maxCloseCol) {
          const mClose = FENCE_CLOSE_RE.exec(strippedNl.slice(idx));
          if (mClose && mClose[1][0] === fenceChar && mClose[1].length >= fenceLen) {
            inFence = false;
            fenceChar = '';
            fenceLen = 0;
            fenceListIndent = null;
          }
        }
        inParagraph = false;
        continue;
      }
    }

    if (htmlKind !== null) {
      if (htmlListIndent !== null && !isBlank && cols < htmlListIndent) {
        htmlKind = null;
        htmlListIndent = null;
      } else {
        if (htmlKind === 'blank' && isBlank) {
          htmlKind = null;
          htmlListIndent = null;
          inParagraph = false;
          records.push([rawLine, false, null, false, false]);
          continue;
        }
        records.push([rawLine, false, null, false, false]);
        if (htmlBlockCloses(htmlKind, strippedNl)) {
          htmlKind = null;
          htmlListIndent = null;
        }
        inParagraph = false;
        continue;
      }
    }

    const [bqInner, bqCol] = stripSingleBqPrefix(strippedNl, 0);
    if (bqInner === null) {
      if ((bqInParagraph || bqInNestedPara) && !lineInterruptsBqParagraph(strippedNl, cols)) {
        if (bqInNestedPara) {
          records.push([rawLine, false, null, false, false]);
        } else {
          records.push([rawLine, false, strippedNl, true, false]);
        }
        inParagraph = false;
        continue;
      }
      bqFenceChar = '';
      bqFenceLen = 0;
      bqFenceListIndent = null;
      bqHtmlKind = null;
      bqHtmlListIndent = null;
      bqInParagraph = false;
      bqInNestedPara = false;
      bqInIndented = false;
      bqListIndents = [];
      resetBqNestedBlocks();
    }

    if (isBlank) {
      records.push([rawLine, false, null, false, false]);
      inParagraph = false;
      listInPara = false;
      continue;
    }

    if (listIndents.length > 0) {
      if (cols < listIndents[listIndents.length - 1] && listInPara && bqInner === null && !lineInterruptsBqParagraph(strippedNl, cols)) {
        records.push([rawLine, false, null, false, false]);
        inParagraph = false;
        continue;
      }
      while (listIndents.length > 0 && cols < listIndents[listIndents.length - 1]) {
        listIndents.pop();
      }
      if (listIndents.length === 0) {
        listInPara = false;
      } else {
        const relCols = cols - listIndents[listIndents.length - 1];
        const relText = ' '.repeat(relCols) + strippedNl.slice(idx);
        let openedFence = false;
        let openedHtml = false;
        if (relCols <= 3) {
          const mLf = FENCE_OPEN_RE.exec(relText);
          if (mLf && !(mLf[1][0] === '`' && mLf[2].includes('`'))) {
            inFence = true;
            fenceChar = mLf[1][0];
            fenceLen = mLf[1].length;
            fenceListIndent = listIndents[listIndents.length - 1];
            openedFence = true;
          } else {
            const hkL = htmlBlockEndKind(relText, !listInPara);
            if (hkL !== null) {
              if (!htmlBlockCloses(hkL, relText)) {
                htmlKind = hkL;
                htmlListIndent = listIndents[listIndents.length - 1];
              }
              openedHtml = true;
            }
          }
        }
        listInPara = (openedFence || openedHtml) ? false : nestedLineOpensOrContinuesPara(relText, 0, listInPara);
        records.push([rawLine, false, null, false, false]);
        inParagraph = false;
        continue;
      }
    }

    if (inIndented) {
      if (cols >= 4) {
        records.push([rawLine, false, null, false, false]);
        inParagraph = false;
        continue;
      }
      inIndented = false;
    }

    if (!inParagraph && cols >= 4) {
      inIndented = true;
      inParagraph = false;
      records.push([rawLine, false, null, false, false]);
      continue;
    }

    if (cols <= 3) {
      const mOpen = FENCE_OPEN_RE.exec(strippedNl);
      if (mOpen) {
        const marker = mOpen[1];
        const info = mOpen[2];
        if (!(marker[0] === '`' && info.includes('`'))) {
          inFence = true;
          fenceChar = marker[0];
          fenceLen = marker.length;
          fenceListIndent = null;
          inParagraph = false;
          records.push([rawLine, false, null, false, false]);
          continue;
        }
      }
    }

    const hk = htmlBlockEndKind(strippedNl, !inParagraph);
    if (hk !== null) {
      records.push([rawLine, false, null, false, false]);
      if (!htmlBlockCloses(hk, strippedNl)) {
        htmlKind = hk;
        htmlListIndent = null;
      }
      inParagraph = false;
      continue;
    }

    if (cols <= 3 && (
      ATX_HEADING_RE.test(strippedNl) ||
      (inParagraph && SETEXT_UNDERLINE_RE.test(strippedNl)) ||
      THEMATIC_BREAK_RE.test(strippedNl)
    )) {
      inParagraph = false;
      records.push([rawLine, false, null, false, false]);
      continue;
    }

    if (!inParagraph && cols <= 3 && idx < strippedNl.length && strippedNl[idx] === '[') {
      const refLines = parseLinkRefDef(strippedLines, lineIdx, false);
      if (refLines > 0) {
        skipRefDefLines = refLines - 1;
        inParagraph = false;
        records.push([rawLine, false, null, false, false]);
        continue;
      }
    }

    const mList = LIST_ITEM_RE.exec(strippedNl);
    if (mList && (!inParagraph || canListInterruptParagraph(mList, strippedNl))) {
      listIndents.push(listItemContentIndent(strippedNl, 0, mList));
      const [body, bodyCol] = listItemBody(strippedNl, 0, mList);
      const [bColsL] = leadingColumns(body, bodyCol);
      let openedFence = false;
      let openedHtml = false;
      if (bColsL <= 3) {
        const mLf = FENCE_OPEN_RE.exec(body);
        if (mLf && !(mLf[1][0] === '`' && mLf[2].includes('`'))) {
          inFence = true;
          fenceChar = mLf[1][0];
          fenceLen = mLf[1].length;
          fenceListIndent = listIndents[listIndents.length - 1];
          openedFence = true;
        } else {
          const hkL = htmlBlockEndKind(body, true);
          if (hkL !== null) {
            if (!htmlBlockCloses(hkL, body)) {
              htmlKind = hkL;
              htmlListIndent = listIndents[listIndents.length - 1];
            }
            openedHtml = true;
          }
        }
      }
      listInPara = (openedFence || openedHtml) ? false : nestedLineOpensOrContinuesPara(body, bodyCol, false);
      records.push([rawLine, false, null, false, false]);
      inParagraph = false;
      continue;
    }

    if (bqInner !== null) {
      inParagraph = false;
      const innerBlank = isBlankText(bqInner);
      const [bcols, bidx] = leadingColumns(bqInner, bqCol);

      if (bqFenceChar) {
        resetBqNestedBlocks();
        if (bqFenceListIndent !== null && !innerBlank && bcols < bqFenceListIndent) {
          bqFenceChar = '';
          bqFenceLen = 0;
          bqFenceListIndent = null;
        } else {
          records.push([rawLine, false, null, false, false]);
          const bmaxClose = bqFenceListIndent === null ? 3 : bqFenceListIndent + 3;
          if (!innerBlank && bcols <= bmaxClose) {
            const mBc = FENCE_CLOSE_RE.exec(bqInner.slice(bidx));
            if (mBc && mBc[1][0] === bqFenceChar && mBc[1].length >= bqFenceLen) {
              bqFenceChar = '';
              bqFenceLen = 0;
              bqFenceListIndent = null;
            }
          }
          bqInParagraph = false;
          bqInNestedPara = false;
          continue;
        }
      }

      if (bqHtmlKind !== null) {
        resetBqNestedBlocks();
        if (bqHtmlListIndent !== null && !innerBlank && bcols < bqHtmlListIndent) {
          bqHtmlKind = null;
          bqHtmlListIndent = null;
        } else {
          if (bqHtmlKind === 'blank' && innerBlank) {
            bqHtmlKind = null;
            bqHtmlListIndent = null;
          } else if (htmlBlockCloses(bqHtmlKind, bqInner)) {
            bqHtmlKind = null;
            bqHtmlListIndent = null;
          }
          records.push([rawLine, false, null, false, false]);
          bqInParagraph = false;
          bqInNestedPara = false;
          continue;
        }
      }

      if (innerBlank) {
        records.push([rawLine, false, null, false, false]);
        bqInParagraph = false;
        bqInNestedPara = false;
        resetBqNestedBlocks();
        continue;
      }

      if (bqListIndents.length > 0) {
        while (bqListIndents.length > 0 && bcols < bqListIndents[bqListIndents.length - 1]) {
          bqListIndents.pop();
        }
        if (bqListIndents.length > 0) {
          resetBqNestedBlocks();
          const relBcols = bcols - bqListIndents[bqListIndents.length - 1];
          const relBtext = ' '.repeat(relBcols) + bqInner.slice(bidx);
          let openedBfence = false;
          let openedBhtml = false;
          if (relBcols <= 3) {
            const mBlf = FENCE_OPEN_RE.exec(relBtext);
            if (mBlf && !(mBlf[1][0] === '`' && mBlf[2].includes('`'))) {
              bqFenceChar = mBlf[1][0];
              bqFenceLen = mBlf[1].length;
              bqFenceListIndent = bqListIndents[bqListIndents.length - 1];
              openedBfence = true;
            } else {
              const bhkL = htmlBlockEndKind(relBtext, !bqInNestedPara);
              if (bhkL !== null) {
                if (!htmlBlockCloses(bhkL, relBtext)) {
                  bqHtmlKind = bhkL;
                  bqHtmlListIndent = bqListIndents[bqListIndents.length - 1];
                }
                openedBhtml = true;
              }
            }
          }
          records.push([rawLine, false, null, false, false]);
          bqInParagraph = false;
          bqInNestedPara = (openedBfence || openedBhtml) ? false : nestedLineOpensOrContinuesPara(relBtext, 0, bqInNestedPara);
          continue;
        }
      }

      if (bqInIndented) {
        resetBqNestedBlocks();
        if (bcols >= 4) {
          records.push([rawLine, false, null, false, false]);
          bqInParagraph = false;
          bqInNestedPara = false;
          continue;
        }
        bqInIndented = false;
      }
      if (!bqInParagraph && !bqInNestedPara && bcols >= 4) {
        resetBqNestedBlocks();
        bqInIndented = true;
        records.push([rawLine, false, null, false, false]);
        bqInParagraph = false;
        bqInNestedPara = false;
        continue;
      }

      if (bcols <= 3) {
        const mBo = FENCE_OPEN_RE.exec(bqInner.slice(bidx));
        if (mBo && !(mBo[1][0] === '`' && mBo[2].includes('`'))) {
          resetBqNestedBlocks();
          bqFenceChar = mBo[1][0];
          bqFenceLen = mBo[1].length;
          bqFenceListIndent = null;
          records.push([rawLine, false, null, false, false]);
          bqInParagraph = false;
          bqInNestedPara = false;
          continue;
        }
        const bhk = htmlBlockEndKind(bqInner, !bqInParagraph && !bqInNestedPara);
        if (bhk !== null) {
          resetBqNestedBlocks();
          if (!htmlBlockCloses(bhk, bqInner)) {
            bqHtmlKind = bhk;
            bqHtmlListIndent = null;
          }
          records.push([rawLine, false, null, false, false]);
          bqInParagraph = false;
          bqInNestedPara = false;
          continue;
        }
        if (
          ATX_HEADING_RE.test(bqInner) ||
          (bqInParagraph && SETEXT_UNDERLINE_RE.test(bqInner)) ||
          THEMATIC_BREAK_RE.test(bqInner)
        ) {
          resetBqNestedBlocks();
          records.push([rawLine, false, null, false, false]);
          bqInParagraph = false;
          bqInNestedPara = false;
          continue;
        }
        if (!bqInParagraph && !bqInNestedPara && bidx < bqInner.length && bqInner[bidx] === '[') {
          const bqRefLines = parseLinkRefDef(strippedLines, lineIdx, true);
          if (bqRefLines > 0) {
            resetBqNestedBlocks();
            bqSkipRefDefLines = bqRefLines - 1;
            bqInParagraph = false;
            bqInNestedPara = false;
            records.push([rawLine, false, null, false, false]);
            continue;
          }
        }
        const mBlist = LIST_ITEM_RE.exec(bqInner);
        if (mBlist && ((!bqInParagraph && !bqInNestedPara) || canListInterruptParagraph(mBlist, bqInner))) {
          resetBqNestedBlocks();
          bqListIndents.push(listItemContentIndent(bqInner, bqCol, mBlist));
          const [bBody, bBodyCol] = listItemBody(bqInner, bqCol, mBlist);
          const [bBodyCols] = leadingColumns(bBody, bBodyCol);
          let openedBfence = false;
          let openedBhtml = false;
          if (bBodyCols <= 3) {
            const mBlf = FENCE_OPEN_RE.exec(bBody);
            if (mBlf && !(mBlf[1][0] === '`' && mBlf[2].includes('`'))) {
              bqFenceChar = mBlf[1][0];
              bqFenceLen = mBlf[1].length;
              bqFenceListIndent = bqListIndents[bqListIndents.length - 1];
              openedBfence = true;
            } else {
              const bhkL = htmlBlockEndKind(bBody, true);
              if (bhkL !== null) {
                if (!htmlBlockCloses(bhkL, bBody)) {
                  bqHtmlKind = bhkL;
                  bqHtmlListIndent = bqListIndents[bqListIndents.length - 1];
                }
                openedBhtml = true;
              }
            }
          }
          records.push([rawLine, false, null, false, false]);
          bqInParagraph = false;
          bqInNestedPara = (openedBfence || openedBhtml) ? false : nestedLineOpensOrContinuesPara(bBody, bBodyCol, false);
          continue;
        }
      }

      const [nestedInner, nestedCol] = stripSingleBqPrefix(bqInner, bqCol);
      if (nestedInner !== null) {
        if (bqNestedFenceChar || bqNestedHtmlKind !== null) {
          const [exactInner, exactCol] = stripExactBqLayers(bqInner, bqCol, bqNestedDepth);
          if (exactInner !== null) {
            const [ecols, eidx] = leadingColumns(exactInner, exactCol);
            const eBlank = isBlankText(exactInner);
            if (bqNestedFenceChar) {
              if (!eBlank && ecols <= 3) {
                const mNc = FENCE_CLOSE_RE.exec(exactInner.slice(eidx));
                if (mNc && mNc[1][0] === bqNestedFenceChar && mNc[1].length >= bqNestedFenceLen) {
                  bqNestedFenceChar = '';
                  bqNestedFenceLen = 0;
                }
              }
            } else if (bqNestedHtmlKind !== null) {
              if (bqNestedHtmlKind === 'blank' && eBlank) {
                bqNestedHtmlKind = null;
              } else if (htmlBlockCloses(bqNestedHtmlKind, exactInner)) {
                bqNestedHtmlKind = null;
              }
            }
            bqInNestedPara = false;
            bqInParagraph = false;
            records.push([rawLine, false, null, false, false]);
            continue;
          }
          resetBqNestedBlocks();
        }

        let deepInner = nestedInner;
        let deepCol = nestedCol;
        let depth = 1;
        while (true) {
          const [nxt, nxtCol] = stripSingleBqPrefix(deepInner, deepCol);
          if (nxt === null) break;
          deepInner = nxt;
          deepCol = nxtCol;
          depth += 1;
        }

        const prevSamePara = bqInNestedPara && (depth <= bqNestedDepth);
        const [dcols, didx] = leadingColumns(deepInner, deepCol);
        const dBlank = isBlankText(deepInner);
        if (dBlank) {
          bqInNestedPara = false;
        } else if (dcols <= 3) {
          const dnorm = ' '.repeat(dcols) + deepInner.slice(didx);
          const mNf = FENCE_OPEN_RE.exec(dnorm);
          if (mNf && !(mNf[1][0] === '`' && mNf[2].includes('`'))) {
            bqNestedFenceChar = mNf[1][0];
            bqNestedFenceLen = mNf[1].length;
            bqInNestedPara = false;
          } else {
            const nhk = htmlBlockEndKind(dnorm, !prevSamePara);
            if (nhk !== null) {
              if (!htmlBlockCloses(nhk, dnorm)) {
                bqNestedHtmlKind = nhk;
              }
              bqInNestedPara = false;
            } else {
              bqInNestedPara = nestedLineOpensOrContinuesPara(deepInner, deepCol, prevSamePara);
            }
          }
        } else {
          bqInNestedPara = nestedLineOpensOrContinuesPara(deepInner, deepCol, prevSamePara);
        }
        bqNestedDepth = depth;
        bqInParagraph = false;
        records.push([rawLine, false, null, false, false]);
        continue;
      }

      resetBqNestedBlocks();
      if (bqInNestedPara) {
        records.push([rawLine, false, null, false, true]);
        continue;
      }

      bqInParagraph = true;
      records.push([rawLine, bcols <= 3, bqInner, true, false]);
      continue;
    }

    inParagraph = true;
    records.push([rawLine, false, strippedNl, false, false]);
  }

  const nRec = records.length;
  let idxRec = 0;
  while (idxRec < nRec) {
    if (!records[idxRec][3]) {
      idxRec += 1;
      continue;
    }
    const startRec = idxRec;
    while (idxRec < nRec && records[idxRec][3]) idxRec += 1;
    let endRec = idxRec;
    while (endRec < nRec && !records[endRec][3] && records[endRec][2] !== null) endRec += 1;
    const chunks = [];
    for (let k = startRec; k < endRec; k += 1) chunks.push(records[k][2]);
    const joined = chunks.join('\n');
    if (joined.includes('`') || joined.includes('](')) {
      const spanRanges = commonmarkProtectedInlineRanges(joined);
      if (spanRanges.length > 0) {
        let offset = 0;
        for (let k = startRec; k < endRec; k += 1) {
          const chunk = records[k][2];
          if (records[k][1] && commentInCodeSpan(offset, chunk, spanRanges)) {
            records[k][1] = false;
          }
          offset += chunk.length + 1;
        }
      }
    }
    idxRec = endRec;
  }

  return records.map((rec) => [rec[0], rec[1], rec[4]]);
}

export function iterMarkdownLines(content) {
  return iterMarkdownRecords(content).map(([rawLine, eligible]) => [rawLine, eligible]);
}

export function countMarkers(content) {
  if (typeof content !== 'string') return 0;
  let total = 0;
  let inWrapLegacySameBq = false;
  for (const [line, eligible, lazyNested] of iterMarkdownRecords(content)) {
    if (inWrapLegacySameBq && stripSingleBqPrefix(stripTrailingNewlines(line), 0)[0] === null) {
      inWrapLegacySameBq = false;
    }
    if (eligible || (inWrapLegacySameBq && lazyNested)) {
      const m = matchMarkerLine(line);
      if (m) {
        const isLegacy = m.groups.kind === undefined;
        const kind = m.groups.kind || m.groups.legacy || 'classic';
        if (!eligible && !(isLegacy && kind === 'wrap-end')) {
          continue;
        }
        if (kind === 'wrap-start') {
          inWrapLegacySameBq = isLegacy;
        } else if (kind === 'wrap-end') {
          inWrapLegacySameBq = false;
        }
        total += 1;
      }
    }
  }
  return total;
}

export function stripMarkers(content) {
  if (typeof content !== 'string') return { content: '', removed: 0 };
  const items = iterMarkdownRecords(content);
  const nItems = items.length;

  function isNonwrapDrop(idxPos) {
    if (idxPos >= nItems) return false;
    const [raw, elig] = items[idxPos];
    if (!elig) return false;
    const mm = matchMarkerLine(raw);
    if (!mm) return false;
    const k = mm.groups.kind || mm.groups.legacy || 'classic';
    return k !== 'wrap-start' && k !== 'wrap-end';
  }

  const kept = [];
  let removed = 0;
  let inWrap = false;
  let inWrapLegacy = false;
  let inWrapLegacySameBq = false;
  let eatNextBlank = false;
  let prevRemovedDrop = false;
  let pendingBqSep = false;
  let pendingBlankSep = false;

  for (let i = 0; i < nItems; i += 1) {
    const [line, eligible, lazyNested] = items[i];
    if (inWrapLegacySameBq && stripSingleBqPrefix(stripTrailingNewlines(line), 0)[0] === null) {
      inWrapLegacySameBq = false;
    }
    if (eatNextBlank) {
      eatNextBlank = false;
      if (isBareNewline(line) || isBareBqSep(line)) {
        continue;
      }
    }
    if (eligible || (inWrapLegacySameBq && lazyNested)) {
      let m = matchMarkerLine(line);
      let isLegacy = false;
      let kind = 'classic';
      if (m) {
        isLegacy = m.groups.kind === undefined;
        kind = m.groups.kind || m.groups.legacy || 'classic';
        if (!eligible && !(isLegacy && kind === 'wrap-end')) {
          m = null;
        }
      }
      if (m) {
        const meta = m.groups.meta || '';
        const metaFlags = new Set(meta ? meta.split(',') : []);
        if (kind === 'wrap-start') {
          inWrap = true;
          inWrapLegacy = isLegacy;
          inWrapLegacySameBq = isLegacy;
          eatNextBlank = !isLegacy;
          prevRemovedDrop = false;
          pendingBqSep = false;
          pendingBlankSep = false;
        } else if (kind === 'wrap-end') {
          eatNextBlank = false;
          if (inWrap) {
            if (!inWrapLegacy) {
              if (kept.length > 0 && (isBareNewline(kept[kept.length - 1]) || isBareBqSep(kept[kept.length - 1]))) {
                kept.pop();
              }
            } else if (
              endsWithAnyNewline(line) &&
              i + 1 === nItems - 1 &&
              isBareNewline(items[i + 1][0])
            ) {
              eatNextBlank = true;
            }
            if (!endsWithAnyNewline(line) && kept.length > 0 && kept[kept.length - 1].endsWith('\n')) {
              const lastIdx = kept.length - 1;
              kept[lastIdx] = kept[lastIdx].slice(0, -1);
              if (kept[lastIdx] === '') {
                kept.pop();
              }
            }
          }
          inWrap = false;
          inWrapLegacy = false;
          inWrapLegacySameBq = false;
          prevRemovedDrop = false;
          pendingBqSep = false;
          pendingBlankSep = false;
        } else {
          if (pendingBqSep && kept.length > 0) {
            kept.pop();
          } else if (pendingBlankSep && kept.length > 0) {
            kept.pop();
          } else if (metaFlags.has('noeol') && kept.length >= 2 && isBareNewline(kept[kept.length - 1])) {
            kept.pop();
            const lastIdx = kept.length - 1;
            if (kept[lastIdx].endsWith('\r\n')) {
              kept[lastIdx] = kept[lastIdx].slice(0, -2);
            } else if (endsWithAnyNewline(kept[lastIdx])) {
              kept[lastIdx] = kept[lastIdx].slice(0, -1);
            }
          } else if (metaFlags.has('sep1') && kept.length > 0 && isBareNewline(kept[kept.length - 1])) {
            kept.pop();
          } else if (metaFlags.has('keepblank')) {
            // Keep pre-existing trailing blank line intact.
          } else if (
            !isLegacy &&
            kept.length >= 2 &&
            isBareNewline(kept[kept.length - 1]) &&
            !isBareNewline(kept[kept.length - 2])
          ) {
            const nextIsEof = i + 1 >= nItems;
            const nextIsBlank = !nextIsEof && isBareNewline(items[i + 1][0]);
            const nextIsDrop = isNonwrapDrop(i + 1) || (
              i + 2 < nItems && isBareBqSep(items[i + 1][0]) && isNonwrapDrop(i + 2)
            );
            if (prevRemovedDrop || nextIsEof || nextIsBlank || nextIsDrop) {
              kept.pop();
            }
          }
          prevRemovedDrop = true;
          pendingBqSep = false;
          pendingBlankSep = false;
        }
        removed += 1;
        continue;
      }
    }
    if (prevRemovedDrop && !pendingBqSep && !pendingBlankSep && isBareBqSep(line)) {
      pendingBqSep = true;
    } else if (prevRemovedDrop && !pendingBqSep && !pendingBlankSep && isBareNewline(line) && isNonwrapDrop(i + 1)) {
      pendingBlankSep = true;
    } else {
      prevRemovedDrop = false;
      pendingBqSep = false;
      pendingBlankSep = false;
    }
    kept.push(line);
  }
  return { content: kept.join(''), removed };
}

export function effectiveCaption(captionRaw, locale) {
  let raw = String(captionRaw || '');
  raw = raw.replace(/[\r\n\u2028\u2029]+/g, ' ');
  while (raw.includes('<!--') || raw.includes('-->')) {
    raw = raw.replaceAll('-->', '').replaceAll('<!--', '');
  }
  raw = raw.replaceAll('`', "'");
  raw = raw.replace(EMOJI_RE, '');
  while (true) {
    const trimmed = raw.trim().replace(/\\+$/, '').trim();
    if (trimmed === raw) break;
    raw = trimmed;
  }
  if (raw && !(isEn(locale) && CHINESE_RE.test(raw))) {
    const probe = `${raw}${DROP_SIGNATURE}`;
    const isOpener = (
      stripSingleBqPrefix(raw, 0)[0] !== null ||
      stripSingleBqPrefix(probe, 0)[0] !== null ||
      ATX_HEADING_RE.test(raw) ||
      ATX_HEADING_RE.test(probe) ||
      THEMATIC_BREAK_RE.test(raw) ||
      THEMATIC_BREAK_RE.test(probe) ||
      SETEXT_UNDERLINE_RE.test(raw) ||
      SETEXT_UNDERLINE_RE.test(probe) ||
      FENCE_OPEN_RE.test(raw) ||
      FENCE_OPEN_RE.test(probe) ||
      LIST_ITEM_RE.test(raw) ||
      LIST_ITEM_RE.test(probe) ||
      htmlBlockEndKind(raw, true) !== null ||
      htmlBlockEndKind(probe, true) !== null
    );
    const cand = isOpener ? `· ${raw}` : raw;
    const probes = [
      `> ${cand}${DROP_SIGNATURE}`,
      `> ${cand} #1${DROP_SIGNATURE}`,
      `> --- ${cand} ---${DROP_SIGNATURE}`,
      `> · ${cand} ·${DROP_SIGNATURE}`,
      `> prev\n> ${cand}${DROP_SIGNATURE}`,
    ];
    if (probes.every((p) => countMarkers(p) === 1)) {
      return cand;
    }
  }
  return getStrings(locale).default_caption;
}

export function buildDropBlock({ caption, style, shape, locale, wrappedText = '', firstMeta = '' }) {
  const cap = effectiveCaption(caption, locale);
  const repeat = { shy: 1, normal: 1, wild: 3 }[style] || 1;
  if (wrappedText) {
    if (wrappedText.endsWith('\r\n')) {
      return `> ${cap}${dropSig('wrap-start')}\n\n${wrappedText}\n> ···${dropSig('wrap-end')}\r\n`;
    }
    if (wrappedText.endsWith('\n')) {
      return `> ${cap}${dropSig('wrap-start')}\n\n${wrappedText}\n> ···${dropSig('wrap-end')}\n`;
    }
    if (wrappedText.endsWith('\r')) {
      return `> ${cap}${dropSig('wrap-start')}\n\n${wrappedText}\r> ···${dropSig('wrap-end')}\r`;
    }
    return `> ${cap}${dropSig('wrap-start')}\n\n${wrappedText}\n\n> ···${dropSig('wrap-end')}`;
  }
  const lines = [];
  for (let idx = 0; idx < repeat; idx += 1) {
    const suffix = repeat > 1 ? ` #${idx + 1}` : '';
    const meta = idx === 0 ? firstMeta : '';
    if (shape === 'ribbon') {
      lines.push(`> --- ${cap}${suffix} ---${dropSig('ribbon', meta)}`);
    } else if (shape === 'pellet') {
      lines.push(`> · ${cap}${suffix} ·${dropSig('pellet', meta)}`);
    } else {
      lines.push(`> ${cap}${suffix}${dropSig('classic', meta)}`);
    }
  }
  return lines.join('\n\n');
}

export function isEditorWrapSafe(text) {
  if (typeof text !== 'string' || !text) return false;
  if (text.includes('\r') || text.startsWith('\n') || text.endsWith('\n')) return false;
  const lines = splitMdLines(text);
  if (lines.length > 0 && (isBareBqSep(lines[0]) || isBareBqSep(lines[lines.length - 1]))) {
    return false;
  }
  let inFence = false;
  let fenceCh = '';
  let fenceLen = 0;
  let htmlKind = null;
  let blankRun = 0;
  let prevWasAnyBq = false;
  let prevParaBqDepth = 0;
  let sawBlankAfterBq = false;

  for (const raw of lines) {
    const s = raw.endsWith('\n') ? raw.slice(0, -1) : raw;
    const isBlank = isBlankText(s);
    const [cols, idx] = leadingColumns(s, 0);
    if (inFence) {
      if (!isBlank && cols <= 3) {
        const mc = FENCE_CLOSE_RE.exec(s.slice(idx));
        if (mc && mc[1][0] === fenceCh && mc[1].length >= fenceLen) {
          inFence = false;
        }
      }
      blankRun = 0;
      prevWasAnyBq = false;
      prevParaBqDepth = 0;
      sawBlankAfterBq = false;
      continue;
    }
    if (htmlKind !== null) {
      if (htmlKind === 'blank' && isBlank) {
        htmlKind = null;
        blankRun = 1;
        continue;
      }
      if (htmlBlockCloses(htmlKind, s)) {
        htmlKind = null;
      }
      blankRun = 0;
      prevWasAnyBq = false;
      prevParaBqDepth = 0;
      sawBlankAfterBq = false;
      continue;
    }
    if (isBlank) {
      blankRun += 1;
      if (blankRun >= 2) return false;
      if (prevWasAnyBq) sawBlankAfterBq = true;
      continue;
    }
    blankRun = 0;
    let curBqDepth = 0;
    let curRem = s;
    let curCol = 0;
    while (true) {
      const [nxt, nxtCol] = stripSingleBqPrefix(curRem, curCol);
      if (nxt === null) break;
      curBqDepth += 1;
      curRem = nxt;
      curCol = nxtCol;
    }
    if (curBqDepth > 0 && isBlankText(curRem)) {
      if (curBqDepth >= 2) return false;
      prevWasAnyBq = true;
      prevParaBqDepth = 0;
      sawBlankAfterBq = false;
      continue;
    }
    if (prevParaBqDepth > 0 && !sawBlankAfterBq && curBqDepth < prevParaBqDepth) {
      return false;
    }
    if (curBqDepth > 0 && sawBlankAfterBq) {
      return false;
    }
    prevWasAnyBq = curBqDepth > 0;
    prevParaBqDepth = curBqDepth;
    sawBlankAfterBq = false;
    if (cols <= 3) {
      const mo = FENCE_OPEN_RE.exec(s);
      if (mo && !(mo[1][0] === '`' && mo[2].includes('`'))) {
        inFence = true;
        fenceCh = mo[1][0];
        fenceLen = mo[1].length;
        continue;
      }
      const hk = htmlBlockEndKind(s, true);
      if (hk !== null && !htmlBlockCloses(hk, s)) {
        htmlKind = hk;
        continue;
      }
    }
  }
  if (inFence || htmlKind === 'type1' || htmlKind === 'comment' || htmlKind === 'pi' || htmlKind === 'decl' || htmlKind === 'cdata') {
    return false;
  }
  return true;
}
