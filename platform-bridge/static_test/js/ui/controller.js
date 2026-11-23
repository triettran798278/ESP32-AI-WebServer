// UI controller module
import { loadConfig, saveConfig } from '../config/manager.js';
import { getAudioPlayer } from '../core/audio/player.js';
import { getAudioRecorder } from '../core/audio/recorder.js';
import { getWebSocketHandler } from '../core/network/websocket.js';

// UI controller class
export class UIController {
    constructor() {
        this.isEditing = false;
        this.visualizerCanvas = null;
        this.visualizerContext = null;
        this.audioStatsTimer = null;
    }

    // Initialize
    init() {
        this.visualizerCanvas = document.getElementById('audioVisualizer');
        this.visualizerContext = this.visualizerCanvas.getContext('2d');

        this.initVisualizer();
        this.initEventListeners();
        this.startAudioStatsMonitor();
        loadConfig();
    }

    // Initialize visualizer
    initVisualizer() {
        this.visualizerCanvas.width = this.visualizerCanvas.clientWidth;
        this.visualizerCanvas.height = this.visualizerCanvas.clientHeight;
        this.visualizerContext.fillStyle = '#fafafa';
        this.visualizerContext.fillRect(0, 0, this.visualizerCanvas.width, this.visualizerCanvas.height);
    }

    // Update status display
    updateStatusDisplay(element, text) {
        element.textContent = text;
        element.removeAttribute('style');
        element.classList.remove('connected');
        if (text.includes('已连接')) {
            element.classList.add('connected');
        }
        console.log('更新状态:', text, '类列表:', element.className, '样式属性:', element.getAttribute('style'));
    }

    // Update connection status UI
    updateConnectionUI(isConnected) {
        const connectionStatus = document.getElementById('connectionStatus');
        const otaStatus = document.getElementById('otaStatus');
        const connectButton = document.getElementById('connectButton');
        const messageInput = document.getElementById('messageInput');
        const sendTextButton = document.getElementById('sendTextButton');
        const recordButton = document.getElementById('recordButton');

        if (isConnected) {
            this.updateStatusDisplay(connectionStatus, '● WS已连接');
            this.updateStatusDisplay(otaStatus, '● OTA已连接');
            connectButton.textContent = '断开';
            messageInput.disabled = false;
            sendTextButton.disabled = false;
            recordButton.disabled = false;
        } else {
            this.updateStatusDisplay(connectionStatus, '● WS未连接');
            this.updateStatusDisplay(otaStatus, '● OTA未连接');
            connectButton.textContent = '连接';
            messageInput.disabled = true;
            sendTextButton.disabled = true;
            recordButton.disabled = true;
            // Set session status to offline when disconnected
            this.updateSessionStatus(null);
        }
    }

    // Update record button state
    updateRecordButtonState(isRecording, seconds = 0) {
        const recordButton = document.getElementById('recordButton');
        if (isRecording) {
            recordButton.textContent = `停止录音 ${seconds.toFixed(1)}秒`;
            recordButton.classList.add('recording');
        } else {
            recordButton.textContent = '开始录音';
            recordButton.classList.remove('recording');
        }
        recordButton.disabled = false;
    }

    // Update session status UI
    updateSessionStatus(isSpeaking) {
        const sessionStatus = document.getElementById('sessionStatus');
        if (!sessionStatus) return;

        // Preserve background element
        const bgHtml = '<span id="sessionStatusBg" style="position: absolute; left: 0; top: 0; bottom: 0; width: 0%; background: linear-gradient(90deg, rgba(76, 175, 80, 0.2), rgba(33, 150, 243, 0.2)); transition: width 0.15s ease-out, background 0.3s ease; z-index: 0; border-radius: 20px;"></span>';

        if (isSpeaking === null) {
            // Offline state
            sessionStatus.innerHTML = bgHtml + '<span style="position: relative; z-index: 1;"><span class="emoji-large">😶</span> 小智离线中</span>';
            sessionStatus.className = 'status offline';
        } else if (isSpeaking) {
            // Speaking
            sessionStatus.innerHTML = bgHtml + '<span style="position: relative; z-index: 1;"><span class="emoji-large">😶</span> 小智说话中</span>';
            sessionStatus.className = 'status speaking';
        } else {
            // Listening
            sessionStatus.innerHTML = bgHtml + '<span style="position: relative; z-index: 1;"><span class="emoji-large">😶</span> 小智聆听中</span>';
            sessionStatus.className = 'status listening';
        }
    }

    // Update session emotion
    updateSessionEmotion(emoji) {
        const sessionStatus = document.getElementById('sessionStatus');
        if (!sessionStatus) return;

        // Get current text content and extract non-emoji part
        let currentText = sessionStatus.textContent;
        // Remove existing emojis
        currentText = currentText.replace(/[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]/gu, '').trim();

        // Preserve background element
        const bgHtml = '<span id="sessionStatusBg" style="position: absolute; left: 0; top: 0; bottom: 0; width: 0%; background: linear-gradient(90deg, rgba(76, 175, 80, 0.2), rgba(33, 150, 243, 0.2)); transition: width 0.15s ease-out, background 0.3s ease; z-index: 0; border-radius: 20px;"></span>';

        // Use innerHTML to add styled emoji
        sessionStatus.innerHTML = bgHtml + `<span style="position: relative; z-index: 1;"><span class="emoji-large">${emoji}</span> ${currentText}</span>`;
    }

    // Update audio stats
    updateAudioStats() {
        const audioPlayer = getAudioPlayer();
        const stats = audioPlayer.getAudioStats();

        const sessionStatus = document.getElementById('sessionStatus');
        const sessionStatusBg = document.getElementById('sessionStatusBg');

        // Only show background progress while speaking
        if (sessionStatus && sessionStatus.classList.contains('speaking') && sessionStatusBg) {
            if (stats.pendingPlay > 0) {
                // Compute progress: 5 packets = 50%, 10+ packets = 100%
                let percentage;
                if (stats.pendingPlay >= 10) {
                    percentage = 100;
                } else {
                    percentage = (stats.pendingPlay / 10) * 100;
                }

                sessionStatusBg.style.width = `${percentage}%`;

                // Change background color based on buffer level
                if (stats.pendingPlay < 5) {
                    // Low buffer: translucent orange-red
                    sessionStatusBg.style.background = 'linear-gradient(90deg, rgba(255, 152, 0, 0.25), rgba(255, 87, 34, 0.25))';
                } else if (stats.pendingPlay < 10) {
                    // Moderate buffer: translucent yellow-green
                    sessionStatusBg.style.background = 'linear-gradient(90deg, rgba(205, 220, 57, 0.25), rgba(76, 175, 80, 0.25))';
                } else {
                    // Sufficient buffer: translucent green-blue
                    sessionStatusBg.style.background = 'linear-gradient(90deg, rgba(76, 175, 80, 0.25), rgba(33, 150, 243, 0.25))';
                }
            } else {
                // No buffer; hide background
                sessionStatusBg.style.width = '0%';
            }
        } else {
            // Not speaking; hide background
            if (sessionStatusBg) {
                sessionStatusBg.style.width = '0%';
            }
        }
    }

    // Start audio stats monitor
    startAudioStatsMonitor() {
        // Update audio stats every 100ms
        this.audioStatsTimer = setInterval(() => {
            this.updateAudioStats();
        }, 100);
    }

    // Stop audio stats monitor
    stopAudioStatsMonitor() {
        if (this.audioStatsTimer) {
            clearInterval(this.audioStatsTimer);
            this.audioStatsTimer = null;
        }
    }

    // Draw audio visualizer
    drawVisualizer(dataArray) {
        this.visualizerContext.fillStyle = '#fafafa';
        this.visualizerContext.fillRect(0, 0, this.visualizerCanvas.width, this.visualizerCanvas.height);

        const barWidth = (this.visualizerCanvas.width / dataArray.length) * 2.5;
        let barHeight;
        let x = 0;

        for (let i = 0; i < dataArray.length; i++) {
            barHeight = dataArray[i] / 2;

            // Create gradient color from cyan to blue to purple
            const hue = 200 + (barHeight / this.visualizerCanvas.height) * 60; // 200-260 deg, cyan to purple
            const saturation = 80 + (barHeight / this.visualizerCanvas.height) * 20; // Saturation 80-100%
            const lightness = 45 + (barHeight / this.visualizerCanvas.height) * 15; // Lightness 45-60%

            this.visualizerContext.fillStyle = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
            this.visualizerContext.fillRect(x, this.visualizerCanvas.height - barHeight, barWidth, barHeight);

            x += barWidth + 1;
        }
    }

    // Initialize event listeners
    initEventListeners() {
        const wsHandler = getWebSocketHandler();
        const audioRecorder = getAudioRecorder();

        // Set WebSocket callbacks
        wsHandler.onConnectionStateChange = (isConnected) => {
            this.updateConnectionUI(isConnected);
        };

        wsHandler.onRecordButtonStateChange = (isRecording) => {
            this.updateRecordButtonState(isRecording);
        };

        wsHandler.onSessionStateChange = (isSpeaking) => {
            this.updateSessionStatus(isSpeaking);
        };

        wsHandler.onSessionEmotionChange = (emoji) => {
            this.updateSessionEmotion(emoji);
        };

        // Set recorder callbacks
        audioRecorder.onRecordingStart = (seconds) => {
            this.updateRecordButtonState(true, seconds);
        };

        audioRecorder.onRecordingStop = () => {
            this.updateRecordButtonState(false);
        };

        audioRecorder.onVisualizerUpdate = (dataArray) => {
            this.drawVisualizer(dataArray);
        };

        // Connect button
        const connectButton = document.getElementById('connectButton');
        let isConnecting = false;

        const handleConnect = async () => {
            if (isConnecting) return;

            if (wsHandler.isConnected()) {
                wsHandler.disconnect();
            } else {
                isConnecting = true;
                await wsHandler.connect();
                isConnecting = false;
            }
        };

        connectButton.addEventListener('click', handleConnect);

        // Device config panel edit/confirm toggle
        const toggleButton = document.getElementById('toggleConfig');
        const deviceMacInput = document.getElementById('deviceMac');
        const deviceNameInput = document.getElementById('deviceName');
        const clientIdInput = document.getElementById('clientId');

        toggleButton.addEventListener('click', () => {
            this.isEditing = !this.isEditing;

            deviceMacInput.disabled = !this.isEditing;
            deviceNameInput.disabled = !this.isEditing;
            clientIdInput.disabled = !this.isEditing;

            toggleButton.textContent = this.isEditing ? '确定' : '编辑';

            if (!this.isEditing) {
                saveConfig();
            }
        });

        // Tab switching
        const tabs = document.querySelectorAll('.tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

                tab.classList.add('active');
                const tabContent = document.getElementById(`${tab.dataset.tab}Tab`);
                tabContent.classList.add('active');

                if (tab.dataset.tab === 'voice') {
                    setTimeout(() => {
                        this.initVisualizer();
                    }, 50);
                }
            });
        });

        // Send text message
        const messageInput = document.getElementById('messageInput');
        const sendTextButton = document.getElementById('sendTextButton');

        const sendMessage = () => {
            const message = messageInput.value.trim();
            if (message && wsHandler.sendTextMessage(message)) {
                messageInput.value = '';
            }
        };

        sendTextButton.addEventListener('click', sendMessage);
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });

        // Record button
        const recordButton = document.getElementById('recordButton');
        recordButton.addEventListener('click', () => {
            if (audioRecorder.isRecording) {
                audioRecorder.stop();
            } else {
                audioRecorder.start();
            }
        });

        // Window resize
        window.addEventListener('resize', () => this.initVisualizer());
    }
}

// Create singleton
let uiControllerInstance = null;

export function getUIController() {
    if (!uiControllerInstance) {
        uiControllerInstance = new UIController();
    }
    return uiControllerInstance;
}
