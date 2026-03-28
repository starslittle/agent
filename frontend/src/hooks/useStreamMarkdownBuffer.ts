import { useMemo } from "react";

interface StreamMarkdownBuffer {
  stableMarkdown: string;
  pendingText: string;
  hasUnclosedFence: boolean;
}

function isFenceLine(line: string): boolean {
  return /^\s*```/.test(line);
}

function isTableDivider(line: string): boolean {
  return /^\s*\|?[\s:-]+(\|[\s:-]+)+\|?\s*$/.test(line);
}

function isTableLikeLine(line: string): boolean {
  const pipeCount = (line.match(/\|/g) || []).length;
  if (pipeCount < 2) return false;
  // 至少存在一个非分隔符内容字符，避免把分隔行误判为表头
  return /[^\s|:-]/.test(line);
}

function isTableRow(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return false;
  return (line.match(/\|/g) || []).length >= 2;
}

function splitLinesWithEndings(text: string): string[] {
  if (!text) return [];
  const lines: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === "\n") {
      lines.push(text.slice(start, i + 1));
      start = i + 1;
    }
  }
  if (start < text.length) {
    lines.push(text.slice(start));
  }
  return lines;
}

function computeStableOffset(text: string, streaming: boolean): StreamMarkdownBuffer {
  if (!text) {
    return {
      stableMarkdown: "",
      pendingText: "",
      hasUnclosedFence: false,
    };
  }

  if (!streaming) {
    return {
      stableMarkdown: text,
      pendingText: "",
      hasUnclosedFence: false,
    };
  }

  const lines = splitLinesWithEndings(text);
  let idx = 0;
  let offset = 0;
  let stableOffset = 0;
  let inFence = false;
  let fenceStartOffset = -1;

  while (idx < lines.length) {
    const line = lines[idx];
    const trimmed = line.trim();

    if (isFenceLine(line)) {
      if (!inFence) {
        inFence = true;
        fenceStartOffset = offset;
      } else {
        inFence = false;
        stableOffset = offset + line.length;
      }
      offset += line.length;
      idx += 1;
      continue;
    }

    if (inFence) {
      offset += line.length;
      idx += 1;
      continue;
    }

    // 处理表格：未形成完整 "表头 + 分隔线" 前，暂不提交到稳定区
    if (isTableLikeLine(line)) {
      const next = lines[idx + 1] || "";
      if (!isTableDivider(next)) {
        offset += line.length;
        idx += 1;
        continue;
      }

      let tableOffset = offset + line.length + next.length;
      let j = idx + 2;
      while (j < lines.length && isTableRow(lines[j])) {
        tableOffset += lines[j].length;
        j += 1;
      }
      stableOffset = tableOffset;
      offset = tableOffset;
      idx = j;
      continue;
    }

    // 普通文本可以直接进入稳定区
    if (trimmed || line.includes("\n")) {
      stableOffset = offset + line.length;
    }
    offset += line.length;
    idx += 1;
  }

  // 代码围栏未闭合时，从起始围栏处转入 pending 区
  if (inFence && fenceStartOffset >= 0) {
    stableOffset = Math.min(stableOffset, fenceStartOffset);
  }

  return {
    stableMarkdown: text.slice(0, stableOffset),
    pendingText: text.slice(stableOffset),
    hasUnclosedFence: inFence,
  };
}

export function useStreamMarkdownBuffer(content: string, streaming: boolean): StreamMarkdownBuffer {
  return useMemo(() => computeStableOffset(content, streaming), [content, streaming]);
}

