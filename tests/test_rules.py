import time

from app.rules import Incoming, find_rule, pick, rule_matches


def rule(**kw):
    base = {
        "id": 1,
        "channels": ["comment"],
        "post_scope": "all",
        "triggers": [{"match": "any"}],
        "actions": {"public_replies": ["a"]},
        "advanced": {},
    }
    base.update(kw)
    return base


def comment(text="سلام", media="m1", user="u1"):
    return Incoming(channel="comment", user_id=user, text=text, media_id=media)


def test_match_types():
    assert rule_matches(rule(triggers=[{"match": "exact", "value": "تقویم"}]), comment("تقويم."), None)
    assert not rule_matches(rule(triggers=[{"match": "exact", "value": "تقویم"}]), comment("تقویم رو میخوام"), None)
    assert rule_matches(rule(triggers=[{"match": "contains", "value": "تقویم"}]), comment("سلام تقویم رو میخوام"), None)
    assert rule_matches(rule(triggers=[{"match": "starts_with", "value": "سلام"}]), comment("سلام خوبی"), None)
    assert rule_matches(rule(triggers=[{"match": "regex", "value": r"^\d+$"}]), comment("۱۲۳"), None)
    assert not rule_matches(rule(triggers=[{"match": "regex", "value": "("}]), comment("x"), None)


def test_or_between_triggers():
    r = rule(triggers=[{"match": "exact", "value": "لینک"}, {"match": "exact", "value": "تقویم"}])
    assert rule_matches(r, comment("لینک"), None)
    assert rule_matches(r, comment("تقویم"), None)
    assert not rule_matches(r, comment("سلام"), None)


def test_channel_and_scope():
    assert not rule_matches(rule(channels=["dm"]), comment(), None)
    assert rule_matches(rule(channels=["dm"]), Incoming("dm", "u1", "hi"), None)
    assert rule_matches(rule(post_scope=["m1"]), comment(media="m1"), None)
    assert not rule_matches(rule(post_scope=["m1"]), comment(media="m2"), None)


def test_once_and_cooldown():
    now = time.time()
    assert not rule_matches(rule(advanced={"once_per_user": True}), comment(), now - 10, now)
    assert rule_matches(rule(advanced={"once_per_user": True}), comment(), None, now)
    assert not rule_matches(rule(advanced={"cooldown_seconds": 60}), comment(), now - 10, now)
    assert rule_matches(rule(advanced={"cooldown_seconds": 60}), comment(), now - 100, now)


def test_active_hours():
    r = rule(advanced={"active_hours": [9, 23]})
    at_10 = time.mktime((2026, 11, 1, 10, 0, 0, 0, 0, -1))
    at_3 = time.mktime((2026, 11, 1, 3, 0, 0, 0, 0, -1))
    assert rule_matches(r, comment(), None, at_10)
    assert not rule_matches(r, comment(), None, at_3)
    wrap = rule(advanced={"active_hours": [22, 2]})
    assert rule_matches(wrap, comment(), None, time.mktime((2026, 11, 1, 23, 0, 0, 0, 0, -1)))
    assert not rule_matches(wrap, comment(), None, at_10)


def test_priority_and_rotation():
    rules = [
        rule(id=2, priority=10, triggers=[{"match": "exact", "value": "تقویم"}]),
        rule(id=1, priority=100),
    ]
    assert find_rule(rules, comment("تقویم"), lambda *_: None)["id"] == 2
    assert find_rule(rules, comment("سلام"), lambda *_: None)["id"] == 1
    assert [pick(["a", "b", "c"], i) for i in range(5)] == ["a", "b", "c", "a", "b"]
    assert pick([], 0) is None
