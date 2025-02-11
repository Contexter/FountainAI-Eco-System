# **FountainAI Docker Deployment Guide for Administrators**

## **1. Introduction**
This guide provides **FountainAI system administrators** with a structured approach to deploying and managing the FountainAI ecosystem using **Docker Compose**. It follows a logical deployment order based on **service dependencies**, ensuring **Typesense is available before launching dependent services**. 

Key highlights:
- **Step-by-step deployment instructions**
- **Scripts for dependency analysis and environment validation**
- **Secure `.env` variable management**
- **Docker commands for efficient system administration**

---

## **2. Understanding the Deployment Strategy**
FountainAI consists of **multiple services**, some of which depend on each other. Our analysis identified a **critical dependency**:
- **`central_sequence_service` requires `typesense_client_service`**, which means **Typesense must be running before any dependent service starts**.

To solve this, the system is deployed in **two separate Docker compositions**:

| **Docker Compose File**            | **Purpose**                                     |
|------------------------------------|---------------------------------------------|
| `docker-compose.typesense.yml`     | Deploys **Typesense** and **Typesense Client** |
| `docker-compose.yml`               | Deploys the **FountainAI Core Services**    |

This ensures **stability, modular deployment, and easier debugging**.

---

## **3. Preparing the Environment**
### **3.1 Install Required Tools**
Ensure Docker and Docker Compose are installed:
```sh
sudo apt update && sudo apt install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker
```
Verify installation:
```sh
docker --version
docker-compose --version
```

### **3.2 Clone the Repository**
```sh
cd /opt
sudo git clone https://github.com/Contexter/FountainAI-Eco-System.git
cd FountainAI-Eco-System
```

### **3.3 Analyzing Dependencies**
Run the **dependency analysis script** to detect service dependencies:
```sh
python analyze_service_dependencies.py
```
This generates `env_dependency_report.md`, which highlights **required service startup order**.

---

## **4. Secure Environment Variable Management**
### **4.1 Generating and Validating `.env` Files**
To ensure each service has its required environment variables, run:
```sh
python generate_env_report.py
```
This outputs `env_report.md`, listing:
- ✅ **Existing variables per service**
- ❌ **Missing variables**
- ⚠️ **Potential security risks (duplicate variables)**

### **4.2 Recommended Secure Variable Storage**
1. **Use `.env` files per service** (already structured within the repo):
   ```sh
   action_service/.env
   central_sequence_service/.env
   typesense_client_service/.env
   ```
2. **Restrict `.env` file permissions**:
   ```sh
   chmod 600 services/*/.env
   ```
3. **Never commit `.env` files to Git** (already `.gitignore`d).
4. **If needed, centralize secrets using a vault** (e.g., AWS Secrets Manager, HashiCorp Vault).

---

## **5. Deploying the FountainAI Ecosystem**
### **5.1 Deploying Typesense Services First**
Since **Typesense is a critical dependency**, deploy it separately:

#### **📜 `docker-compose.typesense.yml`**
```yaml
version: '3.8'

services:
  typesense:
    image: typesense/typesense:0.24.1
    container_name: typesense
    restart: always
    ports:
      - "8108:8108"
    environment:
      TYPESENSE_API_KEY: "your-secret-api-key"
      TYPESENSE_ENABLE_CORS: "true"
      TYPESENSE_DATA_DIR: "/data"
    volumes:
      - typesense_data:/data

  typesense_client_service:
    build:
      context: ./typesense_client_service
    container_name: typesense_client_service
    restart: unless-stopped
    environment:
      TYPESENSE_API_KEY: "your-secret-api-key"
      TYPESENSE_HOST: "typesense"
      TYPESENSE_PORT: "8108"
    depends_on:
      - typesense

volumes:
  typesense_data:
```

Run the composition:
```sh
docker-compose -f docker-compose.typesense.yml up -d --build
```
Verify Typesense is running:
```sh
docker ps | grep typesense
```

### **5.2 Deploying the Main FountainAI Services**
Once Typesense is available, deploy all other FountainAI services:

#### **📜 `docker-compose.yml` (Main Services)**
```yaml
version: '3.8'

services:
  action_service:
    build:
      context: ./action_service
    env_file:
      - ./action_service/.env
    depends_on:
      - central_sequence_service

  central_sequence_service:
    build:
      context: ./central_sequence_service
    env_file:
      - ./central_sequence_service/.env
    depends_on:
      - typesense_client_service

  session_context_service:
    build:
      context: ./session_context_service
    env_file:
      - ./session_context_service/.env
    depends_on:
      - central_sequence_service
```

Deploy the services:
```sh
docker-compose -f docker-compose.yml up -d --build
```

Check the logs to ensure services are running:
```sh
docker-compose logs -f
```

---

## **6. Managing and Updating the Deployment**
### **6.1 Restarting Services**
Restart a single service:
```sh
docker-compose restart action_service
```
Restart all services:
```sh
docker-compose restart
```

### **6.2 Stopping Services**
Stop the entire FountainAI system:
```sh
docker-compose down
```
Stop Typesense services only:
```sh
docker-compose -f docker-compose.typesense.yml down
```

### **6.3 Updating the Deployment**
If new changes are pushed to GitHub, update the deployment:
```sh
git pull origin main
docker-compose -f docker-compose.typesense.yml up -d --build
docker-compose -f docker-compose.yml up -d --build
```

### **6.4 Checking Running Containers**
```sh
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

---

## **7. Conclusion**
This guide provides **a structured, secure, and modular deployment approach** for FountainAI using Docker Compose. **By deploying Typesense first**, we ensure stability and avoid dependency issues. 

For further automation, consider:
- **A deployment script** to automate the full process
- **CI/CD integration** to keep deployments consistent

🚀 **Now your FountainAI ecosystem is securely deployed!**

