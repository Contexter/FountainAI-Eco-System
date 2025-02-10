# FountainAI `.env` Analysis Report

## ✅ Services with `.env` Files
- **notification-service** (2 variables)
- **core_script_management_service** (5 variables)
- **central_gateway** (4 variables)
- **story_factory_service** (5 variables)
- **2fa_service** (2 variables)
- **spokenword_service** (5 variables)
- **paraphrase_service** (5 variables)
- **typesense_client_service** (7 variables)
- **session_context_service** (5 variables)
- **performer_service** (5 variables)
- **central_sequence_service** (5 variables)
- **fountainai-rbac** (2 variables)
- **kms-app** (2 variables)
- **character_service** (5 variables)
- **action_service** (5 variables)

## ❌ Services Missing `.env` Files
- **docs**
- **.github**
- **.git**

## 📌 Variables Per Service
| Service | Variable | Value |
|---------|----------|-------|
| notification-service | SECRET_KEY | your_very_secret_key_here |
| notification-service | DATABASE_URL | sqlite:///./notifications.db |
| core_script_management_service | SERVICE_PORT | 8000 |
| core_script_management_service | DATABASE_URL | sqlite:///./core_script.db |
| core_script_management_service | API_GATEWAY_URL | http://gateway:8000 |
| core_script_management_service | JWT_SECRET | your_jwt_secret_key |
| core_script_management_service | JWT_ALGORITHM | HS256 |
| central_gateway | GATEWAY_PORT | 8000 |
| central_gateway | JWT_SECRET | your_jwt_secret_key |
| central_gateway | JWT_ALGORITHM | HS256 |
| central_gateway | DATABASE_URL | sqlite:///./registry.db |
| story_factory_service | SERVICE_PORT | 8000 |
| story_factory_service | DATABASE_URL | sqlite:///./story_factory.db |
| story_factory_service | API_GATEWAY_URL | http://gateway:8000 |
| story_factory_service | JWT_SECRET | your_jwt_secret_key |
| story_factory_service | JWT_ALGORITHM | HS256 |
| 2fa_service | SECRET_KEY | your_super_secret_key_here |
| 2fa_service | DATABASE_URL | sqlite:///./2fa.db |
| spokenword_service | SERVICE_PORT | 8000 |
| spokenword_service | DATABASE_URL | sqlite:///./spokenword.db |
| spokenword_service | API_GATEWAY_URL | http://gateway:8000 |
| spokenword_service | JWT_SECRET | your_jwt_secret_key |
| spokenword_service | JWT_ALGORITHM | HS256 |
| paraphrase_service | SERVICE_PORT | 8000 |
| paraphrase_service | DATABASE_URL | sqlite:///./paraphrase.db |
| paraphrase_service | API_GATEWAY_URL | http://gateway:8000 |
| paraphrase_service | JWT_SECRET | your_jwt_secret_key |
| paraphrase_service | JWT_ALGORITHM | HS256 |
| typesense_client_service | TYPESENSE_HOST | typesense |
| typesense_client_service | TYPESENSE_PORT | 8108 |
| typesense_client_service | TYPESENSE_PROTOCOL | http |
| typesense_client_service | TYPESENSE_API_KEY | super_secure_typesense_key |
| typesense_client_service | KEY_MANAGEMENT_URL | http://key_management_service:8003 |
| typesense_client_service | SERVICE_NAME | typesense_client_service |
| typesense_client_service | ADMIN_TOKEN | your_admin_jwt_token |
| session_context_service | SERVICE_PORT | 8000 |
| session_context_service | DATABASE_URL | sqlite:///./session_context.db |
| session_context_service | API_GATEWAY_URL | http://gateway:8000 |
| session_context_service | JWT_SECRET | your_jwt_secret_key |
| session_context_service | JWT_ALGORITHM | HS256 |
| performer_service | SERVICE_PORT | 8000 |
| performer_service | DATABASE_URL | sqlite:///./performer.db |
| performer_service | API_GATEWAY_URL | http://gateway:8000 |
| performer_service | JWT_SECRET | your_jwt_secret_key |
| performer_service | JWT_ALGORITHM | HS256 |
| central_sequence_service | DATABASE_URL | sqlite:///./database.db |
| central_sequence_service | TYPESENSE_CLIENT_URL | http://typesense_client_service:8001 |
| central_sequence_service | TYPESENSE_SERVICE_API_KEY | your_secure_typesense_service_api_key |
| central_sequence_service | SERVICE_NAME | central_sequence_service |
| central_sequence_service | ADMIN_TOKEN | your_admin_jwt_token |
| fountainai-rbac | SECRET_KEY | your_very_secret_key_here |
| fountainai-rbac | DATABASE_URL | sqlite:///./app.db |
| kms-app | SECRET_KEY | your_very_secret_key_here |
| kms-app | DATABASE_URL | sqlite:///./keys.db |
| character_service | SERVICE_PORT | 8000 |
| character_service | DATABASE_URL | sqlite:///./character.db |
| character_service | API_GATEWAY_URL | http://gateway:8000 |
| character_service | JWT_SECRET | your_jwt_secret_key |
| character_service | JWT_ALGORITHM | HS256 |
| action_service | SERVICE_PORT | 8000 |
| action_service | DATABASE_URL | sqlite:///./action.db |
| action_service | API_GATEWAY_URL | http://gateway:8000 |
| action_service | JWT_SECRET | your_jwt_secret_key |
| action_service | JWT_ALGORITHM | HS256 |

## 🔍 Missing Variables Across Services
| Variable | Missing in Services |
|----------|----------------------|
| TYPESENSE_HOST | notification-service, core_script_management_service, central_gateway, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, session_context_service, performer_service, central_sequence_service, fountainai-rbac, kms-app, character_service, action_service |
| GATEWAY_PORT | notification-service, core_script_management_service, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, typesense_client_service, session_context_service, performer_service, central_sequence_service, fountainai-rbac, kms-app, character_service, action_service |
| KEY_MANAGEMENT_URL | notification-service, core_script_management_service, central_gateway, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, session_context_service, performer_service, central_sequence_service, fountainai-rbac, kms-app, character_service, action_service |
| ADMIN_TOKEN | notification-service, core_script_management_service, central_gateway, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, session_context_service, performer_service, fountainai-rbac, kms-app, character_service, action_service |
| TYPESENSE_CLIENT_URL | notification-service, core_script_management_service, central_gateway, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, typesense_client_service, session_context_service, performer_service, fountainai-rbac, kms-app, character_service, action_service |
| TYPESENSE_SERVICE_API_KEY | notification-service, core_script_management_service, central_gateway, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, typesense_client_service, session_context_service, performer_service, fountainai-rbac, kms-app, character_service, action_service |
| SERVICE_NAME | notification-service, core_script_management_service, central_gateway, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, session_context_service, performer_service, fountainai-rbac, kms-app, character_service, action_service |
| JWT_ALGORITHM | notification-service, 2fa_service, typesense_client_service, central_sequence_service, fountainai-rbac, kms-app |
| TYPESENSE_PROTOCOL | notification-service, core_script_management_service, central_gateway, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, session_context_service, performer_service, central_sequence_service, fountainai-rbac, kms-app, character_service, action_service |
| TYPESENSE_API_KEY | notification-service, core_script_management_service, central_gateway, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, session_context_service, performer_service, central_sequence_service, fountainai-rbac, kms-app, character_service, action_service |
| DATABASE_URL | typesense_client_service |
| SECRET_KEY | core_script_management_service, central_gateway, story_factory_service, spokenword_service, paraphrase_service, typesense_client_service, session_context_service, performer_service, central_sequence_service, character_service, action_service |
| SERVICE_PORT | notification-service, central_gateway, 2fa_service, typesense_client_service, central_sequence_service, fountainai-rbac, kms-app |
| JWT_SECRET | notification-service, 2fa_service, typesense_client_service, central_sequence_service, fountainai-rbac, kms-app |
| TYPESENSE_PORT | notification-service, core_script_management_service, central_gateway, story_factory_service, 2fa_service, spokenword_service, paraphrase_service, session_context_service, performer_service, central_sequence_service, fountainai-rbac, kms-app, character_service, action_service |
| API_GATEWAY_URL | notification-service, central_gateway, 2fa_service, typesense_client_service, central_sequence_service, fountainai-rbac, kms-app |

## ⚠️ Duplicate Variables Within Services
| Service | Duplicate Variables |
|---------|----------------------|

## 🎯 Improvement Recommendations
- Ensure all services have an `.env` file.
- Standardize missing keys across services.
- Remove duplicate keys within `.env` files.
- Review variable consistency across services.
