import logging
from typing import Any, Optional, Callable, Awaitable
from collections.abc import Sequence
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed
import socket
import asyncio
import contextlib

from samsung_mdc import MDC
from samsung_mdc.exceptions import (
    MDCTimeoutError,
    MDCResponseError,
    NAKError,
    MDCReadTimeoutError,
)
from samsung_mdc.commands import MODEL_NAME, POWER, INPUT_SOURCE, MUTE, BRIGHTNESS

_LOGGER = logging.getLogger(__name__)

RETRYABLE_ERRORS = (
    asyncio.TimeoutError,
    MDCTimeoutError,
    MDCResponseError,
    MDCReadTimeoutError,
    OSError,
    socket.error,
)

try:
    from asyncio import timeout as async_timeout_ctx
except ImportError:  # HA on older Python
    import async_timeout  # type: ignore

    async_timeout_ctx = async_timeout.timeout  # type: ignore


class MdcApi:
    """Thin, low-level API wrapper—no retries/backoff here."""

    def __init__(self, host: str, display_id: int) -> None:
        self._host = host
        self._display_id = display_id
        self._client: MDC = MDC(self._host)
        self._connect_lock = asyncio.Lock()
        self._read_lock = asyncio.Lock()  # Protect against concurrent socket reads
        self._connected = False
        # cached static info (only valid when panel is ON)
        self._model: str | None = None
        self._sw_version: str | None = None

    @property
    def host(self) -> str:
        """Return the display IP address."""
        return self._host

    @property
    def display_id(self) -> int:
        """Return the display ID."""
        return self._display_id

    @property
    def model(self) -> Optional[str]:
        """Return the last known model name (None if unknown)."""
        return self._model

    @property
    def sw_version(self) -> Optional[str]:
        """Return the last known SW version (None if unknown)."""
        return self._sw_version

    async def async_connect(self, *, timeout: float = 10.0) -> None:
        """Connect to the MDC display with timeout."""
        if self._connected:
            return
        async with self._connect_lock:
            if self._connected:
                return
            try:
                async with async_timeout_ctx(timeout):
                    await self._client.open()
                self._connected = True
            except RETRYABLE_ERRORS as err:
                raise ConfigEntryNotReady(
                    f"Failed to connect to MDC display: {err}"
                ) from err

    async def _ensure_client(self) -> MDC:
        await self.async_connect()
        return self._client

    async def async_close(self) -> None:
        """Close the MDC client connection."""
        async with self._connect_lock:
            with contextlib.suppress(Exception):
                await self._client.close()
            self._connected = False

    async def _call(
        self, op: Callable[[], Awaitable[Any]], *, timeout: float = 10.0
    ) -> Any:
        """Run an MDC coroutine with a timeout; on transport errors, close so next call reconnects."""
        async with self._read_lock:  # Prevent concurrent socket operations
            try:
                async with async_timeout_ctx(timeout):
                    return await op()
            except NAKError:
                # NAK received; do not close connection
                raise
            except RETRYABLE_ERRORS:
                # transport likely broken; close so the next call re-opens
                await self.async_close()
                raise

    async def async_refresh_static_info(self, *, timeout: float = 10.0) -> None:
        """Try to refresh model/SW version (only works when panel is ON)."""
        client = await self._ensure_client()
        model = await self._call(
            lambda: client.model_name(self._display_id), timeout=timeout
        )
        self._model = model

        try:
            sw = await self._call(
                lambda: client.software_version(self._display_id), timeout=timeout
            )
            self._sw_version = sw
        except Exception as e:
            _LOGGER.debug("Software version not available (likely panel off): %s", e)

    async def async_status(self, *, timeout: float = 10.0) -> dict[str, Any]:
        """Return normalized status used by entities/coordinator."""
        client = await self._ensure_client()

        status = await self._call(
            lambda: client.status(self._display_id), timeout=timeout
        )
        power, volume, muted, input_source, *_ = status

        # Only try static info when powered on; otherwise keep last known values
        if power:
            await self.async_refresh_static_info(timeout=timeout)

        brightness, *_ = (
            await self._call(
                lambda: client.manual_lamp(self._display_id), timeout=timeout
            )
            if power
            else (None,)
        )

        return {
            "power": power,
            "input": input_source,
            "volume": volume,
            "muted": muted,
            "brightness": brightness,
            "model": self._model or "Unknown",
            "sw_version": self._sw_version or "Unknown",
        }

    async def async_command(
        self, *, fn: str, args: Sequence[Any] | None = None, timeout: float = 10.0
    ) -> Any:
        """Run a specific MDC command on the display (no retries here)."""
        if args is None:
            args = []
        client = await self._ensure_client()
        method = getattr(client, fn)
        return await self._call(
            lambda: method(display_id=self._display_id, data=args), timeout=timeout
        )
