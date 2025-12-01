import os
import json
import aiohttp
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP
from keycloak import KeycloakOpenID

# Initialize the MCP server
mcp = FastMCP("amq-jolokia-server")

# Configuration - AMQ
AMQ_HOST = os.getenv("AMQ_HOST", "localhost")
AMQ_PORT = os.getenv("AMQ_PORT", "8161")
AMQ_BROKER_NAME = os.getenv("AMQ_BROKER_NAME", "amq-broker-primary")
AMQ_ORIGIN = os.getenv("AMQ_ORIGIN", "mydomain.com")

BASE_URL = f"http://{AMQ_HOST}:{AMQ_PORT}/console/jolokia"

# Configuration - Keycloak
KEYCLOAK_SERVER_URL = os.getenv("KEYCLOAK_SERVER_URL", "http://localhost:8080/")
KEYCLOAK_REALM_NAME = os.getenv("KEYCLOAK_REALM_NAME", "myrealm")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "myclient")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "secret")

# Store authenticated sessions
authenticated_sessions = {}


def init_keycloak():
    """Initialize Keycloak OpenID client"""

    try:
        keycloak_openid = KeycloakOpenID(
            server_url=KEYCLOAK_SERVER_URL,
            client_id=KEYCLOAK_CLIENT_ID,
            realm_name=KEYCLOAK_REALM_NAME,
            client_secret_key=KEYCLOAK_CLIENT_SECRET
        )
        return keycloak_openid
    except Exception as e:
        print(f"Failed to initialize Keycloak: {e}")
        return None


def check_resource_access(keycloak_openid, access_token: str, resource: str, scope: str = "view") -> bool:
    """
    Check if user has access to a specific resource and scope
    
    Args:
        keycloak_openid: Keycloak OpenID client
        access_token: User's access token
        resource: Resource name (e.g., "messages", "version")
        scope: Scope name (e.g., "view", "delete")
    
    Returns:
        True if user has access, False otherwise
    """
    try:
        resource_scope = f"{resource}#{scope}"
        has_access = keycloak_openid.has_uma_access(access_token, resource_scope)
        print(f"Permission check - Resource: {resource_scope}, Access: {has_access}")
        return has_access
    except Exception as e:
        print(f"Error checking resource access: {e}")
        return False


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
async def keycloak_login(username: str, password: str) -> str:
    """
    Authenticate with Keycloak and obtain access token
    
    Args:
        username: Keycloak username
        password: Keycloak password
    
    Returns:
        Success or failure message
    """
    try:
        keycloak_openid = init_keycloak()
        if not keycloak_openid:
            return "Error: Failed to initialize Keycloak client"
        
        # Get token from Keycloak
        token_response = keycloak_openid.token(username, password)
        access_token = token_response.get('access_token')
        
        if not access_token:
            return f"Authentication failed: No access token received"
        
        # Store session with token and keycloak client
        authenticated_sessions[username] = {
            "access_token": access_token,
            "token_response": token_response,
            "keycloak_openid": keycloak_openid
        }
        
        return f"Successfully authenticated with Keycloak as user: {username}"
    
    except Exception as e:
        return f"Keycloak authentication failed: {str(e)}"


@mcp.tool()
async def keycloak_logout(username: str) -> str:
    """
    Clear the Keycloak authenticated session
    
    Args:
        username: Username to logout
    
    Returns:
        Success message
    """
    if username in authenticated_sessions:
        authenticated_sessions.pop(username)
        return f"Successfully logged out user: {username}"
    else:
        return f"No active session for user: {username}"


@mcp.tool()
async def check_permission(username: str, resource: str, scope: str = "view") -> str:
    """
    Check if user has permission to access a resource
    
    Args:
        username: Username
        resource: Resource name (e.g., "messages", "version", "queues")
        scope: Scope name (e.g., "view", "delete", "edit")
    
    Returns:
        Permission status message
    """
    if username not in authenticated_sessions:
        return f"Error: User {username} is not authenticated"
    
    try:
        session = authenticated_sessions[username]
        access_token = session["access_token"]
        keycloak_openid = session["keycloak_openid"]
        
        has_access = check_resource_access(keycloak_openid, access_token, resource, scope)
        
        if has_access:
            return f"User {username} has access to {resource}#{scope}: ALLOWED"
        else:
            return f"User {username} has access to {resource}#{scope}: DENIED"
    
    except Exception as e:
        return f"Error checking permission: {str(e)}"


@mcp.tool()
async def login(username: str, password: str) -> str:
    """
    Authenticate with Keycloak and use same credentials for AMQ login
    
    Args:
        username: Username (used for both Keycloak and AMQ)
        password: Password (used for both Keycloak and AMQ)
    
    Returns:
        Success or failure message
    """
    try:
        # Initialize Keycloak client
        keycloak_openid = init_keycloak()
        if not keycloak_openid:
            return "Error: Failed to initialize Keycloak client"
        
        # Authenticate with Keycloak
        token_response = keycloak_openid.token(username, password)
        access_token = token_response.get('access_token')
        
        if not access_token:
            return f"Authentication failed: No access token received from Keycloak"
        
        # Test AMQ credentials with the same username/password
        endpoint = f'org.apache.activemq.artemis:broker=!%22{AMQ_BROKER_NAME}!%22'
        response = await call_jolokia_api(endpoint, method="read", username=username, password=password, attribute="Version")
        
        if "error" in response:
            return f"AMQ authentication failed: {response.get('error')} - {response.get('message', '')}"
        
        if response.get("status") != 200:
            return f"AMQ authentication failed: {response}"
        
        # Store session with both Keycloak token and AMQ credentials
        authenticated_sessions[username] = {
            "access_token": access_token,
            "token_response": token_response,
            "keycloak_openid": keycloak_openid,
            "amq_username": username,
            "amq_password": password
        }
        
        return f"Successfully authenticated user: {username} (Keycloak + AMQ)"
    
    except Exception as e:
        return f"Authentication failed: {str(e)}"


@mcp.tool()
async def logout(username: str) -> str:
    """
    Clear the authenticated session for a user
    
    Args:
        username: Username to logout
    
    Returns:
        Success message
    """
    if username in authenticated_sessions:
        authenticated_sessions.pop(username)
        return f"Successfully logged out user: {username}"
    else:
        return f"No active session for user: {username}"


@mcp.tool()
async def get_version(username: str) -> str:
    """
    Get the version of the Red Hat AMQ broker via Jolokia API
    
    Requires permission: version#view
    
    Args:
        username: Username (must be authenticated first)
    
    Returns:
        The AMQ broker version string
    """
    # Check if user is authenticated
    if username not in authenticated_sessions:
        return "Error: Not authenticated. Please login first using the login tool."
    
    session = authenticated_sessions[username]
    access_token = session.get("access_token")
    keycloak_openid = session.get("keycloak_openid")
    amq_username = session.get("amq_username")
    amq_password = session.get("amq_password")
    
    # Check Keycloak authorization - REQUIRED
    if not access_token or not keycloak_openid:
        return "Error: Keycloak session is invalid"
    
    if not check_resource_access(keycloak_openid, access_token, "version", "view"):
        return f"Error: User {username} does not have permission to view version (version#view). Access DENIED."
    
    # Call AMQ API
    endpoint = f'org.apache.activemq.artemis:broker=!%22{AMQ_BROKER_NAME}!%22'
    response = await call_jolokia_api(endpoint, method="read", username=amq_username, password=amq_password, attribute="Version")
    
    if "error" in response:
        return f"Error: {response.get('error')} - {response.get('message', '')}"
    
    if response.get("status") == 200:
        version = response.get("value", "Unknown")
        return f"AMQ Broker Version: {version}"
    else:
        return f"Failed to retrieve version: {response}"


@mcp.tool()
async def browse_queue(username: str, queue_name: str, routing_type: str = "anycast") -> str:
    """
    Browse messages in a queue using the Jolokia API
    
    Requires permission: messages#view
    
    Args:
        username: Username (must be authenticated first)
        queue_name: The name of the queue to browse
        routing_type: The routing type of the queue (default: anycast)
    
    Returns:
        JSON formatted list of messages in the queue
    """
    # Check if user is authenticated
    if username not in authenticated_sessions:
        return json.dumps({
            "error": "Not authenticated",
            "message": "Please login first using the login tool"
        })
    
    session = authenticated_sessions[username]
    access_token = session.get("access_token")
    keycloak_openid = session.get("keycloak_openid")
    amq_username = session.get("amq_username")
    amq_password = session.get("amq_password")
    
    # Check Keycloak authorization - REQUIRED
    if not access_token or not keycloak_openid:
        return json.dumps({
            "error": "Authorization failed",
            "message": "Keycloak session is invalid"
        })
    
    if not check_resource_access(keycloak_openid, access_token, "messages", "view"):
        return json.dumps({
            "error": "Authorization denied",
            "message": f"User {username} does not have permission to view messages (messages#view). Access DENIED."
        })
    
    # Build the endpoint for queue browse operation
    endpoint = (
        f'org.apache.activemq.artemis:broker=!%22{AMQ_BROKER_NAME}!%22,'
        f'component=addresses,address=!%22{queue_name}!%22,'
        f'subcomponent=queues,routing-type=!%22{routing_type}!%22,'
        f'queue=!%22{queue_name}!%22'
    )
    
    response = await call_jolokia_api(endpoint, method="exec", username=amq_username, password=amq_password, operation="browse()")
    
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
    print("starting...")
    mcp.run()
