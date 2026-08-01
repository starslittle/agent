import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { RunList } from "./RunList";

describe("RunList internal empty state", () => {
  it("shows a clear empty state without a product write action", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <RunList
          items={[]}
          status=""
          loading={false}
          loadingMore={false}
          hasMore={false}
          error=""
          onStatusChange={() => undefined}
          onRetry={() => undefined}
          onLoadMore={() => undefined}
          basePath="/internal/agent-runs"
          showEmptyAction={false}
          emptyDescription="当前筛选条件下没有可查看的运行记录。"
        />
      </MemoryRouter>,
    );

    expect(html).toContain("当前筛选条件下没有可查看的运行记录。");
    expect(html).not.toContain("开始对话");
    expect(html).not.toContain("取消 Run");
    expect(html).not.toContain("重放 Run");
  });
});
