import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";

import { presentMarkdownDocument, safeMarkdownURL } from "./markdown";

describe("presentMarkdownDocument", () => {
  it("uses a leading level-one heading as the reading title without rendering it twice", () => {
    expect(presentMarkdownDocument("# 文档标题\n\n## 第一节\n正文", "fallback")).toEqual({
      title: "文档标题",
      body: "## 第一节\n正文",
    });
  });

  it("keeps the original body when the document has no leading level-one heading", () => {
    expect(presentMarkdownDocument("普通正文\n\n- 项目", "文件名")).toEqual({
      title: "文件名",
      body: "普通正文\n\n- 项目",
    });
  });
});

describe("safeMarkdownURL", () => {
  it("keeps safe web, mail and local links", () => {
    expect(safeMarkdownURL("https://example.com/path")).toBe("https://example.com/path");
    expect(safeMarkdownURL("mailto:user@example.com")).toBe("mailto:user@example.com");
    expect(safeMarkdownURL("#section")).toBe("#section");
    expect(safeMarkdownURL("/space")).toBe("/space");
  });

  it("removes executable and unknown protocols", () => {
    expect(safeMarkdownURL("javascript:alert(1)")).toBe("");
    expect(safeMarkdownURL("data:text/html,<script>alert(1)</script>")).toBe("");
    expect(safeMarkdownURL("file:///etc/passwd")).toBe("");
  });

  it("escapes raw HTML and strips executable Markdown links", () => {
    const html = renderToStaticMarkup(createElement(ReactMarkdown, {
      urlTransform: safeMarkdownURL,
      children: '<script>alert("x")</script>\n\n[run](javascript:alert(1))',
    }));
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("javascript:");
    expect(html).toContain("&lt;script&gt;");
  });
});
