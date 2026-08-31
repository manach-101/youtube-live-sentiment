def calculate_spam_score(message: dict) -> float:
    score = 0.0

    duplicate_text_count = message.get("duplicate_text_count", 0)
    repeated_character_ratio = message.get("repeated_character_ratio", 0.0)
    seconds_since_previous = message.get("seconds_since_previous_message")

    if duplicate_text_count >= 3:
        score += 0.4

    if (
        seconds_since_previous is not None
        and seconds_since_previous < 15
    ):
        score += 0.4

    if repeated_character_ratio > 0.10:
        score += 0.2

    return min(score, 1.0)


def classify_spam(message: dict) -> dict:
    classified_message = message.copy()

    spam_score = calculate_spam_score(message)

    classified_message["spam_score"] = round(spam_score, 2)
    classified_message["is_spam"] = spam_score >= 0.7

    return classified_message