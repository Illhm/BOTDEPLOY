import modal

# Define the Modal application
app = modal.App("bot-deploy-manager")

# Build the Modal image from the existing Dockerfile
# This will copy the requirements and install them, and set up the environment
image = modal.Image.from_dockerfile("Dockerfile")

# Create a web server function that runs the Flask application
# The Flask app in run.py is configured to listen on port 5000 by default.
# We also attach the secret "botdeploy-secrets" which contains the environment variables.
@app.function(
    image=image,
    secrets=[modal.Secret.from_name("botdeploy-secrets")],
    min_containers=1, # Keep one instance warm to avoid cold starts for the bot
)
@modal.web_server(port=5000, startup_timeout=60)
def run_bot():
    import subprocess

    # Run the main bot script
    # The bot uses Flask for the web server and long polling or webhooks for Telegram
    subprocess.run(["python", "run.py"])
