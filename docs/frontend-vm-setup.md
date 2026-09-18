# NetPro Frontend VM Setup

> Status: HTTPS development server, Backend connectivity, authentication, dashboard device status, systemd startup, and reboot persistence verified on 17 September 2026.

This guide follows `Network-Laboratory-UI/NetPro-Frontend`. The certificate, runtime environment file, and systemd service are VM-local configuration and must not be committed to the component repository.

## Verified result

- Ubuntu 24.04.5 LTS
- Node.js 18.19.1 and npm 9.2.0
- Repository dependencies installed exactly with `npm ci`
- React HTTPS server available on port 3005
- Frontend reachable from the Windows host at `https://192.168.31.136:3005`
- Backend API reachable from the browser at `https://192.168.31.135:3000`
- Registration, login, dashboard display, and paired NPB/Policy device creation verified
- `netpro-frontend` starts automatically and survived a reboot

## VMware hardware and addressing

| Setting | Value |
| --- | --- |
| VM name | `Frontend-VM` |
| Hostname | `frontend-vm` |
| Username | `netpro` |
| Guest OS | Ubuntu 24.04 |
| Network Adapter | NAT |
| Stable NetPro address | `192.168.0.95/24` |
| Verified DHCP/NAT address | `192.168.31.136/24` |

The Frontend does not use DPDK. Keep the management adapter under its normal kernel driver.

Create the persistent secondary address in `/etc/netplan/99-netpro-control.yaml`:

```yaml
network:
  version: 2
  ethernets:
    ens33:
      addresses:
        - 192.168.0.95/24
```

Apply and verify it:

```bash
sudo chmod 600 /etc/netplan/99-netpro-control.yaml
sudo netplan generate
sudo netplan apply
ip -br addr show ens33
ping -c 2 192.168.0.94
curl -k -i https://192.168.0.94:3000/ps/blocked-list
```

## Install and configure the Frontend

```bash
sudo apt update
sudo apt install -y nodejs npm git openssl

cd ~
git clone https://github.com/Network-Laboratory-UI/NetPro-Frontend.git
cd ~/NetPro-Frontend
npm ci
git status --short
```

Do not run `npm audit fix --force` during baseline setup because it may introduce breaking dependency changes.

## Create the repository's certificate path

The repository expects the following fixed paths:

```text
/home/ubuntu/cert/server.crt
/home/ubuntu/cert/server.key
```

Create a self-signed certificate for this isolated lab:

```bash
sudo mkdir -p /home/ubuntu/cert
sudo openssl req \
  -x509 \
  -newkey rsa:2048 \
  -nodes \
  -keyout /home/ubuntu/cert/server.key \
  -out /home/ubuntu/cert/server.crt \
  -days 3650 \
  -subj "/CN=frontend-vm" \
  -addext "subjectAltName=DNS:frontend-vm,DNS:localhost,IP:192.168.0.95"

sudo chown root:netpro /home/ubuntu/cert/server.key
sudo chmod 640 /home/ubuntu/cert/server.key
sudo chmod 644 /home/ubuntu/cert/server.crt
```

## Runtime environment

Create `~/NetPro-Frontend/.env.local`:

```dotenv
HOST=0.0.0.0
PORT=3005
REACT_APP_BASE_URL=https://192.168.31.135:3000
```

The React application runs in the Windows browser, so its API URL must be an address reachable by Windows. In the verified VMware NAT setup this is the Backend DHCP/NAT address `192.168.31.135`, not the VM-only `192.168.0.94` control address. DHCP addresses may change; update `.env.local` and restart the service if that happens.

## Automatic startup

Create `/etc/systemd/system/netpro-frontend.service`:

```ini
[Unit]
Description=NetPro React Frontend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=netpro
Group=netpro
WorkingDirectory=/home/netpro/NetPro-Frontend
Environment=BROWSER=none
ExecStart=/usr/bin/npm start
Restart=on-failure
RestartSec=5
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
```

Enable and verify it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netpro-frontend
sudo systemctl status netpro-frontend --no-pager
sudo ss -ltnp | grep ':3005'
sudo journalctl -u netpro-frontend -n 30 --no-pager
```

The webpack deprecation and outdated Browserslist messages observed at startup are warnings; the verified build still compiled successfully.

## Browser access and certificate trust

Because both services use self-signed lab certificates, first open the Backend endpoint from Windows and accept its certificate warning:

```text
https://192.168.31.135:3000/ps/blocked-list
```

Then open the Frontend and accept its certificate warning:

```text
https://192.168.31.136:3005
```

Registration and login were verified with a disposable lab account. Do not record its password in Git.

## Device pairing and generated configuration

The verified dashboard device pair used:

| Setting | Value |
| --- | --- |
| Name | `NetPro` |
| Location | `NetLab` |
| Statistics period | 1 second |
| Send period | 1 minute |
| NPB ID | `79c57972-db3b-409e-b4e8-ab4ee526f666` |
| Policy Server ID | `6f7e663a-dfae-4b31-9e4e-93bc64d3e0a1` |

The downloaded `config.cfg` initially contained the browser-facing Backend address. For Policy and NPB processes, create a VM runtime copy using the stable control address:

```text
HOSTNAME= https://192.168.0.94:3000
```

Install that runtime copy as `config/config.cfg` in both component repositories. Back up the repository default outside the repository, and never commit the generated IDs or VM-specific configuration.

## Trust the Backend certificate on Policy and NPB VMs

Copy only the Backend public certificate to both VMs, then install it into the system trust store:

```bash
sudo cp ~/netpro-backend.crt \
  /usr/local/share/ca-certificates/netpro-backend.crt
sudo update-ca-certificates
```

Verify without `-k`:

```bash
curl -i https://192.168.0.94:3000/ps/blocked-list
```

This is required because the native Policy and NPB processes use libcurl and reject an untrusted self-signed certificate.

## Dashboard Active status

Policy and NPB heartbeats reached PostgreSQL correctly, but the Backend repository's existing 15-second status-check cron block was commented out. It was enabled locally in `src/app.js`, syntax-checked, and the Backend service was restarted. After that, both dashboard cards changed from **Inactive** to **Active**.

This is the intentional local Backend commit `bd3c3fc Enable device heartbeat status checks` (placeholder author metadata). Keep it local during a rebuild and review it separately before any upstream push.

## Reboot verification

After reboot, the Frontend VM reported:

```text
ens33  UP  192.168.0.95/24 192.168.31.136/24
netpro-frontend: enabled
netpro-frontend: active
0.0.0.0:3005: LISTEN
```

The login flow was verified again after the reboot.

## Local-only and sensitive data

Keep these outside Git:

- `/home/ubuntu/cert/server.key` and `server.crt`;
- `~/NetPro-Frontend/.env.local`;
- `/etc/systemd/system/netpro-frontend.service`;
- downloaded/generated `config.cfg` files and UUIDs;
- account passwords, browser certificate exceptions, logs, and build output.
