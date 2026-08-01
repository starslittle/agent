import type { ReactNode } from "react";

import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";

export function RunWorkspaceShell({
  children,
  mode = "user",
}: {
  children: ReactNode;
  mode?: "user" | "internal";
}) {
  return (
    <WorkspaceShell
      title={mode === "internal" ? "内部观测" : "Agent Runs"}
      subtitle={mode === "internal" ? "跨用户只读运行检查" : "查看我的任务实际发生了什么"}
      mainId="runs-main"
      skipLabel="跳到运行内容"
    >
      {children}
    </WorkspaceShell>
  );
}
