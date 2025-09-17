from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import timedelta
import logging
import random
import time
from typing import Any

from samsung_mdc.commands import POWER
from samsung_mdc.exceptions import MDCResponseError, NAKError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BACKOFF_FACTOR,
    BASE_BACKOFF,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_CMD_CONCURRENCY,
    MAX_POWER_ON_CHECKS,
    MAX_RETRY_ATTEMPTS,
    POWER_ON_CHECK_INTERVAL,
    POWER_ON_EXTERNAL_GRACE,
    POWER_ON_SOCKET_RECONNECT_TIME,
    RETRY_DELAY,
)
from .mdc_api import RETRYABLE_ERRORS, MdcApi

_LOGGER = logging.getLogger(__name__)


class MDCUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Central policy: retries, backoff, polling, and command execution."""

    def __init__(self, hass: HomeAssistant, api: MdcApi, name: str) -> None:
        super().__init__(
            hass,
            _LOGGER,  # HA’s default logger
            name=f"{DOMAIN} - {name}",
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self.hass = hass
        self.api = api
        self._cmd_sem = asyncio.Semaphore(MAX_CMD_CONCURRENCY)
        self._power_operation_lock = asyncio.Lock()

        self._last_power_command: str | None = None
        self._power_command_time = 0.0
        self._power_transition_timeout = 30.0  # seconds to wait for power state change
        self._external_power_on_timeout = 45.0  # longer timeout for external power-on

        self._power_transition_complete = asyncio.Event()
        self._power_transition_complete.set()  # Initially complete

    @property
    def in_power_transition(self) -> bool:
        """Check if we're potentially in a power transition."""
        if not self._last_power_command:
            return False

        # Use extended timeout for external power-on scenarios
        timeout = (
            self._external_power_on_timeout
            if self._last_power_command == "on"
            else self._power_transition_timeout
        )

        return time.monotonic() - self._power_command_time < timeout

    @property
    def effective_power_state(self) -> bool:
        """Return the effective power state (actual or assumed during transition)."""
        data = self.data or {}
        actual_power = data.get("power", False)

        # During power-on transition, assume ON for immediate UI feedback
        if self.in_power_transition and self._last_power_command == "on":
            return True

        return actual_power

    @property
    def actual_power_state(self) -> bool:
        """Return the actual power state from hardware (for debugging/automation)."""
        data = self.data or {}
        return data.get("power", False)

    def _set_power_command(self, power_state: str) -> None:
        """Track the last power command sent."""
        self._last_power_command = power_state
        self._power_command_time = time.monotonic()
        self._power_transition_complete.clear()  # Mark transition as in progress

        # Immediately update entities with new effective state
        if self.data is not None:
            self.async_set_updated_data(self.data)

    def _clear_power_command(self) -> None:
        """Clear power command tracking."""
        self._last_power_command = None
        self._power_command_time = 0.0
        self._power_transition_complete.set()  # Mark transition as complete

    async def _wait_for_power_transition_complete(self, timeout: float = 60.0) -> bool:
        """Wait for power transition to complete or timeout."""
        try:
            await asyncio.wait_for(
                self._power_transition_complete.wait(), timeout=timeout
            )
        except TimeoutError:
            _LOGGER.warning("Power transition timeout after %s seconds", timeout)
            self._clear_power_command()  # Clear on timeout
            return False
        else:
            return True

    async def _retry_with_backoff(
        self, f: Callable[[], Coroutine[Any, Any, Any]]
    ) -> Any:
        delay = BASE_BACKOFF
        last_exception = None
        for attempt in range(MAX_RETRY_ATTEMPTS + 1):
            try:
                return await f()
            except RETRYABLE_ERRORS as exc:
                last_exception = exc
                if attempt >= MAX_RETRY_ATTEMPTS:
                    raise

                jitter = random.uniform(0, delay * 0.25)
                await asyncio.sleep(delay + jitter)
                delay *= BACKOFF_FACTOR

                _LOGGER.debug(
                    "Retrying operation after %s, attempt %d/%d",
                    type(exc).__name__,
                    attempt + 2,
                    MAX_RETRY_ATTEMPTS + 1,
                )
        raise last_exception or UpdateFailed("Maximum retries exceeded")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the display with power state transition handling."""
        if self.in_power_transition:
            _LOGGER.debug("Skipping update during power transition")
            return self.data or {}

        prev_data = self.data or {}
        prev_power = prev_data.get("power", False)

        try:
            data = await self._retry_with_backoff(self.api.async_status)
            current_power = data.get("power", False)

            # Detect external power state changes
            if prev_data and prev_power != current_power:
                if current_power:
                    _LOGGER.debug("External power-on detected, entering lenient mode")
                    self._set_power_command("on")  # Track external power-on
                else:
                    _LOGGER.debug("External power-off detected")
                    self._clear_power_command()

            # If we get valid data, clear any power command tracking if state matches
            if self._last_power_command and "power" in data:
                expected_state = self._last_power_command == "on"
                if expected_state == current_power:
                    _LOGGER.debug(
                        "Power state change confirmed: %s", self._last_power_command
                    )
                    self._clear_power_command()
                elif not self.in_power_transition:
                    _LOGGER.warning(
                        "Power state mismatch after timeout. Expected: %s, Got: %s",
                        expected_state,
                        current_power,
                    )
                    self._clear_power_command()
            return data
        except RETRYABLE_ERRORS as err:
            if prev_data and not prev_power:
                _LOGGER.debug(
                    "Communication error after display was off - possible external power-on, being lenient"
                )
                # Assume external power-on and be lenient for boot-up period
                self._set_power_command("on")
                return prev_data

            if self.in_power_transition and prev_data:
                _LOGGER.debug(
                    "Communication error during power transition - assuming display is still transitioning"
                )
                return prev_data
            await self.api.async_close()  # Force reconnect on next command
            raise UpdateFailed(f"Failed to communicate with display: {err}") from err
        except (MDCResponseError, NAKError) as err:
            await self.api.async_close()  # Force reconnect on next command
            raise UpdateFailed(f"Failed to communicate with display: {err}") from err

    async def async_execute(
        self, fn: str, args: list[Any], wait_for_power: bool = True
    ) -> Any:
        """Execute a command, waiting for power-on completion if in progress."""
        async with self._cmd_sem:
            # Wait for any ongoing power transition to complete before sending commands
            if wait_for_power and self.in_power_transition:
                _LOGGER.debug(
                    "Waiting for power transition to complete before executing %s", fn
                )
                await self._wait_for_power_transition_complete()

            result = await self.api.async_command(fn=fn, args=args)
            if not self.in_power_transition:
                await self.async_request_refresh()
            return result

    # ---------- Samsung-spec Power Sequence ----------
    async def _send_power_command(self, power_state: POWER.POWER_STATE) -> None:
        """Send a power command with retries."""
        last_exc = None
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                await self.api.async_command(fn="power", args=[power_state])
                _LOGGER.debug("Power command sent successfully")
                return

            except NAKError as exc:
                last_exc = exc
                _LOGGER.info(
                    "Power NAK response, attempt %d/%d",
                    attempt + 1,
                    MAX_RETRY_ATTEMPTS,
                )
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_DELAY)

            except RETRYABLE_ERRORS as exc:
                last_exc = exc
                _LOGGER.warning(
                    "Power connection error, attempt %d/%d: %s",
                    attempt + 1,
                    MAX_RETRY_ATTEMPTS,
                    type(exc).__name__,
                )
                await self.api.async_close()  # Force reconnection
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_DELAY)

        raise UpdateFailed(
            f"Power failed after {MAX_RETRY_ATTEMPTS} attempts: {last_exc}"
        )

    async def _wait_for_responsive_display(self) -> None:
        for _attempt in range(MAX_POWER_ON_CHECKS):
            try:
                data = await self._retry_with_backoff(self.api.async_status)
            except RETRYABLE_ERRORS:
                # still warming up; short wait and retry
                await asyncio.sleep(POWER_ON_CHECK_INTERVAL)
            else:
                _LOGGER.debug(
                    "Power-on warm-up check: display is responsive after %d seconds",
                    POWER_ON_SOCKET_RECONNECT_TIME
                    + (_attempt + 1) * POWER_ON_CHECK_INTERVAL,
                )
                self._clear_power_command()  # Clear power command tracking
                self.async_set_updated_data(data)
                return
        _LOGGER.warning("Display not responsive after power-on warm-up")

    async def async_power_on(self) -> None:
        """Send POWER ON with Samsung's NAK/connection retry rules, then warm-up checks."""
        async with self._power_operation_lock:
            self._set_power_command("on")
            await self._send_power_command(POWER.POWER_STATE.ON)

            await self.api.async_close()  # Force socket reconnect
            _LOGGER.debug(
                "Waiting %ds for display boot-up", POWER_ON_SOCKET_RECONNECT_TIME
            )
            await asyncio.sleep(POWER_ON_SOCKET_RECONNECT_TIME)
            await self._wait_for_responsive_display()

    async def async_power_off(self) -> None:
        """Send POWER OFF."""

        async with self._power_operation_lock:
            try:
                # self._set_power_command("off")
                await self._send_power_command(POWER.POWER_STATE.OFF)
                await asyncio.sleep(1)  # brief pause before checking status
                await self.async_request_refresh()
            except RETRYABLE_ERRORS:
                _LOGGER.error("Power-off failed after retries")
                raise
            except Exception:
                self._clear_power_command()
                raise
