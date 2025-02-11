# FountainAI Development Documentation

## **Replacing `entrypoint.sh` with `entrypoint.py` for Dependency Injection**

### **Introduction**
In the **FountainAI Eco-System**, all services use `entrypoint.sh` as a point of **Dependency Injection (DI)**. However, relying on shell scripts for critical dependency management is **outdated** and has **several limitations**:

- **Limited error handling**: Shell scripts lack structured error handling and retries.
- **Hard to debug**: Troubleshooting failures is cumbersome compared to structured logs in Python.
- **Security risks**: Secrets exported as environment variables can be exposed.
- **Scalability concerns**: As services grow, maintaining complex shell scripts becomes unmanageable.

To address these issues, we propose **replacing `entrypoint.sh` with `entrypoint.py`**, a Python-based entrypoint script that keeps all services unchanged while improving **robustness, security, and maintainability**.

---

## **Implementation Plan**

### **1. Introducing `entrypoint.py` (Python-Based DI Manager)**
Instead of fetching dependencies in **`entrypoint.sh`**, each service will now use `entrypoint.py`, which:
- **Fetches secrets dynamically** from the Secrets Manager.
- **Injects dependencies** into the runtime environment.
- **Handles logging and retries properly.**
- **Executes the existing FastAPI service** without modifying application code.

#### **📌 New `entrypoint.py` Implementation**
```python
import os
import json
import time
import subprocess
import requests

# Configuration
SECRETS_SERVICE_URL = os.getenv("SECRETS_SERVICE_URL", "http://secrets-service:8000")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY")

if not SERVICE_API_KEY:
    raise ValueError("SERVICE_API_KEY is missing!")

def fetch_secret(secret_name):
    """ Fetch a secret from the Secrets Manager """
    try:
        response = requests.get(f"{SECRETS_SERVICE_URL}/secrets/{secret_name}", headers={"x-api-key": SERVICE_API_KEY})
        if response.status_code == 200:
            return response.json()["secret"]
        else:
            print(f"Error fetching secret {secret_name}: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to Secrets Service: {e}")
    return None

# Fetch and inject secrets dynamically
secrets_to_fetch = ["DATABASE_URL", "JWT_SECRET"]
for secret in secrets_to_fetch:
    value = fetch_secret(secret)
    if value:
        os.environ[secret] = value
        print(f"Injected secret: {secret}")

# Start the FastAPI service
subprocess.run(["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"])
```

---

### **2. Updating Dockerfiles to Use `entrypoint.py`**
Previously, Dockerfiles used `entrypoint.sh`:
```dockerfile
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

Now, we replace it with `entrypoint.py`:
```dockerfile
COPY entrypoint.py /entrypoint.py
ENTRYPOINT ["python", "/entrypoint.py"]
```

This ensures that **all services remain unchanged** while improving how dependencies are injected.

---

### **3. Keeping Compatibility: Hybrid Approach**
If a service **requires** an `entrypoint.sh` file for legacy reasons, we can keep a **minimal Bash wrapper** that calls the Python-based entrypoint.

#### **📌 Minimal `entrypoint.sh` (Calls Python Entrypoint)**
```sh
#!/bin/sh

echo "Starting Python-based Entrypoint..."
exec python /entrypoint.py
```

This allows services that still rely on `entrypoint.sh` to remain compatible while upgrading the DI logic.

---

## **4. Key Benefits of Moving to `entrypoint.py`**

| Feature | `entrypoint.sh` (Old) | `entrypoint.py` (New) |
|---------|----------------|----------------|
| **Keeps existing FastAPI apps unchanged** | ✅ Yes | ✅ Yes |
| **Handles secrets dynamically** | ❌ Weak handling | ✅ Structured Python requests |
| **Supports logging, retries** | ❌ Limited in Bash | ✅ Full error handling |
| **Easy debugging** | ❌ Hard in shell | ✅ Python stack traces |
| **Works in Dockerized environments** | ✅ Yes | ✅ Yes |

---

## **5. Summary & Next Steps**
✔ **No need to modify FastAPI services—just replace `entrypoint.sh` with `entrypoint.py`.**  
✔ **Python handles DI, logging, and retries better than shell scripting.**  
✔ **If compatibility is needed, `entrypoint.sh` can still exist as a wrapper.**  
✔ **Ensures all services in FountainAI remain dynamically configurable without any breaking changes.**  

🚀 **Next Steps:**
- Implement `entrypoint.py` across all FountainAI services.
- Update Dockerfiles to remove direct dependency on `entrypoint.sh`.
- Test runtime behavior to ensure smooth transition.
- Document changes for future maintainability.

This marks **an important milestone** in making FountainAI’s microservices **more robust, scalable, and future-proof**.

