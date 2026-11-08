import { useState } from 'react';
import { Agent, AgentConfig } from '../types';
import { INITIAL_VOICES, INITIAL_MODELS, MCP_TOOLS } from '../data/mockData';
import { X, Volume2, Search, RotateCcw, Sparkles, ShieldAlert, Laptop, Check } from 'lucide-react';
import { useToast } from './Toast';
import { SupportedLanguage, TRANSLATIONS } from '../i18n';
import { testThingsBoard } from '../api/client';

interface ConfigModalProps {
  open: boolean;
  agent: Agent;
  language: SupportedLanguage;
  onClose: () => void;
  onSave: (updatedConfig: AgentConfig) => void;
}

export function ConfigModal({ open, agent, language, onClose, onSave }: ConfigModalProps) {
  const { success } = useToast();
  const t = TRANSLATIONS[language];
  const [activeTab, setActiveTab] = useState<'role' | 'model' | 'extensions'>('role');
  const [config, setConfig] = useState<AgentConfig>(() => JSON.parse(JSON.stringify(agent.config)));
  const [voiceSearch, setVoiceSearch] = useState('');
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);

  const [tbTesting, setTbTesting] = useState(false);
  const [tbTestStatus, setTbTestStatus] = useState<string | null>(null);

  if (!open) return null;

  const handleTestTbConnection = async () => {
    setTbTesting(true);
    setTbTestStatus(null);
    try {
      const host = config.integrations?.thingsboard?.host;
      const key = config.integrations?.thingsboard?.api_key;
      const res = await testThingsBoard(agent.id, host, key);
      if (res.status === 'success') {
        setTbTestStatus(`✓ ${res.message || 'ThingsBoard connection successful!'}`);
        success(language === 'vi' ? 'Kết nối ThingsBoard thành công!' : 'Connected to ThingsBoard successfully!');
      } else {
        setTbTestStatus(`✕ ${res.message || 'Connection failed'}`);
      }
    } catch (e: any) {
      setTbTestStatus(`✕ Connection error: ${e.message}`);
    } finally {
      setTbTesting(false);
    }
  };

  const filteredVoices = INITIAL_VOICES.filter(v => 
    v.name.toLowerCase().includes(voiceSearch.toLowerCase()) || 
    v.tags.some(tag => tag.toLowerCase().includes(voiceSearch.toLowerCase())) || 
    v.description.toLowerCase().includes(voiceSearch.toLowerCase())
  );

  const selectedVoice = INITIAL_VOICES.find(v => v.id === config.ttsVoice) || INITIAL_VOICES[0];

  const handlePlayVoice = (vId: string) => {
    if (playingVoiceId === vId) {
      setPlayingVoiceId(null);
      return;
    }
    setPlayingVoiceId(vId);
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      gain.gain.setValueAtTime(0.1, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.2);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 1.2);
    } catch {}
    setTimeout(() => {
      setPlayingVoiceId(null);
    }, 1500);
  };

  const handleRestoreDefaultCharacter = () => {
    setConfig(prev => ({
      ...prev,
      character: selectedVoice.description || (language === 'vi' ? 'Bạn là một trợ lý AI thông minh, nhiệt tình và thân thiện.' : 'You are an intelligent, enthusiastic and helpful AI companion.')
    }));
  };

  const handleToggleMcp = (toolId: string) => {
    setConfig(prev => {
      const exists = prev.mcpEndpoints.includes(toolId);
      return {
        ...prev,
        mcpEndpoints: exists
          ? prev.mcpEndpoints.filter(id => id !== toolId)
          : [...prev.mcpEndpoints, toolId]
      };
    });
  };

  const handleSave = () => {
    onSave(config);
    success(t.config.savedSuccess);
    onClose();
  };

  const characterTokens = Math.round(config.character.length * 1.5);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="relative flex flex-col w-full max-w-3xl h-[min(48rem,calc(100vh-2rem))] rounded-xl border bg-card shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold tracking-tight">
              {agent.name} <span className="text-muted-foreground font-normal">· {t.config.title}</span>
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b bg-muted/20 px-6 pt-2">
          <button
            onClick={() => setActiveTab('role')}
            className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === 'role'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t.config.roleTab}
          </button>
          <button
            onClick={() => setActiveTab('model')}
            className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === 'model'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t.config.modelTab}
          </button>
          <button
            onClick={() => setActiveTab('extensions')}
            className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === 'extensions'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t.config.extensionsTab}
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* TAB 1: ROLE */}
          {activeTab === 'role' && (
            <div className="space-y-6 animate-in fade-in duration-150">
              {/* Language Selection */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">{t.config.languageLabel}</label>
                <select
                  value={config.language}
                  onChange={e => setConfig({ ...config, language: e.target.value })}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="en">English (en)</option>
                  <option value="vi">Tiếng Việt (vi)</option>
                </select>
              </div>

              {/* TTS Voice Select */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-foreground">{t.config.roleVoice}</label>
                  <div className="relative w-44">
                    <Search className="absolute left-2.5 top-2 size-3.5 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder={t.config.searchVoice}
                      value={voiceSearch}
                      onChange={e => setVoiceSearch(e.target.value)}
                      className="w-full rounded-md border bg-background pl-8 pr-2 py-1 text-xs outline-none focus:ring-2 focus:ring-ring"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-48 overflow-y-auto p-1 border rounded-lg bg-muted/10">
                  {filteredVoices.map(v => {
                    const isSelected = config.ttsVoice === v.id;
                    const isPlaying = playingVoiceId === v.id;
                    return (
                      <div
                        key={v.id}
                        onClick={() => setConfig({ ...config, ttsVoice: v.id })}
                        className={`flex items-center justify-between p-3 rounded-lg border text-left cursor-pointer transition-all ${
                          isSelected
                            ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                            : 'border-border bg-card hover:border-primary/30'
                        }`}
                      >
                        <div className="min-w-0 pr-2">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-sm text-foreground">{v.name}</span>
                            <span className="text-[11px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground">
                              {v.gender}
                            </span>
                          </div>
                          <div className="flex gap-1 mt-1">
                            {v.tags.map(tag => (
                              <span key={tag} className="text-[10px] text-muted-foreground">
                                #{tag}
                              </span>
                            ))}
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={e => {
                            e.stopPropagation();
                            handlePlayVoice(v.id);
                          }}
                          className={`size-8 shrink-0 rounded-full flex items-center justify-center transition-colors ${
                            isPlaying
                              ? 'bg-primary text-primary-foreground animate-pulse'
                              : 'bg-muted text-muted-foreground hover:bg-primary/20 hover:text-primary'
                          }`}
                          title="Preview voice"
                        >
                          <Volume2 className="size-4" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Character Persona Prompt */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <label className="text-sm font-medium text-foreground">{t.config.characterPersona}</label>
                    <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={config.customCharacter}
                        onChange={e => setConfig({ ...config, customCharacter: e.target.checked })}
                        className="rounded border-border text-primary focus:ring-ring"
                      />
                      <span>{t.config.customPersona}</span>
                    </label>
                  </div>
                  {config.customCharacter && (
                    <button
                      type="button"
                      onClick={handleRestoreDefaultCharacter}
                      className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      <RotateCcw className="size-3" /> {t.config.restoreDefault}
                    </button>
                  )}
                </div>

                <div className="relative">
                  <textarea
                    rows={4}
                    disabled={!config.customCharacter}
                    value={config.character}
                    onChange={e => setConfig({ ...config, character: e.target.value })}
                    placeholder={t.config.personaPlaceholder}
                    className={`w-full rounded-md border bg-background p-3 text-sm outline-none focus:ring-2 focus:ring-ring resize-none ${
                      !config.customCharacter ? 'opacity-60 bg-muted/30 cursor-not-allowed' : ''
                    }`}
                  />
                  <div className="text-right text-[11px] text-muted-foreground mt-1">
                    {characterTokens} / 4000 {t.config.tokens}
                  </div>
                </div>
              </div>

              {/* Speech Settings */}
              <div className="space-y-3 pt-2 border-t">
                <h3 className="text-sm font-medium text-foreground">{t.config.speechSettings}</h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {/* ASR speed */}
                  <div className="space-y-1.5">
                    <span className="text-xs text-muted-foreground">{t.config.recognitionSpeed}</span>
                    <select
                      value={config.asrSpeed}
                      onChange={e => setConfig({ ...config, asrSpeed: e.target.value as any })}
                      className="w-full rounded-md border bg-background px-2.5 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                    >
                      <option value="slow">{t.config.slow}</option>
                      <option value="standard">{t.config.standard}</option>
                      <option value="fast">{t.config.fast}</option>
                    </select>
                  </div>

                  {/* TTS speed */}
                  <div className="space-y-1.5">
                    <span className="text-xs text-muted-foreground">{t.config.replySpeed}</span>
                    <select
                      value={config.ttsSpeechSpeed}
                      onChange={e => setConfig({ ...config, ttsSpeechSpeed: e.target.value as any })}
                      className="w-full rounded-md border bg-background px-2.5 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                    >
                      <option value="slow">{t.config.slow}</option>
                      <option value="standard">{t.config.standard}</option>
                      <option value="fast">{t.config.fast}</option>
                    </select>
                  </div>

                  {/* TTS pitch */}
                  <div className="space-y-1.5">
                    <span className="text-xs text-muted-foreground">{t.config.replyPitch}</span>
                    <select
                      value={config.ttsPitch}
                      onChange={e => setConfig({ ...config, ttsPitch: e.target.value as any })}
                      className="w-full rounded-md border bg-background px-2.5 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                    >
                      <option value="low">{t.config.low}</option>
                      <option value="standard">{t.config.standard}</option>
                      <option value="high">{t.config.high}</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: MODEL & MEMORY */}
          {activeTab === 'model' && (
            <div className="space-y-6 animate-in fade-in duration-150">
              {/* LLM Model Selection */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">{t.config.llmModel}</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {INITIAL_MODELS.map(m => {
                    const isSelected = config.llmModel === m.id;
                    return (
                      <div
                        key={m.id}
                        onClick={() => setConfig({ ...config, llmModel: m.id })}
                        className={`p-3.5 rounded-lg border text-left cursor-pointer transition-all ${
                          isSelected
                            ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                            : 'border-border bg-card hover:border-primary/30'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-sm text-foreground">{m.name}</span>
                          {m.badge && (
                            <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                              {m.badge}
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground leading-relaxed line-clamp-2">
                          {m.description}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: EXTENSIONS (MCP & SPEAKERS) */}
          {activeTab === 'extensions' && (
            <div className="space-y-6 animate-in fade-in duration-150">
              {/* ThingsBoard IoT Integration (MCP) */}
              <div className="space-y-3 p-4 rounded-xl border bg-card/60 shadow-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Laptop className="size-4 text-primary" />
                    <h3 className="text-sm font-semibold text-foreground">ThingsBoard IoT Platform (MCP)</h3>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                    Alpha 0.1 · Active
                  </span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {language === 'vi'
                    ? 'Tích hợp máy chủ IoT ThingsBoard để đọc dữ liệu cảm biến đo xa (Telemetry) và thực thi điều khiển qua MCP tools.'
                    : 'Connect your ThingsBoard IoT instance to inspect telemetry, list sensors, and issue authorized commands via MCP tools.'}
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">ThingsBoard Host URL</label>
                    <input
                      type="text"
                      value={config.integrations?.thingsboard?.host || 'https://codehelpers.tech'}
                      onChange={e => {
                        const host = e.target.value;
                        setConfig(prev => ({
                          ...prev,
                          integrations: {
                            ...prev.integrations,
                            thingsboard: {
                              ...prev.integrations?.thingsboard,
                              host,
                            }
                          }
                        }));
                      }}
                      placeholder="https://codehelpers.tech"
                      className="w-full rounded-md border bg-background px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">
                      ThingsBoard REST API Key
                      <span className="text-muted-foreground font-normal ml-1">
                        ({config.integrations?.thingsboard?.is_configured ? (language === 'vi' ? 'Đã lưu' : 'Configured') : (language === 'vi' ? 'Chưa có' : 'Not set')})
                      </span>
                    </label>
                    <input
                      type="password"
                      defaultValue={config.integrations?.thingsboard?.api_key || ''}
                      onChange={e => {
                        const api_key = e.target.value;
                        setConfig(prev => ({
                          ...prev,
                          integrations: {
                            ...prev.integrations,
                            thingsboard: {
                              ...prev.integrations?.thingsboard,
                              api_key,
                            }
                          }
                        }));
                      }}
                      placeholder={config.integrations?.thingsboard?.api_key ? '••••••••••••••••' : 'tb_...'}
                      className="w-full rounded-md border bg-background px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">
                      {language === 'vi' ? 'Tên hiển thị tích hợp' : 'Integration Display Name'}
                    </label>
                    <input
                      type="text"
                      value={config.integrations?.thingsboard?.display_name || 'CodeHelpers Production IoT'}
                      onChange={e => {
                        const display_name = e.target.value;
                        setConfig(prev => ({
                          ...prev,
                          integrations: {
                            ...prev.integrations,
                            thingsboard: {
                              ...prev.integrations?.thingsboard,
                              display_name,
                            }
                          }
                        }));
                      }}
                      className="w-full rounded-md border bg-background px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">
                      {language === 'vi' ? 'Chính sách công cụ (Tool Policy)' : 'MCP Tool Policy'}
                    </label>
                    <select
                      value={config.tool_policy || 'full_control'}
                      onChange={e => setConfig(prev => ({ ...prev, tool_policy: e.target.value as any }))}
                      className="w-full rounded-md border bg-background px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-ring"
                    >
                      <option value="full_control">
                        {language === 'vi' ? 'Toàn quyền (Telemetry, Danh sách & RPC)' : 'Full Control (Telemetry, List & RPC)'}
                      </option>
                      <option value="read_only_telemetry">
                        {language === 'vi' ? 'Chỉ đọc (Chỉ cảm biến đo xa - Safe Default)' : 'Read-Only (Telemetry & Sensors Only - Safe Default)'}
                      </option>
                    </select>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t text-xs">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <ShieldAlert className="size-3.5 text-amber-500 shrink-0" />
                    <span className="text-[11px]">
                      {language === 'vi'
                        ? 'Lưu ý Alpha 0.1: MCP chia sẻ tệp cấu hình agent_profile.json. Phân lập đa phiên đồng thời sẽ hoàn thiện ở Phase 2.'
                        : 'Alpha 0.1 Notice: MCP reads active credentials from shared agent_profile.json. Concurrent session isolation is planned for Phase 2.'}
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={handleTestTbConnection}
                    disabled={tbTesting}
                    className="inline-flex items-center gap-1.5 rounded-lg border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50"
                  >
                    <Check className="size-3.5 text-emerald-500" />
                    {tbTesting ? (language === 'vi' ? 'Đang kiểm tra...' : 'Testing...') : (language === 'vi' ? 'Kiểm tra kết nối' : 'Test Connection')}
                  </button>
                </div>

                {tbTestStatus && (
                  <div className="p-2.5 rounded-md bg-muted/30 text-xs font-mono text-foreground border">
                    {tbTestStatus}
                  </div>
                )}
              </div>

              {/* Common MCP Tools */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-foreground">{t.config.mcpTools}</h3>
                    <p className="text-xs text-muted-foreground">
                      {t.config.mcpDesc}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {MCP_TOOLS.map(tool => {
                    const isEnabled = config.mcpEndpoints.includes(tool.id);
                    return (
                      <div
                        key={tool.id}
                        className="flex items-start justify-between p-3.5 rounded-lg border bg-card gap-3"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5">
                            <Sparkles className="size-3.5 text-primary" />
                            <span className="text-xs font-semibold text-foreground">{tool.title}</span>
                          </div>
                          <p className="text-[11px] text-muted-foreground leading-snug">
                            {tool.description}
                          </p>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleToggleMcp(tool.id)}
                          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                            isEnabled ? 'bg-primary' : 'bg-muted'
                          }`}
                        >
                          <span
                            className={`inline-block size-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                              isEnabled ? 'translate-x-4' : 'translate-x-0'
                            }`}
                          />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t bg-muted/20 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border bg-card px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {t.config.cancel}
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 shadow-sm"
          >
            {t.config.saveConfig}
          </button>
        </div>
      </div>
    </div>
  );
}
