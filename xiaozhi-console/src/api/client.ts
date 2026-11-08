/**
 * Platform Bridge API Client for AI Agent Management Console.
 * Directly communicates with the backend services on port 8005.
 */

import { Agent, Device } from '../types';

const API_BASE = window.location.port === '5173' ? 'http://localhost:8005' : '';

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${API_BASE}/api/agents`);
  if (!res.ok) throw new Error(`Failed to fetch agents: ${res.statusText}`);
  const data = await res.json();
  return data.agents || [];
}

export async function createAgent(payload: Partial<Agent>): Promise<Agent> {
  const res = await fetch(`${API_BASE}/api/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to create agent: ${res.statusText}`);
  const data = await res.json();
  return data.agent;
}

export async function updateAgent(agentId: string, payload: Partial<Agent>): Promise<any> {
  const res = await fetch(`${API_BASE}/api/agents/${agentId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to update agent: ${res.statusText}`);
  return await res.json();
}

export async function deleteAgent(agentId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/agents/${agentId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete agent: ${res.statusText}`);
  return await res.json();
}

export async function fetchDevices(): Promise<Device[]> {
  const res = await fetch(`${API_BASE}/api/devices`);
  if (!res.ok) throw new Error(`Failed to fetch devices: ${res.statusText}`);
  const data = await res.json();
  return data.devices || [];
}

export async function createActivationCode(agentId: string, expirationSeconds: number = 300): Promise<{
  status: string;
  code: string;
  agent_id: string;
  expires_at: number;
  ttl_seconds: number;
}> {
  const res = await fetch(`${API_BASE}/api/devices/activation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, expiration_seconds: expirationSeconds }),
  });
  if (!res.ok) throw new Error(`Failed to create activation code: ${res.statusText}`);
  return await res.json();
}

export async function getActivationStatus(code: string): Promise<{
  code: string;
  agent_id: string;
  status: 'pending' | 'redeemed' | 'expired' | 'not_found';
  remaining_seconds?: number;
  device?: any;
}> {
  const res = await fetch(`${API_BASE}/api/devices/activation/status?code=${encodeURIComponent(code)}`);
  if (!res.ok) throw new Error(`Failed to get activation status: ${res.statusText}`);
  return await res.json();
}

export async function bindActivationCode(code: string, agentId: string, deviceName?: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/devices/activation/bind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, agent_id: agentId, device_name: deviceName }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Failed to activate device: ${res.statusText}`);
  }
  return await res.json();
}

export async function bindDevice(macAddress: string, agentId: string, deviceName: string = 'ESP32 Device'): Promise<any> {
  const res = await fetch(`${API_BASE}/api/devices/bind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mac_address: macAddress,
      agent_id: agentId,
      device_name: deviceName,
    }),
  });
  if (!res.ok) throw new Error(`Failed to bind device: ${res.statusText}`);
  return await res.json();
}

export async function unbindDevice(macAddress: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/devices/unbind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mac_address: macAddress }),
  });
  if (!res.ok) throw new Error(`Failed to unbind device: ${res.statusText}`);
  return await res.json();
}

export async function testThingsBoard(agentId?: string, host?: string, apiKey?: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/integrations/thingsboard/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, host, api_key: apiKey }),
  });
  if (!res.ok) throw new Error(`Failed to test ThingsBoard: ${res.statusText}`);
  return await res.json();
}

export async function fetchThingsBoardTelemetry(agentId: string = 'agent_101'): Promise<any> {
  const res = await fetch(`${API_BASE}/api/integrations/thingsboard/telemetry?agent_id=${agentId}`);
  if (!res.ok) throw new Error(`Failed to fetch telemetry: ${res.statusText}`);
  return await res.json();
}

export async function sendAgentChat(agentId: string, message: string, history: any[] = []): Promise<{
  reply: string;
  tool_calls: Array<{
    id: string;
    name: string;
    arguments: string;
    result: string;
  }>;
}> {
  const res = await fetch(`${API_BASE}/api/agents/${agentId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Chat request failed: ${res.statusText}`);
  }
  return await res.json();
}
