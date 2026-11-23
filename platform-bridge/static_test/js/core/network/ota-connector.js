import { otaStatusStyle } from '../../ui/dom-helper.js';
import { log } from '../../utils/logger.js';

// WebSocket connection
export async function webSocketConnect(otaUrl, config) {

    if (!validateConfig(config)) {
        return;
    }

    // Send OTA request and get returned WebSocket info
    const otaResult = await sendOTA(otaUrl, config);
    if (!otaResult) {
        log('无法从OTA服务器获取信息', 'error');
        return;
    }

    // Extract WebSocket info from OTA response
    const { websocket } = otaResult;
    if (!websocket || !websocket.url) {
        log('OTA响应中缺少websocket信息', 'error');
        return;
    }

    // Use WebSocket URL returned by OTA
    let connUrl = new URL(websocket.url);

    // Add token parameter (from OTA response)
    if (websocket.token) {
        if (websocket.token.startsWith("Bearer ")) {
            connUrl.searchParams.append('authorization', websocket.token);
        } else {
            connUrl.searchParams.append('authorization', 'Bearer ' + websocket.token);
        }
    }

    // Add auth parameters (keep original logic)
    connUrl.searchParams.append('device-id', config.deviceId);
    connUrl.searchParams.append('client-id', config.clientId);

    const wsurl = connUrl.toString()

    log(`正在连接: ${wsurl}`, 'info');

    if (wsurl) {
        document.getElementById('serverUrl').value = wsurl;
    }

    return new WebSocket(connUrl.toString());
}

// Validate configuration
function validateConfig(config) {
    if (!config.deviceMac) {
        log('设备MAC地址不能为空', 'error');
        return false;
    }
    if (!config.clientId) {
        log('客户端ID不能为空', 'error');
        return false;
    }
    return true;
}

// Check if wsUrl path is valid
function validateWsUrl(wsUrl) {
    if (wsUrl === '') return false;
    // Check URL format
    if (!wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://')) {
        log('URL格式错误，必须以ws://或wss://开头', 'error');
        return false;
    }
    return true
}


// Send OTA request, verify status, and return response data
async function sendOTA(otaUrl, config) {
    try {
        const res = await fetch(otaUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Device-Id': config.deviceId,
                'Client-Id': config.clientId
            },
            body: JSON.stringify({
                version: 0,
                uuid: '',
                application: {
                    name: 'xiaozhi-web-test',
                    version: '1.0.0',
                    compile_time: '2025-04-16 10:00:00',
                    idf_version: '4.4.3',
                    elf_sha256: '1234567890abcdef1234567890abcdef1234567890abcdef'
                },
                ota: { label: 'xiaozhi-web-test' },
                board: {
                    type: 'xiaozhi-web-test',
                    ssid: 'xiaozhi-web-test',
                    rssi: 0,
                    channel: 0,
                    ip: '192.168.1.1',
                    mac: config.deviceMac
                },
                flash_size: 0,
                minimum_free_heap_size: 0,
                mac_address: config.deviceMac,
                chip_model_name: '',
                chip_info: { model: 0, cores: 0, revision: 0, features: 0 },
                partition_table: [{ label: '', type: 0, subtype: 0, address: 0, size: 0 }]
            })
        });

        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);

        const result = await res.json();
        otaStatusStyle(true)
        return result; // Return full response data
    } catch (err) {
        otaStatusStyle(false)
        return null; // Return null on failure
    }
}