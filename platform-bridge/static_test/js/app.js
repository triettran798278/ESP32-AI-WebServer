// Main application entry point
import { log } from './utils/logger.js';
import { checkOpusLoaded, initOpusEncoder } from './core/audio/opus-codec.js';
import { getUIController } from './ui/controller.js';
import { getAudioPlayer } from './core/audio/player.js';
import { initMcpTools } from './core/mcp/tools.js';

// Application class
class App {
    constructor() {
        this.uiController = null;
        this.audioPlayer = null;
    }

    // Initialize application
    async init() {
        log('正在初始化应用...', 'info');

        // Initialize UI controller
        this.uiController = getUIController();
        this.uiController.init();

        // Check Opus library
        checkOpusLoaded();

        // Initialize Opus encoder
        initOpusEncoder();

        // Initialize audio player
        this.audioPlayer = getAudioPlayer();
        await this.audioPlayer.start();

        // Initialize MCP tools
        initMcpTools();

        log('应用初始化完成', 'success');
    }
}

// Create and start application
const app = new App();

// Initialize after DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => app.init());
} else {
    app.init();
}

export default app;
