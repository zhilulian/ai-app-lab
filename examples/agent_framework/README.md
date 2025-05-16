# Simple Agent

## Agent

**Default Agent**
通过自定义instruction 和tools 来实现一个通用的agent，整体执行流由SDK托管

**Tools**
可以传入任何python方法作为tool ，也可以通过传入MCP clients 来调用MCPserver里的工具作为tool

**Runner**
Agent的执行器。通过Runner 来运行agent

**Hooks**
Custom logic

目前支持6种hooks
Pre/Post Agent call hook: 在进入和结束agent的时候调用，除非有多agent 和多次handoff，一般来讲，一次http请求种只会发生一次

Pre/Post LLM call hook: 每次llm调用前/后发生，如果agent 有toolcall就可能会有多次LLM调用

Pre/Post Tool call hook: 在工具调用前/后发生，每调用一次就会调用一次