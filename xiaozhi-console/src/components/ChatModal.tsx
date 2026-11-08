import { useState, useRef, useEffect } from 'react';
import { Agent, ChatSession, ChatMessage } from '../types';
import { sendAgentChat } from '../api/client';
import { X, MessageSquare, Trash2, Plus, Volume2, VolumeX, Send, ArrowLeft, Wrench, Sparkles, Check, Copy } from 'lucide-react';
import { useToast } from './Toast';
import { SupportedLanguage, TRANSLATIONS } from '../i18n';

interface ChatModalProps {
  open: boolean;
  agent: Agent;
  language: SupportedLanguage;
  onClose: () => void;
  onUpdateChats: (chats: ChatSession[]) => void;
}

export function ChatModal({ open, agent, language, onClose, onUpdateChats }: ChatModalProps) {
  const { success } = useToast();
  const t = TRANSLATIONS[language];
  const [sessions, setSessions] = useState<ChatSession[]>(() => agent.chats || []);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    agent.chats && agent.chats.length > 0 ? agent.chats[0].id : null
  );
  const [mobileView, setMobileView] = useState<'sessions' | 'messages'>('messages');
  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [playingMsgId, setPlayingMsgId] = useState<string | null>(null);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const activeSession = sessions.find(s => s.id === selectedSessionId) || sessions[0];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.messages, isTyping]);

  if (!open) return null;

  const handleCreateNewSession = () => {
    const newSession: ChatSession = {
      id: 'chat_' + Date.now(),
      title: language === 'vi' ? 'Phiên trò chuyện mới' : 'New Session',
      createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      messageCount: 0,
      messages: []
    };
    const updated = [newSession, ...sessions];
    setSessions(updated);
    setSelectedSessionId(newSession.id);
    setMobileView('messages');
    onUpdateChats(updated);
    success(t.chat.newChatCreated);
  };

  const handleDeleteSession = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = sessions.filter(s => s.id !== sessionId);
    setSessions(updated);
    if (selectedSessionId === sessionId) {
      setSelectedSessionId(updated.length > 0 ? updated[0].id : null);
    }
    onUpdateChats(updated);
    success(t.chat.sessionDeleted);
  };

  const handleSendMessage = async () => {
    if (!inputText.trim()) return;
    const text = inputText.trim();
    setInputText('');

    const userMsg: ChatMessage = {
      id: 'msg_' + Date.now(),
      role: 'user',
      content: text,
      createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    };

    let curSession = activeSession;
    let updatedSessions = [...sessions];

    if (!curSession) {
      curSession = {
        id: 'chat_' + Date.now(),
        title: text.slice(0, 18),
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        messageCount: 1,
        messages: [userMsg]
      };
      updatedSessions = [curSession, ...updatedSessions];
      setSelectedSessionId(curSession.id);
    } else {
      const isFirst = curSession.messages.length === 0;
      const updatedMessages = [...curSession.messages, userMsg];
      curSession = {
        ...curSession,
        title: isFirst ? text.slice(0, 18) : curSession.title,
        messageCount: updatedMessages.length,
        messages: updatedMessages
      };
      updatedSessions = updatedSessions.map(s => s.id === curSession!.id ? curSession! : s);
    }

    setSessions(updatedSessions);
    onUpdateChats(updatedSessions);
    setIsTyping(true);

    try {
      const history = (curSession?.messages || []).map(m => ({ role: m.role, content: m.content }));
      const res = await sendAgentChat(agent.id, text, history);

      const newMessages: ChatMessage[] = [];

      // Append any executed ThingsBoard tool calls
      if (res.tool_calls && res.tool_calls.length > 0) {
        for (const tc of res.tool_calls) {
          newMessages.push({
            id: 'tc_' + Date.now() + '_' + Math.random().toString(36).substring(2, 6),
            role: 'tool',
            content: language === 'vi' ? `Thực thi công cụ ThingsBoard: ${tc.name}` : `ThingsBoard Tool: ${tc.name}`,
            createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            toolName: tc.name,
            toolArgs: tc.arguments,
            toolResult: tc.result
          });
        }
      }

      // Append real LLM response
      newMessages.push({
        id: 'msg_' + (Date.now() + 1),
        role: 'assistant',
        content: res.reply || (language === 'vi' ? 'Không có phản hồi từ mô hình.' : 'No response from model.'),
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        audioDuration: '2.4s'
      });

      const finalMessages = [...curSession!.messages, ...newMessages];
      const finalizedSession = {
        ...curSession!,
        messageCount: finalMessages.length,
        messages: finalMessages
      };

      const finalSessions = updatedSessions.map(s => s.id === finalizedSession.id ? finalizedSession : s);
      setSessions(finalSessions);
      onUpdateChats(finalSessions);
    } catch (err: any) {
      const errMsg: ChatMessage = {
        id: 'err_' + Date.now(),
        role: 'assistant',
        content: language === 'vi' ? `Lỗi kết nối mô hình: ${err.message}` : `Model inference error: ${err.message}`,
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      };
      const finalMessages = [...curSession!.messages, errMsg];
      const finalizedSession = {
        ...curSession!,
        messageCount: finalMessages.length,
        messages: finalMessages
      };
      const finalSessions = updatedSessions.map(s => s.id === finalizedSession.id ? finalizedSession : s);
      setSessions(finalSessions);
      onUpdateChats(finalSessions);
    } finally {
      setIsTyping(false);
    }
  };

  const handlePlayVoice = (msgId: string) => {
    if (playingVoiceId(msgId)) {
      setPlayingMsgId(null);
      return;
    }
    setPlayingMsgId(msgId);
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(520, ctx.currentTime);
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.5);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 1.5);
    } catch {}
    setTimeout(() => {
      setPlayingMsgId(null);
    }, 2000);
  };

  const playingVoiceId = (id: string) => playingMsgId === id;

  const handleCopy = (msg: ChatMessage) => {
    navigator.clipboard.writeText(msg.content);
    setCopiedMsgId(msg.id);
    setTimeout(() => setCopiedMsgId(null), 1500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="relative flex flex-col w-full max-w-5xl h-[min(48rem,calc(100vh-1rem))] rounded-xl border bg-card shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-3.5 bg-card">
          <div className="flex items-center gap-2">
            {mobileView === 'messages' && (
              <button
                onClick={() => setMobileView('sessions')}
                className="md:hidden rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <ArrowLeft className="size-4" />
              </button>
            )}
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              {agent.name} <span className="text-muted-foreground font-normal">· {t.chat.title}</span>
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* 2-Column Split Pane */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-[17rem_minmax(0,1fr)] min-h-0 divide-x overflow-hidden">
          {/* Left Session List */}
          <div className={`flex flex-col h-full bg-muted/10 min-h-0 ${mobileView === 'messages' ? 'hidden md:flex' : 'flex'}`}>
            <div className="p-3 border-b flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground">
                {t.chat.historyTitle(sessions.length)}
              </span>
              <button
                onClick={handleCreateNewSession}
                className="inline-flex items-center gap-1 rounded bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/20"
              >
                <Plus className="size-3.5" /> {t.chat.newChat}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
              {sessions.length === 0 ? (
                <div className="py-10 text-center text-xs text-muted-foreground">
                  {t.chat.noChats}
                </div>
              ) : (
                sessions.map(s => {
                  const isSelected = activeSession?.id === s.id;
                  return (
                    <div
                      key={s.id}
                      onClick={() => {
                        setSelectedSessionId(s.id);
                        setMobileView('messages');
                      }}
                      className={`group flex items-center justify-between p-2.5 rounded-lg border text-left cursor-pointer transition-all ${
                        isSelected
                          ? 'border-primary bg-primary/5 text-primary font-medium'
                          : 'border-transparent hover:bg-muted/60 text-foreground'
                      }`}
                    >
                      <div className="min-w-0 flex-1 pr-2">
                        <div className="text-xs font-medium truncate">{s.title || t.chat.newChat}</div>
                        <div className="flex items-center gap-2 mt-1 text-[11px] text-muted-foreground">
                          <span>{s.createdAt}</span>
                          <span>·</span>
                          <span>{s.messageCount} msg</span>
                        </div>
                      </div>

                      <button
                        onClick={e => handleDeleteSession(s.id, e)}
                        className="opacity-0 group-hover:opacity-100 p-1 text-muted-foreground hover:text-destructive rounded transition-opacity"
                        title="Delete chat"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Message Feed & Chat Input */}
          <div className={`flex flex-col h-full bg-background min-h-0 ${mobileView === 'sessions' ? 'hidden md:flex' : 'flex'}`}>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {!activeSession || activeSession.messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-8 text-muted-foreground">
                  <div className="size-12 rounded-full bg-muted flex items-center justify-center mb-3">
                    <MessageSquare className="size-6 text-muted-foreground" />
                  </div>
                  <p className="text-sm font-medium">{t.chat.noMessages}</p>
                  <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                    {t.chat.startPrompt}
                  </p>
                </div>
              ) : (
                activeSession.messages.map(msg => (
                  <div key={msg.id} className="space-y-1.5 animate-in fade-in duration-100">
                    {msg.role === 'user' && (
                      <div className="flex justify-end">
                        <div className="max-w-[80%] rounded-2xl rounded-tr-xs bg-primary px-4 py-2.5 text-xs text-primary-foreground shadow-sm">
                          <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                          <div className="text-right text-[10px] text-primary-foreground/70 mt-1">
                            {msg.createdAt}
                          </div>
                        </div>
                      </div>
                    )}

                    {msg.role === 'tool' && (
                      <div className="flex justify-start my-2">
                        <div className="max-w-[90%] rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs space-y-1.5">
                          <div className="flex items-center gap-1.5 font-semibold text-primary text-[11px]">
                            <Wrench className="size-3.5" />
                            <span>{t.chat.toolCall}: {msg.toolName}</span>
                          </div>
                          {msg.toolArgs && (
                            <div className="font-mono text-[11px] bg-background/60 p-2 rounded border">
                              <span className="text-muted-foreground">{t.chat.toolArgs}: </span>
                              <span>{msg.toolArgs}</span>
                            </div>
                          )}
                          {msg.toolResult && (
                            <div className="font-mono text-[11px] bg-background/60 p-2 rounded border">
                              <span className="text-muted-foreground">{t.chat.toolResult}: </span>
                              <span className="text-emerald-600 dark:text-emerald-400">{msg.toolResult}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {msg.role === 'assistant' && (
                      <div className="flex justify-start">
                        <div className="group relative max-w-[85%] rounded-2xl rounded-tl-xs border bg-card px-4 py-3 text-xs text-foreground shadow-sm space-y-2">
                          <p className="whitespace-pre-wrap leading-relaxed text-xs">{msg.content}</p>

                          <div className="flex items-center justify-between pt-1 border-t border-border/40 text-[11px] text-muted-foreground">
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => handlePlayVoice(msg.id)}
                                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] border transition-colors ${
                                  playingVoiceId(msg.id)
                                    ? 'border-primary bg-primary/10 text-primary animate-pulse'
                                    : 'border-border hover:bg-muted text-muted-foreground'
                                }`}
                              >
                                {playingVoiceId(msg.id) ? (
                                  <VolumeX className="size-3 text-primary" />
                                ) : (
                                  <Volume2 className="size-3" />
                                )}
                                <span>{playingVoiceId(msg.id) ? t.chat.playingAudio : `${t.chat.playAudio} ${msg.audioDuration || '3s'}`}</span>
                              </button>

                              <button
                                onClick={() => handleCopy(msg)}
                                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-muted text-muted-foreground"
                                title={t.chat.copy}
                              >
                                {copiedMsgId === msg.id ? (
                                  <>
                                    <Check className="size-3 text-emerald-500" />
                                    <span className="text-[10px] text-emerald-500">{t.chat.copied}</span>
                                  </>
                                ) : (
                                  <Copy className="size-3" />
                                )}
                              </button>
                            </div>

                            <span className="text-[10px] text-muted-foreground">{msg.createdAt}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}

              {isTyping && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground p-2">
                  <Sparkles className="size-3.5 text-primary animate-spin" />
                  <span>{t.chat.thinking(agent.name)}</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <div className="px-4 py-1 text-center text-[10px] text-muted-foreground/60 border-t bg-muted/10">
              {t.chat.disclaimer}
            </div>

            <div className="p-3 border-t bg-card">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                  placeholder={t.chat.inputPlaceholder(agent.name)}
                  className="flex-1 rounded-lg border bg-background px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-ring"
                />
                <button
                  onClick={handleSendMessage}
                  disabled={!inputText.trim()}
                  className="rounded-lg bg-primary px-3 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 flex items-center gap-1 shrink-0"
                >
                  <Send className="size-3.5" />
                  <span>{t.chat.send}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
