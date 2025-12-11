import redis
from .config import settings

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=settings.REDIS_DECODE_RESPONSES,
    username=settings.REDIS_USERNAME,
    password=settings.REDIS_PASSWORD,
)

def get_redis():
    return redis_client