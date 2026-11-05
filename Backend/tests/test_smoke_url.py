from scripts.smoke_chat import chat_url


def test_chat_url_defaults_to_local_and_accepts_site_or_full_address():
    assert chat_url(["smoke"]) == "http://127.0.0.1:8000/chat"
    assert chat_url(["smoke", "https://api.example.app"]) == "https://api.example.app/chat"
    assert chat_url(["smoke", "https://api.example.app/"]) == "https://api.example.app/chat"
    assert chat_url(["smoke", "https://api.example.app/chat"]) == "https://api.example.app/chat"
