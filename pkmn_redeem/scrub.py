class Scrubber:
    def __init__(self) -> None:
        self._secrets: list[str] = []

    def add_secret(self, value: str) -> None:
        # Minimum length guard: scrub() is a naive substring replace, so a short value
        # (a stray line in the codes file, a two-letter screen name) would shred unrelated
        # text everywhere it happened to appear. 6 is comfortably under a real code's ~13
        # chars and under any realistic password, while ruling out short stray tokens.
        if value and len(value) >= 6:
            self._secrets.append(value)

    def scrub(self, text) -> str:
        if not isinstance(text, str):
            text = str(text)
        for secret in self._secrets:
            text = text.replace(secret, "[REDACTED]")
        return text
