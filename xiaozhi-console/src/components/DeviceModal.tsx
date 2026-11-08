import { useState } from 'react';
import { Agent, Device } from '../types';
import { X, Cpu, Edit2, Check, Wifi, WifiOff, Trash2, Plus, ArrowLeft, Palette } from 'lucide-react';
import { useToast } from './Toast';
import { SupportedLanguage, TRANSLATIONS } from '../i18n';

interface DeviceModalProps {
  open: boolean;
  agent: Agent;
  language: SupportedLanguage;
  onClose: () => void;
  onUpdateDevices: (devices: Device[]) => void;
}

export function DeviceModal({ open, agent, language, onClose, onUpdateDevices }: DeviceModalProps) {
  const { success, error } = useToast();
  const t = TRANSLATIONS[language];
  const [viewMode, setViewMode] = useState<'list' | 'bind' | 'unbind'>('list');
  const [deviceList, setDeviceList] = useState<Device[]>(() => agent.devices || []);
  const [editingMac, setEditingMac] = useState<string | null>(null);
  const [editAlias, setEditAlias] = useState('');
  const [deviceToUnbind, setDeviceToUnbind] = useState<Device | null>(null);

  const [codeDigits, setCodeDigits] = useState<string[]>(['', '', '', '', '', '']);

  if (!open) return null;

  const handleStartEdit = (dev: Device) => {
    setEditingMac(dev.mac_address);
    setEditAlias(dev.name);
  };

  const handleSaveAlias = (mac: string) => {
    if (!editAlias.trim()) return;
    const updated = deviceList.map(d => d.mac_address === mac ? { ...d, name: editAlias.trim() } : d);
    setDeviceList(updated);
    setEditingMac(null);
    onUpdateDevices(updated);
    success(t.device.aliasUpdated);
  };

  const handleToggleOta = (mac: string) => {
    const updated = deviceList.map(d => d.mac_address === mac ? { ...d, ota_enabled: !d.ota_enabled } : d);
    setDeviceList(updated);
    onUpdateDevices(updated);
    success(t.device.otaUpdated);
  };

  const handleConfirmUnbind = () => {
    if (!deviceToUnbind) return;
    const updated = deviceList.filter(d => d.id !== deviceToUnbind.id);
    setDeviceList(updated);
    setDeviceToUnbind(null);
    setViewMode('list');
    onUpdateDevices(updated);
    success(t.device.unbindSuccess);
  };

  const handleCodeChange = (index: number, val: string) => {
    const clean = val.replace(/\D/g, '').slice(-1);
    const updated = [...codeDigits];
    updated[index] = clean;
    setCodeDigits(updated);

    if (clean && index < 5) {
      document.getElementById(`digit-input-${index + 1}`)?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !codeDigits[index] && index > 0) {
      document.getElementById(`digit-input-${index - 1}`)?.focus();
    }
  };

  const handleBindDevice = () => {
    const fullCode = codeDigits.join('');
    if (fullCode.length !== 6) {
      error(t.device.enterCode);
      return;
    }

    const randomMac = Array.from({ length: 6 }, () => 
      Math.floor(Math.random() * 256).toString(16).padStart(2, '0').toUpperCase()
    ).join(':');

    const newDevice: Device = {
      id: 'dev_' + Date.now(),
      name: `ESP32-S3 (${fullCode})`,
      mac_address: randomMac,
      status: 'online',
      firmware_version: 'v2.2.0',
      is_auth: false,
      ota_enabled: true
    };

    const updated = [...deviceList, newDevice];
    setDeviceList(updated);
    setCodeDigits(['', '', '', '', '', '']);
    setViewMode('list');
    onUpdateDevices(updated);
    success(t.device.bindSuccess);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="relative flex flex-col w-full max-w-2xl max-h-[90vh] rounded-xl border bg-card shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2">
            {viewMode !== 'list' && (
              <button
                onClick={() => setViewMode('list')}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <ArrowLeft className="size-4" />
              </button>
            )}
            <h2 className="text-base font-semibold tracking-tight">
              {agent.name} <span className="text-muted-foreground font-normal">· {t.device.title}</span>
            </h2>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {viewMode === 'list' && (
            <>
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  {t.device.subtitle}
                </p>
                <button
                  onClick={() => setViewMode('bind')}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/20"
                >
                  <Plus className="size-3.5" /> {t.device.bindNew}
                </button>
              </div>

              {deviceList.length === 0 ? (
                <div className="rounded-lg border border-dashed py-12 text-center text-xs text-muted-foreground space-y-3">
                  <div className="size-10 rounded-full bg-muted flex items-center justify-center mx-auto">
                    <Cpu className="size-5 text-muted-foreground" />
                  </div>
                  <p>{t.device.noDevices}</p>
                  <button
                    onClick={() => setViewMode('bind')}
                    className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
                  >
                    {t.device.bindNow}
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {deviceList.map(dev => (
                    <div
                      key={dev.id}
                      className="rounded-xl border bg-card p-4 shadow-xs space-y-3 hover:border-primary/30 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            {editingMac === dev.mac_address ? (
                              <div className="flex items-center gap-1.5">
                                <input
                                  type="text"
                                  value={editAlias}
                                  onChange={e => setEditAlias(e.target.value)}
                                  onKeyDown={e => e.key === 'Enter' && handleSaveAlias(dev.mac_address)}
                                  className="rounded border px-2 py-0.5 text-xs font-semibold outline-none focus:ring-1 focus:ring-ring"
                                  autoFocus
                                />
                                <button
                                  onClick={() => handleSaveAlias(dev.mac_address)}
                                  className="text-primary hover:text-primary/80"
                                >
                                  <Check className="size-3.5" />
                                </button>
                              </div>
                            ) : (
                              <div className="flex items-center gap-1.5">
                                <span className="font-semibold text-sm text-foreground">{dev.name}</span>
                                <button
                                  onClick={() => handleStartEdit(dev)}
                                  className="text-muted-foreground hover:text-foreground"
                                  title="Edit Alias"
                                >
                                  <Edit2 className="size-3" />
                                </button>
                              </div>
                            )}

                            {dev.status === 'online' ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400">
                                <Wifi className="size-3" /> {t.agents.online}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                                <WifiOff className="size-3" /> {t.agents.offline}
                              </span>
                            )}

                            {dev.is_auth ? (
                              <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 dark:bg-blue-500/10 dark:text-blue-400">
                                {t.device.authorized}
                              </span>
                            ) : (
                              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                                {t.device.openSource}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono">
                            <span>{t.device.mac}: {dev.mac_address}</span>
                            <span>·</span>
                            <span>{t.device.firmware}: {dev.firmware_version}</span>
                          </div>
                        </div>

                        <button
                          onClick={() => {
                            setDeviceToUnbind(dev);
                            setViewMode('unbind');
                          }}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          title={t.device.unbind}
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </div>

                      <div className="flex items-center justify-between border-t pt-3 text-xs">
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={dev.ota_enabled}
                            onChange={() => handleToggleOta(dev.mac_address)}
                            className="rounded border-border text-primary focus:ring-ring"
                          />
                          <span className="text-muted-foreground">{t.device.ota}</span>
                        </label>

                        <button
                          onClick={() => success(language === 'vi' ? 'Trình tạo theme đã sẵn sàng' : 'Theme builder ready')}
                          className="inline-flex items-center gap-1 rounded px-2.5 py-1 text-muted-foreground hover:bg-muted text-xs"
                        >
                          <Palette className="size-3.5" /> {t.device.theme}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* VIEW: BIND NEW DEVICE */}
          {viewMode === 'bind' && (
            <div className="space-y-6 py-4 animate-in fade-in duration-150">
              <div className="text-center space-y-1">
                <h3 className="font-semibold text-base text-foreground">{t.device.bindTitle(agent.name)}</h3>
                <p className="text-xs text-muted-foreground">
                  {t.device.bindNotice}
                </p>
              </div>

              <div className="flex justify-center gap-2.5 my-6">
                {codeDigits.map((digit, idx) => (
                  <input
                    key={idx}
                    id={`digit-input-${idx}`}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={digit}
                    onChange={e => handleCodeChange(idx, e.target.value)}
                    onKeyDown={e => handleKeyDown(idx, e)}
                    className="size-11 rounded-lg border text-center text-lg font-bold bg-background text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
                  />
                ))}
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t">
                <button
                  type="button"
                  onClick={() => setViewMode('list')}
                  className="rounded-lg border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
                >
                  {t.device.back}
                </button>
                <button
                  type="button"
                  onClick={handleBindDevice}
                  disabled={codeDigits.join('').length !== 6}
                  className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {language === 'vi' ? 'Xác nhận liên kết' : 'Confirm Bind'}
                </button>
              </div>
            </div>
          )}

          {/* VIEW: UNBIND CONFIRMATION */}
          {viewMode === 'unbind' && deviceToUnbind && (
            <div className="space-y-4 py-3 animate-in fade-in duration-150">
              <div className="space-y-1">
                <h3 className="font-semibold text-base text-destructive">{t.device.unbindConfirmTitle}</h3>
                <p className="text-xs text-muted-foreground">
                  {t.device.unbindConfirmDesc(deviceToUnbind.name)}
                </p>
              </div>

              <div className="rounded-lg border bg-muted/20 p-3 text-xs font-mono space-y-1">
                <div className="font-semibold text-foreground">{deviceToUnbind.name}</div>
                <div className="text-muted-foreground">{deviceToUnbind.mac_address}</div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t">
                <button
                  type="button"
                  onClick={() => setViewMode('list')}
                  className="rounded-lg border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
                >
                  {t.device.cancel}
                </button>
                <button
                  type="button"
                  onClick={handleConfirmUnbind}
                  className="rounded-lg bg-destructive px-4 py-2 text-xs font-medium text-destructive-foreground hover:bg-destructive/90"
                >
                  {t.device.confirmUnbind}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {viewMode === 'list' && (
          <div className="flex items-center justify-end border-t bg-muted/20 px-6 py-3">
            <button
              onClick={onClose}
              className="rounded-lg border bg-card px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted"
            >
              {t.device.close}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
