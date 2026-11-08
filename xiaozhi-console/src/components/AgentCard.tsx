import { useState, useRef, useEffect } from 'react';
import { Agent } from '../types';
import { Settings, MessageSquare, Cpu, MoreVertical, Edit2, Trash2, Mic, Bot, Clock } from 'lucide-react';
import { SupportedLanguage, TRANSLATIONS } from '../i18n';

interface AgentCardProps {
  agent: Agent;
  language: SupportedLanguage;
  onSelect: () => void;
  onOpenConfig: () => void;
  onOpenChat: () => void;
  onOpenDevice: () => void;
  onOpenRename: () => void;
  onOpenDelete: () => void;
}

const AVATAR_GRADIENTS = [
  'from-blue-500/22 via-sky-400/12 to-cyan-400/24 text-blue-700 ring-blue-500/20 dark:from-blue-400/25 dark:via-sky-400/12 dark:to-cyan-300/20 dark:text-blue-200 dark:ring-blue-300/20',
  'from-violet-500/22 via-purple-400/12 to-fuchsia-400/22 text-violet-700 ring-violet-500/20 dark:from-violet-400/25 dark:via-purple-400/12 dark:to-fuchsia-300/20 dark:text-violet-200 dark:ring-violet-300/20',
  'from-amber-400/28 via-orange-300/14 to-rose-400/20 text-amber-800 ring-amber-500/25 dark:from-amber-300/25 dark:via-orange-300/12 dark:to-rose-300/20 dark:text-amber-200 dark:ring-amber-300/20',
  'from-emerald-500/22 via-teal-400/12 to-cyan-400/22 text-emerald-700 ring-emerald-500/20 dark:from-emerald-400/25 dark:via-teal-400/12 dark:to-cyan-300/20 dark:text-emerald-200 dark:ring-emerald-300/20',
  'from-rose-500/22 via-pink-400/12 to-amber-400/22 text-rose-700 ring-rose-500/20 dark:from-rose-400/25 dark:via-pink-400/12 dark:to-amber-300/20 dark:text-rose-200 dark:ring-rose-300/20'
];

export function AgentCard({
  agent,
  language,
  onSelect,
  onOpenConfig,
  onOpenChat,
  onOpenDevice,
  onOpenRename,
  onOpenDelete
}: AgentCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const t = TRANSLATIONS[language];

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const firstLetter = (agent.name.trim()[0] || '?').toUpperCase();
  const colorIndex = Array.from(agent.id).reduce((acc, ch) => acc + (ch.codePointAt(0) || 0), 0) % AVATAR_GRADIENTS.length;
  const gradientClass = AVATAR_GRADIENTS[colorIndex];

  return (
    <section
      onClick={onSelect}
      className="group relative min-w-0 overflow-hidden rounded-xl border bg-card shadow-sm transition-[border-color,box-shadow] duration-200 hover:border-primary/40 hover:shadow-md cursor-pointer"
    >
      {/* Top Header */}
      <div className="p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            {/* Avatar */}
            <span
              className={`relative grid size-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br shadow-sm ring-1 ring-inset ${gradientClass}`}
              aria-hidden="true"
            >
              <span className="pointer-events-none absolute inset-[1px] rounded-[11px] bg-gradient-to-br from-white/45 via-white/5 to-transparent dark:from-white/10 dark:via-transparent" />
              <span className="relative text-lg font-bold leading-none tracking-tight">{firstLetter}</span>
            </span>

            {/* Title & Status */}
            <div className="flex min-w-0 flex-col gap-0.5">
              <div className="flex items-center gap-2">
                <h2 className="min-w-0 truncate text-base font-semibold tracking-tight text-foreground" title={agent.name}>
                  {agent.name}
                </h2>
                {agent.status === 'online' && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-600 ring-1 ring-inset ring-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-400">
                    <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    {t.agents.online}
                  </span>
                )}
                {agent.status === 'setup' && (
                  <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-600 ring-1 ring-inset ring-amber-500/20 dark:bg-amber-500/10 dark:text-amber-400">
                    {t.agents.setup}
                  </span>
                )}
                {agent.status === 'offline' && (
                  <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                    {t.agents.offline}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Action Menu (...) */}
          <div className="relative shrink-0" ref={menuRef} onClick={e => e.stopPropagation()}>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="Actions"
            >
              <MoreVertical className="size-4" />
            </button>
            {menuOpen && (
              <div className="absolute right-0 mt-1 w-36 rounded-md border bg-card p-1 shadow-md z-30 text-sm">
                <button
                  onClick={() => { setMenuOpen(false); onOpenRename(); }}
                  className="w-full flex items-center gap-2 rounded px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground text-left"
                >
                  <Edit2 className="size-3.5" /> {t.agents.renameAction}
                </button>
                <button
                  onClick={() => { setMenuOpen(false); onOpenDelete(); }}
                  className="w-full flex items-center gap-2 rounded px-2.5 py-1.5 text-xs text-destructive hover:bg-destructive/10 text-left"
                >
                  <Trash2 className="size-3.5" /> {t.agents.deleteAction}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 3-Column Stats Box */}
      <div className="mx-4 mb-4 grid grid-cols-3 divide-x rounded-lg border bg-muted/20 py-3 text-xs">
        <div className="flex flex-col items-center px-2 text-center">
          <div className="flex items-center gap-1 text-muted-foreground">
            <Mic className="size-3.5" />
            <span>{t.agents.role}</span>
          </div>
          <span className="mt-1 font-medium text-foreground truncate w-full" title={agent.role}>
            {agent.role}
          </span>
        </div>

        <div className="flex flex-col items-center px-2 text-center">
          <div className="flex items-center gap-1 text-muted-foreground">
            <Bot className="size-3.5" />
            <span>{t.agents.model}</span>
          </div>
          <span className="mt-1 font-medium text-foreground truncate w-full" title={agent.model}>
            {agent.model}
          </span>
        </div>

        <div className="flex flex-col items-center px-2 text-center">
          <div className="flex items-center gap-1 text-muted-foreground">
            <Clock className="size-3.5" />
            <span>{t.agents.lastChat}</span>
          </div>
          <span className="mt-1 font-medium text-foreground truncate w-full" title={agent.lastSeen}>
            {agent.lastSeen === 'Just now' ? t.agents.justNow : agent.lastSeen || '—'}
          </span>
        </div>
      </div>

      {/* Bottom 3 Action Buttons */}
      <div className="grid grid-cols-3 gap-2 border-t bg-muted/30 p-2.5" onClick={e => e.stopPropagation()}>
        <button
          onClick={onOpenConfig}
          className="inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border bg-background text-xs font-medium text-muted-foreground transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600 dark:hover:border-blue-800 dark:hover:bg-blue-950/40 dark:hover:text-blue-400"
        >
          <Settings className="size-3.5" />
          <span>{t.agents.configure}</span>
        </button>

        <button
          onClick={onOpenChat}
          className="inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border bg-background text-xs font-medium text-muted-foreground transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600 dark:hover:border-blue-800 dark:hover:bg-blue-950/40 dark:hover:text-blue-400"
        >
          <MessageSquare className="size-3.5" />
          <span>{t.agents.chat}</span>
        </button>

        <button
          onClick={onOpenDevice}
          className="inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border bg-background text-xs font-medium text-muted-foreground transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600 dark:hover:border-blue-800 dark:hover:bg-blue-950/40 dark:hover:text-blue-400"
        >
          <Cpu className="size-3.5" />
          <span>{t.agents.device} ({agent.deviceCount})</span>
        </button>
      </div>
    </section>
  );
}
