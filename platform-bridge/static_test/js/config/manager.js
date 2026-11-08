// 配置管理模块

// 生成随机MAC地址
function generateRandomMac() {
    const hexDigits = '0123456789ABCDEF';
    let mac = '';
    for (let i = 0; i < 6; i++) {
        if (i > 0) mac += ':';
        for (let j = 0; j < 2; j++) {
            mac += hexDigits.charAt(Math.floor(Math.random() * 16));
        }
    }
    return mac;
}

// 加载配置
export function loadConfig() {
    const deviceMacInput = document.getElementById('deviceMac');
    const deviceNameInput = document.getElementById('deviceName');
    const clientIdInput = document.getElementById('clientId');
    const otaUrlInput = document.getElementById('otaUrl');

    // 默认使用虚拟 PC 测试设备的 MAC 地址 (agent_103: Aero)
    let savedMac = localStorage.getItem('xz_tester_deviceMac');
    if (!savedMac) {
        savedMac = '02:00:00:00:00:01';
        localStorage.setItem('xz_tester_deviceMac', savedMac);
    }
    deviceMacInput.value = savedMac;

    // 从localStorage加载其他配置，并预设 Virtual PC 默认值
    const savedDeviceName = localStorage.getItem('xz_tester_deviceName') || 'Virtual PC Test Client';
    deviceNameInput.value = savedDeviceName;

    const savedClientId = localStorage.getItem('xz_tester_clientId') || 'virtual_pc_client';
    clientIdInput.value = savedClientId;

    const defaultOta = window.location.origin ? `${window.location.origin}/xiaozhi/ota/` : 'http://127.0.0.1:8005/xiaozhi/ota/';
    const savedOtaUrl = localStorage.getItem('xz_tester_otaUrl') || defaultOta;
    otaUrlInput.value = savedOtaUrl;
}

// 保存配置
export function saveConfig() {
    const deviceMacInput = document.getElementById('deviceMac');
    const deviceNameInput = document.getElementById('deviceName');
    const clientIdInput = document.getElementById('clientId');

    localStorage.setItem('xz_tester_deviceMac', deviceMacInput.value);
    localStorage.setItem('xz_tester_deviceName', deviceNameInput.value);
    localStorage.setItem('xz_tester_clientId', clientIdInput.value);
}

// 获取配置值
export function getConfig() {
    const deviceMac = document.getElementById('deviceMac').value.trim();
    return {
        deviceId: deviceMac,  // 使用MAC地址作为deviceId
        deviceName: document.getElementById('deviceName').value.trim(),
        deviceMac: deviceMac,
        clientId: document.getElementById('clientId').value.trim()
    };
}

// 保存连接URL
export function saveConnectionUrls() {
    const otaUrl = document.getElementById('otaUrl').value.trim();
    const wsUrl = document.getElementById('serverUrl').value.trim();
    localStorage.setItem('xz_tester_otaUrl', otaUrl);
    localStorage.setItem('xz_tester_wsUrl', wsUrl);
}
