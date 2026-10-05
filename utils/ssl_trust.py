"""Подключение системного хранилища сертификатов для HTTPS (requests/ssl)."""

from __future__ import annotations


def use_system_certificates() -> None:
    """Доверять сертификатам из хранилища ОС (Windows и др.) через truststore.

    Вызывать до импортов, которые поднимают requests/ssl-клиенты.
    Проверку сертификатов не отключает.
    """
    import truststore

    truststore.inject_into_ssl()
