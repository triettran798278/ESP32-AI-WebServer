import { useState } from 'react';
import { X, Bot } from 'lucide-react';
import { useToast } from './Toast';
import { SupportedLanguage, TRANSLATIONS } from '../i18n';

interface CreateAgentModalProps {
  open: boolean;
  language: SupportedLanguage;
  onClose: () => void;
  onCreate: (name: string) => void;
}

export function CreateAgentModal({ open, language, onClose, onCreate }: CreateAgentModalProps) {
  const { error } = useToast();
  const t = TRANSLATIONS[language];
  const [name, setName] = useState('');

  if (!open) return null;

  const handleSubmit = () => {
    if (!name.trim()) {
      error(t.createAgentModal.required);
      return;
    }
    onCreate(name.trim());
    setName('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="relative flex flex-col w-full max-w-md rounded-xl border bg-card shadow-2xl overflow-hidden p-6 space-y-4">
        <div className="flex items-center justify-between border-b pb-3">
          <div className="flex items-center gap-2">
            <Bot className="size-5 text-primary" />
            <h2 className="text-base font-semibold tracking-tight">{t.createAgentModal.title}</h2>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">
              <span className="text-destructive mr-1">*</span>{t.createAgentModal.nameLabel}
            </label>
            <input
              type="text"
              autoFocus
              maxLength={50}
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              placeholder={t.createAgentModal.namePlaceholder}
              className="w-full rounded-md border bg-background px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            {t.createAgentModal.desc}
          </p>
        </div>

        <div className="flex justify-end gap-3 pt-3 border-t">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
          >
            {t.createAgentModal.cancel}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!name.trim()}
            className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {t.createAgentModal.create}
          </button>
        </div>
      </div>
    </div>
  );
}
