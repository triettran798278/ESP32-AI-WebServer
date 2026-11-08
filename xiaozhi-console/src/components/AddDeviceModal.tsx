import { useState, useEffect } from 'react';
import { X, Cpu, Volume2, Laptop, Sparkles, Check, Loader2 } from 'lucide-react';
import { useToast } from './Toast';
import { SupportedLanguage, TRANSLATIONS } from '../i18n';
import { Agent } from '../types';
import { bindActivationCode } from '../api/client';

interface AddDeviceModalProps {
  open: boolean;
  language: SupportedLanguage;
  agents: Agent[];
  activeAgentId?: string;
  onClose: () => void;
  onDeviceRegistered: () => void;
  onManualAddDevice: (mac: string, agentId: string, deviceName?: string) => Promise<void>;
}

export function AddDeviceModal({
  open,
  language,
  agents,
  activeAgentId,
  onClose,
  onDeviceRegistered,
  onManualAddDevice,
}: AddDeviceModalProps) {
  const { error, success } = useToast();
  const t = TRANSLATIONS[language];

  // Mode: activation code entry (Method A - Default) vs manual MAC binding (Method B)
  const [activeTab, setActiveTab] = useState<'activation' | 'manual'>('activation');

  // Method A State: User enters 6 digits spoken/printed by ESP32
  const [digits, setDigits] = useState<string[]>(['', '', '', '', '', '']);
  const [selectedAgentId, setSelectedAgentId] = useState<string>(activeAgentId || (agents[0]?.id || 'agent_101'));
  const [deviceName, setDeviceName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [activatedSuccess, setActivatedSuccess] = useState(false);

  // Method B State: Manual MAC entry
  const [manualMac, setManualMac] = useState('');
  const [manualDeviceName, setManualDeviceName] = useState('');
  const [manualAgentId, setManualAgentId] = useState(activeAgentId || (agents[0]?.id || 'agent_101'));
  const [manualSubmitting, setManualSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      const defaultAgent = activeAgentId || agents[0]?.id || 'agent_101';
      setSelectedAgentId(defaultAgent);
      setManualAgentId(defaultAgent);
      setDigits(['', '', '', '', '', '']);
      setDeviceName('');
      setActivatedSuccess(false);
    }
  }, [open, activeAgentId]);

  const handleDigitChange = (index: number, val: string) => {
    const clean = val.replace(/\D/g, '').slice(-1);
    const updated = [...digits];
    updated[index] = clean;
    setDigits(updated);

    if (clean && index < 5) {
      document.getElementById(`esp32-activation-digit-${index + 1}`)?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      document.getElementById(`esp32-activation-digit-${index - 1}`)?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const pasteData = e.clipboardData.getData('text').trim().replace(/\D/g, '');
    if (pasteData.length === 6) {
      e.preventDefault();
      const newDigits = pasteData.split('');
      setDigits(newDigits);
      document.getElementById('esp32-activation-digit-5')?.focus();
    }
  };

  const handleActivateByCode = async () => {
    const code = digits.join('');
    if (code.length !== 6) {
      error(language === 'vi' ? 'Vui lòng nhập đủ 6 chữ số mã kích hoạt' : 'Please enter all 6 digits of activation code');
      return;
    }

    setSubmitting(true);
    try {
      await bindActivationCode(code, selectedAgentId, deviceName.trim() || undefined);
      setActivatedSuccess(true);
      success(language === 'vi' ? 'Kích hoạt thiết bị thành công!' : 'Device activated successfully!');
      onDeviceRegistered();
      setTimeout(() => {
        onClose();
      }, 1500);
    } catch (e: any) {
      error(e.message || 'Activation failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleManualSubmit = async () => {
    if (!manualMac.trim()) {
      error(language === 'vi' ? 'Vui lòng nhập địa chỉ MAC' : 'Please enter MAC address');
      return;
    }
    setManualSubmitting(true);
    try {
      await onManualAddDevice(manualMac.trim(), manualAgentId, manualDeviceName.trim() || undefined);
      setManualMac('');
      setManualDeviceName('');
      onClose();
    } catch (e: any) {
      error(e.message || 'Binding failed');
    } finally {
      setManualSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="relative flex flex-col w-full max-w-lg rounded-xl border bg-card shadow-2xl overflow-hidden p-6 space-y-5">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b pb-3">
          <div className="flex items-center gap-2">
            <Cpu className="size-5 text-primary" />
            <h2 className="text-base font-semibold tracking-tight">
              {language === 'vi' ? 'Kích hoạt & Thêm Thiết bị ESP32' : 'Activate & Add ESP32 Device'}
            </h2>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted-foreground hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="grid grid-cols-2 p-1 bg-muted/60 rounded-lg text-xs font-medium">
          <button
            type="button"
            onClick={() => setActiveTab('activation')}
            className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${
              activeTab === 'activation'
                ? 'bg-background text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Volume2 className="size-3.5 text-primary" />
            <span>{language === 'vi' ? 'Mã kích hoạt loa/màn hình' : 'Voice/Screen Activation Code'}</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('manual')}
            className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${
              activeTab === 'manual'
                ? 'bg-background text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Laptop className="size-3.5 text-muted-foreground" />
            <span>{language === 'vi' ? 'Gán MAC thủ công' : 'Manual MAC Binding'}</span>
          </button>
        </div>

        {/* Tab 1: Enter 6-digit Activation Code spoken/printed by ESP32 */}
        {activeTab === 'activation' && (
          <div className="space-y-4">
            {/* Guide Banner */}
            <div className="rounded-xl border border-primary/20 bg-primary/5 p-3.5 text-xs text-muted-foreground flex gap-2.5 items-start">
              <Volume2 className="size-4 text-primary shrink-0 mt-0.5 animate-pulse" />
              <div className="space-y-1">
                <p className="font-medium text-foreground">
                  {language === 'vi'
                    ? 'Nghe mã 6 chữ số phát qua loa hoặc xem trên màn hình ESP32'
                    : 'Listen to the 6-digit code from the speaker or check the ESP32 screen'}
                </p>
                <p className="text-[11px] leading-relaxed">
                  {language === 'vi'
                    ? 'Sau khi kết nối Wi-Fi, thiết bị chưa liên kết sẽ tự động phát âm thanh mã xác minh 6 chữ số. Nhập mã này bên dưới để liên kết với trợ lý AI.'
                    : 'After connecting to Wi-Fi, the unbound ESP32 speaks out and displays a 6-digit verification code. Enter it below to bind.'}
                </p>
              </div>
            </div>

            {/* Agent Profile Selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">
                {language === 'vi' ? 'Chọn Hồ sơ Agent muốn liên kết' : 'Assign to Agent Profile'}
              </label>
              <select
                value={selectedAgentId}
                onChange={e => setSelectedAgentId(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-ring"
              >
                {agents.map(a => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.role})
                  </option>
                ))}
              </select>
            </div>

            {/* 6 Digit Input Boxes */}
            <div className="space-y-1.5" onPaste={handlePaste}>
              <label className="text-xs font-medium text-foreground">
                {language === 'vi' ? 'Nhập mã 6 chữ số từ ESP32' : 'Enter 6-Digit Code from ESP32'}
              </label>
              <div className="flex justify-between gap-2 my-2">
                {digits.map((d, i) => (
                  <input
                    key={i}
                    id={`esp32-activation-digit-${i}`}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={d}
                    onChange={e => handleDigitChange(i, e.target.value)}
                    onKeyDown={e => handleKeyDown(i, e)}
                    className="size-11 rounded-lg border text-center text-xl font-mono font-bold bg-background text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all shadow-xs"
                    placeholder="•"
                  />
                ))}
              </div>
            </div>

            {/* Device Name (Optional) */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">
                {language === 'vi' ? 'Tên thiết bị (Tùy chọn)' : 'Device Name (Optional)'}
              </label>
              <input
                type="text"
                value={deviceName}
                onChange={e => setDeviceName(e.target.value)}
                placeholder={language === 'vi' ? 'VD: Trợ lý bàn làm việc ESP32' : 'e.g. Desk Companion ESP32'}
                className="w-full rounded-md border bg-background px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {activatedSuccess && (
              <div className="flex items-center gap-2 p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-emerald-600 dark:text-emerald-400 text-xs font-semibold animate-in fade-in">
                <Check className="size-4" />
                <span>{language === 'vi' ? 'Kích hoạt thành công! Thiết bị đã sẵn sàng.' : 'Activation complete! Device is ready.'}</span>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Manual MAC Binding (Method B) */}
        {activeTab === 'manual' && (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">
                {language === 'vi' ? 'Hồ sơ AI Agent liên kết' : 'Assign to Agent Profile'}
              </label>
              <select
                value={manualAgentId}
                onChange={e => setManualAgentId(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-ring"
              >
                {agents.map(a => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.role})
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">
                {language === 'vi' ? 'Địa chỉ MAC thiết bị' : 'Device MAC Address'}
              </label>
              <input
                type="text"
                value={manualMac}
                onChange={e => setManualMac(e.target.value)}
                placeholder="VD: 30:ED:A0:29:54:4C hoặc AA:BB:CC:11:22:33"
                className="w-full rounded-md border bg-background px-3 py-2 text-xs font-mono outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">
                {t.addDeviceModal.agentNameLabel}
              </label>
              <input
                type="text"
                value={manualDeviceName}
                onChange={e => setManualDeviceName(e.target.value)}
                placeholder={t.addDeviceModal.agentNamePlaceholder}
                className="w-full rounded-md border bg-background px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            <p className="text-[11px] text-muted-foreground">
              {language === 'vi'
                ? '* Chế độ gán MAC thủ công được duy trì cho mục đích phát triển, kiểm thử ảo (Virtual PC) và quản trị viên.'
                : '* Manual MAC binding is preserved for development, virtual testing nodes, and administrative overrides.'}
            </p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex justify-end gap-3 pt-3 border-t">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
          >
            {t.addDeviceModal.cancel}
          </button>

          {activeTab === 'activation' && (
            <button
              type="button"
              onClick={handleActivateByCode}
              disabled={submitting || digits.join('').length !== 6 || activatedSuccess}
              className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 flex items-center gap-1.5"
            >
              {submitting ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  <span>{language === 'vi' ? 'Đang kích hoạt...' : 'Activating...'}</span>
                </>
              ) : (
                <>
                  <Sparkles className="size-3.5" />
                  <span>{language === 'vi' ? 'Kích hoạt ngay' : 'Activate Now'}</span>
                </>
              )}
            </button>
          )}

          {activeTab === 'manual' && (
            <button
              type="button"
              onClick={handleManualSubmit}
              disabled={manualSubmitting || !manualMac.trim()}
              className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {manualSubmitting ? (language === 'vi' ? 'Đang gán...' : 'Binding...') : t.addDeviceModal.submit}
            </button>
          )}
        </div>

      </div>
    </div>
  );
}
