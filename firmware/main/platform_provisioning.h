#ifndef PLATFORM_PROVISIONING_H
#define PLATFORM_PROVISIONING_H

#include <string>
#include <functional>
#include <esp_err.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

enum DeviceLifecycleState {
    kLifecycleBoot = 0,
    kLifecycleWifiProvisioning,
    kLifecycleConnecting,
    kLifecycleUnregistered,
    kLifecycleRegistering,
    kLifecycleRegistered,
    kLifecycleOnline
};

class PlatformProvisioning {
public:
    static PlatformProvisioning& GetInstance();

    DeviceLifecycleState GetState() const { return state_; }
    const char* GetStateName() const;
    void SetState(DeviceLifecycleState new_state);

    bool IsRegistered();
    std::string GetDeviceToken();
    std::string GetDeviceId();
    std::string GetAgentId();
    std::string GetPlatformUrl();

    // Core Provisioning & Activation
    esp_err_t SubmitActivationCode(const std::string& code);
    esp_err_t FetchConfig();
    esp_err_t SendHeartbeat();
    void StartHeartbeatTask(int interval_seconds = 30);
    void StopHeartbeatTask();

    // Lifecycle reset
    void Unbind();
    void FactoryReset();

private:
    PlatformProvisioning();
    ~PlatformProvisioning();

    static void HeartbeatTaskTrampoline(void* arg);
    void HeartbeatTaskLoop();

    DeviceLifecycleState state_ = kLifecycleBoot;
    std::string device_token_;
    std::string device_id_;
    std::string agent_id_;
    int heartbeat_interval_ = 30;
    TaskHandle_t heartbeat_task_handle_ = nullptr;
    bool running_heartbeat_ = false;
};

#endif // PLATFORM_PROVISIONING_H
