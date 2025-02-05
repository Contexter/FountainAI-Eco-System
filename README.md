# FountainAI Eco‑System

The FountainAI Eco‑System is a collection of containerized, FastAPI‑based microservices that together power the FountainAI platform. Each service is designed to perform a specific function within the ecosystem while adhering to a common set of guidelines that ensure clarity, interoperability, and maintainability. This README outlines the standards and best practices for developing and integrating new services into the ecosystem.

---

## Core Service Requirements

Every FountainAI service must satisfy the following criteria:

### Framework & Deployment
- **FastAPI (Python):**  
  Each service is built using FastAPI, which automatically generates a complete OpenAPI specification.
- **Containerized:**  
  Services are packaged with Docker and orchestrated via Docker Compose. All services share a common network (e.g., `fountainai-net`) and are exposed via a reverse proxy (Caddy).

### Configuration & Security
- **Environment Configuration:**  
  Each service loads its configuration from a `.env` file containing service-specific settings (ports, database URLs, authentication keys, etc.).
- **Authentication:**  
  Security is enforced via JWT (or API key) authentication with role‑based access control (RBAC).

### Data Persistence & Models
- **SQLAlchemy & Pydantic:**  
  Persistence is typically handled by SQLAlchemy (commonly with SQLite), and explicit Pydantic models are defined for input and output validation.
- **Consistent Models:**  
  Data models and schemas are clearly defined and documented in the service’s main file.

### Inter‑Service Integration
- **Dynamic Service Discovery:**  
  Every service must implement dynamic service discovery by leveraging the API Gateway’s lookup endpoint. This enables services to dynamically resolve peer service URLs at runtime.
- **Notification Service Integration:**  
  Each service must include a standardized interface for both sending **and receiving notifications** via the central Notification Service—even if the receive functionality is implemented as a stub for future enhancements.
  - **Sending Notifications:** Services should provide a helper function or client to push notifications (e.g., alerts, status changes) to the Notification Service.
  - **Receiving Notifications:** Services should implement (or stub) an endpoint or interface capable of receiving notifications, preparing them for future two-way communication.

### Observability
- **Prometheus Metrics:**  
  All services expose Prometheus metrics (via tools like `prometheus_fastapi_instrumentator`) for performance and health monitoring.
- **Standardized Logging:**  
  Logging is configured to output to stdout in a consistent format suitable for centralized logging.

### API Documentation & Semantic Metadata
- **OpenAPI Specification:**  
  Each service generates a complete OpenAPI specification, forcing the version to 3.0.3 for Swagger UI compatibility.
- **Semantic Operation IDs:**  
  Endpoints must have descriptive, camelCase operationIds (e.g., `createCharacter`, `listScripts`, `updateAction`).
- **Summaries & Descriptions:**  
  Each endpoint must include a brief summary and a description that is concise (description ≤300 characters) yet clear about the endpoint’s behavior.

---

## Standard Project Layout

Every FountainAI service must follow a standardized project layout to ensure consistency across the ecosystem. The typical structure is as follows:

```
service-name/
├── .env                  # Service-specific configuration (environment variables)
├── requirements.txt      # Python package dependencies
├── Dockerfile            # Docker build instructions for the service image
├── entrypoint.sh         # Shell script to start the service or run tests
├── main.py               # Single entry point containing the complete FastAPI application
└── tests/
    └── test_main.py      # Comprehensive test suite using pytest and FastAPI's TestClient
```

### File Descriptions

- **.env:**  
  Contains key-value pairs for service configuration (e.g., ports, database URLs, secrets). Loaded at runtime using `python-dotenv`.

- **requirements.txt:**  
  Lists all Python dependencies required by the service. Used during Docker image build time.

- **Dockerfile:**  
  Provides instructions to build the service image, including copying source code, installing dependencies, and setting the default entrypoint.

- **entrypoint.sh:**  
  A shell script that acts as the container’s entrypoint. It typically decides whether to start the service (using Uvicorn) or run tests (using pytest).

- **main.py:**  
  Contains the entire FastAPI application. This file must include:
  - Extended header comments describing the service’s purpose and key integrations.
  - Configuration setup, database initialization, authentication, and Pydantic model definitions.
  - Helper functions for dynamic service discovery and notification integration.
  - Endpoint definitions with semantic metadata (camelCase operationIds, clear summaries, and concise descriptions).
  - A default landing page and a health endpoint.
  - Custom OpenAPI generation to force version 3.0.3.
  - The application’s entry point to run the service using Uvicorn.

- **tests/test_main.py:**  
  Contains a comprehensive test suite that validates the service’s functionality. Tests should simulate external dependencies (using monkeypatching) to ensure isolated testing.

---

## Default Landing Page

Every service must include a default landing page at the root URL (`/`) that provides a friendly greeting and useful links. The landing page must:

- Display the service name and version.
- Include a brief description (≤300 characters) of what the service does.
- Provide navigation links to the API documentation (`/docs`) and the health check (`/health`).
- Be styled for clarity and readability.

**Example Implementation (in main.py):**

```python
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse, tags=["Landing"], operation_id="getLandingPage", summary="Display landing page", description="Returns a styled landing page with service name, version, and links to API docs and health check.")
def landing_page():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{service_title}</title>
      <style>
        body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; height: 100vh; }}
        .container {{ background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); text-align: center; max-width: 600px; margin: auto; }}
        h1 {{ font-size: 2.5rem; color: #333; }}
        p {{ font-size: 1.1rem; color: #666; line-height: 1.6; }}
        a {{ color: #007acc; text-decoration: none; font-weight: bold; }}
        a:hover {{ text-decoration: underline; }}
      </style>
    </head>
    <body>
      <div class="container">
        <h1>Welcome to {service_title}</h1>
        <p><strong>Version:</strong> {service_version}</p>
        <p>{service_description}</p>
        <p>
          Visit the <a href="/docs">API Documentation</a> or check the 
          <a href="/health">Health Status</a>.
        </p>
      </div>
    </body>
    </html>
    """
    filled_html = html_content.format(
        service_title=app.title,
        service_version=app.version,
        service_description="This service provides its core functionality within the FountainAI ecosystem."
    )
    return HTMLResponse(content=filled_html, status_code=200)
```

---

## Standard Health Endpoint

Every service must implement a health endpoint to facilitate monitoring. The health endpoint must:

- **Path:** `/health`
- **Method:** GET
- **Response:** JSON containing at least `{ "status": "healthy" }`
- **HTTP Status:** 200
- **Semantic Metadata:**  
  - **operationId:** `getHealthStatus` (camelCase)
  - **Summary:** `Retrieve service health status`
  - **Description:** `Returns the current health status of the service as a JSON object (e.g., {'status': 'healthy'}).`
  
**Example Implementation:**

```python
@app.get("/health", response_model=dict, tags=["Health"], operation_id="getHealthStatus", summary="Retrieve service health status", description="Returns the current health status of the service as a JSON object (e.g., {'status': 'healthy'}).")
def health_check():
    return {"status": "healthy"}
```

---

## Reverse Proxy Exposure (Caddy Integration)

The FountainAI ecosystem is exposed externally via a Caddy reverse proxy that handles TLS termination, HTTP-to-HTTPS redirection, and subdomain routing.

- **Caddyfile:**  
  A file named `Caddyfile` must reside at the root of the repository and be mounted into the Caddy container (e.g., at `/etc/caddy/Caddyfile`). It defines reverse proxy rules for each service using subdomains under the TLD `fountain.coach`.

- **DNS Configuration:**  
  AWS Route 53 (or a similar provider) must be configured with a wildcard record (`*.fountain.coach`) that points to the host running Caddy.

**Example Caddyfile:**

```caddyfile
{
    email your@example.com
}

# Redirect HTTP to HTTPS
http:// {
    redir https://{host}{uri} permanent
}

2fa.fountain.coach {
    reverse_proxy 2fa_service:8004
}

action.fountain.coach {
    reverse_proxy action_service:8000
}

centralGateway.fountain.coach {
    reverse_proxy central_gateway:8000
}

centralSequence.fountain.coach {
    reverse_proxy central_sequence_service:8000
}

character.fountain.coach {
    reverse_proxy character_service:8000
}

core.fountain.coach {
    reverse_proxy core_script_management_service:8000
}

rbac.fountain.coach {
    reverse_proxy fountainai-rbac:8001
}

kms.fountain.coach {
    reverse_proxy kms-app:8002
}

notification.fountain.coach {
    reverse_proxy notification-service:8003
}

paraphrase.fountain.coach {
    reverse_proxy paraphrase_service:8000
}

performer.fountain.coach {
    reverse_proxy performer_service:8000
}

session.fountain.coach {
    reverse_proxy session_context_service:8000
}

spokenword.fountain.coach {
    reverse_proxy spokenword_service:8000
}

story.fountain.coach {
    reverse_proxy story_factory_service:8000
}

typesense.fountain.coach {
    reverse_proxy typesense_client_service:8001
}

*.fountain.coach {
    reverse_proxy central_gateway:8000
}
```

**Docker Compose Caddy Service Example:**

```yaml
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
```

---

## Summary

A FountainAI service must be:
- **Modular and Containerized:** Built with FastAPI, following a standardized project layout (.env, requirements.txt, Dockerfile, entrypoint.sh, main.py, and tests).
- **Configurable and Secure:** Loading settings from a `.env` file, and implementing JWT or API key authentication with RBAC.
- **Persistent and Validated:** Using SQLAlchemy for data persistence and Pydantic for model validation.
- **Interoperable:** Featuring dynamic service discovery (via the API Gateway lookup endpoint) and a standardized interface for both sending and receiving notifications via the Notification Service.
- **Observable:** Exposing Prometheus metrics and standardized logging.
- **Well-Documented:** Generating an OpenAPI specification with semantic metadata (camelCase operationIds, clear summaries, and concise descriptions ≤300 characters).
- **User-Friendly:** Providing a default landing page and a consistent health endpoint.
- **Exposed via Caddy:** Accessible via subdomains under `fountain.coach` managed by a Caddy reverse proxy.

This comprehensive specification serves as the blueprint for creating new services within the FountainAI Eco‑System, ensuring consistency, clarity, and future‑proofing across the platform.

---

This README is intended for internal documentation and as a prompt for new service creation sessions, ensuring that every new service adheres to these high standards.
