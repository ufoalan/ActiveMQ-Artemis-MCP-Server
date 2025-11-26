import os
import json
import aiohttp
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("amq-jolokia-server")

# Configuration
AMQ_HOST = os.getenv("AMQ_HOST", "localhost")
AMQ_PORT = os.getenv("AMQ_PORT", "8161")
AMQ_BROKER_NAME = os.getenv("AMQ_BROKER_NAME", "amq-broker-primary")
AMQ_ORIGIN = os.getenv("AMQ_ORIGIN", "mydomain.com")

BASE_URL = f"http://{AMQ_HOST}:{AMQ_PORT}/console/jolokia"

# Store authenticated credentials per session
authenticated_credentials = {}


async def call_jolokia_api(endpoint: str, method: str = "read", username: Optional[str] = None, password: Optional[str] = None, **params) -> dict:
    """
    Generic function to call Jolokia API
    
    Args:
        endpoint: The Jolokia endpoint (e.g., "org.apache.activemq.artemis:broker=\"{broker}\"")
        method: The Jolokia method (read, write, exec, search)
        username: The AMQ username for authentication
        password: The AMQ password for authentication
        **params: Additional parameters like attribute, args, etc.
    
    Returns:
        The parsed JSON response from Jolokia
    """
    # Build the URL
    url = f"{BASE_URL}/{method}/{endpoint}"
    
    # Add parameters to URL if provided
    if params:
        param_str = "/".join(str(v) for v in params.values())
        url = f"{url}/{param_str}"
    
    # Use provided credentials or raise error if not authenticated
    if not username or not password:
        return {"error": "Authentication required", "message": "Please login first using the login tool"}
    
    auth = aiohttp.BasicAuth(username, password)
    
    headers = {
        "Origin": AMQ_ORIGIN
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=auth, headers=headers) as response:
                # Read response as text first
                text_response = await response.text()
                
                if response.status == 200:
                    try:
                        # Try to parse as JSON
                        return json.loads(text_response)
                    except json.JSONDecodeError:
                        return {
                            "error": "Invalid JSON response",
                            "message": text_response
                        }
                else:
                    return {
                        "error": f"HTTP {response.status}",
                        "message": text_response
                    }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def login(username: str, password: str) -> str:
    """
    Authenticate with AMQ broker using credentials
    
    Args:
        username: The AMQ broker username
        password: The AMQ broker password
    
    Returns:
        Success or failure message
    """
    # Test the credentials by making a simple API call
    endpoint = f'org.apache.activemq.artemis:broker=!%22{AMQ_BROKER_NAME}!%22'
    response = await call_jolokia_api(endpoint, method="read", username=username, password=password, attribute="Version")
    
    if "error" in response:
        return f"Authentication failed: {response.get('error')} - {response.get('message', '')}"
    
    if response.get("status") == 200:
        # Store credentials in session
        authenticated_credentials["username"] = username
        authenticated_credentials["password"] = password
        return f"Successfully authenticated as user: {username}"
    else:
        return f"Authentication failed: {response}"


@mcp.tool()
async def logout() -> str:
    """
    Clear the authenticated session
    
    Returns:
        Success message
    """
    if "username" in authenticated_credentials:
        username = authenticated_credentials.get("username")
        authenticated_credentials.clear()
        return f"Successfully logged out user: {username}"
    else:
        return "No active session to logout"


@mcp.tool()
async def get_version() -> str:
    """
    Get the version of the Red Hat AMQ broker via Jolokia API
    
    Returns:
        The AMQ broker version string
    """
    username = authenticated_credentials.get("username")
    password = authenticated_credentials.get("password")
    
    if not username or not password:
        return "Error: Not authenticated. Please login first using the login tool."
    
    endpoint = f'org.apache.activemq.artemis:broker=!%22{AMQ_BROKER_NAME}!%22'
    response = await call_jolokia_api(endpoint, method="read", username=username, password=password, attribute="Version")
    
    if "error" in response:
        return f"Error: {response.get('error')} - {response.get('message', '')}"
    
    if response.get("status") == 200:
        version = response.get("value", "Unknown")
        return f"AMQ Broker Version: {version}"
    else:
        return f"Failed to retrieve version: {response}"


@mcp.tool()
async def browse_queue(queue_name: str, routing_type: str = "anycast") -> str:
    """
    Browse messages in a queue using the Jolokia API
    
    Args:
        queue_name: The name of the queue to browse
        routing_type: The routing type of the queue (default: anycast)
    
    Returns:
        JSON formatted list of messages in the queue
    """
    username = authenticated_credentials.get("username")
    password = authenticated_credentials.get("password")
    
    if not username or not password:
        return json.dumps({
            "error": "Not authenticated",
            "message": "Please login first using the login tool"
        })
    
    # Build the endpoint for queue browse operation
    endpoint = (
        f'org.apache.activemq.artemis:broker=!%22{AMQ_BROKER_NAME}!%22,'
        f'component=addresses,address=!%22{queue_name}!%22,'
        f'subcomponent=queues,routing-type=!%22{routing_type}!%22,'
        f'queue=!%22{queue_name}!%22'
    )
    
    response = await call_jolokia_api(endpoint, method="exec", username=username, password=password, operation="browse()")
    
    if "error" in response:
        return json.dumps({
            "error": response.get("error"),
            "message": response.get("message", "")
        })
    
    if response.get("status") == 200:
        messages = response.get("value", [])
        return json.dumps({
            "queue": queue_name,
            "routing_type": routing_type,
            "message_count": len(messages),
            "messages": messages
        }, indent=2)
    else:
        return json.dumps({
            "error": "Failed to browse queue",
            "response": response
        })


if __name__ == "__main__":
    mcp.run()
