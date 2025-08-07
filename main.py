from loguru import logger
from model.utils.logging import setup_logger

def main():
    setup_logger('development')
    logger.info("Hello from chunkformer!")


if __name__ == "__main__":
    main()
