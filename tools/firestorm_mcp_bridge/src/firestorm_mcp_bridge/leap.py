"""Minimal client for Firestorm's LLSD Event API Plugin (LEAP) protocol."""

from __future__ import annotations

import base64
import datetime as dt
import logging
import queue
import threading
import uuid
from collections.abc import Mapping
from typing import Any, BinaryIO

import llsd

LOGGER = logging.getLogger(__name__)

MAX_PREFIX_BYTES = 20
MAX_PACKET_BYTES = 32 * 1024 * 1024


class LeapError(RuntimeError):
    """Base exception for LEAP transport and viewer API errors."""


class LeapDisconnected(LeapError):
    """Raised when the viewer closes the LEAP connection."""


class LeapProtocolError(LeapError):
    """Raised for an invalid length-prefixed LLSD packet."""


class LeapTimeout(LeapError):
    """Raised when Firestorm does not reply before an operation timeout."""


def read_framed_llsd(stream: BinaryIO, *, max_packet_bytes: int = MAX_PACKET_BYTES) -> Any:
    """Read one ``length:LLSD`` packet from a binary stream."""

    prefix = bytearray()
    while True:
        byte = stream.read(1)
        if not byte:
            if not prefix:
                raise LeapDisconnected("Firestorm closed the LEAP input stream")
            raise LeapProtocolError("LEAP input ended in the packet length prefix")
        if byte == b":":
            break
        if not byte.isdigit():
            raise LeapProtocolError(f"LEAP packet length contained {byte!r}")
        prefix.extend(byte)
        if len(prefix) > MAX_PREFIX_BYTES:
            raise LeapProtocolError("LEAP packet length prefix is too long")

    if not prefix:
        raise LeapProtocolError("LEAP packet length prefix is empty")

    length = int(prefix)
    if length < 0 or length > max_packet_bytes:
        raise LeapProtocolError(
            f"LEAP packet size {length} exceeds the {max_packet_bytes}-byte limit"
        )

    payload = bytearray()
    while len(payload) < length:
        chunk = stream.read(length - len(payload))
        if not chunk:
            raise LeapProtocolError(
                f"LEAP input ended after {len(payload)} of {length} payload bytes"
            )
        payload.extend(chunk)

    try:
        return llsd.parse(bytes(payload))
    except Exception as exc:  # llsd exposes different parse errors by serializer
        raise LeapProtocolError("LEAP payload was not valid LLSD") from exc


def write_framed_llsd(stream: BinaryIO, packet: Any, *, binary: bool = False) -> None:
    """Write one Firestorm-compatible framed LLSD packet and flush it."""

    encoded = llsd.format_binary(packet) if binary else llsd.format_notation(packet)
    if isinstance(encoded, str):
        encoded = encoded.encode("utf-8")
    stream.write(str(len(encoded)).encode("ascii") + b":" + encoded)
    stream.flush()


def to_jsonable(value: Any) -> Any:
    """Convert LLSD Python values into JSON-safe values for MCP results."""

    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii")}
    return value


class LeapConnection:
    """Thread-safe request/reply access to a viewer-owned LEAP connection."""

    def __init__(
        self,
        input_stream: BinaryIO,
        output_stream: BinaryIO,
        initial_packet: Mapping[str, Any],
    ) -> None:
        self._input = input_stream
        self._output = output_stream
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[str, queue.Queue[Any]] = {}
        self._closed = threading.Event()
        self._disconnect_reason = ""

        try:
            self.reply_pump = str(initial_packet["pump"])
            initial_data = initial_packet["data"]
            self.command_pump = str(initial_data["command"])
            self.features = to_jsonable(initial_data.get("features", {}))
        except (KeyError, TypeError) as exc:
            raise LeapProtocolError(
                "Initial LEAP packet did not contain pump/data/command"
            ) from exc

        self._reader = threading.Thread(
            target=self._reader_loop,
            name="firestorm-leap-reader",
            daemon=True,
        )
        self._reader.start()

    @classmethod
    def accept(cls, input_stream: BinaryIO, output_stream: BinaryIO) -> "LeapConnection":
        """Wait for Firestorm's initial handshake and start reading replies."""

        initial = read_framed_llsd(input_stream)
        if not isinstance(initial, Mapping):
            raise LeapProtocolError("Initial LEAP packet was not an LLSD map")
        return cls(input_stream, output_stream, initial)

    @property
    def connected(self) -> bool:
        return not self._closed.is_set()

    @property
    def disconnect_reason(self) -> str:
        return self._disconnect_reason

    def wait_closed(self, timeout: float | None = None) -> bool:
        return self._closed.wait(timeout)

    def request(
        self,
        pump: str,
        data: Mapping[str, Any],
        *,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Send a request and wait for the reply carrying the same ``reqid``."""

        if self._closed.is_set():
            raise LeapDisconnected(self._disconnect_reason or "LEAP connection is closed")

        reqid = uuid.uuid4().hex
        response_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[reqid] = response_queue

        request_data = dict(data)
        request_data["reply"] = self.reply_pump
        request_data["reqid"] = reqid

        try:
            self._send(pump, request_data)
            try:
                response = response_queue.get(timeout=timeout)
            except queue.Empty as exc:
                raise LeapTimeout(
                    f"Firestorm did not reply to {pump}/{data.get('op')} within {timeout:g}s"
                ) from exc
        finally:
            with self._pending_lock:
                self._pending.pop(reqid, None)

        if isinstance(response, BaseException):
            raise response
        if not isinstance(response, Mapping):
            raise LeapProtocolError("LEAP reply data was not an LLSD map")

        result = to_jsonable(response)
        error = result.get("error")
        if error:
            raise LeapError(str(error))
        result.pop("reqid", None)
        return result

    def notify(self, pump: str, data: Mapping[str, Any]) -> None:
        """Send an operation that has no viewer reply, such as ``requestTouch``."""

        if self._closed.is_set():
            raise LeapDisconnected(self._disconnect_reason or "LEAP connection is closed")
        self._send(pump, dict(data))

    def discover_apis(self, *, timeout: float = 15.0) -> dict[str, Any]:
        return self.request(self.command_pump, {"op": "getAPIs"}, timeout=timeout)

    def get_api(self, api: str, *, timeout: float = 15.0) -> dict[str, Any]:
        return self.request(
            self.command_pump,
            {"op": "getAPI", "api": api},
            timeout=timeout,
        )

    def _send(self, pump: str, data: Mapping[str, Any]) -> None:
        packet = {"pump": pump, "data": dict(data)}
        try:
            with self._write_lock:
                write_framed_llsd(self._output, packet)
        except Exception as exc:
            self._mark_closed(f"Could not write to Firestorm: {exc}")
            raise LeapDisconnected(self._disconnect_reason) from exc

    def _reader_loop(self) -> None:
        try:
            while True:
                packet = read_framed_llsd(self._input)
                if not isinstance(packet, Mapping):
                    raise LeapProtocolError("LEAP packet was not an LLSD map")
                data = packet.get("data")
                if not isinstance(data, Mapping):
                    LOGGER.warning("Ignoring LEAP packet without map data: %r", packet)
                    continue
                reqid = data.get("reqid")
                if reqid is None:
                    LOGGER.debug("Ignoring unsolicited LEAP event on %s", packet.get("pump"))
                    continue
                with self._pending_lock:
                    waiter = self._pending.get(str(reqid))
                if waiter is not None:
                    waiter.put(dict(data))
                else:
                    LOGGER.debug("Ignoring late or unknown LEAP reply %s", reqid)
        except LeapDisconnected as exc:
            self._mark_closed(str(exc))
        except Exception as exc:
            LOGGER.exception("LEAP reader stopped")
            self._mark_closed(str(exc))

    def _mark_closed(self, reason: str) -> None:
        if self._closed.is_set():
            return
        self._disconnect_reason = reason
        self._closed.set()
        error = LeapDisconnected(reason)
        with self._pending_lock:
            waiters = list(self._pending.values())
        for waiter in waiters:
            try:
                waiter.put_nowait(error)
            except queue.Full:
                pass
