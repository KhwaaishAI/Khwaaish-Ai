import asyncio
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

def mcp_to_langchain_tool(mcp_tool, session):
    """Convert MCP tool to LangChain StructuredTool with proper schema"""
    
    # Create Pydantic model from inputSchema
    schema = mcp_tool.inputSchema
    fields = {}
    
    if "properties" in schema:
        for prop_name, prop_info in schema["properties"].items():
            prop_type = str
            if prop_info.get("type") == "number":
                prop_type = float
            elif prop_info.get("type") == "integer":
                prop_type = int
            elif prop_info.get("type") == "boolean":
                prop_type = bool
            
            is_required = prop_name in schema.get("required", [])
            default = ... if is_required else None
            
            fields[prop_name] = (
                prop_type,
                Field(default=default, description=prop_info.get("description", ""))
            )
    
    InputModel = create_model(f"{mcp_tool.name}_input", **fields)
    
    async def tool_func(**kwargs):
        """Execute MCP tool"""
        result = await session.call_tool(mcp_tool.name, kwargs)
        if result.content:
            return str(result.content[0].text) if hasattr(result.content[0], 'text') else str(result.content[0])
        return "Success"
    
    return StructuredTool(
        name=mcp_tool.name,
        description=mcp_tool.description or mcp_tool.name,
        func=lambda **kwargs: asyncio.create_task(tool_func(**kwargs)),
        coroutine=tool_func,
        args_schema=InputModel
    )
