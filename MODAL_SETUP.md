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

## Additional Commands

- To test the app ephemerally before deploying:
  ```bash
  modal serve modal_app.py
  ```
- To view logs of the running app, go to the Modal Dashboard or use:
  ```bash
  modal app logs bot-deploy-manager
  ```
