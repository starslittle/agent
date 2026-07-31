import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { RuntimeCitation } from "@/lib/chat-api";
import { CitationList } from "./CitationList";
import {
  citationAnchorID,
  formatCitedAnswerForCopy,
  parseStoredCitations,
  remarkCitationMarkers,
} from "./citations";

const citation: RuntimeCitation = {
  citation_id: "source-abc",
  title: "Verified source",
  url: "https://example.com/report",
  snippet: "Public summary",
  source_type: "web",
  artifact_id: "research_evidence:abc",
  sequence: 1,
};

describe("structured citations", () => {
  it("restores only valid, deduplicated message metadata", () => {
    expect(
      parseStoredCitations({
        citations: [
          citation,
          { ...citation, title: "Latest title" },
          { ...citation, citation_id: "unsafe", url: "javascript:alert(1)" },
          { citation_id: "missing-fields" },
        ],
      }),
    ).toEqual([{ ...citation, title: "Latest title" }]);
  });

  it("replaces only exact structured IDs and leaves code nodes alone", () => {
    const tree = {
      type: "root",
      children: [
        {
          type: "paragraph",
          children: [
            { type: "text", value: "事实[source-abc] 普通[unknown]" },
            { type: "inlineCode", value: "[source-abc]" },
          ],
        },
      ],
    };
    remarkCitationMarkers({ citations: [citation], scope: "message-1" })(tree);

    expect(tree.children[0].children).toEqual([
      { type: "text", value: "事实" },
      {
        type: "link",
        url: `#${citationAnchorID("message-1", citation.citation_id)}`,
        title: "来源 1：Verified source",
        children: [{ type: "text", value: "1" }],
      },
      { type: "text", value: " 普通[unknown]" },
      { type: "inlineCode", value: "[source-abc]" },
    ]);
  });

  it("copies readable markers plus a deterministic source appendix", () => {
    expect(
      formatCitedAnswerForCopy(
        "事实[source-abc]，普通文本[unknown]。",
        [citation],
      ),
    ).toBe(
      "事实[1]，普通文本[unknown]。\n\n来源\n" +
        "[1] Verified source — https://example.com/report",
    );
  });

  it("renders a keyboard-focusable external source with safe attributes", () => {
    const markup = renderToStaticMarkup(
      createElement(CitationList, {
        citations: [citation],
        scope: "message-1",
      }),
    );

    expect(markup).toContain('target="_blank"');
    expect(markup).toContain('rel="noopener noreferrer"');
    expect(markup).toContain('aria-label="打开来源 1：Verified source（新窗口）"');
    expect(markup).toContain(
      `id="${citationAnchorID("message-1", citation.citation_id)}"`,
    );
  });
});
