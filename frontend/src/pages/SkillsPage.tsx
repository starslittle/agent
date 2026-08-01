import { useMemo } from "react";
import { ArrowRight, BookOpenText, Check, Database, LoaderCircle, RefreshCw, Search, ShieldCheck, Sparkles } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { filterVisibleSkills } from "@/features/skills/skills";
import { useSkillCatalog } from "@/features/skills/skill-catalog-context";

const versionFormatter = new Intl.NumberFormat("zh-CN");

export default function SkillsPage() {
  const { skillId } = useParams<{ skillId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { skills, loading, error, reload } = useSkillCatalog();
  const query = searchParams.get("q") || "";
  const visible = useMemo(() => filterVisibleSkills(skills, query), [query, skills]);
  const selected = skills.find((skill) => skill.id === skillId) ?? null;
  const detailOpen = Boolean(skillId);

  const setQuery = (value: string) => {
    const params = new URLSearchParams(searchParams);
    if (value) params.set("q", value); else params.delete("q");
    setSearchParams(params, { replace: true });
  };

  const closeDetail = () => navigate({ pathname: "/skills", search: searchParams.toString() ? `?${searchParams}` : "" });

  return (
    <WorkspaceShell title="Skills" subtitle="查看启点怎样完成不同类型的任务" mainId="skills-main" mainClassName="overflow-y-auto overscroll-contain">
      <div className="mx-auto w-full max-w-6xl px-5 pb-16 pt-8 sm:px-8 sm:pt-12">
        <header className="max-w-3xl">
          <div className="flex items-center gap-2 text-xs font-medium text-primary"><Sparkles className="h-4 w-4" aria-hidden="true" />启点能力目录</div>
          <h2 className="mt-4 text-pretty text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">先看清它怎样工作，再决定何时使用。</h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground">这里仅展示当前真实可用的内置 Skill、公开能力和上下文规则。运行指令、Prompt 与内部工具参数不会出现在这里。</p>
        </header>

        <div className="mt-8 max-w-2xl">
          <Label htmlFor="skill-search" className="sr-only">搜索 Skills</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input id="skill-search" name="skill-search" type="search" autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、用途或命令…" className="h-12 rounded-2xl pl-11 text-base" />
          </div>
        </div>

        <section className="mt-8" aria-label="可用 Skills" aria-live="polite">
          {loading && <div className="flex min-h-48 items-center justify-center gap-2 text-sm text-muted-foreground" role="status"><LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />正在读取可用 Skills…</div>}
          {!loading && error && <div className="max-w-xl rounded-2xl border border-destructive/25 bg-destructive/5 p-5" role="alert"><p className="text-sm font-medium">Skills 暂时无法加载</p><p className="mt-2 text-xs leading-5 text-muted-foreground">{error}</p><Button type="button" variant="outline" className="mt-4 min-h-11" onClick={reload}><RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />重试</Button></div>}
          {!loading && !error && visible.length === 0 && <div className="max-w-xl rounded-2xl border border-dashed p-8 text-center"><BookOpenText className="mx-auto h-7 w-7 text-primary" aria-hidden="true" /><h3 className="mt-4 text-sm font-semibold">没有匹配的可用 Skill</h3><p className="mt-2 text-xs leading-5 text-muted-foreground">换一个名称、用途或命令试试。</p>{query && <Button type="button" variant="link" className="mt-2 min-h-11" onClick={() => setQuery("")}>清除搜索</Button>}</div>}
          {!loading && !error && visible.length > 0 && <div className="grid gap-4 md:grid-cols-2">{visible.map((skill, index) => (
            <Link id={`skill-card-${skill.id}`} key={skill.id} to={`/skills/${encodeURIComponent(skill.id)}${searchParams.toString() ? `?${searchParams}` : ""}`} className="group relative min-w-0 overflow-hidden rounded-2xl border bg-card p-5 transition-[border-color,background-color,box-shadow] hover:border-primary/35 hover:bg-muted/20 hover:shadow-sm focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/20">
              <div className="flex items-start gap-4"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Sparkles className="h-5 w-5" aria-hidden="true" /></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline gap-x-3 gap-y-1"><h3 className="text-base font-semibold text-pretty">{skill.title}</h3><code className="text-xs text-muted-foreground" translate="no">{skill.command}</code></div><p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{skill.description}</p></div></div>
              <div className="mt-6 flex items-center justify-between border-t pt-4 text-xs"><span className="text-muted-foreground">版本 {versionFormatter.format(skill.version)} · {skill.public_capabilities.length} 项公开能力</span><span className="flex items-center gap-1 font-medium text-primary">查看详情<ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 motion-reduce:transform-none" aria-hidden="true" /></span></div>
              <span className={`absolute left-0 top-5 h-10 w-0.5 rounded-r bg-primary ${index === 0 ? "opacity-100" : "opacity-40"}`} aria-hidden="true" />
            </Link>
          ))}</div>}
        </section>
      </div>

      <Dialog open={detailOpen} onOpenChange={(open) => { if (!open) closeDetail(); }}>
        <DialogContent
          className="inset-0 flex h-dvh w-full max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-none p-0 sm:left-1/2 sm:top-1/2 sm:h-auto sm:max-h-[min(88dvh,46rem)] sm:max-w-2xl sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            window.requestAnimationFrame(() => {
              const target = document.getElementById(`skill-card-${skillId}`) || document.getElementById("skill-search");
              target?.focus();
            });
          }}
        >
          {loading ? <div className="flex min-h-80 flex-1 items-center justify-center gap-2 text-sm text-muted-foreground" role="status"><DialogTitle className="sr-only">正在读取 Skill</DialogTitle><DialogDescription className="sr-only">请稍候，正在读取当前 Skill 的公开详情。</DialogDescription><LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />正在读取 Skill…</div> : error ? <div className="flex min-h-80 flex-1 flex-col items-center justify-center px-6 text-center" role="alert"><RefreshCw className="h-8 w-8 text-primary" aria-hidden="true" /><DialogTitle className="mt-4">Skill 详情暂时无法加载</DialogTitle><DialogDescription className="mt-2 max-w-sm leading-6">{error}</DialogDescription><Button type="button" variant="outline" className="mt-5 min-h-11" onClick={reload}><RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />重试</Button></div> : selected ? <>
            <DialogHeader className="border-b px-6 pb-6 pt-7 text-left sm:px-8">
              <div className="flex items-start gap-4 pr-8"><span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Sparkles className="h-5 w-5" aria-hidden="true" /></span><div className="min-w-0"><div className="flex flex-wrap items-baseline gap-3"><DialogTitle className="text-xl text-pretty sm:text-2xl">{selected.title}</DialogTitle><code className="text-xs text-muted-foreground" translate="no">{selected.command}</code></div><DialogDescription className="mt-2 text-sm leading-6">{selected.description}</DialogDescription></div></div>
            </DialogHeader>
            <div className="min-h-0 flex-1 space-y-7 overflow-y-auto overscroll-contain px-6 py-6 sm:px-8">
              <section aria-labelledby="skill-purpose"><h3 id="skill-purpose" className="flex items-center gap-2 text-sm font-semibold"><BookOpenText className="h-4 w-4 text-primary" aria-hidden="true" />适合用来做什么</h3><p className="mt-3 text-sm leading-7 text-muted-foreground">{selected.public_purpose}</p></section>
              <section aria-labelledby="skill-capabilities"><h3 id="skill-capabilities" className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />公开能力</h3><div className="mt-3 space-y-2">{selected.public_capabilities.map((capability) => <div key={capability.label} className="rounded-xl border bg-muted/25 p-4"><p className="flex items-center gap-2 text-sm font-medium"><Check className="h-4 w-4 text-primary" aria-hidden="true" />{capability.label}</p><p className="mt-1.5 pl-6 text-xs leading-5 text-muted-foreground">{capability.description}</p></div>)}</div></section>
              <section aria-labelledby="skill-context"><h3 id="skill-context" className="flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-primary" aria-hidden="true" />可能使用的个人上下文</h3>{selected.context_scope.length > 0 ? <ul className="mt-3 flex flex-wrap gap-2">{selected.context_scope.map((scope) => <li key={scope.label} className="rounded-full bg-primary/10 px-3 py-2 text-xs font-medium text-primary">{scope.label}</li>)}</ul> : <p className="mt-3 text-xs text-muted-foreground">不读取长期个人上下文。</p>}<p className="mt-4 rounded-xl border-l-2 border-primary/40 bg-muted/35 px-4 py-3 text-xs leading-5 text-muted-foreground">{selected.confirmation_summary}</p><p className="mt-3 text-xs text-muted-foreground">{selected.may_propose_updates ? "可以提出上下文更新建议，但必须由你确认。" : "不会提出长期上下文更新。"}</p></section>
            </div>
            <div className="border-t bg-background px-6 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-8"><Button asChild className="min-h-11 w-full sm:w-auto"><Link to={`/?skill=${encodeURIComponent(selected.id)}`}>在对话中使用<ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" /></Link></Button><p className="mt-2 text-[11px] text-muted-foreground">发送时服务端会再次检查这个 Skill 是否仍可用。</p></div>
          </> : <div className="flex min-h-80 flex-1 flex-col items-center justify-center px-6 text-center"><ShieldCheck className="h-8 w-8 text-primary" aria-hidden="true" /><DialogTitle className="mt-4">这个 Skill 当前不可用</DialogTitle><DialogDescription className="mt-2 max-w-sm leading-6">它可能不存在、暂时不可用，或不在你的可见范围内。目录不会展示内部原因。</DialogDescription><Button type="button" variant="outline" className="mt-5 min-h-11" onClick={closeDetail}>返回 Skills</Button></div>}
        </DialogContent>
      </Dialog>
    </WorkspaceShell>
  );
}
