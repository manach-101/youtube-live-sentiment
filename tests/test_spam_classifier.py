from src.classification.spam_classifier import classify_spam


def test_spam_classifier_flags_suspicious_message():
    message = {
        "duplicate_text_count": 4,
        "repeated_character_ratio": 0.18,
        "seconds_since_previous_message": 8.5,
    }

    result = classify_spam(message)

    assert result["spam_score"] == 1.0
    assert result["is_spam"] is True


def test_spam_classifier_keeps_normal_message():
    message = {
        "duplicate_text_count": 1,
        "repeated_character_ratio": 0.0,
        "seconds_since_previous_message": None,
    }

    result = classify_spam(message)

    assert result["spam_score"] == 0.0
    assert result["is_spam"] is False