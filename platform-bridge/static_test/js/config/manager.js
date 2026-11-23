// Configuration management module

// Generate random MAC address
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

// Load configuration
export function loadConfig() {
    const deviceMacInput = document.getElementById('deviceMac');
    const deviceNameInput = document.getElementById('deviceName');
    const clientIdInput = document.getElementById('clientId');
    const otaUrlInput = document.getElementById('otaUrl');

    // Default to virtual PC test device MAC address (agent_103: Aero)
    let savedMac = localStorage.getItem('xz_tester_deviceMac');
    if (!savedMac) {
        savedMac = '02:00:00:00:00:01';
        localStorage.setItem('xz_tester_deviceMac', savedMac);
    }
    deviceMacInput.value = savedMac;

    // Load other config from localStorage with Virtual PC defaults
    const savedDeviceName = localStorage.getItem('xz_tester_deviceName') || 'Virtual PC Test Client';
    deviceNameInput.value = savedDeviceName;

    const savedClientId = localStorage.getItem('xz_tester_clientId') || 'virtual_pc_client';
    clientIdInput.value = savedClientId;

    const defaultOta = window.location.origin ? `${window.location.origin}/xiaozhi/ota/` : 'http://127.0.0.1:8005/xiaozhi/ota/';
    const savedOtaUrl = localStorage.getItem('xz_tester_otaUrl') || defaultOta;
    otaUrlInput.value = savedOtaUrl;
}

// Save configuration
export function saveConfig() {
    const deviceMacInput = document.getElementById('deviceMac');
    const deviceNameInput = document.getElementById('deviceName');
    const clientIdInput = document.getElementById('clientId');

    localStorage.setItem('xz_tester_deviceMac', deviceMacInput.value);
    localStorage.setItem('xz_tester_deviceName', deviceNameInput.value);
    localStorage.setItem('xz_tester_clientId', clientIdInput.value);
}

// Get configuration values
export function getConfig() {
    const deviceMac = document.getElementById('deviceMac').value.trim();
    return {
        deviceId: deviceMac,  // Use MAC address as deviceId
        deviceName: document.getElementById('deviceName').value.trim(),
        deviceMac: deviceMac,
        clientId: document.getElementById('clientId').value.trim()
    };
}

// Save connection URLs
export function saveConnectionUrls() {
    const otaUrl = document.getElementById('otaUrl').value.trim();
    const wsUrl = document.getElementById('serverUrl').value.trim();
    localStorage.setItem('xz_tester_otaUrl', otaUrl);
    localStorage.setItem('xz_tester_wsUrl', wsUrl);
}
