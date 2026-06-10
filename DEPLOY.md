# TradeBook License Server — Deployment Guide

## One-time setup (~20 minutes)

### Step 1 — Create the Supabase database (free)

1. Go to https://supabase.com and sign up / log in
2. Click **New project**, name it `tradebook-licenses`
3. Once created, click **SQL Editor** in the left panel
4. Paste and run this SQL:

```sql
CREATE TABLE licenses (
    id          BIGSERIAL PRIMARY KEY,
    key         TEXT UNIQUE NOT NULL,
    customer_name  TEXT DEFAULT '',
    customer_phone TEXT DEFAULT '',
    machine_id     TEXT DEFAULT '',
    machine_name   TEXT DEFAULT '',
    is_active      BOOLEAN DEFAULT TRUE,
    activated_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    notes          TEXT DEFAULT ''
);
```

5. Go to **Project Settings → API**
   - Copy **Project URL** → this is your `SUPABASE_URL`
   - Copy **service_role** key (under "Project API keys") → this is your `SUPABASE_KEY`
   - **Never share the service_role key publicly**

---

### Step 2 — Deploy the server to Render.com (free)

1. Go to https://render.com and sign up / log in
2. Click **New → Web Service**
3. Choose **"Deploy an existing repository"** → connect your GitHub and push the
   `tradebook_license_server/` folder, OR choose **"Upload files"** and zip + upload
4. Set the following:
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add these **Environment Variables** in Render:

   | Key              | Value                          |
   |------------------|--------------------------------|
   | SUPABASE_URL     | (paste from Step 1)            |
   | SUPABASE_KEY     | (paste service_role from Step 1)|
   | ADMIN_KEY        | (choose a strong secret)       |
   | HMAC_SECRET      | (choose another strong secret) |

6. Click **Deploy**. After ~2 minutes your server URL will be shown:
   `https://your-app-name.onrender.com`

---

### Step 3 — Update the app with your server URL

In `utils/license.py`, change line 18:

```python
ACTIVATION_SERVER = os.environ.get("TRADEBOOK_SERVER", "https://your-app-name.onrender.com")
```

Then rebuild the installer (see `build.bat`).

---

## Daily usage — creating and managing keys

Set environment variables once (Windows PowerShell):
```powershell
$env:TRADEBOOK_SERVER   = "https://your-app-name.onrender.com"
$env:TRADEBOOK_ADMIN_KEY = "the-admin-key-you-set-in-render"
```

Create a key for a new customer:
```
python admin_tool.py create "Ravi Poultry Traders" 9876543210
```

List all keys:
```
python admin_tool.py list
```

Customer got a new computer — reset the key:
```
python admin_tool.py reset TB-XXXX-XXXX-XXXX
```

Stop a customer's access:
```
python admin_tool.py revoke TB-XXXX-XXXX-XXXX
```

---

## What happens on the customer's machine

1. They run `TradeBook_Setup_v1.0.exe` and install the app
2. First launch shows the activation screen
3. They enter the key you gave them
4. Internet required for 30 seconds — server verifies and registers their machine
5. All future launches are instant and **100% offline**
6. If they move to a new computer: you reset the key, they activate again

## Notes on the free tiers

- **Supabase free**: 500MB storage, unlimited API calls — enough for thousands of customers
- **Render free**: Server sleeps after 15 minutes idle. The first activation of the day
  may take 30-60 seconds while the server wakes up. This is fine since activation
  only happens once per machine.
