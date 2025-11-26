# AMQ Jolokia MCP Server - Source Code README

## Overview

This is a Model Context Protocol (MCP) server that provides Claude with access to Red Hat AMQ 7.13+ via the Jolokia API. It uses FastMCP for simplified server implementation and aiohttp for async HTTP communication.

## Project Information

- **Name:** AMQ Jolokia MCP Server
- **Type:** MCP Server
- **Framework:** FastMCP
- **Protocol:** Model Context Protocol (MCP)
- **Python:** 3.8+

## Architecture

### File Structure

```
amq-jolokia-mcp-server/
├── amq_server.py          # Main source file
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

### Source Code Components

#### 1. Imports

```python
import os                           # Environment variable access
import json                         # JSON serialization
import aiohttp                      # Async HTTP client
from typing import Optional         # Type hints
from mcp.server.fastmcp import FastMCP  # FastMCP framework
```

#### 2. Initialization

```python
mcp = FastMCP("amq-jolokia-server")
```

Creates the MCP server instance with the name `amq-jolokia-server`.

#### 3. Configuration (Environment Variables)

```python
AMQ_HOST = os.getenv("AMQ_HOST", "localhost")              # AMQ server hostname
AMQ_PORT = os.getenv("AMQ_PORT", "8161")                   # AMQ Jolokia port
AMQ_BROKER_NAME = os.getenv("AMQ_BROKER_NAME", "amq-broker-primary")  # Broker name
AMQ_ORIGIN = os.getenv("AMQ_ORIGIN", "mydomain.com")       # Origin header for CORS

BASE_URL = f"http://{AMQ_HOST}:{AMQ_PORT}/console/jolokia" # Jolokia API base URL

authenticated_credentials = {}  # Session storage for credentials
```

### Core Functions

#### `call_jolokia_api()`

**Signature:**
```python
async def call_jolokia_api(
    endpoint: str,
    method: str = "read",
    username: Optional[str] = None,
    password: Optional[str] = None,
    **params
) -> dict:
```

**Purpose:** Generic handler for all Jolokia API requests

**Parameters:**
- `endpoint` (str): Jolokia MBean object name
  - Example: `org.apache.activemq.artemis:broker="amq-broker-primary"`
- `method` (str): Jolokia operation type - "read", "write", "exec", or "search"
- `username` (Optional[str]): AMQ broker username for authentication
- `password` (Optional[str]): AMQ broker password for authentication
- `**params`: Additional URL parameters (e.g., attribute="Version", operation="browse()")

**Logic Flow:**

1. **URL Construction:**
   ```python
   url = f"{BASE_URL}/{method}/{endpoint}"
   ```
   - Combines base URL with method and endpoint
   - Appends additional parameters if provided
   - Example: `http://localhost:8161/console/jolokia/read/org.apache.activemq.artemis:broker="..."/Version`

2. **Authentication Validation:**
   - Checks if both username and password are provided
   - Returns error if missing credentials

3. **HTTP Request:**
   ```python
   auth = aiohttp.BasicAuth(username, password)
   headers = {"Origin": AMQ_ORIGIN}
   async with aiohttp.ClientSession() as session:
       async with session.get(url, auth=auth, headers=headers) as response:
   ```
   - Uses Basic Authentication with username/password
   - Sets Origin header for CORS compliance
   - Makes async GET request to Jolokia API

4. **Response Handling:**
   - Reads response as text (handles text/plain mimetype from Jolokia)
   - Parses JSON response
   - Returns parsed JSON on success (status 200)
   - Returns error dict on failure

5. **Error Handling:**
   - HTTP Errors: Captures non-200 status codes
   - JSON Parse Errors: Handles invalid JSON responses
   - Network Errors: Catches all exceptions from aiohttp

**Returns:**
```python
{
    "error": "string",              # Error message if error occurred
    "message": "string",             # Additional error details
    "value": any,                    # Response data/payload
    "status": 200,                   # HTTP status code
    "timestamp": 1764119847,         # Server timestamp
    "request": {...}                 # Request metadata
}
```

### MCP Tool Functions

Tools are defined using the `@mcp.tool()` decorator from FastMCP.

#### `login(username: str, password: str) -> str`

**Purpose:** Authenticate user with AMQ broker credentials

**Implementation:**
1. Tests credentials by calling `get_version` API
2. If successful, stores credentials in `authenticated_credentials` dict
3. Returns success/failure message

**Usage:**
```python
login("admin", "admin-password")
```

**Returns:**
```
"Successfully authenticated as user: admin"
```

#### `logout() -> str`

**Purpose:** Clear the authenticated session

**Implementation:**
1. Checks if credentials exist in `authenticated_credentials`
2. Clears the dictionary
3. Returns logout confirmation

**Usage:**
```python
logout()
```

**Returns:**
```
"Successfully logged out user: admin"
```

#### `get_version() -> str`

**Purpose:** Retrieve the Red Hat AMQ broker version

**Prerequisites:** User must be authenticated (call login first)

**Implementation:**
1. Retrieves stored username and password from session
2. Validates authentication state
3. Builds endpoint for Version attribute: `org.apache.activemq.artemis:broker="..."`
4. Calls `call_jolokia_api()` with method="read"
5. Extracts and returns version string

**Usage:**
```python
get_version()
```

**Returns:**
```
"AMQ Broker Version: 2.33.0.redhat-00013"
```

#### `browse_queue(queue_name: str, routing_type: str = "anycast") -> str`

**Purpose:** Browse messages in a specified queue

**Prerequisites:** User must be authenticated

**Parameters:**
- `queue_name` (str, required): Name of queue to browse (e.g., "HelloQueue")
- `routing_type` (str, optional): Queue routing type - "anycast" or "multicast" (default: "anycast")

**Implementation:**
1. Retrieves stored credentials from session
2. Validates authentication
3. Builds complex MBean endpoint for queue:
   ```
   org.apache.activemq.artemis:broker="...",component=addresses,address="...",
   subcomponent=queues,routing-type="...",queue="..."
   ```
4. Calls `call_jolokia_api()` with method="exec" and operation="browse()"
5. Processes response and extracts message array
6. Returns formatted JSON with metadata

**Usage:**
```python
browse_queue("HelloQueue", "anycast")
```

**Returns:**
```json
{
  "queue": "HelloQueue",
  "routing_type": "anycast",
  "message_count": 10,
  "messages": [
    {
      "messageID": "243788",
      "text": "hello3",
      "priority": 4,
      "timestamp": 1752717147852,
      "redelivered": false,
      "durable": true,
      "protocol": "CORE",
      "persistentSize": 234
    },
    ...
  ]
}
```

### Main Entry Point

```python
if __name__ == "__main__":
    mcp.run()
```

- Starts the FastMCP server
- Uses stdio transport by default (compatible with Claude and other MCP clients)

## Dependencies

### requirements.txt

```
mcp>=0.1.0
aiohttp>=3.8.0
```

**Installation:**
```bash
pip install -r requirements.txt
```

### Dependency Details

| Package | Version | Purpose |
|---------|---------|---------|
| mcp | >=0.1.0 | Model Context Protocol library and FastMCP |
| aiohttp | >=3.8.0 | Async HTTP client for Jolokia API calls |

## Usage Flow

### 1. Start the Server

```bash
export AMQ_HOST=localhost
export AMQ_PORT=8161
export AMQ_BROKER_NAME=amq-broker-primary
export AMQ_ORIGIN=mydomain.com

python amq_server.py
```

### 2. In Claude (or MCP client)

**Step 1: Authenticate**
```
login("admin", "admin-password")
```

**Step 2: Check Version**
```
get_version()
```

**Step 3: Browse Queues**
```
browse_queue("HelloQueue")
browse_queue("OrderQueue", "anycast")
```

**Step 4: Logout**
```
logout()
```

## Session Management

### Credential Storage

Credentials are stored in the module-level dictionary:
```python
authenticated_credentials = {
    "username": "admin",
    "password": "admin-password"
}
```

### Key Characteristics

- **In-Memory:** Credentials stored only in memory during server runtime
- **Per-Process:** Each server process maintains its own credentials
- **Session-Based:** Credentials cleared when `logout()` is called
- **Not Persistent:** Credentials lost when server restarts

### Security Notes

- Credentials are only used for HTTP Basic Auth to Jolokia
- No credentials are logged or stored to disk
- All communication uses HTTP (upgrade to HTTPS in production)
- Use environment variables (not hardcoded) for configuration

## Error Handling

### Error Response Format

All tools return errors as strings describing the issue:

```python
"Error: Authentication required - Please login first using the login tool"
"Error: HTTP 401 - Unauthorized"
"Error: Failed to browse queue - Queue not found"
```

### Common Error Cases

1. **Not Authenticated**
   - Trigger: Calling tools before login
   - Response: "Error: Not authenticated. Please login first"

2. **Invalid Credentials**
   - Trigger: Wrong username/password in login
   - Response: "Authentication failed: HTTP 401 - ..."

3. **Queue Not Found**
   - Trigger: browse_queue with non-existent queue name
   - Response: "Failed to browse queue"

4. **Connection Error**
   - Trigger: AMQ server unreachable
   - Response: "Error: [connection error details]"

## Configuration Examples

### Development Environment
```bash
export AMQ_HOST=localhost
export AMQ_PORT=8161
export AMQ_BROKER_NAME=amq-broker-primary
export AMQ_ORIGIN=localhost
python amq_server.py
```

### Remote Production Environment
```bash
export AMQ_HOST=amq-prod.example.com
export AMQ_PORT=8161
export AMQ_BROKER_NAME=amq-broker-primary
export AMQ_ORIGIN=example.com
python amq_server.py
```

## Code Quality

- **Type Hints:** Used for function parameters and return types
- **Docstrings:** Comprehensive docstrings for all functions and tools
- **Error Handling:** Try-catch blocks for network operations
- **Async/Await:** Proper async implementation for I/O operations
- **Separation of Concerns:** Generic API handler with specific tool implementations

## Performance Considerations

- **Async I/O:** Non-blocking HTTP requests using aiohttp
- **Connection Management:** aiohttp handles connection pooling
- **Single Session:** Credentials stored in memory (suitable for single user)
- **Minimal Overhead:** FastMCP provides lightweight MCP server

## Testing

### Test Credentials

```bash
# Verify connection
export AMQ_HOST=localhost
export AMQ_PORT=8161
python amq_server.py

# In Claude/MCP client:
login("admin", "admin-password")
get_version()
```

### Debug Tips

1. Add print statements to see API calls
2. Check `BASE_URL` is correct: `http://localhost:8161/console/jolokia`
3. Verify credentials with manual curl:
   ```bash
   curl -u admin:admin http://localhost:8161/console/jolokia/read/org.apache.activemq.artemis:broker=%22amq-broker-primary%22/Version
   ```
4. Ensure `AMQ_ORIGIN` header is whitelisted on AMQ server

## Limitations

- Single credential session (one user at a time)
- Credentials stored in memory (not persisted)
- No SSL/TLS support (use reverse proxy for HTTPS)
- No message filtering or pagination
- Read-only operations (browse only, no send/delete)
- Blocking on credential validation in login

## Future Enhancements

- Multiple concurrent sessions
- Persistent credential storage
- SSL/TLS certificate support
- Message send/delete operations
- Queue statistics and monitoring
- Message filtering and pagination
- Rate limiting
- Better error recovery