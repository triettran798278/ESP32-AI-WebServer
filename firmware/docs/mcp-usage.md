# MCP 

>  MCP  ESP32 device.  [`mcp-protocol.md`](./mcp-protocol.md). 

## 

MCP (Model Context Protocol) ,  JSON-RPC 2.0 devicecall"tool" (Tool) , device. 

## use

1. device ( WebSocket/MQTT) connect. 
2.  MCP  `initialize` initialize. 
3.  `tools/list` getdevicesupporttool () param. 
4.  `tools/call` calltool, device. 

 [`mcp-protocol.md`](./mcp-protocol.md). 

## devicetool

device `McpServer::AddTool` call"tool". : 

```cpp
void AddTool(
    const std::string& name,           // toolname, ,  self.dog.forward
    const std::string& description,    // tooldescription, , model
    const PropertyList& properties,    // param () , supporttype: , , 
    std::function<ReturnValue(const PropertyList&)> callback // toolcall
);
```
- name: tool, ".". 
- description: description,  AI/user. 
- properties: param, supporttype, , , default. 
- callback: call, return bool/int/string. 

##  ( ESP-Hi ) 

```cpp
void InitializeTools() {
    auto& mcp_server = McpServer::GetInstance();
    // 1: param, 
    mcp_server.AddTool("self.dog.forward", "Move forward", PropertyList(), [this](const PropertyList&) -> ReturnValue {
        servo_dog_ctrl_send(DOG_STATE_FORWARD, NULL);
        return true;
    });
    // 2: param, set RGB 
    mcp_server.AddTool("self.light.set_rgb", "Set RGB color", PropertyList({
        Property("r", kPropertyTypeInteger, 0, 255),
        Property("g", kPropertyTypeInteger, 0, 255),
        Property("b", kPropertyTypeInteger, 0, 255)
    }), [this](const PropertyList& properties) -> ReturnValue {
        int r = properties["r"].value<int>();
        int g = properties["g"].value<int>();
        int b = properties["b"].value<int>();
        led_on_ = true;
        SetLedColor(r, g, b);
        return true;
    });
}
```

## toolcall JSON-RPC 

### 1. gettool
```json
{
  "jsonrpc": "2.0",
  "method": "tools/list",
  "params": { "cursor": "" },
  "id": 1
}
```

### 2. 
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "self.chassis.go_forward",
    "arguments": {}
  },
  "id": 2
}
```

### 3. 
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "self.chassis.switch_light_mode",
    "arguments": { "light_mode": 3 }
  },
  "id": 3
}
```

### 4. 
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "self.camera.set_camera_flipped",
    "arguments": {}
  },
  "id": 4
}
```

## remark
- toolname, paramreturndevice `AddTool` . 
-  MCP . 
-  [`mcp-protocol.md`](./mcp-protocol.md).  