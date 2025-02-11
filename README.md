
# FountainAI Eco-System

The **FountainAI Eco-System** is a collection of containerized, FastAPI-based microservices powering the FountainAI platform. Each service is designed to perform a specific function and must follow a common set of guidelines for clarity, interoperability, and maintainability. This document outlines the **core requirements**, **project layout**, **authentication**, **observability**, **service discovery**, **notification integration**, **landing page**, **health endpoint**, and **reverse proxy details** for developing and integrating new services.

---

## 1. Core Service Requirements

### 1.1 Framework & Deployment

- **FastAPI (Python):**  
  Each service is built using [FastAPI](https://fastapi.tiangolo.com/), which automatically generates an OpenAPI specification.
- **Containerized:**  
  Each service runs in Docker and is orchestrated using Docker Compose. All services share a common network (e.g., `fountainai-net`) and are exposed via a reverse proxy (Caddy).

### 1.2 Configuration & Security

- **Secrets Manager (No `.env` for Secrets):**  
  Each service dynamically fetches secrets (API keys, passwords, etc.) from the **Secrets Manager Service** at runtime. No `.env` file should store secrets.  
  \- *Optionally,* a `.env` file can be used for non-sensitive configurations (e.g., feature flags, log levels), but sensitive data must always come from the Secrets Manager.

- **Authentication:**  
  Security is enforced via JWT (or API key) authentication with role-based access control (RBAC).

### 1.3 Data Persistence & Models

- **SQLAlchemy & Pydantic:**  
  Databases are managed by SQLAlchemy (often with SQLite), and Pydantic models provide strong input and output validation.
- **Consistent Models:**  
  Data models and schemas must be clearly defined and documented (e.g., in the service’s `main.py`).

### 1.4 Inter-Service Integration

#### 1.4.1 Dynamic Service Discovery

Every service uses the **API Gateway**’s lookup endpoint to dynamically resolve peer-service URLs at runtime. This keeps service interactions decoupled and prevents hardcoded host/port references.

#### 1.4.2 Notification Service Integration

Each service must integrate with the **Notification Service** for event-driven updates:
- **Receiving Notifications:**  
  - When secrets rotate, services are notified and *must* update them in-memory (no restart needed).  
  - Other critical configuration changes or system events may also be broadcast through notifications.  
- **Sending Notifications:**  
  - Services must send notifications (e.g., status changes, alert triggers) to inform other services of important events in real time.

---

## 2. Secrets Management & Rotation

- **Secrets Manager Service:**  
  All sensitive data is retrieved from a dedicated Secrets Manager at startup and during runtime.
- **Two-Point Dependency Injection:**  
  1. **Build-Time (entrypoint.py):**  
     Pull secrets at container startup from the Secrets Manager.  
  2. **Runtime (Notification Service):**  
     Listen for real-time secret rotation and update in memory as needed.

- **Secret Rotation Mechanism:**  
  1. The Secrets Manager provides an endpoint for rotating secrets.  
  2. Upon rotation, the Notification Service notifies all dependent services.  
  3. Each service fetches the new secret dynamically—no downtime or restart required.

---

## 3. Observability

- **Prometheus Metrics:**  
  All services expose Prometheus metrics (e.g., via [`prometheus_fastapi_instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator)) for performance and health monitoring.
- **Standardized Logging:**  
  Logging goes to stdout in a consistent format, compatible with centralized logs.

---

## 4. API Documentation & Semantic Metadata

- **OpenAPI Specification:**  
  Services must generate a complete OpenAPI spec, pinned to version `3.0.3` for full Swagger UI compatibility.
- **Semantic Operation IDs:**  
  Endpoints must have descriptive, camelCase `operationIds` (e.g., `createCharacter`, `listScripts`, `updateAction`).
- **Summaries & Descriptions:**  
  Keep endpoint summaries and descriptions concise (≤300 characters) while clearly explaining the endpoint’s purpose.

---

## 5. Standard Project Layout

A typical FountainAI service project structure:

```
service-name/
├── requirements.txt      # Python package dependencies
├── Dockerfile            # Docker build instructions for the service image
├── entrypoint.py         # Python-based secret injection & startup script
├── main.py               # The complete FastAPI application
└── tests/
    └── test_main.py      # Comprehensive test suite
```

### 5.1 File Descriptions

- **requirements.txt**  
  Lists Python dependencies, installed at image build-time.

- **Dockerfile**  
  Defines how to build the Docker image, including copying code, installing dependencies, etc.

- **entrypoint.py**  
  - Fetches secrets from the Secrets Manager before launching the app.  
  - Ensures runtime configurations are injected properly.  
  - Contains retry logic to handle transient secret fetching issues.

- **main.py**  
  - Defines the FastAPI application, routes, and Pydantic models.  
  - Implements the logic for secrets rotation (listens for notifications).  
  - Dynamically resolves external services (through the API Gateway).  
  - Runs the application (e.g., via Uvicorn) if not triggered by entrypoint.py.  
  - *Should also include the default landing page and health endpoint (see below).*

- **tests/test_main.py**  
  - Contains unit/integration tests, typically using pytest and FastAPI’s TestClient.  
  - Mocks external dependencies (e.g., secrets) to avoid real network calls in test.

---

## 6. Landing Page Requirement

**Every service** must provide a **default landing page** at `GET /` with the following minimum content:

- **Service Name** and **Version** (taken from FastAPI’s `app.title` and `app.version`, if set)
- **Brief Description** of what the service does (≤300 characters)
- **Links** to:
  - **API docs** at `/docs`
  - **Health check** at `/health`

> This ensures consistency and user-friendliness across the ecosystem.

**Example Implementation Snippet in `main.py`:**

```python
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse, tags=["Landing"], operation_id="getLandingPage",
         summary="Display landing page",
         description="Shows a basic landing page with service name, version, and key links.")
def landing_page():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <title>{service_title}</title>
      <style>
        body {{
          font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
          background-color: #f4f4f4; margin: 0; padding: 0;
          display: flex; justify-content: center; align-items: center;
          height: 100vh;
        }}
        .container {{
          background: #fff; padding: 40px; border-radius: 8px;
          box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); text-align: center;
        }}
      </style>
    </head>
    <body>
      <div class="container">
        <h1>Welcome to {service_title}</h1>
        <p><strong>Version:</strong> {service_version}</p>
        <p>{service_description}</p>
        <p>
          <a href="/docs">API Documentation</a> |
          <a href="/health">Health Status</a>
        </p>
      </div>
    </body>
    </html>
    """
    filled = html_content.format(
        service_title=app.title or "FountainAI Service",
        service_version=app.version or "0.1.0",
        service_description="A microservice in the FountainAI ecosystem."
    )
    return HTMLResponse(content=filled, status_code=200)
```

---

## 7. Standard Health Endpoint

Each service must expose a **health endpoint** at `GET /health`:

- **Response Body:** At minimum: `{"status": "healthy"}`  
- **HTTP Status:** `200 OK` (when healthy)  
- **Operation ID:** `getHealthStatus`  
- **Short Summary & Description** adhering to the 300-char limit

**Example Implementation in `main.py`:**

```python
@app.get("/health", response_model=dict, tags=["Health"],
         operation_id="getHealthStatus",
         summary="Retrieve service health status",
         description="Returns the current health status of the service as a JSON object.")
def health_check():
    return {"status": "healthy"}
```

---

## 8. Reverse Proxy Exposure (Caddy Integration)

All services in the FountainAI ecosystem are exposed publicly via a **Caddy** reverse proxy that handles:

- **TLS Termination**  
- **HTTP→HTTPS Redirects**  
- **Subdomain Routing** under `fountain.coach` (e.g., `action.fountain.coach` → `action_service:8000`)

### 8.1 Example `Caddyfile` Snippet

```caddyfile
{
    email your@example.com
}

# Redirect all HTTP to HTTPS
http:// {
    redir https://{host}{uri} permanent
}

2fa.fountain.coach {
    reverse_proxy 2fa_service:8004
}

action.fountain.coach {
    reverse_proxy action_service:8000
}

notification.fountain.coach {
    reverse_proxy notification_service:8003
}

# Fallback (wildcard) for subdomains
*.fountain.coach {
    reverse_proxy central_gateway:8000
}
```

### 8.2 DNS Configuration

- **Wildcard DNS:**  
  A wildcard record `*.fountain.coach` must point to the host or IP running Caddy, typically set up in AWS Route 53 or a similar DNS provider.

### 8.3 Docker Compose Example for Caddy

```yaml
version: "3.8"
services:
  caddy:
    image: caddy:2
    container_name: caddy
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - fountainai-net
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - central_gateway

  # ... other services ...

networks:
  fountainai-net:
    external: true

volumes:
  caddy_data:
  caddy_config:
```

---

## 9. Summary

A FountainAI service **MUST**:

1. **Use FastAPI & Docker** following a standardized project layout.
2. **Fetch secrets** from the **Secrets Manager**, never storing them in `.env` (except non-sensitive data).
3. **Employ JWT (or API key) Authentication** with RBAC.
4. **Implement Observability** (Prometheus metrics, standardized logging).
5. **Provide a Default Landing Page** (`GET /`) with a short description and links.
6. **Expose a Health Endpoint** (`GET /health`) returning `{"status": "healthy"}`.
7. **Support Dynamic Service Discovery** (via the API Gateway).
8. **Integrate with the Notification Service** for real-time event-driven updates (both sending and receiving).
9. **Expose an OpenAPI Spec** with semantic operation IDs, summaries and descriptions, and version `3.0.3`.
10. **Run behind Caddy** for reverse proxying, TLS, and domain routing (subdomain per service).

By following these guidelines, FountainAI services remain **secure, scalable, user-friendly**, and **adaptable**, benefiting from real-time configuration updates and consistent, discoverable endpoints across the entire ecosystem.
