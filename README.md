

# FountainAI Eco‑System

The FountainAI Eco‑System is composed of several FastAPI‑based microservices that together form the backbone of the FountainAI platform. Each service is self‑documenting via its OpenAPI (Swagger) specification and, where provided, header comments in its main.py file.

Below you will find the descriptions for each service as given verbatim in the header comments.

---

## 2FA Service

**Header Comment (from `2fa_service/main.py`):**

```
"""
FountainAI 2FA Service
=======================

This self-contained FastAPI application implements a Two-Factor Authentication (2FA)
service for the FountainAI ecosystem. It provides endpoints to generate and verify
time-based OTPs (TOTP) using a per-user OTP secret.

For demonstration purposes, the OTP code is returned in the response.
In production, you would deliver the OTP via email or SMS.

Note: In production, sensitive values (like SECRET_KEY) should be managed securely.
"""
```

---

## Central Sequence Service

**Header Comment (from `central_sequence_service/main.py`):**

```
"""
Central Sequence Service
========================

This service manages sequence numbers for various elements (script, section, character, action, spokenWord)
within a story. It persists data to an SQLite database and simulates synchronization with a central Typesense
Client microservice. Collection creation is mandatory: on startup the service ensures the Typesense collection
schema exists. The generated OpenAPI spec is forced to version 3.0.3 for Swagger UI compatibility.
"""
```

---

## Typesense Client Service

**Header Comment (from `typesense_client_service/main.py`):**

```
"""
Typesense Client Microservice (Schema-Agnostic Edition)
=======================================================

This service acts as a relay for indexing and searching documents in Typesense
without imposing a fixed schema. It provides endpoints to create/retrieve collections,
upsert/delete documents, and perform searches. It overrides the default FastAPI
OpenAPI spec to report version 3.1.0.

Environment variables are loaded from .env.
"""
```

---

## Action Service

*No explicit header comment was found in `action_service/main.py`.*

*Please refer to the interactive API documentation (accessed at `/docs`) for details on available endpoints and functionality.*

---

## Central Gateway

*No explicit header comment was found in `central_gateway/main.py`.*

*For details on the endpoints and routing behavior, please consult the Swagger UI available at `/docs` when the service is running.*

---

## Character Service

*No explicit header comment was found in `character_service/main.py`.*

*Refer to the interactive API documentation at `/docs` for endpoint details.*

---

## Core Script Management Service

*No explicit header comment was found in `core_script_management_service/main.py`.*

*Check the Swagger documentation (`/docs`) for a full description of the available endpoints.*

---

## FountainAI-RBAC

*No explicit header comment was found in `fountainai-rbac/main.py`.*

*The interactive API documentation at `/docs` contains the details for all endpoints.*

---

## KMS-App

*No explicit header comment was found in `kms-app/main.py`.*

*Consult the Swagger UI at `/docs` for complete API details.*

---

## Notification Service

*No explicit header comment was found in `notification-service/main.py`.*

*For a full overview of its endpoints, please view the Swagger documentation at `/docs`.*

---

## Paraphrase Service

*No explicit header comment was found in `paraphrase_service/main.py`.*

*Please refer to the `/docs` endpoint for interactive API documentation.*

---

## Performer Service

*No explicit header comment was found in `performer_service/main.py`.*

*View the Swagger UI at `/docs` for complete API endpoint information.*

---

## Session Context Service

*No explicit header comment was found in `session_context_service/main.py`.*

*The service’s endpoints and models are fully documented in the interactive Swagger documentation available at `/docs`.*

---

## Spokenword Service

*No explicit header comment was found in `spokenword_service/main.py`.*

*For endpoint details, please refer to the Swagger UI at `/docs`.*

---

## Story Factory Service

*No explicit header comment was found in `story_factory_service/main.py`.*

*Complete API documentation can be viewed at `/docs` when the service is running.*

---

# Deployment

The entire ecosystem is containerized and orchestrated via Docker Compose. For instructions on building and running the system, please see the root-level documentation or the provided `reset_and_build.sh` script.

Each service’s OpenAPI documentation is accessible at the `/docs` endpoint when that service is running. For example, if the 2FA Service is mapped to port 9000, its documentation is at [http://localhost:9000/docs](http://localhost:9000/docs).

# Repository Structure

```
FountainAI-Eco-System/
├── 2fa_service/                     # Contains 2fa_service/main.py and its Dockerfile; see header above.
├── action_service/                  # Contains action_service/main.py; see notes above.
├── central_gateway/                 # Contains central_gateway/main.py; see notes above.
├── central_sequence_service/        # Contains central_sequence_service/main.py; see header above.
├── character_service/               # Contains character_service/main.py; see notes above.
├── core_script_management_service/  # Contains core_script_management_service/main.py; see notes above.
├── docker-compose.yml               # Orchestrates all services.
├── docker_log_review.sh             # Script for reviewing logs.
├── fountainai-rbac/                 # Contains fountainai-rbac/main.py; see notes above.
├── kms-app/                         # Contains kms-app/main.py; see notes above.
├── notification-service/            # Contains notification-service/main.py; see notes above.
├── paraphrase_service/              # Contains paraphrase_service/main.py; see notes above.
├── performer_service/               # Contains performer_service/main.py; see notes above.
├── reset_and_build.sh               # Script to reset and rebuild the Docker environment.
├── session_context_service/         # Contains session_context_service/main.py; see notes above.
├── spokenword_service/              # Contains spokenword_service/main.py; see notes above.
├── story_factory_service/           # Contains story_factory_service/main.py; see notes above.
└── typesense_client_service/        # Contains typesense_client_service/main.py; see header above.
```

# Contributing

Please base all contributions on the evidence provided by each service’s header comments and the generated OpenAPI documentation. When submitting changes, ensure that the documentation remains consistent with the explicit functionality defined in the source code.

# License

This project is licensed under the [MIT License](LICENSE).

---

This README is constructed entirely from the header comments (when available) in each service’s main.py file, ensuring that the documentation is evidence‑based and directly reflects the implementation. If any service is missing explicit header documentation, users are directed to the interactive Swagger documentation for complete details.
