import logging


def get_logger():
    logger = logging.getLogger(__name_)
    for handler in logger.handlers:
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[%(levelname)s] (%(threadName)-10s) %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


logger = get_logger()


def handler(*args):
    logger.info('lambda!')
    logger.info(*args)


if __name__ == '__main__':
    handler('a', 'b', 'c')
