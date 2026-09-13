from apps.core.tasks import ping


def test_ping_returns_pong():
    assert ping.apply().get() == "pong"
