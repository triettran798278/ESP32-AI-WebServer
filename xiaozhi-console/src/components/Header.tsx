import { useState, useRef, useEffect } from 'react';
import { Bot, Cpu, Globe, Sun, Moon, Laptop } from 'lucide-react';
import { SupportedLanguage, TRANSLATIONS } from '../i18n';

interface HeaderProps {
  currentTab: string;
  onTabChange: (tab: string) => void;
  theme: 'light' | 'dark' | 'system';
  onThemeChange: (theme: 'light' | 'dark' | 'system') => void;
  language: SupportedLanguage;
  onLanguageChange: (lang: SupportedLanguage) => void;
}

export function Header({
  currentTab,
  onTabChange,
  theme,
  onThemeChange,
  language,
  onLanguageChange
}: HeaderProps) {
  const [langOpen, setLangOpen] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);

  const langRef = useRef<HTMLDivElement>(null);
  const themeRef = useRef<HTMLDivElement>(null);

  const t = TRANSLATIONS[language];

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (langRef.current && !langRef.current.contains(e.target as Node)) setLangOpen(false);
      if (themeRef.current && !themeRef.current.contains(e.target as Node)) setThemeOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const navItems = [
    { id: 'devices', label: language === 'vi' ? 'Thiết bị' : 'Devices', icon: Cpu },
    { id: 'agents', label: t.nav.agents, icon: Bot },
    { id: 'integrations', label: 'ThingsBoard IoT', icon: Laptop },
  ];

  const allowedLanguages: { code: SupportedLanguage; label: string; short: string }[] = [
    { code: 'en', label: 'English', short: 'EN' },
    { code: 'vi', label: 'Tiếng Việt', short: 'VI' },
  ];

  const currentLangObj = allowedLanguages.find(l => l.code === language) || allowedLanguages[0];

  return (
    <header className="border-b bg-card sticky top-0 z-40 backdrop-blur-sm">
      <div className="mx-auto flex h-14 w-[90%] max-w-[100rem] items-center gap-1 sm:gap-2">
        {/* Logo */}
        <button
          onClick={() => onTabChange('devices')}
          className="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring pr-2"
        >
          <img src="/logo.svg" alt={t.appName} className="size-8" />
          <span className="font-semibold text-base tracking-tight hidden md:inline">{t.appName}</span>
        </button>

        {/* Navigation Tabs */}
        <nav className="ml-auto flex items-center gap-1">
          {navItems.map(item => {
            const Icon = item.icon;
            const active = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium transition-colors ${
                  active
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground'
                }`}
              >
                <Icon className="size-4 shrink-0" />
                <span className="hidden lg:inline">{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Language selector */}
        <div className="relative" ref={langRef}>
          <button
            onClick={() => setLangOpen(!langOpen)}
            className="inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            title={t.preferences.language}
          >
            <Globe className="size-4" />
            <span className="text-xs font-semibold">{currentLangObj.short}</span>
          </button>
          {langOpen && (
            <div className="absolute right-0 mt-1.5 w-36 rounded-md border bg-card p-1 shadow-md z-50 text-sm">
              {allowedLanguages.map(l => (
                <button
                  key={l.code}
                  onClick={() => {
                    onLanguageChange(l.code);
                    setLangOpen(false);
                  }}
                  className={`w-full flex items-center justify-between rounded px-2.5 py-1.5 text-xs text-left ${
                    language === l.code ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-muted text-muted-foreground'
                  }`}
                >
                  <span>{l.label}</span>
                  {language === l.code && <span className="text-xs font-bold">✓</span>}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Theme toggle */}
        <div className="relative" ref={themeRef}>
          <button
            onClick={() => setThemeOpen(!themeOpen)}
            className="inline-flex h-9 items-center justify-center rounded-md px-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            title={t.preferences.theme}
          >
            {theme === 'dark' ? <Moon className="size-4" /> : theme === 'light' ? <Sun className="size-4" /> : <Laptop className="size-4" />}
          </button>
          {themeOpen && (
            <div className="absolute right-0 mt-1.5 w-32 rounded-md border bg-card p-1 shadow-md z-50 text-sm">
              <button
                onClick={() => { onThemeChange('light'); setThemeOpen(false); }}
                className={`w-full flex items-center gap-2 rounded px-2.5 py-1.5 text-xs text-left ${theme === 'light' ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-muted text-muted-foreground'}`}
              >
                <Sun className="size-3.5" /> {t.preferences.light}
              </button>
              <button
                onClick={() => { onThemeChange('dark'); setThemeOpen(false); }}
                className={`w-full flex items-center gap-2 rounded px-2.5 py-1.5 text-xs text-left ${theme === 'dark' ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-muted text-muted-foreground'}`}
              >
                <Moon className="size-3.5" /> {t.preferences.dark}
              </button>
              <button
                onClick={() => { onThemeChange('system'); setThemeOpen(false); }}
                className={`w-full flex items-center gap-2 rounded px-2.5 py-1.5 text-xs text-left ${theme === 'system' ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-muted text-muted-foreground'}`}
              >
                <Laptop className="size-3.5" /> {t.preferences.system}
              </button>
            </div>
          )}
        </div>

        {/* Real Platform Status Indicator */}
        <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
          <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span>Online</span>
        </div>
      </div>
    </header>
  );
}
