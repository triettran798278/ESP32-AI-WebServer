export type AgentStatus = 'online' | 'offline' | 'setup';

export interface Device {
  id: string;
  device_id?: string;
  name: string;
  mac_address: string;
  status: 'online' | 'offline';
  firmware_version: string;
  hardware_model?: string;
  registration_status?: 'authenticated' | 'manual_mac';
  registered_at?: number | null;
  last_seen_ts?: number;
  is_auth: boolean; // true = official / authorized, false = open source
  ota_enabled: boolean;
  agent_id?: string;
  agent_name?: string;
  agent_role?: string;
  last_seen?: string;
}

export interface MemoryItem {
  id: string;
  content: string;
  createdAt: string;
  type: 'profile' | 'context';
}

export interface SpeakerItem {
  id: string;
  name: string;
  description: string;
  sampleTime: string;
}

export interface AgentConfig {
  language: string;
  ttsVoice: string;
  customCharacter: boolean;
  character: string;
  asrSpeed: 'slow' | 'standard' | 'fast';
  ttsSpeechSpeed: 'slow' | 'standard' | 'fast';
  ttsPitch: 'low' | 'standard' | 'high';
  llmModel: string;
  knowledgeBaseId: string;
  teenMode: boolean;
  memoryEnabled: boolean;
  memories: MemoryItem[];
  mcpEndpoints: string[];
  speakers: SpeakerItem[];
  tool_policy?: 'full_control' | 'read_only_telemetry';
  integrations?: {
    thingsboard?: {
      host?: string;
      api_key?: string;
      display_name?: string;
      is_configured?: boolean;
      timeout_seconds?: number;
    };
  };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  createdAt: string;
  audioDuration?: string;
  toolName?: string;
  toolArgs?: string;
  toolResult?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  messageCount: number;
  messages: ChatMessage[];
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  model: string;
  voice: string;
  status: AgentStatus;
  deviceCount: number;
  onlineDeviceCount: number;
  lastSeen: string;
  devices: Device[];
  config: AgentConfig;
  chats: ChatSession[];
  tool_policy?: string;
  integrations?: Record<string, any>;
}

export interface VoiceOption {
  id: string;
  name: string;
  gender: string;
  tags: string[];
  description: string;
  language: string;
}

export interface ModelOption {
  id: string;
  name: string;
  provider: string;
  description: string;
  badge?: string;
}

export interface McpToolOption {
  id: string;
  name: string;
  title: string;
  description: string;
  iconName: string;
}
