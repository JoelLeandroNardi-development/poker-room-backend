from shared.core.messaging.mq import create_publisher

publisher, cfg = create_publisher(required=True)
RABBIT_URL = cfg.url
EXCHANGE_NAME = cfg.exchange_name
