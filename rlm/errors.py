"""Public errors. CLI maps these to exit codes 2, 3, and 4."""


class RLMError(Exception):
    """Base error for the RLM runtime."""


class PromptBudgetError(RLMError):
    """Parent hist would be 100k tokens or more (or over the configured cap). Exit 2."""


class InstructionBudgetError(RLMError):
    """Composed instruction count exceeds 150 (or the configured cap). Exit 4."""


class BudgetExhaustedError(RLMError):
    """USD, wall-clock, or iteration budget exhausted. Exit 2."""


class ReplErrorsExhausted(RLMError):
    """Too many consecutive REPL errors or a stall. Exit 3."""


class ConfigError(RLMError):
    """Invalid config file, flags, or constructor kwargs. Exit 4."""


class StartupError(RLMError):
    """Missing API key, Docker not running, or other startup failure. Exit 4."""
