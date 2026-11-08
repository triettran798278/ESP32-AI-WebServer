import { useState, useEffect, useMemo, useRef } from 'react';
import { Agent, AgentConfig, Device, ChatSession } from './types';
import { loadAgentsFromStorage, saveAgentsToStorage } from './data/mockData';
import {
  fetchAgents,
  createAgent,
  updateAgent,
  deleteAgent,
  fetchDevices,
  bindDevice,
  unbindDevice,
  testThingsBoard,
  fetchThingsBoardTelemetry,
} from './api/client';
import { Header } from './components/Header';
import { AgentCard } from './components/AgentCard';
import { ConfigModal } from './components/ConfigModal';
import { ChatModal } from './components/ChatModal';
import { DeviceModal } from './components/DeviceModal';
import { AddDeviceModal } from './components/AddDeviceModal';
import { CreateAgentModal } from './components/CreateAgentModal';
import { RenameAgentModal } from './components/RenameAgentModal';
import { DeleteAgentModal } from './components/DeleteAgentModal';
import { useToast } from './components/Toast';
import { SupportedLanguage, TRANSLATIONS } from './i18n';
import {
  Bot,
  Search,
  X,
  Plus,
  ChevronDown,
  Cpu,
  Laptop,
  Check,
  ShieldAlert,
  Trash2,
  RefreshCw,
  ExternalLink,
  Radio,
  SlidersHorizontal,
  ShieldCheck,
} from 'lucide-react';

export function App() {
  const { success, error } = useToast();

  // State
  const [agents, setAgents] = useState<Agent[]>(() => loadAgentsFromStorage());
  const [allDevices, setAllDevices] = useState<Device[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentNavTab, setCurrentNavTab] = useState('devices');

  // Integrations Tab state
  const [tbDevices, setTbDevices] = useState<any[]>([]);
  const [tbTesting, setTbTesting] = useState(false);
  const [tbTestResult, setTbTestResult] = useState<string | null>(null);
  const [isLoadingTelemetry, setIsLoadingTelemetry] = useState(false);

  // Two allowed languages: English and Vietnamese (defaults to English)
  const [language, setLanguage] = useState<SupportedLanguage>(() => {
    const saved = localStorage.getItem('xz_console_lang');
    return saved === 'vi' ? 'vi' : 'en';
  });

  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>('light');

  const t = TRANSLATIONS[language];

  // Modals state
  const [openConfigModal, setOpenConfigModal] = useState(false);
  const [openChatModal, setOpenChatModal] = useState(false);
  const [openDeviceModal, setOpenDeviceModal] = useState(false);
  const [openAddDeviceModal, setOpenAddDeviceModal] = useState(false);
  const [openCreateAgentModal, setOpenCreateAgentModal] = useState(false);
  const [openRenameModal, setOpenRenameModal] = useState(false);
  const [openDeleteModal, setOpenDeleteModal] = useState(false);

  // Split button dropdown
  const [splitDropdownOpen, setSplitDropdownOpen] = useState(false);
  const splitRef = useRef<HTMLDivElement>(null);

  // Sync with Backend
  const loadData = async () => {
    try {
      const remoteAgents = await fetchAgents();
      if (remoteAgents && remoteAgents.length > 0) {
        setAgents(remoteAgents);
        saveAgentsToStorage(remoteAgents);
      }
      const remoteDevices = await fetchDevices();
      setAllDevices(remoteDevices);
    } catch (e) {
      console.warn('Backend sync failed, using cached store', e);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    localStorage.setItem('xz_console_lang', language);
  }, [language]);

  useEffect(() => {
    const root = document.documentElement;
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const applyTheme = () => {
      const isDark = theme === 'system' ? mediaQuery.matches : theme === 'dark';
      root.classList.toggle('dark', isDark);
    };

    applyTheme();
    mediaQuery.addEventListener('change', applyTheme);
    return () => mediaQuery.removeEventListener('change', applyTheme);
  }, [theme]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (splitRef.current && !splitRef.current.contains(e.target as Node)) {
        setSplitDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Fetch telemetry when navigating to integrations tab
  useEffect(() => {
    if (currentNavTab === 'integrations') {
      refreshTelemetry();
    }
  }, [currentNavTab]);

  const refreshTelemetry = async () => {
    setIsLoadingTelemetry(true);
    try {
      const res = await fetchThingsBoardTelemetry('agent_101');
      if (res.status === 'success') {
        setTbDevices(res.devices || []);
      }
    } catch (e) {
      console.warn('Failed to load telemetry preview', e);
    } finally {
      setIsLoadingTelemetry(false);
    }
  };

  const activeAgent = useMemo(() => {
    return agents.find(a => a.id === selectedAgentId) || agents[0];
  }, [agents, selectedAgentId]);

  const filteredAgents = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return agents;
    return agents.filter(a =>
      a.name.toLowerCase().includes(q) ||
      a.role.toLowerCase().includes(q) ||
      a.model.toLowerCase().includes(q) ||
      a.devices.some(d => d.name.toLowerCase().includes(q) || d.mac_address.toLowerCase().includes(q))
    );
  }, [agents, searchQuery]);

  // Actions
  const handleCreateAgent = async (name: string) => {
    try {
      await createAgent({
        name,
        role: 'Assistant',
        config: {
          language: language,
          character: language === 'vi' ? 'Bạn là một trợ lý AI thông minh, nhiệt tình và thân thiện.' : 'You are an intelligent, enthusiastic and helpful AI companion.'
        } as any,
      });
      await loadData();
      success(t.createAgentModal.created);
    } catch (e: any) {
      error(e.message || 'Create agent failed');
    }
  };

  const handleRenameAgent = async (newName: string) => {
    if (!activeAgent) return;
    try {
      await updateAgent(activeAgent.id, { name: newName });
      await loadData();
      success(t.renameAgentModal.updated);
    } catch (e: any) {
      error(e.message || 'Rename failed');
    }
  };

  const handleDeleteAgent = async () => {
    if (!activeAgent) return;
    try {
      await deleteAgent(activeAgent.id);
      await loadData();
      success(t.deleteAgentModal.deleted);
    } catch (e: any) {
      error(e.message || 'Delete failed');
    }
  };

  const handleUpdateConfig = async (updatedConfig: AgentConfig) => {
    if (!activeAgent) return;
    try {
      await updateAgent(activeAgent.id, {
        config: updatedConfig,
        tool_policy: updatedConfig.tool_policy,
        integrations: updatedConfig.integrations,
      });
      await loadData();
      success(t.config.savedSuccess);
    } catch (e: any) {
      error(e.message || 'Update config failed');
    }
  };

  const handleUpdateDevices = async (_updatedDevices: Device[]) => {
    if (!activeAgent) return;
    await loadData();
  };

  const handleUpdateChats = (updatedChats: ChatSession[]) => {
    if (!activeAgent) return;
    setAgents(prev => prev.map(a => {
      if (a.id !== activeAgent.id) return a;
      return {
        ...a,
        chats: updatedChats,
        lastSeen: 'Just now',
      };
    }));
  };

  const handleManualAddDeviceGlobal = async (mac: string, agentId: string, customAgentName?: string) => {
    try {
      await bindDevice(mac, agentId, customAgentName || `ESP32 (${mac.slice(-5)})`);
      await loadData();
      success(language === 'vi' ? 'Gán thiết bị thành công!' : 'Device bound successfully!');
    } catch (e: any) {
      error(e.message || 'Bind device failed');
    }
  };

  const handleUnbindDeviceGlobal = async (mac: string) => {
    try {
      await unbindDevice(mac);
      await loadData();
      success(t.device.unbindSuccess);
    } catch (e: any) {
      error(e.message || 'Unbind failed');
    }
  };

  const handleTestGlobalTb = async () => {
    setTbTesting(true);
    setTbTestResult(null);
    try {
      const res = await testThingsBoard('agent_101');
      if (res.status === 'success') {
        setTbTestResult(`✓ ${res.message}`);
        success(language === 'vi' ? 'Kết nối thành công!' : 'Connected successfully!');
      } else {
        setTbTestResult(`✕ ${res.message}`);
        error(res.message);
      }
    } catch (e: any) {
      setTbTestResult(`✕ ${e.message}`);
      error(e.message);
    } finally {
      setTbTesting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground antialiased selection:bg-primary/20 selection:text-primary">
      {/* Top Navbar */}
      <Header
        currentTab={currentNavTab}
        onTabChange={setCurrentNavTab}
        theme={theme}
        onThemeChange={setTheme}
        language={language}
        onLanguageChange={setLanguage}
      />

      {/* Main Content */}
      <main className="mx-auto w-[90%] max-w-[100rem] py-6 flex-1 space-y-6">
        {/* ==================================================================== */}
        {/* VIEW 1: AGENTS CONSOLE */}
        {/* ==================================================================== */}
        {currentNavTab === 'agents' && (
          <div className="space-y-6 animate-in fade-in duration-200">
            {/* Header Card with Gradient Aura */}
            <div className="relative overflow-hidden rounded-xl border bg-card px-4 py-4 shadow-xs sm:px-5">
              <div className="pointer-events-none absolute -right-16 -top-20 size-48 rounded-full bg-primary/10 blur-3xl" />

              <div className="relative flex flex-wrap items-center justify-between gap-4">
                {/* Left: Icon & Title */}
                <div className="flex items-center gap-3">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-inset ring-blue-100 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-400/20 shadow-xs">
                    <Bot className="size-5" />
                  </span>
                  <div>
                    <h1 className="text-xl font-bold tracking-tight text-foreground">{t.agents.title}</h1>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {t.agents.total(agents.length)}
                    </p>
                  </div>
                </div>

                {/* Right: Search Bar & Action Buttons */}
                <div className="flex w-full min-w-0 items-center gap-2.5 sm:ml-auto sm:w-auto">
                  <label className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg border bg-card px-3 focus-within:ring-2 focus-within:ring-ring sm:w-80 sm:flex-none transition-shadow">
                    <Search className="size-4 shrink-0 text-muted-foreground" />
                    <input
                      aria-label={t.agents.search}
                      value={searchQuery}
                      onChange={e => setSearchQuery(e.target.value)}
                      className="min-w-0 flex-1 bg-transparent text-xs outline-none text-foreground placeholder:text-muted-foreground"
                      placeholder={t.agents.search}
                    />
                    {searchQuery && (
                      <button
                        type="button"
                        onClick={() => setSearchQuery('')}
                        className="shrink-0 text-muted-foreground hover:text-foreground"
                        title={t.agents.clearSearch}
                      >
                        <X className="size-3.5" />
                      </button>
                    )}
                  </label>

                  {/* Split Action Button */}
                  <div className="flex shrink-0 relative" ref={splitRef}>
                    <button
                      onClick={() => setOpenAddDeviceModal(true)}
                      className="inline-flex h-9 items-center gap-1.5 rounded-l-lg bg-primary px-3 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
                    >
                      <Plus className="size-4" />
                      <span>{t.agents.addDevice}</span>
                    </button>

                    <button
                      onClick={() => setSplitDropdownOpen(!splitDropdownOpen)}
                      className="inline-flex h-9 w-8 items-center justify-center rounded-r-lg border-l border-primary-foreground/25 bg-primary px-0 text-primary-foreground hover:bg-primary/90 transition-colors"
                      aria-label="More options"
                    >
                      <ChevronDown className="size-4" />
                    </button>

                    {splitDropdownOpen && (
                      <div className="absolute right-0 top-10 w-36 rounded-md border bg-card p-1 shadow-lg z-30 animate-in fade-in duration-100">
                        <button
                          onClick={() => {
                            setSplitDropdownOpen(false);
                            setOpenCreateAgentModal(true);
                          }}
                          className="w-full flex items-center gap-2 rounded px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground text-left"
                        >
                          <Plus className="size-3.5" /> {t.agents.createAgent}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Grid of Agent Cards */}
            {filteredAgents.length === 0 ? (
              <div className="rounded-xl border border-dashed py-16 text-center space-y-3">
                <div className="size-12 rounded-full bg-muted flex items-center justify-center mx-auto">
                  <Bot className="size-6 text-muted-foreground" />
                </div>
                <p className="text-sm font-medium text-foreground">
                  {searchQuery ? t.agents.noMatch : t.agents.empty}
                </p>
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="text-xs text-primary hover:underline"
                  >
                    {t.agents.clearSearch}
                  </button>
                )}
              </div>
            ) : (
              <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3 xl:gap-6 2xl:grid-cols-4">
                {filteredAgents.map(agent => (
                  <AgentCard
                    key={agent.id}
                    agent={agent}
                    language={language}
                    onSelect={() => setSelectedAgentId(agent.id)}
                    onOpenConfig={() => {
                      setSelectedAgentId(agent.id);
                      setOpenConfigModal(true);
                    }}
                    onOpenChat={() => {
                      setSelectedAgentId(agent.id);
                      setOpenChatModal(true);
                    }}
                    onOpenDevice={() => {
                      setSelectedAgentId(agent.id);
                      setOpenDeviceModal(true);
                    }}
                    onOpenRename={() => {
                      setSelectedAgentId(agent.id);
                      setOpenRenameModal(true);
                    }}
                    onOpenDelete={() => {
                      setSelectedAgentId(agent.id);
                      setOpenDeleteModal(true);
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ==================================================================== */}
        {/* VIEW 2: DEVICE MANAGEMENT */}
        {/* ==================================================================== */}
        {currentNavTab === 'devices' && (
          <div className="space-y-6 animate-in fade-in duration-150">
            {/* Header */}
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card p-5 shadow-xs">
              <div className="flex items-center gap-3">
                <span className="flex size-10 items-center justify-center rounded-xl bg-purple-50 text-purple-600 ring-1 ring-inset ring-purple-100 dark:bg-purple-500/10 dark:text-purple-400 dark:ring-purple-400/20 shadow-xs">
                  <Cpu className="size-5" />
                </span>
                <div>
                  <h1 className="text-lg font-bold tracking-tight text-foreground">
                    {language === 'vi' ? 'Quản lý thiết bị phần cứng (ESP32)' : 'Registered Hardware Devices (ESP32)'}
                  </h1>
                  <p className="text-xs text-muted-foreground">
                    {language === 'vi'
                      ? `Tổng số ${allDevices.length} thiết bị · Định danh địa chỉ MAC chuẩn hóa và liên kết Agent Profile`
                      : `Total ${allDevices.length} registered hardware nodes · MAC address normalization and Agent Profile bindings`}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={loadData}
                  className="inline-flex items-center gap-1.5 rounded-lg border bg-background px-3 py-2 text-xs font-medium text-foreground hover:bg-muted"
                >
                  <RefreshCw className="size-3.5" />
                  <span>{language === 'vi' ? 'Làm mới' : 'Refresh'}</span>
                </button>
                <button
                  onClick={() => setOpenAddDeviceModal(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90"
                >
                  <Plus className="size-4" />
                  <span>{t.agents.addDevice}</span>
                </button>
              </div>
            </div>

            {/* Devices Table */}
            <div className="rounded-xl border bg-card shadow-xs overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="px-4 py-3 font-semibold">{language === 'vi' ? 'Thiết bị & Model' : 'Device & Model'}</th>
                      <th className="px-4 py-3 font-semibold">MAC Address</th>
                      <th className="px-4 py-3 font-semibold">Device ID</th>
                      <th className="px-4 py-3 font-semibold">{language === 'vi' ? 'Hồ sơ Agent liên kết' : 'Bound Agent Profile'}</th>
                      <th className="px-4 py-3 font-semibold">{language === 'vi' ? 'Phương thức đăng ký' : 'Registration'}</th>
                      <th className="px-4 py-3 font-semibold">{language === 'vi' ? 'Trạng thái' : 'Status'}</th>
                      <th className="px-4 py-3 font-semibold">Firmware</th>
                      <th className="px-4 py-3 font-semibold">{language === 'vi' ? 'Ngày đăng ký' : 'Registered'}</th>
                      <th className="px-4 py-3 font-semibold text-right">{language === 'vi' ? 'Thao tác' : 'Actions'}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {allDevices.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="py-8 text-center text-muted-foreground">
                          {language === 'vi' ? 'Chưa có thiết bị nào được gán' : 'No devices currently bound.'}
                        </td>
                      </tr>
                    ) : (
                      allDevices.map(dev => (
                        <tr key={dev.mac_address} className="hover:bg-muted/20 transition-colors">
                          <td className="px-4 py-3 font-medium text-foreground">
                            <div className="flex items-center gap-2">
                              <Radio className="size-4 text-primary shrink-0" />
                              <div>
                                <p className="font-semibold text-foreground">{dev.name}</p>
                                <p className="text-[10px] text-muted-foreground">{dev.hardware_model || 'ESP32-S3'}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3 font-mono font-medium text-foreground">
                            {dev.mac_address}
                          </td>
                          <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">
                            {dev.device_id || dev.id}
                          </td>
                          <td className="px-4 py-3">
                            <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
                              <Bot className="size-3" />
                              {dev.agent_name || 'Agent'} ({dev.agent_role || 'Nova'})
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            {dev.registration_status === 'authenticated' || dev.is_auth ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                                <ShieldCheck className="size-3" />
                                <span>{language === 'vi' ? 'Xác thực phần cứng' : 'Authenticated'}</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded-full bg-slate-500/10 border border-slate-500/20 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                                <Laptop className="size-3" />
                                <span>{language === 'vi' ? 'MAC thủ công' : 'Manual MAC'}</span>
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div>
                              <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${
                                dev.status === 'online' ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'
                              }`}>
                                <span className={`size-2 rounded-full ${
                                  dev.status === 'online' ? 'bg-emerald-500 animate-pulse' : 'bg-muted-foreground'
                                }`} />
                                {dev.status === 'online' ? (language === 'vi' ? 'Trực tuyến' : 'Online') : 'Offline'}
                              </span>
                              <p className="text-[10px] text-muted-foreground">{dev.last_seen || 'Just now'}</p>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-muted-foreground font-mono text-[11px]">
                            {dev.firmware_version}
                          </td>
                          <td className="px-4 py-3 text-muted-foreground text-[11px]">
                            {dev.registered_at
                              ? new Date(dev.registered_at * 1000).toLocaleDateString(language === 'vi' ? 'vi-VN' : 'en-US')
                              : (language === 'vi' ? 'Mặc định' : 'Default')}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button
                              onClick={() => handleUnbindDeviceGlobal(dev.mac_address)}
                              className="inline-flex items-center gap-1 rounded-md border border-destructive/30 px-2.5 py-1 text-[11px] font-medium text-destructive hover:bg-destructive/10 transition-colors"
                            >
                              <Trash2 className="size-3" />
                              <span>{language === 'vi' ? 'Hủy gán' : 'Unbind'}</span>
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ==================================================================== */}
        {/* VIEW 3: THINGSBOARD IOT INTEGRATION & MCP */}
        {/* ==================================================================== */}
        {currentNavTab === 'integrations' && (
          <div className="space-y-6 animate-in fade-in duration-150">
            {/* Header Status Card */}
            <div className="rounded-xl border bg-card p-5 shadow-xs space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-inset ring-blue-100 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-400/20 shadow-xs">
                    <Laptop className="size-5" />
                  </span>
                  <div>
                    <h1 className="text-lg font-bold tracking-tight text-foreground">
                      ThingsBoard IoT Platform & MCP Tools
                    </h1>
                    <p className="text-xs text-muted-foreground">
                      {language === 'vi'
                        ? 'Nguồn cấp dữ liệu cảm biến đo xa thời gian thực và thực thi điều khiển cho Agent Profiles.'
                        : 'External IoT telemetry data source & Model Context Protocol execution interface.'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={refreshTelemetry}
                    disabled={isLoadingTelemetry}
                    className="inline-flex items-center gap-1.5 rounded-lg border bg-background px-3 py-2 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50"
                  >
                    <RefreshCw className={`size-3.5 ${isLoadingTelemetry ? 'animate-spin' : ''}`} />
                    <span>{language === 'vi' ? 'Tải lại Telemetry' : 'Reload Telemetry'}</span>
                  </button>
                  <button
                    onClick={handleTestGlobalTb}
                    disabled={tbTesting}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    <Check className="size-3.5" />
                    <span>{tbTesting ? (language === 'vi' ? 'Đang kiểm tra...' : 'Testing...') : (language === 'vi' ? 'Kiểm tra kết nối' : 'Test Connection')}</span>
                  </button>
                </div>
              </div>

              {/* Status Pills Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t">
                <div className="p-3 rounded-lg border bg-muted/20 space-y-1">
                  <div className="text-[11px] font-medium text-muted-foreground">Instance Host URL</div>
                  <div className="text-xs font-semibold text-foreground flex items-center gap-1">
                    <span>https://codehelpers.tech</span>
                    <a href="https://codehelpers.tech" target="_blank" rel="noreferrer" className="text-primary hover:underline">
                      <ExternalLink className="size-3 inline" />
                    </a>
                  </div>
                </div>

                <div className="p-3 rounded-lg border bg-muted/20 space-y-1">
                  <div className="text-[11px] font-medium text-muted-foreground">API Credential Security</div>
                  <div className="text-xs font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                    tb_G5TS...PluA (Masked · Backend Stored)
                  </div>
                </div>

                <div className="p-3 rounded-lg border bg-muted/20 space-y-1">
                  <div className="text-[11px] font-medium text-muted-foreground">MCP Service Status (Port 8009)</div>
                  <div className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                    <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span>SSE Server Active (3 Tools Registered)</span>
                  </div>
                </div>
              </div>

              {tbTestResult && (
                <div className="p-3 rounded-lg bg-muted/30 border text-xs font-mono">
                  {tbTestResult}
                </div>
              )}
            </div>

            {/* Architecture Limitation Notice */}
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 flex items-start gap-3 text-xs">
              <ShieldAlert className="size-4 text-amber-500 shrink-0 mt-0.5" />
              <div className="space-y-1 text-muted-foreground">
                <div className="font-semibold text-foreground">
                  {language === 'vi' ? 'Giới hạn kiến trúc Alpha 0.1' : 'Important Alpha 0.1 Architectural Boundary'}
                </div>
                <p>
                  {language === 'vi'
                    ? 'ThingsBoard là nguồn dữ liệu IoT bên ngoài. Nền tảng quản lý thông tin xác thực và truy xuất qua MCP tools an toàn. Trong bản Alpha 0.1, ThingsBoard MCP Server đọc thông tin xác thực từ tệp agent_profile.json dùng chung. Cơ chế phân lập định tuyến đa phiên đồng thời sẽ được cung cấp ở Phase 2.'
                    : 'ThingsBoard is an external IoT telemetry source. This console manages credentials and authorized MCP data retrieval. In Alpha 0.1, ThingsBoard MCP reads from the active shared agent_profile.json file. Simultaneous multi-tenant session isolation is planned for Phase 2.'}
                </p>
              </div>
            </div>

            {/* Telemetry Preview Table */}
            <div className="rounded-xl border bg-card shadow-xs overflow-hidden space-y-2">
              <div className="px-5 py-3 border-b flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <SlidersHorizontal className="size-4 text-primary" />
                  <h3 className="text-sm font-semibold text-foreground">
                    {language === 'vi' ? 'Dữ liệu thiết bị & Telemetry thực tế từ ThingsBoard' : 'Real-time ThingsBoard Devices & Telemetry'}
                  </h3>
                </div>
                <span className="text-xs text-muted-foreground font-mono">
                  {tbDevices.length} devices discovered
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="px-4 py-2.5 font-semibold">ThingsBoard Device</th>
                      <th className="px-4 py-2.5 font-semibold">Entity ID</th>
                      <th className="px-4 py-2.5 font-semibold">Type</th>
                      <th className="px-4 py-2.5 font-semibold">Latest Telemetry Data</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {tbDevices.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="py-6 text-center text-muted-foreground">
                          {isLoadingTelemetry ? (language === 'vi' ? 'Đang tải dữ liệu...' : 'Loading ThingsBoard telemetry...') : (language === 'vi' ? 'Không có thiết bị hoặc chưa kết nối' : 'No devices fetched.')}
                        </td>
                      </tr>
                    ) : (
                      tbDevices.map(d => (
                        <tr key={d.id} className="hover:bg-muted/20 transition-colors">
                          <td className="px-4 py-2.5 font-medium text-foreground">{d.name}</td>
                          <td className="px-4 py-2.5 font-mono text-muted-foreground text-[11px]">{d.id}</td>
                          <td className="px-4 py-2.5">
                            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase font-semibold text-muted-foreground">
                              {d.type}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 font-mono text-[11px] text-foreground">
                            {Object.keys(d.telemetry || {}).length > 0 ? (
                              JSON.stringify(d.telemetry)
                            ) : (
                              <span className="text-muted-foreground italic">Ready for live telemetry ingestion</span>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Agent Tool Policy Table */}
            <div className="rounded-xl border bg-card p-5 shadow-xs space-y-3">
              <h3 className="text-sm font-semibold text-foreground">
                {language === 'vi' ? 'Phân quyền công cụ theo Agent Profile (Tool Policy)' : 'Agent Profile Tool Access Policy Matrix'}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {agents.map(a => {
                  const policy = a.tool_policy || a.config?.tool_policy || 'full_control';
                  const isReadOnly = policy === 'read_only_telemetry';
                  return (
                    <div key={a.id} className="p-3.5 rounded-lg border bg-muted/10 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-foreground">{a.name} ({a.role})</span>
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${isReadOnly ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400' : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'}`}>
                          {isReadOnly ? 'Read-Only' : 'Full Control'}
                        </span>
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-snug">
                        {isReadOnly
                          ? 'Chỉ có quyền đọc cảm biến đo xa (Telemetry). Không được phép gửi lệnh điều khiển RPC bật/tắt thiết bị.'
                          : 'Được phép đọc danh sách thiết bị, truy vấn Telemetry và thực thi lệnh RPC điều khiển thiết bị thông minh.'}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

      </main>

      {/* Modals */}
      {activeAgent && (
        <>
          <ConfigModal
            open={openConfigModal}
            agent={activeAgent}
            language={language}
            onClose={() => setOpenConfigModal(false)}
            onSave={handleUpdateConfig}
          />

          <ChatModal
            open={openChatModal}
            agent={activeAgent}
            language={language}
            onClose={() => setOpenChatModal(false)}
            onUpdateChats={handleUpdateChats}
          />

          <DeviceModal
            open={openDeviceModal}
            agent={activeAgent}
            language={language}
            onClose={() => setOpenDeviceModal(false)}
            onUpdateDevices={handleUpdateDevices}
          />

          <RenameAgentModal
            open={openRenameModal}
            agent={activeAgent}
            language={language}
            onClose={() => setOpenRenameModal(false)}
            onRename={handleRenameAgent}
          />

          <DeleteAgentModal
            open={openDeleteModal}
            agent={activeAgent}
            language={language}
            onClose={() => setOpenDeleteModal(false)}
            onConfirm={handleDeleteAgent}
          />
        </>
      )}

      <AddDeviceModal
        open={openAddDeviceModal}
        language={language}
        agents={agents}
        activeAgentId={activeAgent?.id}
        onClose={() => setOpenAddDeviceModal(false)}
        onDeviceRegistered={loadData}
        onManualAddDevice={handleManualAddDeviceGlobal}
      />

      <CreateAgentModal
        open={openCreateAgentModal}
        language={language}
        onClose={() => setOpenCreateAgentModal(false)}
        onCreate={handleCreateAgent}
      />
    </div>
  );
}
