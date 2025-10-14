from src.clubbot.utils.rate_limiter import RateLimiter


def test_rate_limiter_basic():
    rl = RateLimiter(2)
    allowed1, wait1 = rl.allow(123, "qrcode")
    allowed2, wait2 = rl.allow(123, "qrcode")
    allowed3, wait3 = rl.allow(123, "qrcode")

    assert allowed1 is True and wait1 == 0
    assert allowed2 is True and wait2 == 0
    assert allowed3 is False and wait3 > 0
    assert wait3 <= 60
