"""
Simple MCP Client using FastMCP Client.

This client uses FastMCP's Client class which automatically handles
the server process and communication.
"""

import asyncio
import json
from pathlib import Path
from fastmcp import Client


async def main():
    """
    Main function that:
    1. Spawns the MCP server process (automatically)
    2. Lists available tools
    3. Calls the list_models tool
    """
    
    print("🔌 Starting MCP server process...")
    
    # Get absolute path to server file
    # Client is in: mlentory_mcp/client/main.py
    # Server is in: mlentory_mcp/server/main.py
    client_dir = Path(__file__).parent  # mlentory_mcp/client/
    server_path = client_dir.parent / "server" / "main.py"
    
    # FastMCP Client automatically infers stdio transport for .py files
    # Pass absolute path as string
    client = Client(str(server_path.absolute()))
    
    try:
        # Connection and initialization happen automatically
        async with client:
            print("✅ Connected to MCP server!\n")
            
            # Step 1: List available tools
            print("📋 Listing available tools...")
            tools = await client.list_tools()
            
            # FastMCP Client returns a list directly, not an object with .tools
            print(f"\nFound {len(tools)} tool(s):")
            for tool in tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # Step 2: Call the list_models tool
            print("\n🔧 Calling 'list_models' tool...")
            print("   Arguments: page=1, page_size=5")
            
            result = await client.call_tool(
                "list_models",
                arguments={
                    "page": 1,
                    "page_size": 5,
                }
            )
            
            # Display the result
            print("\n📊 Result:")
            print("=" * 50)
            
            # FastMCP Client returns result.data directly
            if hasattr(result, 'data'):
                # If it's JSON, pretty print it
                if isinstance(result.data, (dict, list)):
                    print(json.dumps(result.data, indent=2))
                else:
                    print(result.data)
            else:
                print(result)
            
            print("=" * 50)
            print("\n✅ Done!")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
