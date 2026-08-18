from app.services.conversation import ConversationStore


def test_expand_query_uses_previous_question() -> None:
    store = ConversationStore()
    store.add("c1", "What is the leave policy?", "According to BMI Hub...")
    expanded = store.expand_query("c1", "How many days can I take?")
    assert "How many days can I take?" in expanded
    assert "leave policy" in expanded.lower()


def test_expand_query_without_history_returns_message() -> None:
    store = ConversationStore()
    assert store.expand_query("missing", "Hello") == "Hello"
