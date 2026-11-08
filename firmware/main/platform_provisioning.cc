#include "platform_provisioning.h"
#include "system_info.h"
#include "settings.h"
#include "board.h"

#include <esp_log.h>
#include <esp_app_desc.h>
#include <cJSON.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#define TAG "PlatformProvisioning"

PlatformProvisioning& PlatformProvisioning::GetInstance() {
    static PlatformProvisioning instance;
    return instance;
}

PlatformProvisioning::PlatformProvisioning() {
    Settings settings("platform", false);
    device_token_ = settings.GetString("device_token");
    device_id_ = settings.GetString("device_id");
    agent_id_ = settings.GetString("agent_id");

    if (!device_token_.empty() && !device_id_.empty()) {
        state_ = kLifecycleRegistered;
        ESP_LOGI(TAG, "Device already registered: id=%s, agent=%s", device_id_.c_str(), agent_id_.c_str());
    } else {
        state_ = kLifecycleUnregistered;
        ESP_LOGI(TAG, "Device currently unregistered; awaiting 6-digit activation code");
    }
}

PlatformProvisioning::~PlatformProvisioning() {
    StopHeartbeatTask();
}

const char* PlatformProvisioning::GetStateName() const {
    switch (state_) {
        case kLifecycleBoot: return "BOOT";
        case kLifecycleWifiProvisioning: return "WIFI_PROVISIONING";
        case kLifecycleConnecting: return "CONNECTING";
        case kLifecycleUnregistered: return "UNREGISTERED";
        case kLifecycleRegistering: return "REGISTERING";
        case kLifecycleRegistered: return "REGISTERED";
        case kLifecycleOnline: return "ONLINE";
        default: return "UNKNOWN";
    }
}

void PlatformProvisioning::SetState(DeviceLifecycleState new_state) {
    if (state_ != new_state) {
        ESP_LOGI(TAG, "Lifecycle State Transition: %s -> %s", GetStateName(),
                 [new_state]() {
                     switch (new_state) {
                         case kLifecycleBoot: return "BOOT";
                         case kLifecycleWifiProvisioning: return "WIFI_PROVISIONING";
                         case kLifecycleConnecting: return "CONNECTING";
                         case kLifecycleUnregistered: return "UNREGISTERED";
                         case kLifecycleRegistering: return "REGISTERING";
                         case kLifecycleRegistered: return "REGISTERED";
                         case kLifecycleOnline: return "ONLINE";
                         default: return "UNKNOWN";
                     }
                 }());
        state_ = new_state;
    }
}

bool PlatformProvisioning::IsRegistered() {
    Settings settings("platform", false);
    device_token_ = settings.GetString("device_token");
    return !device_token_.empty();
}

std::string PlatformProvisioning::GetDeviceToken() {
    if (device_token_.empty()) {
        Settings settings("platform", false);
        device_token_ = settings.GetString("device_token");
    }
    return device_token_;
}

std::string PlatformProvisioning::GetDeviceId() {
    if (device_id_.empty()) {
        Settings settings("platform", false);
        device_id_ = settings.GetString("device_id");
    }
    return device_id_;
}

std::string PlatformProvisioning::GetAgentId() {
    if (agent_id_.empty()) {
        Settings settings("platform", false);
        agent_id_ = settings.GetString("agent_id");
    }
    return agent_id_;
}

std::string PlatformProvisioning::GetPlatformUrl() {
    Settings wifi_settings("wifi", false);
    std::string url = wifi_settings.GetString("platform_url");
    if (!url.empty()) {
        return url;
    }

    // Fallback: derive from ota_url by swapping port 8003 with 8005
    std::string ota_url = wifi_settings.GetString("ota_url");
    if (!ota_url.empty()) {
        size_t port_pos = ota_url.find(":8003");
        if (port_pos != std::string::npos) {
            std::string base = ota_url.substr(0, port_pos);
            return base + ":8005";
        }
    }

    return "http://192.168.1.7:8005";
}

esp_err_t PlatformProvisioning::SubmitActivationCode(const std::string& code) {
    if (code.length() != 6) {
        ESP_LOGE(TAG, "Invalid activation code length: %zu", code.length());
        return ESP_ERR_INVALID_ARG;
    }

    SetState(kLifecycleRegistering);

    auto& board = Board::GetInstance();
    auto network = board.GetNetwork();
    if (!network) {
        ESP_LOGE(TAG, "Network interface unavailable");
        SetState(kLifecycleUnregistered);
        return ESP_FAIL;
    }

    std::string url = GetPlatformUrl() + "/api/devices/register";
    ESP_LOGI(TAG, "Submitting activation code to: %s", url.c_str());

    auto http = network->CreateHttp(0);
    http->SetHeader("Content-Type", "application/json");

    const esp_app_desc_t* app_desc = esp_app_get_description();
    std::string fw_ver = app_desc ? app_desc->version : "v2.1.8";
    std::string mac = SystemInfo::GetMacAddress();

    cJSON* root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "activation_code", code.c_str());
    cJSON_AddStringToObject(root, "mac_address", mac.c_str());
    cJSON_AddStringToObject(root, "hardware_model", "esp32s3-yolo-uno");
    cJSON_AddStringToObject(root, "firmware_version", fw_ver.c_str());
    char* payload = cJSON_PrintUnformatted(root);
    std::string body(payload);
    cJSON_free(payload);
    cJSON_Delete(root);

    http->SetContent(std::move(body));
    if (!http->Open("POST", url)) {
        ESP_LOGE(TAG, "Failed to connect to platform registration endpoint");
        SetState(kLifecycleUnregistered);
        return ESP_FAIL;
    }

    int status = http->GetStatusCode();
    std::string resp_data = http->ReadAll();
    http->Close();

    if (status != 200) {
        ESP_LOGE(TAG, "Registration failed with status %d: %s", status, resp_data.c_str());
        SetState(kLifecycleUnregistered);
        return ESP_FAIL;
    }

    cJSON* resp = cJSON_Parse(resp_data.c_str());
    if (!resp) {
        ESP_LOGE(TAG, "Failed to parse registration response JSON");
        SetState(kLifecycleUnregistered);
        return ESP_FAIL;
    }

    cJSON* j_dev_id = cJSON_GetObjectItem(resp, "device_id");
    cJSON* j_token = cJSON_GetObjectItem(resp, "device_token");
    cJSON* j_agent_id = cJSON_GetObjectItem(resp, "agent_id");
    cJSON* j_config = cJSON_GetObjectItem(resp, "config");

    if (cJSON_IsString(j_dev_id) && cJSON_IsString(j_token)) {
        device_id_ = j_dev_id->valuestring;
        device_token_ = j_token->valuestring;
        agent_id_ = cJSON_IsString(j_agent_id) ? j_agent_id->valuestring : "";

        // Persist credentials securely in NVS namespace 'platform'
        Settings settings("platform", true);
        settings.SetString("device_id", device_id_);
        settings.SetString("device_token", device_token_);
        settings.SetString("agent_id", agent_id_);

        // Also update websocket settings
        if (cJSON_IsObject(j_config)) {
            cJSON* j_ws = cJSON_GetObjectItem(j_config, "ws_url");
            if (cJSON_IsString(j_ws)) {
                Settings ws_settings("websocket", true);
                ws_settings.SetString("url", j_ws->valuestring);
                ws_settings.SetString("token", device_token_);
            }
        }

        ESP_LOGI(TAG, "Registration SUCCESS! device_id=%s, agent_id=%s", device_id_.c_str(), agent_id_.c_str());
        SetState(kLifecycleRegistered);
        cJSON_Delete(resp);
        return ESP_OK;
    }

    cJSON_Delete(resp);
    SetState(kLifecycleUnregistered);
    return ESP_FAIL;
}

esp_err_t PlatformProvisioning::FetchConfig() {
    if (device_token_.empty()) {
        GetDeviceToken();
    }
    if (device_token_.empty()) {
        SetState(kLifecycleUnregistered);
        return ESP_FAIL;
    }

    auto& board = Board::GetInstance();
    auto network = board.GetNetwork();
    if (!network) return ESP_FAIL;

    std::string url = GetPlatformUrl() + "/api/devices/me/config";
    auto http = network->CreateHttp(0);
    http->SetHeader("Authorization", ("Bearer " + device_token_).c_str());

    if (!http->Open("GET", url)) {
        ESP_LOGE(TAG, "Failed to connect to /api/devices/me/config");
        return ESP_FAIL;
    }

    int status = http->GetStatusCode();
    std::string resp = http->ReadAll();
    http->Close();

    if (status == 401) {
        ESP_LOGW(TAG, "Device token revoked by server (401). Unbinding device...");
        Unbind();
        return ESP_ERR_INVALID_STATE;
    }

    if (status != 200) {
        ESP_LOGE(TAG, "Fetch config failed: status %d", status);
        return ESP_FAIL;
    }

    cJSON* root = cJSON_Parse(resp.c_str());
    if (!root) return ESP_FAIL;

    cJSON* j_ws = cJSON_GetObjectItem(root, "ws_url");
    if (cJSON_IsString(j_ws)) {
        Settings ws_settings("websocket", true);
        ws_settings.SetString("url", j_ws->valuestring);
        ws_settings.SetString("token", device_token_);
    }

    cJSON_Delete(root);
    return ESP_OK;
}

esp_err_t PlatformProvisioning::SendHeartbeat() {
    if (device_token_.empty()) {
        GetDeviceToken();
    }
    if (device_token_.empty()) {
        return ESP_FAIL;
    }

    auto& board = Board::GetInstance();
    auto network = board.GetNetwork();
    if (!network) return ESP_FAIL;

    std::string url = GetPlatformUrl() + "/api/devices/heartbeat";
    auto http = network->CreateHttp(0);
    http->SetHeader("Authorization", ("Bearer " + device_token_).c_str());
    http->SetHeader("Content-Type", "application/json");
    http->SetContent("{}");

    if (!http->Open("POST", url)) {
        return ESP_FAIL;
    }

    int status = http->GetStatusCode();
    http->Close();

    if (status == 401) {
        ESP_LOGW(TAG, "Heartbeat 401 Unauthorized; token revoked");
        Unbind();
        return ESP_ERR_INVALID_STATE;
    }

    if (status == 200) {
        SetState(kLifecycleOnline);
        return ESP_OK;
    }

    return ESP_FAIL;
}

void PlatformProvisioning::HeartbeatTaskTrampoline(void* arg) {
    auto self = static_cast<PlatformProvisioning*>(arg);
    self->HeartbeatTaskLoop();
}

void PlatformProvisioning::HeartbeatTaskLoop() {
    while (running_heartbeat_) {
        vTaskDelay(pdMS_TO_TICKS(heartbeat_interval_ * 1000));
        if (IsRegistered()) {
            SendHeartbeat();
        }
    }
    vTaskDelete(NULL);
}

void PlatformProvisioning::StartHeartbeatTask(int interval_seconds) {
    if (running_heartbeat_) return;
    heartbeat_interval_ = interval_seconds > 0 ? interval_seconds : 30;
    running_heartbeat_ = true;
    xTaskCreate(HeartbeatTaskTrampoline, "platform_hb", 4096, this, 2, &heartbeat_task_handle_);
}

void PlatformProvisioning::StopHeartbeatTask() {
    running_heartbeat_ = false;
    heartbeat_task_handle_ = nullptr;
}

void PlatformProvisioning::Unbind() {
    ESP_LOGW(TAG, "Clearing platform credentials and unbinding device");
    Settings settings("platform", true);
    settings.EraseAll();

    device_token_.clear();
    device_id_.clear();
    agent_id_.clear();

    SetState(kLifecycleUnregistered);
}

void PlatformProvisioning::FactoryReset() {
    Unbind();
    Settings wifi("wifi", true);
    wifi.EraseAll();
    Settings ws("websocket", true);
    ws.EraseAll();
    esp_restart();
}
