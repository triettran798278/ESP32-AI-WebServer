 WebSocket , deviceservice WebSocket . 

, service. 

---

## 1. 

1. **deviceinitialize**  
   - device, initialize `Application`:   
     - initializeaudio, , LED   
     - connectnetwork  
     - createinitialize `Protocol` api WebSocket  (`WebsocketProtocol`)   
   -  (audio, audio, ) . 

2. ** WebSocket connect**  
   - devicestartvoice (user, ) , call `OpenAudioChannel()`:   
     - configget WebSocket URL
     - set (`Authorization`, `Protocol-Version`, `Device-Id`, `Client-Id`)   
     - call `Connect()` service WebSocket connect  

3. **devicesend "hello" message**  
   - connectsuccess, devicesend JSON message, :   
   ```json
   {
     "type": "hello",
     "version": 1,
     "features": {
       "mcp": true
     },
     "transport": "websocket",
     "audio_params": {
       "format": "opus",
       "sample_rate": 16000,
       "channels": 1,
       "frame_duration": 60
     }
   }
   ```
   -  `features` field, deviceconfig. : `"mcp": true` support MCP . 
   - `frame_duration`  `OPUS_FRAME_DURATION_MS` ( 60ms) . 

4. **service "hello"**  
   - deviceservicereturn `"type": "hello"`  JSON message, check `"transport": "websocket"` .   
   - service `session_id` field, device.   
   - : 
   ```json
   {
     "type": "hello",
     "transport": "websocket",
     "session_id": "xxx",
     "audio_params": {
       "format": "opus",
       "sample_rate": 24000,
       "channels": 1,
       "frame_duration": 60
     }
   }
   ```
   - , service, audiosuccess.   
   - timeouttime (default 10 ) , connectfailednetworkError. 

5. **message**  
   - deviceservicesendtypedata:   
     1. **audiodata** (Opus )   
     2. ** JSON message** (status, TTS/STT , MCP message)   

   - , receive:   
     - `OnData(...)`:  
       -  `binary`  `true` , audio; device Opus data.   
       -  `binary`  `false` ,  JSON , device cJSON process (, TTS, MCP message) .   

   - servicenetwork,  `OnDisconnected()` :   
     - devicecall `on_audio_channel_closed_()`, status. 

6. **close WebSocket connect**  
   - deviceendvoice, call `CloseAudioChannel()` disconnectconnect, status.   
   - servicedisconnect, . 

---

## 2. 

 WebSocket connect, set: 

- `Authorization`: ,  `"Bearer <token>"`  
- `Protocol-Version`: version,  hello message `version` field  
- `Device-Id`: device MAC address
- `Client-Id`:  UUID ( NVS ) 

 WebSocket Shake handsendservice, service, auth. 

---

## 3. version

devicesupportversion, config `version` field: 

### 3.1 version1 (default) 
send Opus audiodata, data. Websocket  text  binary. 

### 3.2 version2
use `BinaryProtocol2` : 
```c
struct BinaryProtocol2 {
    uint16_t version;        // version
    uint16_t type;           // messagetype (0: OPUS, 1: JSON)
    uint32_t reserved;       // field
    uint32_t timestamp;      // time (, serviceAEC) 
    uint32_t payload_size;   //  () 
    uint8_t payload[];       // data
} __attribute__((packed));
```

### 3.3 version3
use `BinaryProtocol3` : 
```c
struct BinaryProtocol3 {
    uint8_t type;            // messagetype
    uint8_t reserved;        // field
    uint16_t payload_size;   // 
    uint8_t payload[];       // data
} __attribute__((packed));
```

---

## 4. JSON message

WebSocket  JSON ,  `"type"` field. messagefield, . 

### 4.1 device→service

1. **Hello**  
   - connectsuccess, devicesend, serviceparam.   
   - : 
     ```json
     {
       "type": "hello",
       "version": 1,
       "features": {
         "mcp": true
       },
       "transport": "websocket",
       "audio_params": {
         "format": "opus",
         "sample_rate": 16000,
         "channels": 1,
         "frame_duration": 60
       }
     }
     ```

2. **Listen**  
   - devicestartstop.   
   - field:   
     - `"session_id"`:   
     - `"type": "listen"`  
     - `"state"`: `"start"`, `"stop"`, `"detect"` ()   
     - `"mode"`: `"auto"`, `"manual"`  `"realtime"`, .   
   - : start  
     ```json
     {
       "session_id": "xxx",
       "type": "listen",
       "state": "start",
       "mode": "manual"
     }
     ```

3. **Abort**  
   -  (TTS ) voice.   
   - : 
     ```json
     {
       "session_id": "xxx",
       "type": "abort",
       "reason": "wake_word_detected"
     }
     ```
   - `reason`  `"wake_word_detected"` . 

4. **Wake Word Detected**  
   - deviceservice. 
   - sendmessage, send Opus audiodata, service.   
   - : 
     ```json
     {
       "session_id": "xxx",
       "type": "listen",
       "state": "detect",
       "text": ""
     }
     ```

5. **MCP**
   - . device, toolcall type: "mcp" message, payload  JSON-RPC 2.0 ( [MCP ](./mcp-protocol.md)) . 
   
   - **deviceservicesend result : **
     ```json
     {
       "session_id": "xxx",
       "type": "mcp",
       "payload": {
         "jsonrpc": "2.0",
         "id": 1,
         "result": {
           "content": [
             { "type": "text", "text": "true" }
           ],
           "isError": false
         }
       }
     }
     ```

---

### 4.2 service→device

1. **Hello**  
   - servicereturnShake handmessage.   
   -  `"type": "hello"`  `"transport": "websocket"`.   
   -  `audio_params`, serviceaudioparam, deviceconfig.    
   - service `session_id` field, device.   
   - successreceivedeviceset,  WebSocket . 

2. **STT**  
   - `{"session_id": "xxx", "type": "stt", "text": "..."}`
   - serviceuservoice.  (voice)   
   - devicedisplay, . 

3. **LLM**  
   - `{"session_id": "xxx", "type": "llm", "emotion": "happy", "text": "😀"}`
   - servicedevice / UI .   

4. **TTS**  
   - `{"session_id": "xxx", "type": "tts", "state": "start"}`: service TTS audio, device "speaking" status.   
   - `{"session_id": "xxx", "type": "tts", "state": "stop"}`:  TTS end.   
   - `{"session_id": "xxx", "type": "tts", "state": "sentence_start", "text": "..."}`
     - device (user) .   

5. **MCP**
   - service type: "mcp" messagereturncall, payload . 
   
   - **servicedevicesend tools/call : **
     ```json
     {
       "session_id": "xxx",
       "type": "mcp",
       "payload": {
         "jsonrpc": "2.0",
         "method": "tools/call",
         "params": {
           "name": "self.light.set_rgb",
           "arguments": { "r": 255, "g": 0, "b": 0 }
         },
         "id": 1
       }
     }
     ```

6. **System**
   - , upgradeupdate. 
   - : 
     ```json
     {
       "session_id": "xxx",
       "type": "system",
       "command": "reboot"
     }
     ```
   - support: 
     - `"reboot"`: Restartdevice

7. **Custom** () 
   - message,  `CONFIG_RECEIVE_CUSTOM_MESSAGE` support. 
   - : 
     ```json
     {
       "session_id": "xxx",
       "type": "custom",
       "payload": {
         "message": ""
       }
     }
     ```

8. **audiodata: **  
   - servicesendaudio (Opus ) , device.   
   - device "listening"  () status, audio. 

---

## 5. audio

1. **devicesenddata**  
   - audio, volume,  Opus sendservice.   
   - version, send Opus data (version1) usedata (version2/3) . 

2. **deviceaudio**  
   - service,  Opus data.   
   - device, audioapi.   
   - serviceaudiodevice, . 

---

## 6. status

devicestatus,  WebSocket message: 

1. **Idle** → **Connecting**  
   - user, devicecall `OpenAudioChannel()` →  WebSocket connect → send `"type":"hello"`.   

2. **Connecting** → **Listening**  
   - successconnect,  `SendStartListening(...)`, status. devicemicrophonedatasendservice.   

3. **Listening** → **Speaking**  
   - service TTS Start message (`{"type":"tts","state":"start"}`) → stopreceiveaudio.   

4. **Speaking** → **Idle**  
   - service TTS Stop (`{"type":"tts","state":"stop"}`) → audioend. , return Idle; config,  Listening.   

5. **Listening** / **Speaking** → **Idle** ()   
   - call `SendAbortSpeaking(...)`  `CloseAudioChannel()` →  → close WebSocket → status Idle.   

### status

```mermaid
stateDiagram
  direction TB
  [*] --> kDeviceStateUnknown
  kDeviceStateUnknown --> kDeviceStateStarting:initialize
  kDeviceStateStarting --> kDeviceStateWifiConfiguring:configWiFi
  kDeviceStateStarting --> kDeviceStateActivating:device
  kDeviceStateActivating --> kDeviceStateUpgrading:version
  kDeviceStateActivating --> kDeviceStateIdle:
  kDeviceStateIdle --> kDeviceStateConnecting:startconnect
  kDeviceStateConnecting --> kDeviceStateIdle:connectfailed
  kDeviceStateConnecting --> kDeviceStateListening:connectsuccess
  kDeviceStateListening --> kDeviceStateSpeaking:start
  kDeviceStateSpeaking --> kDeviceStateListening:end
  kDeviceStateListening --> kDeviceStateIdle:
  kDeviceStateSpeaking --> kDeviceStateIdle:
```

### status

```mermaid
stateDiagram
  direction TB
  [*] --> kDeviceStateUnknown
  kDeviceStateUnknown --> kDeviceStateStarting:initialize
  kDeviceStateStarting --> kDeviceStateWifiConfiguring:configWiFi
  kDeviceStateStarting --> kDeviceStateActivating:device
  kDeviceStateActivating --> kDeviceStateUpgrading:version
  kDeviceStateActivating --> kDeviceStateIdle:
  kDeviceStateIdle --> kDeviceStateConnecting:startconnect
  kDeviceStateConnecting --> kDeviceStateIdle:connectfailed
  kDeviceStateConnecting --> kDeviceStateListening:connectsuccess
  kDeviceStateIdle --> kDeviceStateListening:start
  kDeviceStateListening --> kDeviceStateIdle:stop
  kDeviceStateIdle --> kDeviceStateSpeaking:start
  kDeviceStateSpeaking --> kDeviceStateIdle:end
```

---

## 7. Errorprocess

1. **connectfailed**  
   -  `Connect(url)` returnfailedservice "hello" messagetimeout,  `on_network_error_()` . device"connectservice"Error message. 

2. **servicedisconnect**  
   -  WebSocket disconnect,  `OnDisconnected()`:   
     - device `on_audio_channel_closed_()`  
     -  Idle retry. 

---

## 8. 

1. ****  
   - deviceset `Authorization: Bearer <token>` , serviceverify.   
   - , serviceShake handdisconnect. 

2. ****  
   - message `session_id`, . serviceprocess. 

3. **audio**  
   - defaultuse Opus , set `sample_rate = 16000`, .  `OPUS_FRAME_DURATION_MS` ,  60ms. . music, serviceaudiouse 24000 . 

4. **versionconfig**  
   - set `version` fieldconfigversion (1, 2  3) 
   - version1: send Opus data
   - version2: usetime, service AEC
   - version3: use

5. ** MCP **  
   - deviceservice, status, ,  MCP  (type: "mcp") .  type: "iot" . 
   - MCP  WebSocket, MQTT , . 
   -  [MCP ](./mcp-protocol.md)  [MCP ](./mcp-usage.md). 

6. **Error JSON**  
   -  JSON field,  `{"type": ...}`, deviceError (`ESP_LOGE(TAG, "Missing message type, data: %s", data);`) , . 

---

## 9. message

message () : 

1. **device → service** (Shake hand) 
   ```json
   {
     "type": "hello",
     "version": 1,
     "features": {
       "mcp": true
     },
     "transport": "websocket",
     "audio_params": {
       "format": "opus",
       "sample_rate": 16000,
       "channels": 1,
       "frame_duration": 60
     }
   }
   ```

2. **service → device** (Shake hand) 
   ```json
   {
     "type": "hello",
     "transport": "websocket",
     "session_id": "xxx",
     "audio_params": {
       "format": "opus",
       "sample_rate": 16000
     }
   }
   ```

3. **device → service** (start) 
   ```json
   {
     "session_id": "xxx",
     "type": "listen",
     "state": "start",
     "mode": "auto"
   }
   ```
   devicestartsend (Opus data) . 

4. **service → device** (ASR ) 
   ```json
   {
     "session_id": "xxx",
     "type": "stt",
     "text": "user"
   }
   ```

5. **service → device** (TTSstart) 
   ```json
   {
     "session_id": "xxx",
     "type": "tts",
     "state": "start"
   }
   ```
   servicesendaudiodevice. 

6. **service → device** (TTSend) 
   ```json
   {
     "session_id": "xxx",
     "type": "tts",
     "state": "stop"
   }
   ```
   devicestopaudio, , status. 

---

## 10. 

 WebSocket  JSON audio, successaudio, TTS audio, voicestatus, MCP . : 

- **Shake hand**: send `"type":"hello"`, servicereturn.   
- **audio**:  Opus voice, supportversion.   
- **JSON message**: use `"type"` field,  TTS, STT, MCP, WakeWord, System, Custom .   
- ****:  JSON messagefield,  headers . 

servicedevicemessagefield, Errorprocess, . , , . 
