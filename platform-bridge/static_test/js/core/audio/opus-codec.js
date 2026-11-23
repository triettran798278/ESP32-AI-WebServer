import { log } from '../../utils/logger.js';
import { updateScriptStatus } from '../../ui/dom-helper.js'


// Check if Opus library is loaded
export function checkOpusLoaded() {
    try {
        // Check if Module exists (global variable exported by local library)
        if (typeof Module === 'undefined') {
            throw new Error('Opus库未加载，Module对象不存在');
        }

        // Try Module.instance first (export style on the last line of libopus.js)
        if (typeof Module.instance !== 'undefined' && typeof Module.instance._opus_decoder_get_size === 'function') {
            // Use Module.instance as the global ModuleInstance
            window.ModuleInstance = Module.instance;
            log('Opus库加载成功（使用Module.instance）', 'success');
            updateScriptStatus('Opus库加载成功', 'success');

            // Hide status after 3 seconds
            const statusElement = document.getElementById('scriptStatus');
            if (statusElement) statusElement.style.display = 'none';
            return;
        }

        // If Module.instance is absent, check global Module functions
        if (typeof Module._opus_decoder_get_size === 'function') {
            window.ModuleInstance = Module;
            log('Opus库加载成功（使用全局Module）', 'success');
            updateScriptStatus('Opus库加载成功', 'success');

            // Hide status after 3 seconds
            const statusElement = document.getElementById('scriptStatus');
            if (statusElement) statusElement.style.display = 'none';
            return;
        }

        throw new Error('Opus解码函数未找到，可能Module结构不正确');
    } catch (err) {
        log(`Opus库加载失败，请检查libopus.js文件是否存在且正确: ${err.message}`, 'error');
        updateScriptStatus('Opus库加载失败，请检查libopus.js文件是否存在且正确', 'error');
    }
}


// Create an Opus encoder
let opusEncoder = null;
export function initOpusEncoder() {
    try {
        if (opusEncoder) {
            return opusEncoder; // Already initialized
        }

        if (!window.ModuleInstance) {
            log('无法创建Opus编码器：ModuleInstance不可用', 'error');
            return;
        }

        // Initialize an Opus encoder
        const mod = window.ModuleInstance;
        const sampleRate = 16000; // 16kHz sample rate
        const channels = 1;       // Mono
        const application = 2048; // OPUS_APPLICATION_VOIP = 2048

        // Create encoder
        opusEncoder = {
            channels: channels,
            sampleRate: sampleRate,
            frameSize: 960, // 60ms @ 16kHz = 60 * 16 = 960 samples
            maxPacketSize: 4000, // Max packet size
            module: mod,

            // Initialize encoder
            init: function () {
                try {
                    // Get encoder size
                    const encoderSize = mod._opus_encoder_get_size(this.channels);
                    log(`Opus编码器大小: ${encoderSize}字节`, 'info');

                    // Allocate memory
                    this.encoderPtr = mod._malloc(encoderSize);
                    if (!this.encoderPtr) {
                        throw new Error("无法分配编码器内存");
                    }

                    // Initialize encoder
                    const err = mod._opus_encoder_init(
                        this.encoderPtr,
                        this.sampleRate,
                        this.channels,
                        application
                    );

                    if (err < 0) {
                        throw new Error(`Opus编码器初始化失败: ${err}`);
                    }

                    // Set bitrate (16kbps)
                    mod._opus_encoder_ctl(this.encoderPtr, 4002, 16000); // OPUS_SET_BITRATE

                    // Set complexity (0-10, higher means better quality but more CPU)
                    mod._opus_encoder_ctl(this.encoderPtr, 4010, 5);     // OPUS_SET_COMPLEXITY

                    // Enable DTX (skip transmitting silence frames)
                    mod._opus_encoder_ctl(this.encoderPtr, 4016, 1);     // OPUS_SET_DTX

                    log("Opus编码器初始化成功", 'success');
                    return true;
                } catch (error) {
                    if (this.encoderPtr) {
                        mod._free(this.encoderPtr);
                        this.encoderPtr = null;
                    }
                    log(`Opus编码器初始化失败: ${error.message}`, 'error');
                    return false;
                }
            },

            // Encode PCM data to Opus
            encode: function (pcmData) {
                if (!this.encoderPtr) {
                    if (!this.init()) {
                        return null;
                    }
                }

                try {
                    const mod = this.module;

                    // Allocate memory for PCM data
                    const pcmPtr = mod._malloc(pcmData.length * 2); // 2 bytes/int16

                    // Copy PCM data to HEAP
                    for (let i = 0; i < pcmData.length; i++) {
                        mod.HEAP16[(pcmPtr >> 1) + i] = pcmData[i];
                    }

                    // Allocate memory for output
                    const outPtr = mod._malloc(this.maxPacketSize);

                    // Encode
                    const encodedLen = mod._opus_encode(
                        this.encoderPtr,
                        pcmPtr,
                        this.frameSize,
                        outPtr,
                        this.maxPacketSize
                    );

                    if (encodedLen < 0) {
                        throw new Error(`Opus编码失败: ${encodedLen}`);
                    }

                    // Copy encoded data
                    const opusData = new Uint8Array(encodedLen);
                    for (let i = 0; i < encodedLen; i++) {
                        opusData[i] = mod.HEAPU8[outPtr + i];
                    }

                    // Free memory
                    mod._free(pcmPtr);
                    mod._free(outPtr);

                    return opusData;
                } catch (error) {
                    log(`Opus编码出错: ${error.message}`, 'error');
                    return null;
                }
            },

            // Destroy encoder
            destroy: function () {
                if (this.encoderPtr) {
                    this.module._free(this.encoderPtr);
                    this.encoderPtr = null;
                }
            }
        };

        opusEncoder.init();
        return opusEncoder;
    } catch (error) {
        log(`创建Opus编码器失败: ${error.message}`, 'error');
        return false;
    }
}