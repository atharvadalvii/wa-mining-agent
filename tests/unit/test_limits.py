from geoagent.limits import check_message


def test_allows_a_normal_message():
    assert check_message(0, "gold near Kalgoorlie", max_messages=30, max_chars=600) is None


def test_rejects_an_overlong_message():
    reply = check_message(0, "x" * 601, max_messages=30, max_chars=600)
    assert reply and "too long" in reply


def test_rejects_once_the_session_limit_is_reached():
    assert check_message(29, "hi", max_messages=30, max_chars=600) is None
    reply = check_message(30, "hi", max_messages=30, max_chars=600)
    assert reply and "limit of 30" in reply


def test_zero_disables_each_limit():
    assert check_message(10_000, "x" * 10_000, max_messages=0, max_chars=0) is None
