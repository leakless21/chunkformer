import os
import uvicorn
from model.utils.logging import setup_logger
from model.utils.config import config

def main():
    """Run the Uvicorn server with reload enabled."""
    env = os.environ.get("ENV", "development")
    setup_logger(env)
    uvicorn.run("api:app", host=config['api']['host'], port=config['api']['port'], reload=True)

if __name__ == "__main__":
    main()