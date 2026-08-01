import { useEffect, useState } from "react";
import { Brain, CircleAlert, FileCheck2, Plus, RefreshCw, Scale, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { createWikiItem, listWikiItems, type WikiItem, type WikiType } from "@/lib/wiki-api";

const typeCopy: Record<WikiType, { label: string; icon: typeof Brain }> = {
  confirmed_fact: { label: "确认事实", icon: FileCheck2 },
  current_state: { label: "当前状态", icon: CircleAlert },
  personal_rule: { label: "个人规则", icon: Scale },
  ai_analysis: { label: "AI 分析", icon: Sparkles },
};

interface DocumentContextPanelProps {
  documentID: string;
  documentRevisionID: string;
  className?: string;
}

export function DocumentContextPanel({ documentID, documentRevisionID, className = "" }: DocumentContextPanelProps) {
  const { csrfToken } = useAuth();
  const [items, setItems] = useState<WikiItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<WikiType>("current_state");
  const [domain, setDomain] = useState("general");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void listWikiItems(documentID, false, controller.signal)
      .then((response) => setItems(response.items))
      .catch((reason: unknown) => { if ((reason as Error).name !== "AbortError") setError(reason instanceof Error ? reason.message : "无法读取关联上下文"); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [documentID, retry]);

  const create = async () => {
    if (!content.trim() || saving) return;
    setSaving(true);
    try {
      await createWikiItem(csrfToken, { type, domain, content: content.trim(), document_id: documentID, document_revision_id: documentRevisionID });
      toast.success("已加入关联上下文");
      setContent("");
      setOpen(false);
      setRetry((value) => value + 1);
    } catch (reason) { toast.error(reason instanceof Error ? reason.message : "保存没有完成"); }
    finally { setSaving(false); }
  };

  return (
    <aside className={`flex h-full min-h-0 flex-col bg-muted/20 ${className}`} aria-label="关联上下文">
      <div className="flex items-start justify-between gap-3 border-b px-5 py-5">
        <div><h2 className="text-sm font-semibold">关联上下文</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">经你确认后，才会长期影响回答。</p></div>
        <Button type="button" variant="outline" size="icon" className="h-11 w-11" onClick={() => setOpen(true)} aria-label="添加关联上下文"><Plus className="h-4 w-4" aria-hidden="true" /></Button>
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain p-3">
        {loading && <p role="status" className="px-3 py-10 text-center text-xs text-muted-foreground">正在读取上下文…</p>}
        {!loading && error && <div role="alert" className="px-3 py-8 text-center"><p className="text-xs text-destructive">{error}</p><Button variant="ghost" size="sm" className="mt-2" onClick={() => setRetry((value) => value + 1)}><RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden="true" />重试</Button></div>}
        {!loading && !error && items.length === 0 && <div className="px-4 py-10 text-center"><Brain className="mx-auto h-7 w-7 text-primary/60" aria-hidden="true" /><p className="mt-3 text-sm font-medium">还没有关联信息</p><p className="mt-1 text-xs leading-5 text-muted-foreground">从文档中挑出值得长期保留的事实、状态或规则。</p></div>}
        {!loading && !error && items.map((item) => {
          const copy = typeCopy[item.type]; const Icon = copy.icon;
          const statusLabel = item.type === "ai_analysis" && item.status === "confirmed" ? "用户保留" : item.status === "confirmed" ? "已确认" : item.status === "outdated" ? "已过时" : item.status;
          return <Link key={item.id} to={`/space/context/${item.id}`} className="block rounded-xl border bg-background p-4 transition-colors hover:border-primary/30 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><div className="flex items-center gap-2 text-xs font-medium"><Icon className="h-4 w-4 text-primary" aria-hidden="true" />{copy.label}<span className="ml-auto rounded-full bg-muted px-2 py-1 text-xs text-muted-foreground">{statusLabel}</span></div><p className="mt-3 line-clamp-3 text-xs leading-5 text-muted-foreground">{item.content}</p></Link>;
        })}
      </div>

      <Dialog open={open} onOpenChange={setOpen}><DialogContent><DialogHeader><DialogTitle>添加关联上下文</DialogTitle><DialogDescription>这里保存的是你明确认可的信息，不是 AI 的临时推测。</DialogDescription></DialogHeader><div className="space-y-4 py-2"><div className="space-y-2"><Label htmlFor="context-type">类型</Label><Select value={type} onValueChange={(value: WikiType) => setType(value)}><SelectTrigger id="context-type"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="confirmed_fact">确认事实</SelectItem><SelectItem value="current_state">当前状态</SelectItem><SelectItem value="personal_rule">个人规则</SelectItem><SelectItem value="ai_analysis">AI 分析</SelectItem></SelectContent></Select></div><div className="space-y-2"><Label htmlFor="context-domain">领域</Label><Input id="context-domain" name="context-domain" autoComplete="off" value={domain} onChange={(event) => setDomain(event.target.value)} placeholder="例如：career…" /></div><div className="space-y-2"><Label htmlFor="context-content">内容</Label><Textarea id="context-content" name="context-content" value={content} onChange={(event) => setContent(event.target.value)} rows={6} placeholder="写下需要启点长期记住的信息…" /></div></div><DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>取消</Button><Button onClick={() => void create()} disabled={!content.trim() || !domain.trim() || saving}>{saving ? "正在保存…" : "确认并保存"}</Button></DialogFooter></DialogContent></Dialog>
    </aside>
  );
}
