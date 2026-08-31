# Cloudflare Tunnel Setup Guide
## FinalGrid — Internet Connectivity

---

## What This Does

Cloudflare Tunnel creates a **secure, encrypted connection** from your hotel PC to the internet.
- No static IP needed
- No port forwarding on router
- No firewall changes
- Free (Cloudflare Zero Trust free tier)
- Works through any internet connection (BSNL, Jio, Airtel)

---

## Step 1 — Create a Free Cloudflare Account

1. Go to [cloudflare.com](https://cloudflare.com) → Sign Up (free)
2. Add your domain (e.g. `sukoonhotel.com`) OR use a free Cloudflare subdomain

---

## Step 2 — Install cloudflared on This PC

1. Download `cloudflared-windows-amd64.exe` from:
   https://github.com/cloudflare/cloudflared/releases/latest

2. Rename it to `cloudflared.exe`

3. Move it to `C:\Windows\System32\` (so you can run it from anywhere)

4. Verify: Open Command Prompt and run:
   ```
   cloudflared --version
   ```

---

## Step 3 — Create a Tunnel

Open Command Prompt and run:

```bat
cloudflared tunnel login
```
(Opens browser — log in to Cloudflare)

```bat
cloudflared tunnel create sukoon-pms
```

This creates a tunnel and saves a credentials file at:
`C:\Users\dell\.cloudflared\<TUNNEL_ID>.json`

Copy the TUNNEL_ID shown and paste it into `cloudflare\config.yml`.

---

## Step 4 — Point Your Domain to the Tunnel

```bat
cloudflared tunnel route dns sukoon-pms pms.yourdomain.com
cloudflared tunnel route dns sukoon-pms book.yourdomain.com
```

Replace `yourdomain.com` with your actual domain.
Also update `cloudflare\config.yml` with your domain names.

---

## Step 5 — Start Everything

Double-click **`start_pms.bat`** every morning.

Or run manually:
```bat
# Terminal 1 — Flask PMS
cd front_office_pms
venv\Scripts\python run.py

# Terminal 2 — Cloudflare Tunnel
cloudflared tunnel --config cloudflare\config.yml run
```

---

## What URLs Will Work

| URL | Who Uses It |
|-----|-------------|
| `http://localhost:5000` | Staff on hotel PC |
| `https://pms.yourdomain.com` | Staff on any device (phone/tablet on hotel WiFi or anywhere) |
| `https://pms.yourdomain.com/book` | Guests booking directly online |
| `https://pms.yourdomain.com/webhook/booking` | Channel manager (OTA bookings) |
| `https://pms.yourdomain.com/webhook/ping` | Connectivity test |

---

## Channel Manager Setup (e.g. Staah, Wubook)

Give your channel manager these details:

| Setting | Value |
|---------|-------|
| Availability API | `https://pms.yourdomain.com/book/api/availability?from=YYYY-MM-DD&to=YYYY-MM-DD` |
| Rates API | `https://pms.yourdomain.com/book/api/rates` |
| New Booking Webhook | `https://pms.yourdomain.com/webhook/booking` |
| API Key Header | `X-API-Key: <your webhook_api_key from Masters>` |
| Method | `POST` |
| Format | `JSON` |

Get your webhook API key from **Masters → Settings → webhook_api_key**.

---

## If Internet Goes Down

- The PMS continues working locally (hotel PC)
- Staff can still check in/out, take payments
- OTA bookings queue in channel manager and sync when internet returns
- Night audit runs locally on schedule

---

## Auto-Start on Windows Boot (Optional)

To start everything automatically when PC boots:

1. Press `Win + R`, type `shell:startup`, press Enter
2. Create a shortcut to `start_pms.bat` in that folder

The PMS will start automatically every time Windows starts.
