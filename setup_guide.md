# 🚀 Instagram Auto-Poster Setup Guide (@upscbite)

Welcome! This step-by-step guide will walk you through setting up automated posting to your Instagram Creator account (**@upscbite**) for free.

Follow each section in order. Every step includes exact URLs, instructions on what to click, and what to copy.

---

## 📋 Prerequisites Check

Before starting, make sure you have:
- [x] Instagram Professional/Creator account (**@upscbite**)
- [x] A Facebook Page linked to your Instagram account
- [x] A GitHub account
- [x] A Windows PC with Python installed

---

## 🔑 Step 1: Google Gemini API Key (FREE)

We use Google Gemini AI to automatically generate rich captions, hashtags, and quiz content for UPSC posts.

1. Go to Google AI Studio:  
   👉 **https://aistudio.google.com/apikey**
2. Log in with your Google account.
3. Click the **"Create API key"** button.
4. Select or create a Google Cloud project, then click **"Create API key in existing project"**.
5. Copy the generated API Key and save it in a text file.

> ℹ️ **Note:** The Gemini API free tier allows **15 requests per minute** and **1,000,000 tokens per day**, which is far more than needed for 20 posts/day!

---

## 🖼️ Step 2: imgbb API Key (FREE)

imgbb is used to host post images publicly so Meta's servers can download and publish them to Instagram.

1. Go to imgbb API setup:  
   👉 **https://api.imgbb.com/**
2. Click **"Get API key"** (or Sign Up if you don't have an account).
3. Once logged in, click **"Add API Key"** or copy your key directly from the dashboard.
4. Copy the API key string and save it.

> ℹ️ **Note:** imgbb free accounts offer unlimited public image uploads up to **32MB per image**.

---

## 🌐 Step 3: Meta Developer Account & App (FREE)

To publish posts via the Instagram Graph API, you need a Meta Developer account and a Business App.

1. Go to Meta for Developers:  
   👉 **https://developers.facebook.com/**
2. Click **"Get Started"** or **"My Apps"** in the top right corner.
3. Complete the registration using your existing Facebook login (accept terms, confirm email).
4. On the **Apps** page, click the green **"Create App"** button.
5. Select **"Other"** (or directly choose **"Business"** type if prompted for use case).
6. Select **"Business"** as the app type and click **Next**.
7. Enter your App Display Name: `upscbite-poster` (or any name you prefer).
8. Ensure your App Contact Email is correct and click **"Create App"**.
9. Enter your Facebook password when prompted. You will be redirected to the **App Dashboard**.

---

## 🔌 Step 4: Add Instagram Product to Meta App

1. In your **App Dashboard** (`https://developers.facebook.com/apps/YOUR_APP_ID/dashboard/`), scroll down to **"Add products to your app"**.
2. Locate **"Instagram Graph API"** (or **"Instagram"**).
3. Click **"Set Up"**.
4. This enables the Instagram API endpoints for your Meta application.

---

## ⚡ Step 5: Generate Short-Lived Access Token

1. Open the Graph API Explorer tool:  
   👉 **https://developers.facebook.com/tools/explorer/**
2. In the **Meta App** dropdown at the top right, select **`upscbite-poster`**.
3. Under **User or Page**, select **"User Token"**.
4. Under **Permissions**, click **"Add a Permission"** and grant the following permissions:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `publish_to_groups` *(optional)*
5. Click **"Generate Access Token"** (blue button).
6. A Facebook login popup will appear. Select your Facebook Page and Instagram Account (**@upscbite**), grant all permissions, and click **Done**.
7. Copy the generated **Access Token** from the text field.

> ⚠️ This is a **short-lived token** (valid for 1-2 hours). We will convert it to a long-lived token next.

---

## ⏳ Step 6: Get Long-Lived User Access Token (60 Days)

To convert your short-lived token into a 60-day long-lived token:

1. Get your **App ID** and **App Secret**:
   - Go to your App Dashboard: `https://developers.facebook.com/apps/`
   - Go to **App settings** > **Basic**.
   - Copy **App ID** and click **Show** to copy **App Secret**.
2. Construct the following URL in your web browser (replace placeholders):

```text
https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=YOUR_SHORT_LIVED_TOKEN
```

3. Press Enter. You will see a JSON response in your browser like this:

```json
{
  "access_token": "EAAG...",
  "token_type": "bearer",
  "expires_in": 5183999
}
```

4. Copy the long `access_token` string. **This token is valid for 60 days.**

---

## 📄 Step 7: Get Page Access Token & Page ID

1. Open Graph API Explorer or paste this URL into your browser (replace `YOUR_LONG_LIVED_USER_TOKEN`):

```text
https://graph.facebook.com/v21.0/me/accounts?access_token=YOUR_LONG_LIVED_USER_TOKEN
```

2. Look at the JSON response. Find your Facebook Page object:

```json
{
  "data": [
    {
      "access_token": "EAA...",
      "category": "Education",
      "name": "UPSC Bite",
      "id": "123456789012345",
      "tasks": [...]
    }
  ]
}
```

3. Copy the two values:
   - **`id`**: This is your **Page ID** (e.g., `123456789012345`).
   - **`access_token`**: This is your **Page Access Token** (permanent token generated from long-lived user token).

---

## 📸 Step 8: Get Instagram Business Account ID

1. Open Graph API Explorer or paste this URL into your browser (replace `YOUR_PAGE_ID` and `YOUR_PAGE_ACCESS_TOKEN`):

```text
https://graph.facebook.com/v21.0/YOUR_PAGE_ID?fields=instagram_business_account&access_token=YOUR_PAGE_ACCESS_TOKEN
```

2. You will receive a response like this:

```json
{
  "instagram_business_account": {
    "id": "17841400000000000"
  },
  "id": "123456789012345"
}
```

3. Copy the `id` inside `instagram_business_account` (e.g., `17841400000000000`). This is your **Instagram Business Account ID** (`META_IG_USER_ID`).

---

## ⚙️ Step 9: Fill in config.json

1. Open `config.example.json` in your project folder as reference.
2. Create or update `config.json` with your real keys:

```json
{
  "GEMINI_API_KEY": "YOUR_GEMINI_API_KEY",
  "IMGBB_API_KEY": "YOUR_IMGBB_API_KEY",
  "META_USER_ACCESS_TOKEN": "YOUR_LONG_LIVED_USER_TOKEN",
  "META_PAGE_ACCESS_TOKEN": "YOUR_PAGE_ACCESS_TOKEN",
  "META_IG_USER_ID": "YOUR_INSTAGRAM_BUSINESS_ACCOUNT_ID",
  "META_PAGE_ID": "YOUR_FACEBOOK_PAGE_ID"
}
```

| Config Key | Source Step |
| :--- | :--- |
| `GEMINI_API_KEY` | Step 1 |
| `IMGBB_API_KEY` | Step 2 |
| `META_USER_ACCESS_TOKEN` | Step 6 |
| `META_PAGE_ACCESS_TOKEN` | Step 7 |
| `META_PAGE_ID` | Step 7 |
| `META_IG_USER_ID` | Step 8 |

---

## 🐙 Step 10: Set Up GitHub Repository (FREE)

Setting up GitHub Actions allows your posts to be published on an automatic schedule for free.

1. Go to GitHub: 👉 **https://github.com/new**
2. Repository Name: `upscbite-poster`
3. Visibility: Select **Private** 🔒 *(Important to protect your API keys!)*
4. Click **"Create repository"**.
5. Open Terminal / PowerShell in your project folder on your PC and run:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/upscbite-poster.git
git push -u origin main
```

6. Add GitHub Repository Secrets:
   - Go to your GitHub repository page.
   - Click **Settings** > **Secrets and variables** > **Actions**.
   - Click **"New repository secret"** for each of the following:

| Secret Name | Value |
| :--- | :--- |
| `META_USER_ACCESS_TOKEN` | Long-lived User Access Token (Step 6) |
| `META_PAGE_ACCESS_TOKEN` | Page Access Token (Step 7) |
| `META_IG_USER_ID` | Instagram Account ID (Step 8) |
| `META_PAGE_ID` | Facebook Page ID (Step 7) |
| `IMGBB_API_KEY` | imgbb API Key (Step 2) |

> ℹ️ **Note:** Gemini API key is not required in GitHub Actions if content generation (`prepare.py`) is run locally on your PC.

---

## 📦 Step 11: Install Python Dependencies

Open PowerShell or Command Prompt in `C:\Users\Welcome\.gemini\antigravity\scratch\insta-automation\` and run:

```powershell
pip install -r requirements.txt
```

---

## 🧪 Step 12: Test the Setup

Validate your pipeline by executing dry runs and status checks:

1. **Test dry run (generates content & test image without posting to IG):**
   ```powershell
   python prepare.py --dry-run
   ```

2. **Check account status and credentials:**
   ```powershell
   python prepare.py --status
   ```

🎉 **Congratulations!** Your Instagram Automation pipeline is fully configured and ready to publish.
