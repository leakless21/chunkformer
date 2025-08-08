import os
import uvicorn
from model.utils.logging import setup_logger
from model.utils.config import config

def main():
    """Run the Uvicorn server with reload enabled."""
    env = os.environ.get("ENV", "development")
    setup_logger(env)
    # Use watchfiles reloader (default) and ensure only worker initializes heavy resources.
    # No change in behavior for dev; api.startup_handler guards with RUN_MAIN/WATCHFILES_RELOADER.
    uvicorn.run("api:app", host=config['api']['host'], port=config['api']['port'], reload=True)

if __name__ == "__main__":
    main()