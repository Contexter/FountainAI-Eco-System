# Deployment on Hetzner Guide

## **1. Introduction**

This guide provides a step-by-step process to deploy and manage the **FountainAI Eco System** on a **Hetzner Cloud** server. Deployment is handled via GitHub, with optional automation using Rsync. However, the process halts at the point where environment variables (`.env` files) are required, as they are not stored in the repository.

---

## **2. Provisioning a Hetzner Server Using `hcloud` CLI**

### **2.1 Install Hetzner Cloud CLI (`hcloud`)**

#### **MacOS:**

```sh
brew install hcloud
```

#### **Linux:**

```sh
curl -fsSL https://packages.hetzner.com/hcloud/deb/key | sudo tee /etc/apt/trusted.gpg.d/hcloud.asc
echo "deb https://packages.hetzner.com/hcloud/deb $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hcloud.list
sudo apt update && sudo apt install -y hcloud
```

#### **Windows (WSL or Git Bash):**

```sh
choco install hcloud
```

### **2.2 Configure `hcloud` CLI with an API Token**

1. Go to [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Navigate to **Security → API Tokens**
3. Click **Generate API Token** (Full Access)
4. Copy the API token securely
5. Configure `hcloud` CLI with the token:

```sh
hcloud context create fountainai
```
- When prompted, **paste your API token**.
- This **stores the token** and **creates a new context** named `fountainai`.

6. Verify that the token is configured:

```sh
hcloud context list
```

If the context is not active, activate it:

```sh
hcloud context use fountainai
```

### **2.3 Create the Server**

Before creating the server, list available types by running:
```sh
hcloud server-type list
```
Choose a suitable type, such as `cax31`, based on availability.

Now, create the server:
```sh
hcloud server create \
    --name fountainai-server \
    --type cax31 \
    --image ubuntu-24.04 \
    --location fsn1 \
    --ssh-key "$(hcloud ssh-key list | awk 'NR==2 {print $2}')"
```

Retrieve the public IP:
```sh
hcloud server ip fountainai-server
```

Now, **SSH into the server**:
```sh
ssh root@$(hcloud server ip fountainai-server)
```

---

## **3. Setting Up Docker & Docker Compose on Hetzner**

### **3.1 Install Docker**

```sh
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker
```

Verify installation:
```sh
docker --version
docker-compose --version
```

---

## **4. Deploying FountainAI from GitHub**

### **4.1 Clone the GitHub Repository**

```sh
cd /opt
sudo git clone https://github.com/Contexter/FountainAI-Eco-System.git
cd FountainAI-Eco-System
```

### **4.2 Missing `.env` Files Halt Deployment**

Each service requires its own `.env` file, which is **not stored in the repository**. These environment variables must be manually created or securely transferred before deployment can proceed.

At this point, the deployment process **halts** due to missing `.env` files. The next steps depend on how the `.env` files are securely provided to the server.

---

## **5. Next Steps**

To continue deployment, you must:
- **Manually create the `.env` files** for each service on the Hetzner server.
- **Securely transfer the `.env` files** from a trusted source.

Once the `.env` files are available, restart the deployment with:
```sh
docker-compose up -d --build
```

This ensures that each service has the necessary environment variables to run securely.

---

## **6. Conclusion**

This guide provides a structured approach to setting up FountainAI on Hetzner Cloud but **halts at the missing `.env` files**, ensuring that sensitive data is handled securely and not stored in the repository. 🚀

