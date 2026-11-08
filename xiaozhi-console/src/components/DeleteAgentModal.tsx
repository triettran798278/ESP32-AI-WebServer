import { X, AlertTriangle } from 'lucide-react';
import { Agent } from '../types';
import { SupportedLanguage, TRANSLATIONS } from '../i18n';

interface DeleteAgentModalProps {
  open: boolean;
  agent: Agent;
  language: SupportedLanguage;
  onClose: () => void;
  onConfirm: () => void;
}

export function DeleteAgentModal({ open, agent, language, onClose, onConfirm }: DeleteAgentModalProps) {
  const t = TRANSLATIONS[language];
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="relative flex flex-col w-full max-w-md rounded-xl border bg-card shadow-2xl overflow-hidden p-6 space-y-4">
        <div className="flex items-center justify-between border-b pb-3">
          <div className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="size-5" />
            <h2 className="text-base font-semibold tracking-tight">{t.deleteAgentModal.title}</h2>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-2">
          <p className="text-xs text-foreground leading-relaxed">
            {t.deleteAgentModal.confirm(agent.name)}
          </p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {t.deleteAgentModal.warning}
          </p>
        </div>

        <div className="flex justify-end gap-3 pt-3 border-t">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
          >
            {t.deleteAgentModal.cancel}
          </button>
          <button
            type="button"
            onClick={() => {
              onConfirm();
              onClose();
            }}
            className="rounded-lg bg-destructive px-4 py-2 text-xs font-medium text-destructive-foreground hover:bg-destructive/90"
          >
            {t.deleteAgentModal.confirmDelete}
          </button>
        </div>
      </div>
    </div>
  );
}
