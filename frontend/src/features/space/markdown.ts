const safeProtocols = new Set(["http:", "https:", "mailto:"]);

export interface MarkdownDocumentPresentation {
  title: string;
  body: string;
}

export function presentMarkdownDocument(content: string, fallbackTitle: string): MarkdownDocumentPresentation {
  const normalized = content.replace(/^\uFEFF/, "");
  const leadingTitle = /^(?:[ \t]*\r?\n)*#[ \t]+(.+?)[ \t]*#*[ \t]*\r?\n(?:[ \t]*\r?\n)*/.exec(normalized);
  if (!leadingTitle) return { title: fallbackTitle, body: normalized };
  return {
    title: leadingTitle[1].trim() || fallbackTitle,
    body: normalized.slice(leadingTitle[0].length),
  };
}

export function safeMarkdownURL(value: string): string {
  if (value.startsWith("#") || value.startsWith("/")) return value;
  try {
    const parsed = new URL(value);
    return safeProtocols.has(parsed.protocol) ? value : "";
  } catch {
    return "";
  }
}
