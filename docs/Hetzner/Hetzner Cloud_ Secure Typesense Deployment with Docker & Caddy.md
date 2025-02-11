# Hetzner Cloud: Secure Typesense Deployment with Docker & Caddy

Below is a step-by-step guide to deploying Typesense on Hetzner Cloud, starting from basic prerequisites and security considerations to a fully functional public or private deployment.

---

## 1. Introduction

This guide details how to run [Typesense](https://typesense.org/) on a Hetzner Cloud instance using Docker. We cover:

- **Private Network Only**: Accessible only within a secure internal network.
- **Public Access**: Accessible behind Caddy using HTTPS on a custom domain.

Throughout, we focus on best practices for handling API keys, configuring firewall rules, and maintaining a secure environment.

---

## 2. Prerequisites

1. **Hetzner Cloud Instance**: (Ubuntu 22.04 recommended).
2. **Private Network (optional)**: For isolating Typesense in a non-public subnet.
3. **Docker & Docker Compose**: [Installation instructions](https://docs.docker.com/engine/install/ubuntu/).
4. **A Domain**: (e.g., `typesense.fountain.coach`), if you plan on public HTTPS.
5. **Basic Unix Knowledge**: Familiarity with `sudo`, editing config files, etc.

---

## 3. Understanding the Security Model

### 3.1 Key Generation & Storage

Typesense does not supply pre-generated credentials; **you create them**. Typically:

- **Admin Key**: Full privileges (create/delete collections, manage keys, etc.).
- **Search-Only Key**: Limited to performing search queries.

You can define these as high-entropy random strings in an `.env` file or in secrets management systems (Docker Swarm secrets, AWS Secrets Manager, etc.). Keep your Admin Key private.

> **Security Bottleneck**: If the Admin Key is leaked, an attacker can do anything with your cluster.

### 3.2 API Keys & Access Control

Typesense enforces access control using these API keys:

- **Admin Key**: Full cluster control.
- **Search Key**: Limited read/search-only scope.

To reduce risk:

- Rotate keys periodically.
- Store them securely (avoid committing them to version control).

### 3.3 Firewall Rules

Restrict inbound traffic to essential ports:

- By default, Typesense listens on port `8108`.
- On a private network, you can limit access to the subnet.
- For public setups, place Typesense behind a reverse proxy (Caddy) and block direct port `8108` externally.

---

## 4. Private Network Deployment

**Goal**: Restrict Typesense to internal access on your Hetzner Cloud private network.

### 4.1 Prepare Environment

1. **Create a directory**:
   ```bash
   mkdir ~/typesense
   cd ~/typesense
   ```
2. **Create an ********`.env`******** file** (storing keys securely):
   ```bash
   TYPESENSE_API_KEY=YOUR_SEARCH_KEY
   TYPESENSE_ADMIN_API_KEY=YOUR_ADMIN_KEY
   ```
   Replace placeholders with strong random values.

### 4.2 Docker Compose Configuration

Create `docker-compose.yml` in the same directory:

```yaml
version: '3.8'
services:
  typesense:
    image: typesense/typesense:latest
    container_name: typesense
    restart: always
    volumes:
      - ./data:/data
    environment:
      - TYPESENSE_DATA_DIR=/data
      - TYPESENSE_API_KEY=${TYPESENSE_API_KEY}
      - TYPESENSE_ADMIN_API_KEY=${TYPESENSE_ADMIN_API_KEY}
      - TYPESENSE_ENABLE_CORS=false
      - TYPESENSE_BIND_ADDRESS=0.0.0.0
    ports:
      - "8108:8108"  # Expose only for internal usage or debugging

  caddy:
    image: caddy:latest
    container_name: caddy
    restart: always
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
    ports:
      - "80:80"
      - "443:443"
```

### 4.3 Optional: Internal Caddy Configuration

For internal HTTPS (optional), create a `Caddyfile`:

```caddy
{
  admin off
}

http://typesense.localhost {
  reverse_proxy typesense:8108
}
```

### 4.4 Firewall Setup (UFW)

Install and configure UFW:

```bash
sudo apt-get update
sudo apt-get install ufw -y
sudo ufw allow ssh
sudo ufw enable
```

Allow only traffic from your private subnet on `8108`:

```bash
sudo ufw allow from 10.0.0.0/24 to any port 8108  # Example
```

Allow ports 80/443 if using Caddy internally:

```bash
sudo ufw allow 80
sudo ufw allow 443
```

### 4.5 Deploy

```bash
docker-compose up -d
```

### 4.6 Test Private Access

- Verify health:
  ```bash
  curl http://<internal-ip>:8108/health
  ```
- If using Caddy:
  ```bash
  curl http://typesense.localhost/health
  ```

A JSON response indicates Typesense is running.

---

## 5. Public Deployment Behind Caddy

**Goal**: Securely expose Typesense to the public via HTTPS.

### 5.1 Domain & DNS

- Configure a domain (e.g., `typesense.fountain.coach`) pointing to your server’s public IP via an A record.

### 5.2 Adjust Docker Compose for Public Access

In `docker-compose.yml`, restrict direct external exposure of port `8108` by binding it to localhost, and let Caddy proxy it:

```yaml
version: '3.8'
services:
  typesense:
    image: typesense/typesense:latest
    container_name: typesense
    restart: always
    environment:
      - TYPESENSE_API_KEY=${TYPESENSE_API_KEY}
      - TYPESENSE_ADMIN_API_KEY=${TYPESENSE_ADMIN_API_KEY}
      - TYPESENSE_ENABLE_CORS=false
      - TYPESENSE_BIND_ADDRESS=0.0.0.0
    ports:
      - "127.0.0.1:8108:8108"  # Only accessible on localhost

  caddy:
    image: caddy:latest
    container_name: caddy
    restart: always
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
    ports:
      - "80:80"
      - "443:443"
```

### 5.3 Caddy Configuration for HTTPS

Create/modify `Caddyfile`:

```caddy
{
  # Global options block
  email youremail@example.com
}

typesense.fountain.coach {
  reverse_proxy typesense:8108
  tls {
    # Let's Encrypt auto-config
  }

  # Security headers
  header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
  header X-Content-Type-Options "nosniff"
  header X-Frame-Options "DENY"

  # Optional rate limiting
  @searchRequests path /collections/*
  rate_limit @searchRequests 100 1m
}
```

### 5.4 Firewall Configuration for Public Access

- Allow HTTP/HTTPS:
  ```bash
  sudo ufw allow 80
  sudo ufw allow 443
  ```
- Deny direct access to `8108`:
  ```bash
  sudo ufw deny 8108
  ```

### 5.5 Deploy & Validate

```bash
docker-compose up -d
```

- Check `https://typesense.fountain.coach/health`.
- For API calls:
  ```bash
  curl -H "X-TYPESENSE-API-KEY: YOUR_ADMIN_KEY" https://typesense.fountain.coach/collections
  ```

---

## 6. Deployment Validation & Administration

### 6.1 Monitoring Logs

```bash
docker-compose logs -f
```

### 6.2 Testing API Connectivity

```bash
curl \
  -H "X-TYPESENSE-API-KEY: YOUR_ADMIN_KEY" \
  https://typesense.fountain.coach/collections
```

If configured correctly, you see a JSON array (empty if no collections yet).

### 6.3 Creating & Managing Additional API Keys

```bash
curl \
  -X POST \
  -H "X-TYPESENSE-API-KEY: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Search Only Key",
    "actions": ["documents:search"],
    "collections": ["*"]
  }' \
  https://typesense.fountain.coach/keys
```

You’ll receive a JSON response with the newly generated key.

### 6.4 Common Issues & Troubleshooting

1. **Certificate Errors**: Check Caddy logs for DNS or Let’s Encrypt issues.
2. **Firewall Blocks**: Ensure you have correct UFW rules.
3. **Docker Networking**: Confirm containers share the correct network.

---

## 7. Best Practices & Next Steps

1. **Production Security**: Treat your Admin Key like a root password; never expose it publicly.
2. **Scaling**: For higher throughput or redundancy, run a Typesense cluster across multiple nodes.
3. **Backups**: Regularly back up `/data` to avoid data loss.
4. **Monitoring & Metrics**: Tools like Grafana/Prometheus provide cluster health insights.
5. **High Availability**: Use multiple nodes in different regions. Consider RAID for disk resilience.
6. **Continuous Updates**: Keep OS packages, Docker, and Typesense versions up to date.

By following these steps, you can confidently deploy and manage a secure Typesense instance on Hetzner Cloud with Docker and Caddy.

---

**© 2025 FountainAI - Typesense & Hetzner Deployment Guide**

*This guide is for educational purposes. Always follow your organization’s IT and security policies.*

