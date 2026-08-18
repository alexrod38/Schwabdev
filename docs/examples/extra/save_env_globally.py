import schwabdev

# Save your Schwab developer credentials globally so you don't have to pass them to every Client() when made.
# This will create a file at ~/.schwabdev/env.json with the keys: app_key, app_secret, callback_url.
# Run this once with your credentials filled out, then you can use Schwabdev anywhere on your system.
# You will no longer need a .env file or to pass your credentials to Client() when you create it.

schwabdev.save_env_global(
    app_key="your_app_key",
    app_secret="your_app_secret",
    callback_url="your_callback_url",
)