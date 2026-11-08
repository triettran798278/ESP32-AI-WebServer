import { Agent, VoiceOption, ModelOption, McpToolOption } from '../types';

export const INITIAL_VOICES: VoiceOption[] = [
  {
    id: 'vi_female_linh',
    name: 'Thùy Linh (Vietnamese)',
    gender: 'Nữ',
    tags: ['Piper TTS', 'Tiếng Việt', 'Tự nhiên'],
    description: 'Giọng nữ tiếng Việt chuẩn xác, phát âm qua Piper TTS engine nội bộ.',
    language: 'vi'
  },
  {
    id: 'en_US-lessac-medium',
    name: 'Lessac (English)',
    gender: 'Female',
    tags: ['Piper TTS', 'English', 'Clear'],
    description: 'English female voice powered by local Piper TTS engine.',
    language: 'en'
  }
];

export const INITIAL_MODELS: ModelOption[] = [
  {
    id: 'qwen2.5:3b-instruct',
    name: 'Qwen 2.5 (3B Instruct)',
    provider: 'Local Ollama',
    description: 'Local edge LLM with ThingsBoard function calling & low-latency streaming.',
    badge: 'Active'
  }
];

export const MCP_TOOLS: McpToolOption[] = [
  {
    id: 'thingsboard-tools',
    name: 'thingsboard_iot',
    title: 'ThingsBoard IoT Platform',
    description: 'Query telemetry, list devices, and execute RPC control via ThingsBoard instance.',
    iconName: 'Laptop'
  }
];

export const INITIAL_AGENTS: Agent[] = [
  {
    id: 'agent_101',
    name: 'Desk Companion (ESP32-S3)',
    role: 'Nova',
    model: 'qwen2.5:3b-instruct',
    voice: 'vi_female_linh',
    status: 'online',
    deviceCount: 0,
    onlineDeviceCount: 0,
    lastSeen: 'Just now',
    devices: [],
    chats: [],
    config: {
      language: 'vi',
      ttsVoice: 'vi_female_linh',
      customCharacter: true,
      character: 'Bạn là Nova, trợ lý giọng nói thông minh cho gia đình. Trả lời bằng tiếng Việt ngắn gọn, súc tích (1-2 câu), tự nhiên để phát âm qua loa TTS. Khi người dùng hỏi về cảm biến, thông số môi trường (nhiệt độ, độ ẩm, CO2, áp suất) hoặc yêu cầu điều khiển thiết bị, hãy sử dụng các công cụ ThingsBoard tương ứng (list_devices, get_telemetry, send_rpc).',
      asrSpeed: 'standard',
      ttsSpeechSpeed: 'standard',
      ttsPitch: 'standard',
      llmModel: 'qwen2.5:3b-instruct',
      knowledgeBaseId: '',
      teenMode: false,
      memoryEnabled: false,
      memories: [],
      mcpEndpoints: ['thingsboard-tools'],
      speakers: []
    }
  },
  {
    id: 'agent_102',
    name: 'Living Room Monitor (Virtual ESP32)',
    role: 'Luna',
    model: 'qwen2.5:3b-instruct',
    voice: 'en_US-lessac-medium',
    status: 'online',
    deviceCount: 0,
    onlineDeviceCount: 0,
    lastSeen: 'Just now',
    devices: [],
    chats: [],
    config: {
      language: 'en',
      ttsVoice: 'en_US-lessac-medium',
      customCharacter: true,
      character: 'You are Luna, an environmental monitoring and room atmosphere assistant. Answer strictly in English in 1 concise sentence. You have read-only access to query sensors and cannot perform RPC control or switch state changes.',
      asrSpeed: 'standard',
      ttsSpeechSpeed: 'standard',
      ttsPitch: 'standard',
      llmModel: 'qwen2.5:3b-instruct',
      knowledgeBaseId: '',
      teenMode: false,
      memoryEnabled: false,
      memories: [],
      mcpEndpoints: ['thingsboard-tools'],
      speakers: []
    }
  },
  {
    id: 'agent_103',
    name: 'Virtual PC Tester (Browser/Microphone)',
    role: 'Aero',
    model: 'qwen2.5:3b-instruct',
    voice: 'vi_female_linh',
    status: 'online',
    deviceCount: 0,
    onlineDeviceCount: 0,
    lastSeen: 'Just now',
    devices: [],
    chats: [],
    config: {
      language: 'vi',
      ttsVoice: 'vi_female_linh',
      customCharacter: true,
      character: 'Bạn là Aero, trợ lý giọng nói trên máy tính (PC Virtual Companion). Trả lời bằng tiếng Việt ngắn gọn, súc tích (1-2 câu), tự nhiên để phát âm qua loa máy tính.',
      asrSpeed: 'standard',
      ttsSpeechSpeed: 'standard',
      ttsPitch: 'standard',
      llmModel: 'qwen2.5:3b-instruct',
      knowledgeBaseId: '',
      teenMode: false,
      memoryEnabled: false,
      memories: [],
      mcpEndpoints: ['thingsboard-tools'],
      speakers: []
    }
  }
];

const STORAGE_KEY = 'xz_console_agents_v2';

export function loadAgentsFromStorage(): Agent[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed;
      }
    }
  } catch (e) {
    console.error('Failed to load agents from storage:', e);
  }
  return INITIAL_AGENTS;
}

export function saveAgentsToStorage(agents: Agent[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(agents));
  } catch (e) {
    console.error('Failed to save agents to storage:', e);
  }
}
