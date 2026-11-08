#ifndef PRESS_TO_TALK_MCP_TOOL_H
#define PRESS_TO_TALK_MCP_TOOL_H

#include "mcp_server.h"
#include "settings.h"

// MCPtool
class PressToTalkMcpTool {
private:
    bool press_to_talk_enabled_;

public:
    PressToTalkMcpTool();
    
    // initializetool, MCPservice
    void Initialize();
    
    // getstatus
    bool IsPressToTalkEnabled() const;

private:
    // MCPtool
    ReturnValue HandleSetPressToTalk(const PropertyList& properties);
    
    // : setpress to talkstatusset
    void SetPressToTalkEnabled(bool enabled);
};

#endif // PRESS_TO_TALK_MCP_TOOL_H 