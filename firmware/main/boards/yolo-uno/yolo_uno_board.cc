#include "wifi_board.h"
#include "application.h"
#include "button.h"
#include "audio_codec.h"
#include "display/lcd_display.h"

#include <esp_log.h>
#include <esp_heap_caps.h>
#include <driver/i2s_std.h>
#include <driver/spi_common.h>
#include <esp_lcd_panel_vendor.h>
#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>
#include <vector>
#include <cmath>
#include <algorithm>
#include <mutex>

#define TAG "YoloUno"

// Pin Definitions based on verified hardware:
// Microphone INMP441 (I2S Input)
#define MIC_I2S_BCLK GPIO_NUM_4
#define MIC_I2S_WS   GPIO_NUM_5
#define MIC_I2S_DATA GPIO_NUM_6

// Amplifier MAX98357A (I2S Output, shared clocks)
#define SPK_I2S_BCLK GPIO_NUM_4
#define SPK_I2S_WS   GPIO_NUM_5
#define SPK_I2S_DATA GPIO_NUM_7

// LCD ST7789 (SPI)
#define DISPLAY_MOSI_PIN GPIO_NUM_11
#define DISPLAY_CLK_PIN  GPIO_NUM_12
#define DISPLAY_RST_PIN  GPIO_NUM_10
#define DISPLAY_DC_PIN   GPIO_NUM_9
#define DISPLAY_CS_PIN   GPIO_NUM_8
#define DISPLAY_BL_PIN   GPIO_NUM_13

#define DISPLAY_WIDTH    240
#define DISPLAY_HEIGHT   240

LV_FONT_DECLARE(font_puhui_16_4);
LV_FONT_DECLARE(font_awesome_16_4);

class YoloUnoAudioCodec : public AudioCodec {
private:
    std::mutex tx_mutex_;
    std::mutex rx_mutex_;

public:
    YoloUnoAudioCodec(int sample_rate, gpio_num_t bclk, gpio_num_t ws, gpio_num_t dout, gpio_num_t din) {
        duplex_ = true;
        input_sample_rate_ = sample_rate;
        output_sample_rate_ = sample_rate;
        input_channels_ = 1;
        output_channels_ = 1;
        output_volume_ = 90;

        i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
        chan_cfg.dma_desc_num = AUDIO_CODEC_DMA_DESC_NUM;
        chan_cfg.dma_frame_num = AUDIO_CODEC_DMA_FRAME_NUM;
        chan_cfg.auto_clear_after_cb = true;
        chan_cfg.auto_clear_before_cb = false;
        chan_cfg.intr_priority = 0;
        ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, &tx_handle_, &rx_handle_));

        // Shared I2S Philips Standard stereo 32-bit slot configuration
        i2s_std_config_t std_cfg = {
            .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(static_cast<uint32_t>(sample_rate)),
            .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
            .gpio_cfg = {
                .mclk = I2S_GPIO_UNUSED,
                .bclk = bclk,
                .ws = ws,
                .dout = dout,
                .din = din,
                .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false }
            }
        };
        std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_BOTH;

        ESP_ERROR_CHECK(i2s_channel_init_std_mode(tx_handle_, &std_cfg));
        ESP_ERROR_CHECK(i2s_channel_init_std_mode(rx_handle_, &std_cfg));
        ESP_LOGI(TAG, "Duplex stereo I2S ready: BCLK=GPIO%d, WS=GPIO%d, DOUT=GPIO%d, DIN=GPIO%d", bclk, ws, dout, din);
    }

    ~YoloUnoAudioCodec() override {
        if (rx_handle_ != nullptr) {
            i2s_channel_disable(rx_handle_);
        }
        if (tx_handle_ != nullptr) {
            i2s_channel_disable(tx_handle_);
        }
    }

    int Write(const int16_t* data, int samples) override {
        std::lock_guard<std::mutex> lock(tx_mutex_);
        if (tx_handle_ == nullptr || samples <= 0) return 0;
        if (!output_enabled_) {
            EnableOutput(true);
        }

        // Stereo expansion: duplicate mono sample to both Left and Right channels for MAX98357A
        std::vector<int32_t> buffer(samples * 2);
        int32_t volume_factor = (output_volume_ * output_volume_ * 65536) / 10000;
        for (int i = 0; i < samples; i++) {
            int64_t v = (int64_t)data[i] * volume_factor;
            int32_t s32 = (int32_t)std::clamp<int64_t>(v, INT32_MIN, INT32_MAX);
            buffer[i * 2] = s32;     // Left slot
            buffer[i * 2 + 1] = s32; // Right slot
        }

        size_t bytes_written = 0;
        esp_err_t err = i2s_channel_write(tx_handle_, buffer.data(), buffer.size() * sizeof(int32_t), &bytes_written, portMAX_DELAY);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "i2s write failed: %s", esp_err_to_name(err));
            return 0;
        }
        return samples;
    }

    int Read(int16_t* dest, int samples) override {
        std::lock_guard<std::mutex> lock(rx_mutex_);
        if (rx_handle_ == nullptr || samples <= 0) return 0;
        if (!input_enabled_) {
            EnableInput(true);
        }

        std::vector<int32_t> buffer(samples * 2);
        size_t bytes_read = 0;
        esp_err_t err = i2s_channel_read(rx_handle_, buffer.data(), buffer.size() * sizeof(int32_t), &bytes_read, portMAX_DELAY);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "i2s read failed: %s", esp_err_to_name(err));
            return 0;
        }

        // INMP441 with L/R grounded sends 24-bit data on Left channel (index 0, 2, 4...)
        // Bit 31 is sign bit, bits 31..8 are the 24 data bits.
        for (int i = 0; i < samples; i++) {
            int32_t raw_l = buffer[i * 2];
            int32_t raw_r = buffer[i * 2 + 1];
            int32_t raw = (std::abs(raw_l) >= std::abs(raw_r)) ? raw_l : raw_r;
            int32_t val = raw >> 14;
            dest[i] = (int16_t)std::clamp<int32_t>(val, -32768, 32767);
        }
        return samples;
    }
};

static YoloUnoAudioCodec g_audio_codec(16000, MIC_I2S_BCLK, MIC_I2S_WS, SPK_I2S_DATA, MIC_I2S_DATA);

class YoloUnoBoard : public WifiBoard {
private:
    Button boot_button_{GPIO_NUM_0};
    LcdDisplay* display_ = nullptr;

    void InitializeSpi() {
        spi_bus_config_t buscfg = {};
        buscfg.mosi_io_num = DISPLAY_MOSI_PIN;
        buscfg.miso_io_num = GPIO_NUM_NC;
        buscfg.sclk_io_num = DISPLAY_CLK_PIN;
        buscfg.quadwp_io_num = GPIO_NUM_NC;
        buscfg.quadhd_io_num = GPIO_NUM_NC;
        buscfg.max_transfer_sz = DISPLAY_WIDTH * DISPLAY_HEIGHT * sizeof(uint16_t);
        ESP_ERROR_CHECK(spi_bus_initialize(SPI3_HOST, &buscfg, SPI_DMA_CH_AUTO));
    }

    void InitializeLcdDisplay() {
        esp_lcd_panel_io_handle_t panel_io = nullptr;
        esp_lcd_panel_handle_t panel = nullptr;

        esp_lcd_panel_io_spi_config_t io_config = {};
        io_config.cs_gpio_num = DISPLAY_CS_PIN;
        io_config.dc_gpio_num = DISPLAY_DC_PIN;
        io_config.spi_mode = 0;
        io_config.pclk_hz = 40 * 1000 * 1000;
        io_config.trans_queue_depth = 10;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(SPI3_HOST, &io_config, &panel_io));

        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = DISPLAY_RST_PIN;
        panel_config.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB;
        panel_config.bits_per_pixel = 16;
        ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(panel_io, &panel_config, &panel));

        esp_lcd_panel_reset(panel);
        esp_lcd_panel_init(panel);
        esp_lcd_panel_invert_color(panel, true);
        esp_lcd_panel_swap_xy(panel, false);
        esp_lcd_panel_mirror(panel, false, false);

        display_ = new SpiLcdDisplay(panel_io, panel,
                                    DISPLAY_WIDTH, DISPLAY_HEIGHT, 0, 0, false, false, false,
                                    {
                                        .text_font = &font_puhui_16_4,
                                        .icon_font = &font_awesome_16_4,
                                        .emoji_font = font_emoji_32_init(),
                                    });
    }

public:
    YoloUnoBoard() {
        InitializeSpi();
        InitializeLcdDisplay();
        GetBacklight()->RestoreBrightness();

        boot_button_.OnClick([]() {
            Application::GetInstance().ToggleChatState();
        });
    }

    AudioCodec* GetAudioCodec() override {
        return &g_audio_codec;
    }

    Display* GetDisplay() override {
        return display_;
    }

    Backlight* GetBacklight() override {
        static PwmBacklight backlight(DISPLAY_BL_PIN, false);
        return &backlight;
    }
};

DECLARE_BOARD(YoloUnoBoard);
