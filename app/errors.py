"""Исключения уровня приложения."""


class AppError(Exception):
    """Базовое исключение приложения."""


class ConfigError(AppError):
    """Ошибка в конфигурации."""


class CommandParseError(AppError):
    """Ошибка разбора входной команды."""
