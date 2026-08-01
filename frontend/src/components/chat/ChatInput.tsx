import React, { useEffect, useMemo, useRef, useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  filterVisibleSkills,
  getVisibleSkill,
  selectComposerSkill,
  type SkillID,
} from "@/features/skills/skills";
import { useSkillCatalog } from "@/features/skills/skill-catalog-context";
import { ChevronRight, LoaderCircle, Send, Sparkles, Square, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";

interface ChatInputProps {
  onSend: (text: string, requestedSkill: SkillID | null) => void;
  loading?: boolean;
  stopping?: boolean;
  canStop?: boolean;
  onStop?: () => void;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSend,
  loading,
  stopping,
  canStop,
  onStop,
}) => {
  const [value, setValue] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<SkillID | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [sending, setSending] = useState(false);
  const [searchParams] = useSearchParams();
  const { skills, loading: skillsLoading, error: skillsError, reload: reloadSkills } = useSkillCatalog();
  const taRef = useRef<HTMLTextAreaElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const preselectedRef = useRef<string | null>(null);

  const slashQuery = value.startsWith("/") ? value.slice(1).split(/\s/, 1)[0] : "";
  const filteredSkills = useMemo(
    () => filterVisibleSkills(skills, slashQuery),
    [skills, slashQuery],
  );
  const skill = getVisibleSkill(skills, selectedSkill);

  useEffect(() => {
    const requested = searchParams.get("skill")?.trim() || null;
    if (!requested || skillsLoading || preselectedRef.current === requested) return;
    preselectedRef.current = requested;
    if (getVisibleSkill(skills, requested)) setSelectedSkill(requested);
  }, [searchParams, skills, skillsLoading]);

  const autosize = () => {
    const element = taRef.current;
    if (!element) return;
    element.style.height = "0px";
    element.style.height = `${Math.min(Math.max(element.scrollHeight, 24), 160)}px`;
  };

  useEffect(() => {
    autosize();
  }, [value]);

  useEffect(() => {
    setActiveIndex(0);
    if (value.startsWith("/") && !selectedSkill) setMenuOpen(true);
  }, [selectedSkill, slashQuery, value]);

  const chooseSkill = (skillID: SkillID) => {
    const next = selectComposerSkill({ selectedSkill, value }, skillID);
    setSelectedSkill(next.selectedSkill);
    setValue(next.value);
    setMenuOpen(false);
    requestAnimationFrame(() => taRef.current?.focus());
  };

  const handleSend = () => {
    if (loading) return;
    const text = value.trim();
    if (!text) return;
    setSending(true);
    onSend(text, selectedSkill);
    setValue("");
    setSelectedSkill(null);
    setMenuOpen(false);
    window.setTimeout(() => setSending(false), 200);
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (event) => {
    if (menuOpen && filteredSkills.length > 0) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const direction = event.key === "ArrowDown" ? 1 : -1;
        setActiveIndex((current) =>
          (current + direction + filteredSkills.length) % filteredSkills.length,
        );
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        return;
      }
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        chooseSkill(filteredSkills[activeIndex].id);
        return;
      }
    }

    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      handleSend();
    }
  };

  const actionLabel = stopping
    ? "正在停止生成"
    : loading && canStop
      ? "停止生成"
      : loading
        ? "正在创建运行"
        : "发送消息";

  return (
    <div className="relative w-full">
      {menuOpen && (
        <div
          ref={menuRef}
          id="skill-menu"
          className="absolute inset-x-0 bottom-[calc(100%+0.5rem)] z-40 overflow-hidden rounded-2xl border border-border bg-popover p-2 shadow-lg sm:left-0 sm:right-auto sm:w-[22rem]"
          role="listbox"
          aria-label="选择 Skill"
        >
          <div className="px-3 pb-2 pt-1">
            <p className="text-xs font-medium text-foreground">选择 Skill</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              仅对这一条消息生效
            </p>
          </div>
          {skillsLoading ? (
            <p className="flex min-h-14 items-center gap-2 px-3 text-xs text-muted-foreground" role="status"><LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />正在读取可用 Skills…</p>
          ) : skillsError ? (
            <div className="px-3 py-3" role="alert"><p className="text-xs leading-5 text-destructive">{skillsError}</p><button type="button" onClick={reloadSkills} className="mt-2 min-h-11 text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">重试</button></div>
          ) : filteredSkills.length > 0 ? (
            filteredSkills.map((item, index) => (
              <button
                key={item.id}
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => chooseSkill(item.id)}
                className={cn(
                  "flex min-h-14 w-full items-center gap-3 rounded-xl px-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  index === activeIndex ? "bg-muted" : "hover:bg-muted/70",
                )}
              >
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium text-foreground">{item.title}</span>
                    <code className="text-[11px] text-muted-foreground">{item.command}</code>
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                    {item.description}
                  </span>
                </span>
                <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              </button>
            ))
          ) : (
            <p className="px-3 py-4 text-xs text-muted-foreground">没有匹配的可用 Skill</p>
          )}
        </div>
      )}

      <div className="rounded-2xl border border-border bg-background p-2 shadow-[0_12px_36px_-24px_rgba(29,36,33,0.34)]">
        {skill && (
          <div className="mb-1.5 flex items-center px-1">
            <span className="inline-flex min-h-8 items-center gap-1.5 rounded-full bg-primary/10 pl-3 pr-1.5 text-xs font-medium text-primary">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              {skill.title}
              <button
                type="button"
                onClick={() => setSelectedSkill(null)}
                className="relative grid h-8 w-8 place-items-center rounded-full before:absolute before:-inset-1.5 hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label={`移除${skill.title}`}
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </span>
          </div>
        )}

        <div className="flex items-end gap-2">
          <button
            type="button"
            onClick={() => setMenuOpen((current) => !current)}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="选择 Skill"
            aria-expanded={menuOpen}
          >
            <span className="font-mono text-base" aria-hidden="true">/</span>
          </button>

          <Textarea
            ref={taRef}
            name="message"
            autoComplete="off"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={onKeyDown}
            onInput={autosize}
            rows={1}
            placeholder="描述你想解决的问题…"
            className="min-h-11 max-h-40 flex-1 resize-none overflow-y-auto border-0 bg-transparent px-1 py-3 text-sm leading-5 text-foreground shadow-none placeholder:text-muted-foreground focus-visible:ring-0"
            aria-label="消息内容"
            aria-controls={menuOpen ? "skill-menu" : undefined}
          />

          <button
            type="button"
            disabled={stopping || (loading && !canStop) || (!loading && (sending || !value.trim()))}
            onClick={loading && canStop ? onStop : handleSend}
            className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground transition-[background-color,transform,opacity] hover:-translate-y-0.5 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25 disabled:cursor-not-allowed disabled:opacity-35 motion-reduce:transform-none"
            title={actionLabel}
            aria-label={actionLabel}
          >
            {stopping ? (
              <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : loading && canStop ? (
              <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
            ) : loading ? (
              <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : (
              <Send className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>

        <div className="mt-1 flex items-center justify-between px-2 pb-0.5 text-[10px] text-muted-foreground">
          <span>输入 / 选择 Skill</span>
          <span className="hidden sm:inline">Enter 发送 · Shift + Enter 换行</span>
        </div>
      </div>
      <span className="sr-only" aria-live="polite">{loading ? actionLabel : ""}</span>
    </div>
  );
};

export default ChatInput;
