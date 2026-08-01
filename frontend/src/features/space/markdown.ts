const safeProtocols = new Set(["http:", "https:", "mailto:"]);

export function safeMarkdownURL(value: string): string {
  if (value.startsWith("#") || value.startsWith("/")) return value;
  try {
    const parsed = new URL(value);
    return safeProtocols.has(parsed.protocol) ? value : "";
  } catch {
    return "";
  }
}
