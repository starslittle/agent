import {
  parseRuntimeCitation,
  type RuntimeCitation,
} from "@/lib/chat-api";

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  title?: string;
  children?: MarkdownNode[];
}

interface CitationRemarkOptions {
  citations: RuntimeCitation[];
  scope: string;
}

export function sortedCitations(
  citations: RuntimeCitation[],
): RuntimeCitation[] {
  return [...citations].sort(
    (left, right) =>
      left.sequence - right.sequence ||
      left.citation_id.localeCompare(right.citation_id),
  );
}

export function parseStoredCitations(
  metadata?: Record<string, unknown>,
): RuntimeCitation[] {
  if (!metadata || !Array.isArray(metadata.citations)) return [];
  const byID = new Map<string, RuntimeCitation>();
  for (const value of metadata.citations) {
    const citation = parseRuntimeCitation(value);
    if (citation) byID.set(citation.citation_id, citation);
  }
  return sortedCitations([...byID.values()]);
}

export function citationAnchorID(scope: string, citationID: string): string {
  const safeScope = encodeURIComponent(scope).split("%").join("");
  const safeCitationID = encodeURIComponent(citationID).split("%").join("");
  return `citation-source-${safeScope}-${safeCitationID}`;
}

export function remarkCitationMarkers(options: CitationRemarkOptions) {
  const citations = sortedCitations(options.citations);
  const references = citations.map((citation, index) => ({
    citation,
    displayIndex: index + 1,
    token: `[${citation.citation_id}]`,
  }));

  return (tree: MarkdownNode): void => {
    visitMarkdownNode(tree, false, references, options.scope);
  };
}

function visitMarkdownNode(
  node: MarkdownNode,
  blocked: boolean,
  references: Array<{
    citation: RuntimeCitation;
    displayIndex: number;
    token: string;
  }>,
  scope: string,
): void {
  if (!node.children) return;
  const childIsBlocked = blocked || node.type === "link" || node.type === "code";
  for (let index = 0; index < node.children.length; index += 1) {
    const child = node.children[index];
    if (!childIsBlocked && child.type === "text" && child.value) {
      const replacement = citationTextNodes(child.value, references, scope);
      if (replacement.length !== 1 || replacement[0].value !== child.value) {
        node.children.splice(index, 1, ...replacement);
        index += replacement.length - 1;
      }
      continue;
    }
    visitMarkdownNode(child, childIsBlocked, references, scope);
  }
}

function citationTextNodes(
  value: string,
  references: Array<{
    citation: RuntimeCitation;
    displayIndex: number;
    token: string;
  }>,
  scope: string,
): MarkdownNode[] {
  const nodes: MarkdownNode[] = [];
  let offset = 0;
  while (offset < value.length) {
    const match = nextCitationMatch(value, offset, references);
    if (!match) {
      nodes.push({ type: "text", value: value.slice(offset) });
      break;
    }
    if (match.index > offset) {
      nodes.push({ type: "text", value: value.slice(offset, match.index) });
    }
    nodes.push({
      type: "link",
      url: `#${citationAnchorID(scope, match.citation.citation_id)}`,
      title: `来源 ${match.displayIndex}：${match.citation.title}`,
      children: [{ type: "text", value: String(match.displayIndex) }],
    });
    offset = match.index + match.token.length;
  }
  return nodes.length > 0 ? nodes : [{ type: "text", value }];
}

function nextCitationMatch(
  value: string,
  offset: number,
  references: Array<{
    citation: RuntimeCitation;
    displayIndex: number;
    token: string;
  }>,
) {
  let best:
    | (typeof references)[number] & {
        index: number;
      }
    | undefined;
  for (const reference of references) {
    const index = value.indexOf(reference.token, offset);
    if (
      index !== -1 &&
      (!best ||
        index < best.index ||
        (index === best.index && reference.token.length > best.token.length))
    ) {
      best = { ...reference, index };
    }
  }
  return best;
}

export function formatCitedAnswerForCopy(
  content: string,
  citations: RuntimeCitation[],
): string {
  const references = sortedCitations(citations).map((citation, index) => ({
    citation,
    displayIndex: index + 1,
    token: `[${citation.citation_id}]`,
  }));
  if (references.length === 0) return content;

  let body = "";
  let offset = 0;
  while (offset < content.length) {
    const match = nextCitationMatch(content, offset, references);
    if (!match) {
      body += content.slice(offset);
      break;
    }
    body += content.slice(offset, match.index);
    body += `[${match.displayIndex}]`;
    offset = match.index + match.token.length;
  }
  const sources = references.map(
    ({ citation, displayIndex }) =>
      `[${displayIndex}] ${citation.title} — ${citation.url}`,
  );
  return `${body.trimEnd()}\n\n来源\n${sources.join("\n")}`;
}
