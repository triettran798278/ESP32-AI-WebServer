#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mqtt_client.h"
#include "nvs_flash.h"

#include "node_config.h"

#if NODE_RGB_GPIO >= 0
#include "driver/rmt_tx.h"
#include "esp_rom_sys.h"
#endif

#define MQTT_BROKER_URI "mqtt://broker.emqx.io:1883"
#define TOPIC_PREFIX "tbch_8x4k"
#define TELEMETRY_PERIOD_S 10

static const char *TAG = "telemetry_node";
static esp_mqtt_client_handle_t s_mqtt_client = NULL;
static volatile bool s_mqtt_connected = false;
static volatile bool s_publish_now = false;
static volatile bool s_power1 = false;
static volatile bool s_power2 = false;
static uint32_t s_sample_tick = 0;

#if NODE_RGB_GPIO >= 0
static rmt_channel_handle_t s_rgb_chan = NULL;
static rmt_encoder_handle_t s_rgb_enc = NULL;

static void rgb_init(void)
{
    rmt_tx_channel_config_t tx_cfg = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .gpio_num = NODE_RGB_GPIO,
        .mem_block_symbols = 64,
        .resolution_hz = 10 * 1000 * 1000,
        .trans_queue_depth = 4,
    };
    ESP_ERROR_CHECK(rmt_new_tx_channel(&tx_cfg, &s_rgb_chan));

    rmt_bytes_encoder_config_t enc_cfg = {
        .bit0 = { .level0 = 1, .duration0 = 4, .level1 = 0, .duration1 = 9 },
        .bit1 = { .level0 = 1, .duration0 = 8, .level1 = 0, .duration1 = 5 },
        .flags.msb_first = 1,
    };
    ESP_ERROR_CHECK(rmt_new_bytes_encoder(&enc_cfg, &s_rgb_enc));
    ESP_ERROR_CHECK(rmt_enable(s_rgb_chan));
}

static void rgb_set(uint8_t r, uint8_t g, uint8_t b)
{
    if (s_rgb_chan == NULL || s_rgb_enc == NULL) {
        return;
    }
    uint8_t grb[3] = {g, r, b};
    rmt_transmit_config_t tx_cfg = {
        .loop_count = 0,
        .flags.eot_level = 0,
    };
    if (rmt_transmit(s_rgb_chan, s_rgb_enc, grb, sizeof(grb), &tx_cfg) == ESP_OK) {
        rmt_tx_wait_all_done(s_rgb_chan, 100);
    }
    esp_rom_delay_us(60);
}
#endif

static void led_apply_state(void)
{
    bool p1 = s_power1;
    bool p2 = s_power2;

#if NODE_LED_GPIO >= 0 && NODE_RGB_GPIO >= 0
    gpio_set_level(NODE_LED_GPIO, p1 ? 1 : 0);
    rgb_set(0, p2 ? 24 : 0, p2 ? 44 : 0);
    ESP_LOGI(TAG, "LEDs: GPIO%d=%d RGB(GPIO%d)=%s [P1=%d P2=%d]",
             NODE_LED_GPIO, p1 ? 1 : 0, NODE_RGB_GPIO, p2 ? "BLUE" : "OFF", p1, p2);
#elif NODE_RGB_GPIO >= 0
    uint8_t r = 0;
    uint8_t g = 0;
    uint8_t b = 0;
    if (p1 && p2) {
        r = 0;
        g = 40;
        b = 0;
    } else if (p1) {
        r = 40;
        g = 28;
        b = 0;
    } else if (p2) {
        r = 0;
        g = 20;
        b = 44;
    }
    rgb_set(r, g, b);
    ESP_LOGI(TAG, "RGB(GPIO%d): (%u,%u,%u) [P1=%d P2=%d]", NODE_RGB_GPIO, r, g, b, p1, p2);
#elif NODE_LED_GPIO >= 0
    gpio_set_level(NODE_LED_GPIO, (p1 || p2) ? 1 : 0);
    ESP_LOGI(TAG, "LED(GPIO%d): P1=%d P2=%d", NODE_LED_GPIO, p1, p2);
#else
    (void)p1;
    (void)p2;
#endif
}

static void led_init(void)
{
#if NODE_LED_GPIO >= 0
    gpio_reset_pin(NODE_LED_GPIO);
    gpio_set_direction(NODE_LED_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(NODE_LED_GPIO, 0);
#endif
#if NODE_RGB_GPIO >= 0
    rgb_init();
#endif
    ESP_LOGI(TAG, "Built-in LEDs configured: LED_GPIO=%d RGB_GPIO=%d", NODE_LED_GPIO, NODE_RGB_GPIO);
    led_apply_state();
}

#if NODE_I2C_SDA >= 0 && NODE_I2C_SCL >= 0
static i2c_master_bus_handle_t s_i2c_bus = NULL;
static i2c_master_dev_handle_t s_dht20_dev = NULL;

static uint8_t dht20_crc8(const uint8_t *b, size_t n)
{
    uint8_t c = 0xFF;
    for (size_t i = 0; i < n; i++) {
        c ^= b[i];
        for (int k = 0; k < 8; k++) {
            c = (c & 0x80) ? (uint8_t)((c << 1) ^ 0x31) : (uint8_t)(c << 1);
        }
    }
    return c;
}

static void dht20_reset_reg(uint8_t reg)
{
    uint8_t cmd[3] = {reg, 0x00, 0x00};
    uint8_t val[3] = {0};
    if (i2c_master_transmit(s_dht20_dev, cmd, sizeof(cmd), 100) != ESP_OK) {
        return;
    }
    vTaskDelay(pdMS_TO_TICKS(5));
    if (i2c_master_receive(s_dht20_dev, val, sizeof(val), 100) != ESP_OK) {
        return;
    }
    vTaskDelay(pdMS_TO_TICKS(10));
    uint8_t wr[3] = {(uint8_t)(0xB0 | reg), val[1], val[2]};
    if (i2c_master_transmit(s_dht20_dev, wr, sizeof(wr), 100) == ESP_OK) {
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

static void dht20_reset_if_needed(uint8_t st)
{
    if ((st & 0x18) != 0x18) {
        dht20_reset_reg(0x1B);
        dht20_reset_reg(0x1C);
        dht20_reset_reg(0x1E);
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

static bool try_i2c_pair(int sda, int scl, bool scan_all)
{
    i2c_master_bus_handle_t bus = NULL;
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = sda,
        .scl_io_num = scl,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    esp_err_t err = i2c_new_master_bus(&bus_cfg, &bus);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init I2C bus on SDA=GPIO%d SCL=GPIO%d (%s)", sda, scl, esp_err_to_name(err));
        return false;
    }

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = 0x38,
        .scl_speed_hz = 100000,
    };
    i2c_master_dev_handle_t dev = NULL;
    err = i2c_master_bus_add_device(bus, &dev_cfg, &dev);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add 0x38 device on SDA=GPIO%d SCL=GPIO%d (%s)", sda, scl, esp_err_to_name(err));
        i2c_del_master_bus(bus);
        return false;
    }

    uint8_t st = 0;
    err = i2c_master_receive(dev, &st, 1, 100);
    ESP_LOGI(TAG, "Direct 0x38 probe on SDA=GPIO%d SCL=GPIO%d -> %s (status=0x%02x)",
             sda, scl, esp_err_to_name(err), st);
    if (err == ESP_OK) {
        s_i2c_bus = bus;
        s_dht20_dev = dev;
        dht20_reset_if_needed(st);
        ESP_LOGI(TAG, "DHT20 found directly at 0x38 on SDA=GPIO%d SCL=GPIO%d (status=0x%02x)", sda, scl, st);

        static const uint16_t lcd_addrs[] = {0x21, 0x27, 0x3F};
        for (size_t k = 0; k < sizeof(lcd_addrs) / sizeof(lcd_addrs[0]); k++) {
            if (i2c_master_probe(s_i2c_bus, lcd_addrs[k], 50) == ESP_OK) {
                ESP_LOGI(TAG, "Additional I2C device found at 0x%02x", lcd_addrs[k]);
            }
        }
        return true;
    }

    i2c_master_bus_rm_device(dev);
    if (scan_all) {
        if (err == ESP_ERR_TIMEOUT) {
            ESP_LOGW(TAG, "Skipping full scan on SDA=GPIO%d SCL=GPIO%d (bus timeout)", sda, scl);
        } else {
            int found = 0;
            for (uint16_t addr = 0x08; addr <= 0x77; addr++) {
                if (i2c_master_probe(bus, addr, 50) == ESP_OK) {
                    ESP_LOGI(TAG, "I2C scan (SDA=GPIO%d SCL=GPIO%d): found 0x%02x", sda, scl, addr);
                    found++;
                }
            }
            ESP_LOGI(TAG, "I2C scan on SDA=GPIO%d SCL=GPIO%d complete: %d device(s)", sda, scl, found);
        }
    }
    i2c_del_master_bus(bus);
    return false;
}

static void i2c_init_and_scan(void)
{
    gpio_config_t io_cfg = {
        .pin_bit_mask = (1ULL << NODE_I2C_SDA) | (1ULL << NODE_I2C_SCL),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_cfg);
    vTaskDelay(pdMS_TO_TICKS(5));
    ESP_LOGI(TAG, "Idle I2C pin levels: GPIO%d=%d GPIO%d=%d",
             NODE_I2C_SDA, gpio_get_level(NODE_I2C_SDA),
             NODE_I2C_SCL, gpio_get_level(NODE_I2C_SCL));

    if (try_i2c_pair(NODE_I2C_SDA, NODE_I2C_SCL, true)) {
        return;
    }

    static const int fallback_pairs[][2] = {
        {12, 11}, {1, 2}, {2, 1}, {3, 4}, {5, 6}, {6, 7}, {8, 9}, {10, 17}, {18, 21}, {38, 39}
    };
    for (size_t i = 0; i < sizeof(fallback_pairs) / sizeof(fallback_pairs[0]); i++) {
        if (try_i2c_pair(fallback_pairs[i][0], fallback_pairs[i][1], true)) {
            return;
        }
    }

    // Re-attach primary pair + 0x38 handle so periodic reads recover automatically if plugged in later.
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = NODE_I2C_SDA,
        .scl_io_num = NODE_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    if (i2c_new_master_bus(&bus_cfg, &s_i2c_bus) == ESP_OK) {
        i2c_device_config_t dev_cfg = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = 0x38,
            .scl_speed_hz = 100000,
        };
        i2c_master_bus_add_device(s_i2c_bus, &dev_cfg, &s_dht20_dev);
    }
}

static bool dht20_read(float *out_temp, float *out_hum)
{
    if (s_dht20_dev == NULL) {
        return false;
    }

    uint8_t st = 0;
    esp_err_t err = i2c_master_receive(s_dht20_dev, &st, 1, 100);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "DHT20 status read failed: %s", esp_err_to_name(err));
        return false;
    }
    dht20_reset_if_needed(st);

    static const uint8_t trig[3] = {0xAC, 0x33, 0x00};
    err = i2c_master_transmit(s_dht20_dev, trig, sizeof(trig), 100);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "DHT20 trigger write failed: %s", esp_err_to_name(err));
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(85));

    uint8_t buf[7] = {0};
    for (int attempt = 0; attempt < 4; attempt++) {
        err = i2c_master_receive(s_dht20_dev, buf, sizeof(buf), 100);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "DHT20 data read failed: %s", esp_err_to_name(err));
            return false;
        }
        if ((buf[0] & 0x80) == 0) {
            break;
        }
        if (attempt < 3) {
            vTaskDelay(pdMS_TO_TICKS(20));
        }
    }
    if ((buf[0] & 0x80) != 0) {
        ESP_LOGW(TAG, "DHT20 still busy after retries (status=0x%02x)", buf[0]);
        return false;
    }
    uint8_t crc = dht20_crc8(buf, 6);
    if (crc != buf[6]) {
        ESP_LOGW(TAG, "DHT20 CRC mismatch (got=0x%02x expected=0x%02x)", buf[6], crc);
        return false;
    }

    uint32_t raw_h = ((uint32_t)buf[1] << 12) | ((uint32_t)buf[2] << 4) | (buf[3] >> 4);
    uint32_t raw_t = (((uint32_t)buf[3] & 0x0F) << 16) | ((uint32_t)buf[4] << 8) | buf[5];
    *out_hum = (float)raw_h * 100.0f / 1048576.0f;
    *out_temp = (float)raw_t * 200.0f / 1048576.0f - 50.0f;
    return true;
}
#endif

static void publish_telemetry(void)
{
    if (!s_mqtt_connected || s_mqtt_client == NULL) {
        return;
    }

    wifi_ap_record_t ap_info;
    int rssi = 0;
    if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
        rssi = ap_info.rssi;
    }

    long long uptime = esp_timer_get_time() / 1000000LL;
    char topic[96];
    char payload[256];
    snprintf(topic, sizeof(topic), TOPIC_PREFIX "/tele/" NODE_TASMOTA_TOPIC "/SENSOR");

#if NODE_I2C_SDA >= 0 && NODE_I2C_SCL >= 0
    float temp = 0.0f;
    float hum = 0.0f;
    if (dht20_read(&temp, &hum)) {
        snprintf(
            payload,
            sizeof(payload),
            "{\"DHT20\":{\"Temperature\":%.1f,\"Humidity\":%.1f},"
            "\"Wifi\":{\"RSSI\":%d},"
            "\"POWER1\":\"%s\",\"POWER2\":\"%s\","
            "\"fw\":\"%s\",\"uptime\":%lld}",
            temp,
            hum,
            rssi,
            s_power1 ? "ON" : "OFF",
            s_power2 ? "ON" : "OFF",
            NODE_BOARD_TAG,
            uptime
        );
    } else {
        ESP_LOGW(TAG, "DHT20 unavailable or read failed; omitting sensor keys");
        snprintf(
            payload,
            sizeof(payload),
            "{\"Wifi\":{\"RSSI\":%d},"
            "\"POWER1\":\"%s\",\"POWER2\":\"%s\","
            "\"fw\":\"%s\",\"uptime\":%lld}",
            rssi,
            s_power1 ? "ON" : "OFF",
            s_power2 ? "ON" : "OFF",
            NODE_BOARD_TAG,
            uptime
        );
    }
    (void)s_sample_tick;
#else
    uint32_t tick = s_sample_tick++;
    float temp = (float)NODE_BASE_TEMP + (float)((int)(tick % 11) - 5) * 0.1f;
    float hum = (float)NODE_BASE_HUM + (float)((int)(tick % 7) - 3) * 0.5f;
    snprintf(
        payload,
        sizeof(payload),
        "{\"DHT22\":{\"Temperature\":%.1f,\"Humidity\":%.1f},"
        "\"Wifi\":{\"RSSI\":%d},"
        "\"POWER1\":\"%s\",\"POWER2\":\"%s\","
        "\"fw\":\"%s\",\"uptime\":%lld}",
        temp,
        hum,
        rssi,
        s_power1 ? "ON" : "OFF",
        s_power2 ? "ON" : "OFF",
        NODE_BOARD_TAG,
        uptime
    );
#endif

    esp_mqtt_client_publish(s_mqtt_client, topic, payload, 0, 0, 0);
    ESP_LOGI(TAG, "Published %s -> %s", topic, payload);
}

static void publish_relay_state(const char *relay_name, bool state)
{
    if (!s_mqtt_connected || s_mqtt_client == NULL) {
        return;
    }

    const char *state_str = state ? "ON" : "OFF";
    char topic[96];
    char result_payload[64];

    snprintf(topic, sizeof(topic), TOPIC_PREFIX "/stat/" NODE_TASMOTA_TOPIC "/%s", relay_name);
    esp_mqtt_client_publish(s_mqtt_client, topic, state_str, 0, 0, 0);

    snprintf(topic, sizeof(topic), TOPIC_PREFIX "/stat/" NODE_TASMOTA_TOPIC "/RESULT");
    snprintf(result_payload, sizeof(result_payload), "{\"%s\":\"%s\"}", relay_name, state_str);
    esp_mqtt_client_publish(s_mqtt_client, topic, result_payload, 0, 0, 0);

    ESP_LOGI(TAG, "Relay %s -> %s", relay_name, state_str);
}

static void handle_cmnd(const char *topic, int topic_len, const char *data, int data_len)
{
    if (topic == NULL || topic_len <= 0) {
        return;
    }

    char topic_buf[128];
    size_t tcopy = (size_t)topic_len < sizeof(topic_buf) - 1 ? (size_t)topic_len : sizeof(topic_buf) - 1;
    memcpy(topic_buf, topic, tcopy);
    topic_buf[tcopy] = '\0';

    const char *cmnd_prefix = TOPIC_PREFIX "/cmnd/" NODE_TASMOTA_TOPIC "/";
    size_t prefix_len = strlen(cmnd_prefix);
    if (strncmp(topic_buf, cmnd_prefix, prefix_len) != 0) {
        return;
    }

    const char *cmd = topic_buf + prefix_len;
    volatile bool *target = NULL;
    const char *relay_name = NULL;
    if (strcasecmp(cmd, "POWER") == 0 || strcasecmp(cmd, "POWER1") == 0) {
        target = &s_power1;
        relay_name = "POWER1";
    } else if (strcasecmp(cmd, "POWER2") == 0) {
        target = &s_power2;
        relay_name = "POWER2";
    } else {
        ESP_LOGW(TAG, "Ignoring unsupported command: %s", cmd);
        return;
    }

    char val_buf[32];
    size_t vcopy = (data != NULL && data_len > 0)
        ? ((size_t)data_len < sizeof(val_buf) - 1 ? (size_t)data_len : sizeof(val_buf) - 1)
        : 0;
    if (vcopy > 0) {
        memcpy(val_buf, data, vcopy);
    }
    val_buf[vcopy] = '\0';
    while (vcopy > 0 && (val_buf[vcopy - 1] == '\r' || val_buf[vcopy - 1] == '\n' ||
                         val_buf[vcopy - 1] == ' ' || val_buf[vcopy - 1] == '\t')) {
        val_buf[--vcopy] = '\0';
    }

    if (vcopy == 0 || strcmp(val_buf, "?") == 0) {
        publish_relay_state(relay_name, *target);
        return;
    }
    if (strcasecmp(val_buf, "1") == 0 || strcasecmp(val_buf, "ON") == 0 || strcasecmp(val_buf, "true") == 0) {
        *target = true;
    } else if (strcasecmp(val_buf, "0") == 0 || strcasecmp(val_buf, "OFF") == 0 || strcasecmp(val_buf, "false") == 0) {
        *target = false;
    } else if (strcasecmp(val_buf, "TOGGLE") == 0 || strcmp(val_buf, "2") == 0) {
        *target = !(*target);
    } else {
        ESP_LOGW(TAG, "Ignoring invalid %s payload: %s", relay_name, val_buf);
        return;
    }

    led_apply_state();
    publish_relay_state(relay_name, *target);
}

static void mqtt_event_handler(void *arg, esp_event_base_t base, int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;
    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED: {
        char lwt_topic[96];
        char cmnd_sub[96];
        s_mqtt_connected = true;
        ESP_LOGI(TAG, "MQTT connected to %s", MQTT_BROKER_URI);

        snprintf(lwt_topic, sizeof(lwt_topic), TOPIC_PREFIX "/tele/" NODE_TASMOTA_TOPIC "/LWT");
        esp_mqtt_client_publish(s_mqtt_client, lwt_topic, "Online", 6, 0, 1);

        snprintf(cmnd_sub, sizeof(cmnd_sub), TOPIC_PREFIX "/cmnd/" NODE_TASMOTA_TOPIC "/#");
        esp_mqtt_client_subscribe(s_mqtt_client, cmnd_sub, 0);

        s_publish_now = true;
        break;
    }
    case MQTT_EVENT_DISCONNECTED:
        s_mqtt_connected = false;
        ESP_LOGW(TAG, "MQTT disconnected");
        break;
    case MQTT_EVENT_DATA:
        if (event->current_data_offset == 0) {
            handle_cmnd(event->topic, event->topic_len, event->data, event->data_len);
        }
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "MQTT error");
        break;
    default:
        break;
    }
}

static void start_mqtt_once(void)
{
    if (s_mqtt_client != NULL) {
        return;
    }

    static char client_id[64];
    static char lwt_topic[96];
    uint8_t mac[6] = {0};
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    snprintf(client_id, sizeof(client_id), TOPIC_PREFIX "_" NODE_TASMOTA_TOPIC "_%02x%02x", mac[4], mac[5]);
    snprintf(lwt_topic, sizeof(lwt_topic), TOPIC_PREFIX "/tele/" NODE_TASMOTA_TOPIC "/LWT");

    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = MQTT_BROKER_URI,
        .credentials.client_id = client_id,
        .session.keepalive = 30,
        .session.last_will = {
            .topic = lwt_topic,
            .msg = "Offline",
            .msg_len = 7,
            .qos = 0,
            .retain = 1,
        },
    };

    s_mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    esp_mqtt_client_register_event(s_mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    esp_mqtt_client_start(s_mqtt_client);
}

static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t event_id, void *event_data)
{
    if (base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        s_mqtt_connected = false;
        ESP_LOGW(TAG, "Wi-Fi disconnected, reconnecting to %s...", NODE_WIFI_SSID);
        esp_wifi_connect();
    } else if (base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));
        start_mqtt_once();
    }
}

static void wifi_init_sta(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = NODE_WIFI_SSID,
            .password = NODE_WIFI_PASS,
            .threshold.authmode = WIFI_AUTH_WPA_WPA2_PSK,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_LOGI(TAG, "Starting node %s (%s) on SSID %s", NODE_BOARD_TAG, NODE_TASMOTA_TOPIC, NODE_WIFI_SSID);
    led_init();
#if NODE_I2C_SDA >= 0 && NODE_I2C_SCL >= 0
    vTaskDelay(pdMS_TO_TICKS(1000));
    i2c_init_and_scan();
#endif
    wifi_init_sta();

    int telemetry_ticks = 0;
#if NODE_LED_GPIO >= 0 && NODE_RGB_GPIO < 0
    int blink_ticks = 0;
    bool blink_state = false;
#endif
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(50));

#if NODE_LED_GPIO >= 0 && NODE_RGB_GPIO < 0
        bool p1 = s_power1;
        bool p2 = s_power2;
        if (!p1 && !p2) {
            gpio_set_level(NODE_LED_GPIO, 0);
            blink_ticks = 0;
            blink_state = false;
        } else if (p1 && !p2) {
            gpio_set_level(NODE_LED_GPIO, 1);
            blink_ticks = 0;
            blink_state = true;
        } else {
            int period_ticks = (p1 && p2) ? 3 : 10;
            if (++blink_ticks >= period_ticks) {
                blink_ticks = 0;
                blink_state = !blink_state;
                gpio_set_level(NODE_LED_GPIO, blink_state ? 1 : 0);
            }
        }
#endif

        telemetry_ticks++;
        if (s_publish_now || telemetry_ticks >= TELEMETRY_PERIOD_S * 20) {
            s_publish_now = false;
            telemetry_ticks = 0;
            publish_telemetry();
        }
    }
}
