# **Guide: Setting Up Key-Based SSH Access to an AWS Lightsail Instance (From Zero to Streamlined Access)**

This guide walks you through setting up **key-based SSH access** to an **AWS Lightsail** instance, from **creating an SSH key** to **automatically logging in with a short command**.

---

## **1. Generate an SSH Key Pair (If You Don’t Have One)**
On your **local machine**, open a terminal and run:

```sh
ssh-keygen -t rsa -b 4096 -C "your-email@example.com"
```

- Press **Enter** to save the key in the default location (`~/.ssh/id_rsa`).
- Press **Enter** again when prompted for a passphrase (or set one for extra security).
- This creates two files:
  - **Private key**: `~/.ssh/id_rsa` (Keep this safe and never share it!)
  - **Public key**: `~/.ssh/id_rsa.pub`

---

## **2. Upload Your Public Key to Lightsail**
### **Option 1: Upload Directly in Lightsail**
1. Log in to **AWS Lightsail**.
2. Go to the **Networking** tab.
3. Under **SSH Key Pairs**, click **Upload new**.
4. Choose your **public key** file (`~/.ssh/id_rsa.pub`).
5. Click **Save**.

### **Option 2: Manually Add Your Key to an Existing Instance**
If your Lightsail instance is already running:
1. **Connect via the AWS Lightsail Web SSH Console**:
   - In Lightsail, go to **Instances** → Click your instance → **Connect using SSH**.
   
2. **Create and Secure the SSH Directory**:
   ```sh
   mkdir -p ~/.ssh
   chmod 700 ~/.ssh
   ```

3. **Add Your Public Key to the Authorized Keys File**:
   On your **local machine**, print your public key:
   ```sh
   cat ~/.ssh/id_rsa.pub
   ```
   Copy the output and paste it into the instance’s terminal:
   ```sh
   echo "your-public-key-content" >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```

4. **Restart SSH (If Needed)**:
   ```sh
   sudo systemctl restart ssh
   ```

---

## **3. Connect to Your Lightsail Instance via SSH**
Now, test SSH access from your **local machine**:

```sh
ssh -i ~/.ssh/id_rsa ubuntu@your-lightsail-instance-ip
```

- Replace **`ubuntu`** with the correct username for your OS:
  - **Amazon Linux**: `ec2-user`
  - **Ubuntu**: `ubuntu`
  - **Debian**: `admin`
  - **Bitnami**: `bitnami`
- Replace `your-lightsail-instance-ip` with your instance’s **public IP**.

If successful, you're connected using your SSH key!

---

## **4. Streamline SSH Access with an SSH Config File**
Instead of typing the full SSH command every time, set up an **SSH config file**.

### **Create/Edit the SSH Config File**
On your **local machine**, run:

```sh
nano ~/.ssh/config
```

Add the following:

```ini
Host lightsail
    HostName your-lightsail-instance-ip
    User ubuntu
    IdentityFile ~/.ssh/id_rsa
```

- Replace **`your-lightsail-instance-ip`** with your Lightsail **public IP**.
- Replace **`ubuntu`** with the correct user.

Save and exit (**CTRL+X, Y, Enter**).

### **Set Proper Permissions**
```sh
chmod 600 ~/.ssh/config
```

---

## **5. Connect with a Short Command**
Now, instead of running the long SSH command, you can simply type:

```sh
ssh lightsail
```

It will automatically:
- Use your SSH key (`id_rsa`).
- Use the correct user.
- Use the correct IP.

---

## **6. (Optional) Add an Even Shorter Alias**
For even faster access, add an alias:

```sh
echo "alias lsail='ssh lightsail'" >> ~/.bashrc
source ~/.bashrc
```

Now, simply type:

```sh
lsail
```

to connect instantly!

---

## **Final Test**
Run:

```sh
ssh lightsail
```

or, if you added an alias:

```sh
lsail
```

If it logs in without asking for a password, **you've successfully set up key-based SSH access and automated login**!

---

## **7. (Optional) Disable Password Authentication for Extra Security**
To ensure only SSH keys are used for authentication:

1. Edit the SSH configuration:
   ```sh
   sudo nano /etc/ssh/sshd_config
   ```
2. Find and update these lines:
   ```
   PasswordAuthentication no
   PubkeyAuthentication yes
   ```
3. Save and exit (**CTRL+X, Y, Enter**).
4. Restart SSH:
   ```sh
   sudo systemctl restart ssh
   ```

Now, your server only allows **SSH key authentication**, improving security.

---

### **✅ You’re Done!**
Now, you have:
✅ **Generated an SSH key**  
✅ **Uploaded it to AWS Lightsail**  
✅ **Manually added it to an existing instance**  
✅ **Configured SSH for automatic login**  
✅ **Set up an alias for quick access**  
✅ **Secured your server by disabling password login (optional)**  

Enjoy **secure, hassle-free SSH access** to your AWS Lightsail instance! 🚀