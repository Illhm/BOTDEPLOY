# Deploying Bot Deploy Manager to Modal

This guide provides step-by-step instructions on how to run and deploy the Bot Deploy Manager on [Modal](https://modal.com).

## 1. Prerequisites

First, you need to install the Modal client and authenticate with your account.

```bash
pip install modal
modal setup
```

## 2. Environment Variables (Secrets)

The application requires some environment variables like your Telegram Bot Token. In Modal, environment variables are managed as "Secrets".

1. Create a `.env` file locally by copying `.env.example`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in your credentials (`API_ID`, `API_HASH`, `BOT_TOKEN`, `ALLOWED_USERS`, `SHUTDOWN_TOKEN`).
3. Upload these variables to a Modal Secret named `botdeploy-secrets`:
   ```bash
   modal secret create botdeploy-secrets dotenv .env
   ```

## 3. Deploying the App

Once your secrets are set up, you can deploy the app to Modal. Modal will automatically use your existing `Dockerfile` to build the container image and expose port 5000 using `@modal.web_server`.

```bash
modal deploy modal_app.py
```

This will output a URL for your app's web server endpoint, and the bot will start running in the background, communicating with Telegram.

## 4. Deploying via GitHub Actions (CI/CD)

You can also automate your deployments to Modal using GitHub Actions. A workflow file (`.github/workflows/deploy-modal.yml`) is already included in this repository.

To set this up:

1. Go to your Modal dashboard: Settings > API Tokens.
2. Click "New Token" and copy the **Token ID** and **Token Secret**.
3. Go to your GitHub repository: Settings > Secrets and variables > Actions.
4. Click "New repository secret" and add the following:
   - Name: `MODAL_TOKEN_ID`, Secret: `<your_token_id>`
   - Name: `MODAL_TOKEN_SECRET`, Secret: `<your_token_secret>`

Now, every time you push code to the `main` branch, GitHub Actions will automatically deploy your latest code to Modal!

## Additional Commands

- To test the app ephemerally before deploying:
  ```bash
  modal serve modal_app.py
  ```
- To view logs of the running app, go to the Modal Dashboard or use:
  ```bash
  modal app logs bot-deploy-manager
  ```
