import { useState, useEffect } from 'react';
import { X, Edit2 } from 'lucide-react';
import { Agent } from '../types';
import { SupportedLanguage, TRANSLATIONS } from '../i18n';

interface RenameAgentModalProps {
  open: boolean;
  agent: Agent;
  language: SupportedLanguage;
  onClose: () => void;
  onRename: (newName: string) => void;
}

export function RenameAgentModal({ open, agent, language, onClose, onRename }: RenameAgentModalProps) {
  const t = TRANSLATIONS[language];
  const [name, setName] = useState(agent.name);

  useEffect(() => {
    setName(agent.name);
  }, [agent]);

  if (!open) return null;

  const handleSubmit = () => {
    if (!name.trim()) return;
    onRename(name.trim());
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="relative flex flex-col w-full max-w-md rounded-xl border bg-card shadow-2xl overflow-hidden p-6 space-y-4">
        <div className="flex items-center justify-between border-b pb-3">
          <div className="flex items-center gap-2">
            <Edit2 className="size-4 text-primary" />
            <h2 className="text-base font-semibold tracking-tight">{t.renameAgentModal.title}</h2>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            {t.renameAgentModal.desc}
          </p>
          <input
            type="text"
            autoFocus
            maxLength={50}
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            placeholder={t.renameAgentModal.placeholder}
            className="w-full rounded-md border bg-background px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <div className="flex justify-end gap-3 pt-3 border-t">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
          >
            {t.renameAgentModal.cancel}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!name.trim()}
            className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {t.renameAgentModal.save}
          </button>
        </div>
      </div>
    </div>
  );
}
