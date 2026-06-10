from session_manager import SessionManager, Message


def test_create_session_increments_ids():
    sm = SessionManager()
    assert sm.create_session() == "session_1"
    assert sm.create_session() == "session_2"


def test_add_exchange_stores_user_then_assistant():
    sm = SessionManager()
    sid = sm.create_session()
    sm.add_exchange(sid, "question", "answer")
    msgs = sm.sessions[sid]
    assert msgs == [
        Message(role="user", content="question"),
        Message(role="assistant", content="answer"),
    ]


def test_history_is_truncated_to_max():
    sm = SessionManager(max_history=2)
    sid = sm.create_session()
    for i in range(5):
        sm.add_exchange(sid, f"q{i}", f"a{i}")
    msgs = sm.sessions[sid]
    assert len(msgs) == 4
    assert msgs[0].content == "q3"


def test_get_history_formats_roles():
    sm = SessionManager()
    sid = sm.create_session()
    sm.add_exchange(sid, "hello", "hi there")
    assert sm.get_conversation_history(sid) == "User: hello\nAssistant: hi there"


def test_get_history_none_for_unknown_session():
    sm = SessionManager()
    assert sm.get_conversation_history("nope") is None
