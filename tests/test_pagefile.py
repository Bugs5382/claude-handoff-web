"""Tests for template/_site/pagefile.py: every write to a page file, under a lock, with rounds, history and the thread."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "template" / "_site"
sys.path.insert(0, str(SITE))

import pagefile  # noqa: E402
import schema  # noqa: E402

T0 = "2026-10-26T07:42:10-04:00"
T1 = "2026-10-26T08:05:44-04:00"
T2 = "2026-10-26T08:20:02-04:00"


def review(**extra):
    d = {"schema": "handoff.page/v1", "kind": "review", "title": "Design", "items": [
        {"id": "s1", "title": "Purpose", "body": [{"p": "Why."}]},
        {"id": "s2", "title": "Layout", "body": [{"p": "Where."}]},
        {"id": "q1", "type": "question", "title": "Which port?"},
    ]}
    d.update(extra)
    return d


def journey():
    return {"schema": "handoff.page/v1", "kind": "journey", "title": "Journey 1", "build": "app 1", "items": [
        {"id": "j1", "title": "Install", "steps": ["Run it"], "checkpoint": "after-install"},
        {"id": "j2", "title": "Set up", "steps": ["Add a type"], "checkpoint": "system-ready"},
        {"id": "j3", "title": "Order", "steps": ["Order a laptop"]},
    ]}


@pytest.fixture
def path(tmp_path):
    return tmp_path / "app" / "design.json"


def make(path, definition=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    pagefile.write_definition(path, definition or review(), now=T0)
    return path


def test_creating_a_page_starts_at_rev_1_and_round_1(path):
    path.parent.mkdir(parents=True)
    rev = pagefile.write_definition(path, review(), now=T0)
    doc = pagefile.load(path)
    assert rev == 1 and doc["rev"] == 1
    assert doc["rounds"] == [{"round": 1, "build": None, "reset": None, "opened": T0, "closed": None, "openedBy": "created",
                              "answers": {}, "checkpoints": {}, "reopened": {}}]
    assert doc["thread"] == {} and doc["submissions"] == []


def test_a_definition_cannot_write_server_keys(path):
    make(path)
    for key in ("rev", "rounds", "thread", "submissions", "route"):
        with pytest.raises(pagefile.PageError, match=f"{key}: written by the server"):
            pagefile.write_definition(path, review(**{key: 1}))


def test_an_invalid_definition_is_refused_and_the_file_is_untouched(path):
    make(path)
    before = path.read_bytes()
    bad = review()
    bad["items"][0]["body"] = "text"
    with pytest.raises(pagefile.PageError) as err:
        pagefile.write_definition(path, bad)
    assert "items[s1].body: expected a list of blocks" in err.value.errors
    assert path.read_bytes() == before


def test_answers_are_stamped_and_bump_rev(path):
    make(path)
    rev = pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", now=T1)
    doc = pagefile.load(path)
    assert rev == 2 and doc["rev"] == 2
    assert doc["rounds"][0]["answers"]["s1"] == {"answer": "yes", "note": "", "by": "Alex", "at": T1,
                                                 "hash": pagefile.item_hash(doc["items"][0])}


def test_was_keeps_every_earlier_answer_oldest_first(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "changes", "note": "Too long"}}, by="Alex", now=T0)
    pagefile.save_answers(path, {"s1": {"answer": "", "note": ""}}, by="Alex", now=T1)
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", now=T2)
    a = pagefile.load(path)["rounds"][0]["answers"]["s1"]
    assert a["answer"] == "yes" and a["at"] == T2
    assert a["was"] == [{"answer": "changes", "note": "Too long", "by": "Alex", "at": T0},
                        {"answer": "", "note": "", "by": "Alex", "at": T1}]


def test_answers_are_checked_against_the_item(path):
    make(path)
    with pytest.raises(pagefile.PageError, match="s1: Changes needs a note"):
        pagefile.save_answers(path, {"s1": {"answer": "changes", "note": " "}}, by="Alex")
    with pytest.raises(pagefile.PageError, match="s1: expected one of yes, no, changes"):
        pagefile.save_answers(path, {"s1": {"answer": "skipped", "note": ""}}, by="Alex")
    with pytest.raises(pagefile.PageError, match="zz: no item zz on this page"):
        pagefile.save_answers(path, {"zz": {"answer": "yes", "note": ""}}, by="Alex")
    pagefile.save_answers(path, {"q1": {"answer": "5390, like today", "note": ""}}, by="Alex")
    assert pagefile.load(path)["rounds"][0]["answers"]["q1"]["answer"] == "5390, like today"


def test_a_stale_base_merges_item_by_item(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", base=1, now=T0)
    pagefile.save_answers(path, {"s2": {"answer": "no", "note": ""}}, by="Alex", base=1, now=T1)
    pagefile.save_answers(path, {"s1": {"answer": "no", "note": ""}}, by="Alex", base=1, now=T2)
    answers = pagefile.load(path)["rounds"][0]["answers"]
    assert answers["s1"]["answer"] == "no" and answers["s1"]["was"][0]["answer"] == "yes"
    assert answers["s2"]["answer"] == "no"


def test_an_unchanged_answer_does_not_write(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", now=T0)
    assert pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", now=T1) == 2


def test_a_build_change_opens_a_new_round(path):
    make(path, review(build="app 1"))
    pagefile.write_definition(path, review(build="app 1", title="Design v2"), now=T1)
    assert len(pagefile.load(path)["rounds"]) == 1
    pagefile.write_definition(path, review(build="app 2"), now=T2)
    rounds = pagefile.load(path)["rounds"]
    assert [r["round"] for r in rounds] == [1, 2]
    assert rounds[0]["closed"] == T2
    assert rounds[1]["build"] == "app 2" and rounds[1]["openedBy"] == "build changed" and rounds[1]["closed"] is None


def test_a_reset_change_opens_a_new_round(path):
    make(path)
    pagefile.write_definition(path, review(reset=1), now=T1)
    rounds = pagefile.load(path)["rounds"]
    assert rounds[1]["openedBy"] == "reset" and rounds[1]["reset"] == 1


def test_save_round_now_closes_the_round_with_its_results(path):
    make(path)
    n = pagefile.new_round(path, results="1. Purpose: Yes", now=T1)
    rounds = pagefile.load(path)["rounds"]
    assert n == 2
    assert rounds[0]["closed"] == T1 and rounds[0]["results"] == "1. Purpose: Yes"
    assert rounds[1]["openedBy"] == "saved"


def test_a_yes_from_an_earlier_round_is_hidden_and_others_stay_open(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}, "s2": {"answer": "no", "note": ""}}, by="Alex", now=T0)
    pagefile.new_round(path, now=T1)
    states = pagefile.item_states(pagefile.load(path))
    assert states["s1"] == {"answer": "yes", "hidden": True, "reopened": None, "round": 1}
    assert states["s2"] == {"answer": "", "hidden": False, "reopened": None, "round": None}


def test_a_changed_item_reopens(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", now=T0)
    pagefile.new_round(path, now=T1)
    changed = review()
    changed["items"][0]["body"] = [{"p": "Why, now with numbers."}]
    pagefile.write_definition(path, changed, now=T2)
    state = pagefile.item_states(pagefile.load(path))["s1"]
    assert state == {"answer": "", "hidden": False, "reopened": "changed since round 1", "round": None}


def test_a_change_inside_the_open_round_reopens_a_yes_too(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", now=T0)
    changed = review()
    changed["items"][0]["title"] = "Purpose and scope"
    pagefile.write_definition(path, changed, now=T1)
    assert pagefile.item_states(pagefile.load(path))["s1"]["reopened"] == "changed since round 1"


def test_a_reopen_reply_reopens_until_answered_again(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", now=T0)
    pagefile.new_round(path, now=T1)
    pagefile.reply(path, "s1", "app", "Fixed in #70.", action="reopen", reason="fixed in #70", now=T1)
    pagefile.new_round(path, now=T1)
    assert pagefile.item_states(pagefile.load(path))["s1"]["reopened"] == "fixed in #70"
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", now=T2)
    assert pagefile.item_states(pagefile.load(path))["s1"] == {"answer": "yes", "hidden": False, "reopened": None, "round": 3}


def test_replies_are_numbered_from_1_per_item(path):
    make(path)
    assert pagefile.reply(path, "s1", "ops", "Filed #70.", action="filed", ref="example-org/app#70", now=T0) == 1
    assert pagefile.reply(path, "s1", "app", "Fixed.", action="fixed", now=T1) == 2
    assert pagefile.reply(path, "_page", "app", "Round 2 is ready.", now=T1) == 1
    thread = pagefile.load(path)["thread"]
    assert thread["s1"][0] == {"n": 1, "from": "ops", "at": T0, "round": 1, "text": "Filed #70.", "action": "filed",
                               "ref": "example-org/app#70"}
    assert [r["n"] for r in thread["s1"]] == [1, 2]
    with pytest.raises(pagefile.PageError, match="zz: no item zz on this page"):
        pagefile.reply(path, "zz", "app", "?")


def test_a_yes_on_a_checkpoint_step_records_the_checkpoint(path):
    make(path, journey())
    pagefile.save_answers(path, {"j1": {"answer": "yes", "note": ""}}, by="Alex", now=T1)
    assert pagefile.load(path)["rounds"][0]["checkpoints"] == {"after-install": T1}


def test_restart_from_a_checkpoint_carries_steps_up_to_it(path):
    make(path, journey())
    pagefile.save_answers(path, {k: {"answer": "yes", "note": ""} for k in ("j1", "j2", "j3")}, by="Alex", now=T1)
    n = pagefile.restart(path, "after-install", by="Alex", now=T2)
    doc = pagefile.load(path)
    r = doc["rounds"][-1]
    assert n == 2 and r["openedBy"] == "restart from after-install" and r["restart"] == "after-install"
    assert r["checkpoints"] == {"after-install": T1}
    states = pagefile.item_states(doc)
    assert states["j1"]["answer"] == "yes"
    assert states["j2"] == {"answer": "", "hidden": False, "reopened": None, "round": None}
    assert states["j3"]["answer"] == ""
    with pytest.raises(pagefile.PageError, match="checkpoint nowhere: not reached yet"):
        pagefile.restart(path, "nowhere", by="Alex")


def test_writes_take_the_lock_file_and_leave_no_temp_files(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex")
    assert sorted(p.name for p in path.parent.iterdir()) == ["design.json", "design.json.lock"]


def test_a_page_over_the_size_cap_is_refused(path, monkeypatch):
    make(path)
    monkeypatch.setattr(pagefile, "MAX_BYTES", 2000)
    big = review()
    big["items"][0]["body"] = [{"p": "x" * 3000}]
    with pytest.raises(pagefile.PageError, match="page file would be .* bytes; the cap is 2000"):
        pagefile.write_definition(path, big)


def test_concurrent_writers_never_lose_a_write(path):
    items = [{"id": f"i{n}", "title": f"Item {n}"} for n in range(1, 61)]
    make(path, review(items=items))
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); import pagefile\n"
        "for n in range(int(sys.argv[3]), int(sys.argv[4])):\n"
        "    pagefile.save_answers(sys.argv[2], {f'i{n}': {'answer': 'yes', 'note': ''}}, by='Alex')\n"
    )
    procs = [subprocess.Popen([sys.executable, "-c", script, str(SITE), str(path), str(a), str(a + 30)]) for a in (1, 31)]
    assert [p.wait(timeout=60) for p in procs] == [0, 0]
    doc = json.loads(path.read_text())
    assert len(doc["rounds"][0]["answers"]) == 60
    assert doc["rev"] == 61


def test_set_status_writes_the_index_card(path):
    make(path)
    pagefile.set_status(path, "done", note="Stale (Alex, 2026-10-26 08:00 UTC)", chips=["Shipped"], priority=10)
    assert pagefile.load(path)["status"] == {"state": "done", "note": "Stale (Alex, 2026-10-26 08:00 UTC)", "chips": ["Shipped"],
                                             "priority": 10}
    with pytest.raises(pagefile.PageError, match="status.state: expected one of needs-you, reference, done"):
        pagefile.set_status(path, "later")


def test_submissions_are_numbered_from_1_and_marked_taken(path):
    make(path)
    first = pagefile.add_submission(path, {"kind": "send", "to": "ops", "items": ["s1"], "file": "5-a.json"}, now=T0)
    second = pagefile.add_submission(path, {"kind": "blocker", "to": "ops", "items": ["s2"], "file": "0-b.json"}, now=T1)
    assert (first["n"], second["n"]) == (1, 2)
    sub = pagefile.load(path)["submissions"][0]
    assert sub == {"n": 1, "kind": "send", "at": T0, "to": "ops", "round": 1, "rev": 1, "items": ["s1"], "file": "5-a.json",
                   "state": "sent"}
    pagefile.mark_taken(path, 1, at=T2)
    sub = pagefile.load(path)["submissions"][0]
    assert sub["state"] == "taken" and sub["takenAt"] == T2


def test_summary_counts_open_items_like_the_bar(path):
    d = review(items=[
        {"id": "a", "title": "A"},
        {"id": "b", "title": "B", "dependsOn": ["a"]},
        {"id": "c", "title": "C", "blockedBy": "example-org/app#70"},
        {"id": "d", "title": "D"},
        {"id": "q", "type": "question", "title": "Q"},
        {"id": "i", "type": "info", "title": "I"},
    ])
    make(path, d)
    s = pagefile.summary(pagefile.load(path))
    assert (s["open"], s["blocked"], s["counted"], s["yes"], s["reopened"]) == (2, 2, 4, 0, 0)
    pagefile.save_answers(path, {"a": {"answer": "yes", "note": ""}, "d": {"answer": "yes", "note": ""}}, by="Alex")
    pagefile.reply(path, "c", "app", "Landed.", action="unblock")
    s = pagefile.summary(pagefile.load(path))
    assert (s["open"], s["blocked"], s["yes"], s["approved"]) == (2, 0, 2, False)
    pagefile.save_answers(path, {"b": {"answer": "yes", "note": ""}, "c": {"answer": "yes", "note": ""}}, by="Alex")
    s = pagefile.summary(pagefile.load(path))
    assert (s["open"], s["approved"]) == (0, True)


def test_summary_runs_journey_steps_in_order(path):
    make(path, journey())
    s = pagefile.summary(pagefile.load(path))
    assert (s["open"], s["blocked"]) == (1, 2)


def test_summary_counts_backlog_choices_with_the_default(path):
    d = {"schema": "handoff.page/v1", "kind": "backlog", "title": "Backlog",
         "options": {"choices": [{"value": "start", "label": "Start"}, {"value": "hold", "label": "Hold"}], "default": "hold"},
         "items": [{"id": "b1", "title": "One"}, {"id": "b2", "title": "Two"}, {"id": "b3", "title": "Three"}]}
    make(path, d)
    pagefile.save_answers(path, {"b2": {"answer": "start", "note": ""}}, by="Alex")
    s = pagefile.summary(pagefile.load(path))
    assert s["tally"] == {"start": 1, "hold": 2} and s["open"] == 0


def test_import_rounds_fills_a_fresh_page_only(path):
    make(path)
    closed = {"round": 1, "build": None, "reset": None, "opened": T0, "closed": T1, "openedBy": "imported",
              "answers": {"s1": {"answer": "no", "note": "", "by": "Alex", "at": T1}}, "checkpoints": {}, "reopened": {}}
    open_ = {"round": 2, "build": None, "reset": None, "opened": T1, "closed": None, "openedBy": "imported",
             "answers": {}, "checkpoints": {}, "reopened": {}}
    assert pagefile.import_rounds(path, [closed, open_]) == 2
    assert [r["round"] for r in pagefile.load(path)["rounds"]] == [1, 2]
    with pytest.raises(pagefile.PageError, match="rounds can only be imported into a new page"):
        pagefile.import_rounds(path, [closed, open_])


def test_a_note_without_an_answer_is_kept(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "", "note": "Thinking about it"}}, by="Alex", now=T1)
    a = pagefile.load(path)["rounds"][0]["answers"]["s1"]
    assert (a["answer"], a["note"]) == ("", "Thinking about it")


def sent(path, ids, at=T1):
    sub = pagefile.add_submission(path, {"kind": "send", "to": "ops", "items": ids, "file": "f-{n}.json"}, now=at)
    pagefile.hold(path, sub["n"])
    return sub


def test_a_sent_yes_stays_hidden_after_the_agent_updates_the_page_in_the_same_round(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}, "s2": {"answer": "changes", "note": "Move it"}}, by="me", now=T0)
    sent(path, ["s1", "s2"])
    assert pagefile.item_states(pagefile.load(path))["s1"]["hidden"] is False, "stays on screen, locked, until the update"
    pagefile.reply(path, "s2", "ops", "Moved.", now=T2)
    doc = pagefile.load(path)
    states = pagefile.item_states(doc)
    assert len(doc["rounds"]) == 1
    assert states["s1"] == {"answer": "yes", "hidden": True, "reopened": None, "round": 1}
    assert states["s2"]["hidden"] is False and states["s2"]["answer"] == ""
    assert pagefile.summary(doc)["yes"] == 1


def test_a_yes_given_after_the_send_stays_visible_until_the_next_send(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T0)
    sent(path, ["s1"])
    pagefile.reply(path, "_page", "ops", "Updated.", now=T1)
    pagefile.save_answers(path, {"s2": {"answer": "yes"}}, by="me", now=T2)
    assert pagefile.item_states(pagefile.load(path))["s2"]["hidden"] is False


def test_a_blocker_hides_nothing(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T0)
    pagefile.add_submission(path, {"kind": "blocker", "to": "ops", "items": ["s1"], "file": "b.json"}, now=T1)
    assert pagefile.item_states(pagefile.load(path))["s1"]["hidden"] is False


def test_yes_clears_a_reopen_on_an_item_already_yes_in_the_open_round(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T0)
    pagefile.reply(path, "s1", "ops", "Look again", action="reopen", reason="Numbers moved", now=T1)
    assert pagefile.item_states(pagefile.load(path))["s1"]["reopened"] == "Numbers moved"
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T2)
    doc = pagefile.load(path)
    assert pagefile.item_states(doc)["s1"]["reopened"] is None and doc["rounds"][-1]["reopened"] == {}


def test_yes_clears_a_content_change_on_an_item_already_yes_in_the_open_round(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T0)
    changed = review()
    changed["items"][0]["body"] = [{"p": "New."}]
    pagefile.write_definition(path, changed)
    assert pagefile.item_states(pagefile.load(path))["s1"]["reopened"] == "changed since round 1"
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T2)
    assert pagefile.item_states(pagefile.load(path))["s1"]["reopened"] is None


def test_a_held_page_refuses_answers_until_the_agent_updates_it_or_the_owner_unlocks(path):
    make(path)
    sub = sent(path, ["s1"])
    assert pagefile.load(path)["rounds"][-1]["awaiting"] == sub["n"]
    with pytest.raises(pagefile.PageError):
        pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T1)
    pagefile.mark_taken(path, sub["n"], at=T1)
    assert "awaiting" in pagefile.load(path)["rounds"][-1], "being picked up isn't an update"
    pagefile.set_status(path, "needs-you")
    assert "awaiting" in pagefile.load(path)["rounds"][-1], "an index card isn't an update"
    pagefile.write_definition(path, review(summary="Updated"))
    assert "awaiting" not in pagefile.load(path)["rounds"][-1]
    sent(path, [], at=T2)
    pagefile.release(path)
    assert "awaiting" not in pagefile.load(path)["rounds"][-1]
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T2)


def test_a_new_round_is_never_held(path):
    make(path)
    sent(path, [])
    pagefile.new_round(path, now=T2)
    assert "awaiting" not in pagefile.load(path)["rounds"][-1]


def answered(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}, "s2": {"answer": "changes", "note": "Move it"}}, by="me", now=T0)
    sent(path, ["s1", "s2"])


def test_a_reply_under_a_sent_changes_clears_it_and_keeps_it_as_handled_history(path):
    answered(path)
    pagefile.reply(path, "s2", "ops", "Moved.", now=T2)
    doc = pagefile.load(path)
    rnd = doc["rounds"][-1]
    assert "s2" not in rnd["answers"], "an old note can't go out with the next Send"
    assert rnd["handled"]["s2"][0]["answer"] == "changes" and rnd["handled"]["s2"][0]["note"] == "Move it"
    assert rnd["handled"]["s2"][0]["handled"] == T2 and rnd["handled"]["s2"][0]["via"] == "reply"
    assert pagefile.item_states(doc)["s2"] == {"answer": "", "hidden": False, "reopened": None, "round": None}
    assert pagefile.summary(doc)["open"] >= 1


def test_a_changed_item_clears_a_sent_no_and_an_unchanged_one_keeps_it(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "no", "note": "Wrong"}, "s2": {"answer": "changes", "note": "Move it"}}, by="me", now=T0)
    sent(path, ["s1", "s2"])
    changed = review()
    changed["items"][0]["body"] = [{"p": "New."}]
    pagefile.write_definition(path, changed, now=T2)
    rnd = pagefile.load(path)["rounds"][-1]
    assert rnd["handled"]["s1"][0]["via"] == "definition" and "s1" not in rnd["answers"]
    assert rnd["answers"]["s2"]["note"] == "Move it", "nobody touched this one yet"


def test_a_reply_elsewhere_leaves_a_sent_changes_alone(path):
    answered(path)
    pagefile.reply(path, "_page", "ops", "Looking at it.", now=T2)
    rnd = pagefile.load(path)["rounds"][-1]
    assert rnd["answers"]["s2"]["answer"] == "changes" and "handled" not in rnd


def test_a_note_that_was_never_sent_is_not_handled(path):
    make(path)
    pagefile.save_answers(path, {"s2": {"answer": "changes", "note": "Move it"}}, by="me", now=T0)
    pagefile.reply(path, "s2", "ops", "Saw it.", now=T2)
    assert pagefile.load(path)["rounds"][-1]["answers"]["s2"]["note"] == "Move it"


def test_a_handled_no_does_not_bring_back_an_older_yes(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T0)
    pagefile.write_definition(path, review(build="2"), now=T1)
    pagefile.reply(path, "s1", "ops", "Look again", action="reopen", reason="Numbers moved", now=T1)
    pagefile.save_answers(path, {"s1": {"answer": "no", "note": "Still wrong"}}, by="me", now=T1)
    sent(path, ["s1"], at=T1)
    pagefile.reply(path, "s1", "ops", "Fixed.", now=T2)
    assert pagefile.item_states(pagefile.load(path))["s1"]["answer"] == ""
    pagefile.write_definition(path, review(build="3"), now=T2)
    assert pagefile.item_states(pagefile.load(path))["s1"] == {"answer": "", "hidden": False, "reopened": None, "round": None}


def test_unlock_keeps_a_sent_yes_changeable(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T0)
    sent(path, ["s1"])
    pagefile.release(path)
    assert pagefile.item_states(pagefile.load(path))["s1"]["hidden"] is False, "Unlock is there to change an answer"
    pagefile.reply(path, "_page", "ops", "Updated.", now=T2)
    assert pagefile.item_states(pagefile.load(path))["s1"]["hidden"] is False, "that Send was taken back"


def test_a_settled_yes_stays_after_an_item_reply_and_reopens_only_with_a_reason(path):
    answered(path)
    pagefile.reply(path, "s1", "ops", "Noted.", now=T2)
    assert pagefile.item_states(pagefile.load(path))["s1"]["hidden"] is True
    pagefile.reply(path, "s1", "ops", "Look again", action="reopen", reason="Conflicts with s2", now=T2)
    assert pagefile.item_states(pagefile.load(path))["s1"]["reopened"] == "Conflicts with s2"


def test_a_send_locks_only_what_it_carried(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T0)
    sent(path, ["s1"])
    pagefile.save_answers(path, {"s2": {"answer": "no", "note": "Not this"}}, by="me", now=T2)
    with pytest.raises(pagefile.PageError, match="s1"):
        pagefile.save_answers(path, {"s1": {"answer": "no"}}, by="me", now=T2)
    assert pagefile.held_items(pagefile.load(path)) == {"s1"}


def test_a_second_send_adds_to_what_is_held_and_unlock_takes_back_both(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T0)
    sent(path, ["s1"])
    pagefile.save_answers(path, {"s2": {"answer": "yes"}}, by="me", now=T1)
    sent(path, ["s2"], at=T2)
    assert pagefile.held_items(pagefile.load(path)) == {"s1", "s2"}
    pagefile.release(path)
    doc = pagefile.load(path)
    assert pagefile.held_items(doc) == set() and all(s["released"] for s in doc["submissions"])


def test_a_page_held_before_this_change_still_locks_what_its_send_carried(path):
    make(path)
    pagefile.save_answers(path, {"s1": {"answer": "yes"}}, by="me", now=T0)
    sub = pagefile.add_submission(path, {"kind": "send", "to": "ops", "items": ["s1"], "file": "f-{n}.json"}, now=T1)
    doc = pagefile.load(path)
    doc["rounds"][-1]["awaiting"] = sub["n"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    assert pagefile.held_items(pagefile.load(path)) == {"s1"}
    pagefile.reply(path, "_page", "ops", "Done.", now=T2)
    assert "held" not in pagefile.load(path)["rounds"][-1]


def phased():
    return {"schema": schema.SCHEMA, "kind": "round", "title": "Move", "phases": [
        {"id": "A", "title": "Prepare", "goal": "Ready to move"},
        {"id": "B", "title": "Cut over", "dependsOn": ["A"]},
        {"id": "C", "title": "Tidy up"}],
        "items": [{"id": "A1", "title": "One"}, {"id": "A2", "title": "Two"}, {"id": "B1", "title": "Three"},
                  {"id": "C1", "title": "Four", "dependsOn": ["A2"]}]}


def test_a_round_item_takes_accept_risk_with_a_required_note(path):
    make(path, phased())
    with pytest.raises(pagefile.PageError, match="Accept risk needs a note"):
        pagefile.save_answers(path, {"A1": {"answer": "risk", "note": " "}}, by="me", now=T0)
    pagefile.save_answers(path, {"A1": {"answer": "risk", "note": "We say so up front"}}, by="me", now=T0)
    assert pagefile.item_states(pagefile.load(path))["A1"]["answer"] == "risk"


def test_only_a_round_takes_accept_risk(path):
    make(path)
    with pytest.raises(pagefile.PageError):
        pagefile.save_answers(path, {"s1": {"answer": "risk", "note": "x"}}, by="me", now=T0)


def test_a_phase_is_blocked_until_the_one_it_depends_on_closes(path):
    make(path, phased())
    assert pagefile.phase_states(pagefile.load(path))["B"]["blocked"] == "A"
    pagefile.save_answers(path, {"A1": {"answer": "yes"}, "A2": {"answer": "risk", "note": "Said so"}}, by="me", now=T0)
    doc = pagefile.load(path)
    phases = pagefile.phase_states(doc)
    assert phases["A"]["closed"] is True and phases["B"]["blocked"] is None


def test_a_step_can_block_an_item_in_a_later_phase(path):
    make(path, phased())
    doc = pagefile.load(path)
    assert pagefile.summary(doc)["blocked"] == 2
    pagefile.save_answers(path, {"A2": {"answer": "yes"}}, by="me", now=T0)
    assert pagefile.summary(pagefile.load(path))["blocked"] == 1, "C1 is free, B1 still waits on phase A"


def test_done_means_every_item_is_yes_or_accept_risk(path):
    make(path, phased())
    pagefile.save_answers(path, {"A1": {"answer": "yes"}, "A2": {"answer": "risk", "note": "Said so"},
                                 "B1": {"answer": "yes"}, "C1": {"answer": "yes"}}, by="me", now=T0)
    assert pagefile.summary(pagefile.load(path))["approved"] is True


def test_a_sent_accept_risk_settles_like_a_yes(path):
    make(path, phased())
    pagefile.save_answers(path, {"A1": {"answer": "risk", "note": "Said so"}}, by="me", now=T0)
    sent(path, ["A1"])
    pagefile.reply(path, "_page", "ops", "Noted.", now=T2)
    assert pagefile.item_states(pagefile.load(path))["A1"] == {"answer": "risk", "hidden": True, "reopened": None, "round": 1}
