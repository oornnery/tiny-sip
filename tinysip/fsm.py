import asyncio
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from rich.panel import Panel

from tinysip.auth import SIPDigestAuthentication
from tinysip.logging_utils import get_logger
from tinysip.message import SIPMessage, SIPMethod

# Logger global para este módulo
logger = get_logger(__name__)

# ======================= FSM STATES E ENUMS =======================


class TxState(Enum):
    """Estados das transações conforme RFC 3261"""

    INITIAL = "INITIAL"
    TRYING = "TRYING"
    PROCEEDING = "PROCEEDING"
    COMPLETED = "COMPLETED"
    ACCEPTED = "ACCEPTED"  # Para INVITE 2xx (RFC 6026)
    CONFIRMED = "CONFIRMED"  # Para servidor após ACK
    TERMINATED = "TERMINATED"


class DialogState(Enum):
    """Estados do diálogo SIP"""

    INITIAL = "INITIAL"
    EARLY = "EARLY"  # Após 1xx com To tag
    CONFIRMED = "CONFIRMED"  # Após 2xx
    TERMINATED = "TERMINATED"


class TxKind(Enum):
    """Tipos de transação"""

    INVITE_CLIENT = "INVITE_CLIENT"
    INVITE_SERVER = "INVITE_SERVER"
    NON_INVITE_CLIENT = "NON_INVITE_CLIENT"
    NON_INVITE_SERVER = "NON_INVITE_SERVER"


# SIPMethod já importado de message.py


class TimerType(Enum):
    """Tipos de timers SIP"""

    # Non-INVITE timers
    TIMER_E = "TIMER_E"  # Retransmissão
    TIMER_F = "TIMER_F"  # Timeout
    TIMER_K = "TIMER_K"  # Cleanup

    # INVITE timers
    TIMER_A = "TIMER_A"  # Retransmissão INVITE
    TIMER_B = "TIMER_B"  # Timeout INVITE
    TIMER_D = "TIMER_D"  # Cleanup INVITE
    TIMER_G = "TIMER_G"  # Retransmissão resposta final
    TIMER_H = "TIMER_H"  # Timeout resposta final
    TIMER_I = "TIMER_I"  # Cleanup servidor INVITE

    # Additional timers
    TIMER_J = "TIMER_J"  # Cleanup servidor Non-INVITE
    TIMER_L = "TIMER_L"  # ACCEPTED state timeout
    TIMER_M = "TIMER_M"  # ACCEPTED retransmission


# ======================= TIMER CONFIGURATION =======================


@dataclass(frozen=True)
class SIPTimers:
    """Configuração de timers SIP conforme RFC 3261"""

    T1: float = 0.5  # RTT estimate
    T2: float = 4.0  # Maximum retransmit interval
    T4: float = 5.0  # Maximum duration a message remains in network

    # Calculated timers
    @property
    def TIMER_A(self) -> float:
        return self.T1  # INVITE retransmission

    @property
    def TIMER_B(self) -> float:
        return 64 * self.T1  # INVITE timeout

    @property
    def TIMER_D(self) -> float:
        return 32.0  # INVITE cleanup (UDP) / 0 (TCP)

    @property
    def TIMER_E(self) -> float:
        return self.T1  # Non-INVITE retransmission

    @property
    def TIMER_F(self) -> float:
        return 64 * self.T1  # Non-INVITE timeout

    @property
    def TIMER_G(self) -> float:
        return self.T1  # Response retransmission

    @property
    def TIMER_H(self) -> float:
        return 64 * self.T1  # Response timeout

    @property
    def TIMER_I(self) -> float:
        return self.T4  # Server INVITE cleanup

    @property
    def TIMER_J(self) -> float:
        return 64 * self.T1  # Server Non-INVITE cleanup

    @property
    def TIMER_K(self) -> float:
        return self.T4  # Client cleanup

    @property
    def TIMER_L(self) -> float:
        return 64 * self.T1  # ACCEPTED state timeout

    @property
    def TIMER_M(self) -> float:
        return 64 * self.T1  # ACCEPTED retransmission


# ======================= CALLBACK PROTOCOLS =======================


class TransactionCallbacks(Protocol):
    """Callbacks para eventos de transação"""

    async def on_provisional_response(self, tx_id: str, response: SIPMessage) -> None: ...
    async def on_final_response(self, tx_id: str, response: SIPMessage) -> None: ...
    async def on_request_received(self, tx_id: str, request: SIPMessage) -> None: ...
    async def on_timeout(self, tx_id: str, timer_type: TimerType) -> None: ...
    async def on_transport_error(self, tx_id: str, error: Exception) -> None: ...
    async def on_terminated(self, tx_id: str) -> None: ...


class DialogCallbacks(Protocol):
    """Callbacks para eventos de diálogo"""

    async def on_dialog_created(self, dialog_id: str) -> None: ...
    async def on_dialog_confirmed(self, dialog_id: str) -> None: ...
    async def on_dialog_terminated(self, dialog_id: str, reason: str) -> None: ...
    async def on_in_dialog_request(self, dialog_id: str, request: SIPMessage) -> None: ...


class TransportCallbacks(Protocol):
    """Interface para camada de transporte"""

    async def send_message(self, message: str, destination: tuple[str, int]) -> None: ...


# ======================= TRANSACTION CLASSES =======================


class SIPTransaction(ABC):
    """Classe base para transações SIP"""

    def __init__(
        self,
        tx_id: str,
        kind: TxKind,
        callbacks: TransactionCallbacks,
        transport: TransportCallbacks,
        timers: SIPTimers | None = None,
    ):
        self.tx_id = tx_id
        self.kind = kind
        self.state = TxState.INITIAL
        self.callbacks = callbacks
        self.transport = transport
        self.timers = timers or SIPTimers()
        self.timers = timers

        # Message storage
        self.request: SIPMessage | None = None
        self.response: SIPMessage | None = None

        # Timer management
        self._active_timers: dict[TimerType, asyncio.Task] = {}
        self._terminated_event = asyncio.Event()

        # Retry counting
        self._retransmission_count = 0
        self._max_retransmissions = 7

        self._logger = logging.getLogger(f"Transaction.{tx_id}")

        # Rich logging para criação da transação
        method = "Unknown"  # será definido quando start() for chamado
        content = (
            f"🚀 Transaction ID: {tx_id}\n📋 Method: {method}\n🔄 Initial State: {self.state.value}"
        )
        panel = Panel(
            content,
            title="[bold green]Transaction Started",
            border_style="green",
        )
        logger.info(panel)

    @abstractmethod
    async def start(self, message: SIPMessage) -> None:
        """Inicia a transação"""
        pass

    @abstractmethod
    async def process_message(self, message: SIPMessage) -> None:
        """Processa mensagem recebida"""
        pass

    def _transition_to(self, new_state: TxState) -> None:
        """Transição de estado com logging"""
        old_state = self.state
        self.state = new_state
        self._logger.debug(f"State transition: {old_state.value} -> {new_state.value}")

        # Rich logging para mudanças de estado
        content = (
            f"🔄 Transaction ID: {self.tx_id}\n📤 From: {old_state.value}\n📥 To: {new_state.value}"
        )
        panel = Panel(
            content,
            title="[bold blue]State Transition",
            border_style="blue",
        )
        logger.info(panel)

        if new_state == TxState.TERMINATED:
            self._terminated_event.set()
            asyncio.create_task(self._cleanup())

    async def _start_timer(self, timer_type: TimerType, duration: float) -> None:
        """Inicia um timer"""
        if timer_type in self._active_timers:
            self._active_timers[timer_type].cancel()

        async def timer_handler():
            try:
                await asyncio.sleep(duration)
                await self._on_timer_fired(timer_type)
            except asyncio.CancelledError:
                pass

        self._active_timers[timer_type] = asyncio.create_task(timer_handler())
        self._logger.debug(f"Timer {timer_type.value} started for {duration}s")

    async def _cancel_timer(self, timer_type: TimerType) -> None:
        """Cancela um timer"""
        if timer_type in self._active_timers:
            self._active_timers[timer_type].cancel()
            del self._active_timers[timer_type]
            self._logger.debug(f"Timer {timer_type.value} cancelled")

    async def _on_timer_fired(self, timer_type: TimerType) -> None:
        """Handler para timer expirado"""
        self._logger.debug(f"Timer {timer_type.value} fired")

        # Rich logging para timeouts
        content = f"⏰ Transaction ID: {self.tx_id}\n⚠️ Timeout Type: {timer_type.value}"
        panel = Panel(
            content,
            title="[bold red]Transaction Timeout",
            border_style="red",
        )
        logger.info(panel)

        await self.callbacks.on_timeout(self.tx_id, timer_type)

        # Handle specific timer logic
        if timer_type in [TimerType.TIMER_B, TimerType.TIMER_F]:
            # Transaction timeout
            self._transition_to(TxState.TERMINATED)
        elif timer_type in [
            TimerType.TIMER_D,
            TimerType.TIMER_I,
            TimerType.TIMER_J,
            TimerType.TIMER_K,
        ]:
            # Cleanup timeout
            self._transition_to(TxState.TERMINATED)
        elif timer_type in [TimerType.TIMER_A, TimerType.TIMER_E, TimerType.TIMER_G]:
            # Retransmission timeout
            await self._handle_retransmission(timer_type)

    async def _handle_retransmission(self, timer_type: TimerType) -> None:
        """Trata retransmissões"""
        if self._retransmission_count >= self._max_retransmissions:
            self._logger.warning("Maximum retransmissions reached")
            self._transition_to(TxState.TERMINATED)
            return

        self._retransmission_count += 1

        # Retransmit message
        if self.kind in [TxKind.INVITE_CLIENT, TxKind.NON_INVITE_CLIENT] and self.request:
            await self._send_request()
        elif self.kind in [TxKind.INVITE_SERVER, TxKind.NON_INVITE_SERVER] and self.response:
            await self._send_response()

        # Restart timer with exponential backoff
        next_interval = min(self.timers.T2, (2**self._retransmission_count) * self.timers.T1)
        await self._start_timer(timer_type, next_interval)

    async def _send_request(self) -> None:
        """Envia requisição"""
        if not self.request:
            return

        # Convert to raw message
        raw_message = self._serialize_request(self.request)

        # Extract destination from Via or Request-URI
        destination = self._extract_destination(self.request)

        try:
            await self.transport.send_message(raw_message, destination)
            self._logger.debug(f"Sent request: {self.request.method.value}")
        except Exception as e:
            await self.callbacks.on_transport_error(self.tx_id, e)

    async def _send_response(self) -> None:
        """Envia resposta"""
        if not self.response:
            return

        # Convert to raw message
        raw_message = self._serialize_response(self.response)

        # Extract destination from Via
        destination = self._extract_response_destination(self.response)

        try:
            await self.transport.send_message(raw_message, destination)
            self._logger.debug(f"Sent response: {self.response.status_code}")
        except Exception as e:
            await self.callbacks.on_transport_error(self.tx_id, e)

    def _serialize_request(self, request: SIPMessage) -> str:
        """Converte SIPMessage request para string raw"""
        return str(request)

    def _serialize_response(self, response: SIPMessage) -> str:
        """Converte SIPMessage response para string raw"""
        return str(response)

    def _extract_destination(self, request: SIPMessage) -> tuple[str, int]:
        """Extrai destino da requisição"""
        # Use Via header for destination
        via_value = request.get_header("via")
        if via_value:
            # Parse Via: SIP/2.0/UDP host:port
            match = re.search(r"SIP/2\.0/\w+\s+([^;:\s]+)(?::(\d+))?", via_value)
            if match:
                host = match.group(1)
                port = int(match.group(2)) if match.group(2) else 5060
                return (host, port)

        # Fallback to Request-URI
        if request.uri:
            return (request.uri.host, request.uri.port or 5060)

        return ("127.0.0.1", 5060)

    def _extract_response_destination(self, response: SIPMessage) -> tuple[str, int]:
        """Extrai destino da resposta (Via received/rport)"""
        # Extract from Via header with received/rport parameters
        via_value = response.get_header("via")
        if via_value:
            # This is simplified - full implementation would parse Via parameters
            match = re.search(r"SIP/2\.0/\w+\s+([^;:\s]+)(?::(\d+))?", via_value)
            if match:
                host = match.group(1)
                port = int(match.group(2)) if match.group(2) else 5060
                return (host, port)

        return ("127.0.0.1", 5060)  # Fallback

    async def _cleanup(self) -> None:
        """Cleanup da transação"""
        # Cancel all active timers
        for timer_task in self._active_timers.values():
            timer_task.cancel()
        self._active_timers.clear()

        await self.callbacks.on_terminated(self.tx_id)
        self._logger.debug("Transaction terminated and cleaned up")

    async def wait_for_termination(self) -> None:
        """Aguarda término da transação"""
        await self._terminated_event.wait()


class InviteClientTransaction(SIPTransaction):
    """Transação INVITE do cliente"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = TxKind.INVITE_CLIENT

    async def start(self, request: SIPMessage) -> None:
        """Inicia transação INVITE cliente"""
        self.request = request
        self._transition_to(TxState.TRYING)

        # Send initial INVITE
        await self._send_request()

        # Start Timer A (retransmission) and Timer B (timeout)
        await self._start_timer(TimerType.TIMER_A, self.timers.TIMER_A)
        await self._start_timer(TimerType.TIMER_B, self.timers.TIMER_B)

    async def process_message(self, response: SIPMessage) -> None:
        """Processa resposta INVITE"""
        status_code = response.status_code
        if status_code is None:
            return

        if self.state == TxState.TRYING:
            if 100 <= status_code <= 199:
                # Provisional response
                self._transition_to(TxState.PROCEEDING)
                await self._cancel_timer(TimerType.TIMER_A)  # Stop retransmissions
                await self.callbacks.on_provisional_response(self.tx_id, response)

            elif 200 <= status_code <= 299:
                # 2xx success response
                self._transition_to(TxState.ACCEPTED)
                await self._cancel_timer(TimerType.TIMER_A)
                await self._cancel_timer(TimerType.TIMER_B)
                await self.callbacks.on_final_response(self.tx_id, response)

                # Start Timer L for ACCEPTED state
                await self._start_timer(TimerType.TIMER_L, self.timers.TIMER_L)

            elif status_code >= 300:
                # Final error response
                self._transition_to(TxState.COMPLETED)
                await self._cancel_timer(TimerType.TIMER_A)
                await self._cancel_timer(TimerType.TIMER_B)
                await self.callbacks.on_final_response(self.tx_id, response)

                # Start Timer D for cleanup
                await self._start_timer(TimerType.TIMER_D, self.timers.TIMER_D)

        elif self.state == TxState.PROCEEDING:
            if 200 <= status_code <= 299:
                # 2xx success response
                self._transition_to(TxState.ACCEPTED)
                await self.callbacks.on_final_response(self.tx_id, response)
                await self._start_timer(TimerType.TIMER_L, self.timers.TIMER_L)

            elif status_code >= 300:
                # Final error response
                self._transition_to(TxState.COMPLETED)
                await self.callbacks.on_final_response(self.tx_id, response)
                await self._start_timer(TimerType.TIMER_D, self.timers.TIMER_D)

            else:
                # Additional provisional response
                await self.callbacks.on_provisional_response(self.tx_id, response)


class NonInviteClientTransaction(SIPTransaction):
    """Transação Non-INVITE do cliente"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = TxKind.NON_INVITE_CLIENT

    async def start(self, request: SIPMessage) -> None:
        """Inicia transação Non-INVITE cliente"""
        self.request = request
        self._transition_to(TxState.TRYING)

        # Send initial request
        await self._send_request()

        # Start Timer E (retransmission) and Timer F (timeout)
        await self._start_timer(TimerType.TIMER_E, self.timers.TIMER_E)
        await self._start_timer(TimerType.TIMER_F, self.timers.TIMER_F)

    async def process_message(self, response: SIPMessage) -> None:
        """Processa resposta Non-INVITE"""
        status_code = response.status_code
        if status_code is None:
            return

        if self.state == TxState.TRYING:
            if 100 <= status_code <= 199:
                # Provisional response
                self._transition_to(TxState.PROCEEDING)
                await self._cancel_timer(TimerType.TIMER_E)  # Stop retransmissions
                await self.callbacks.on_provisional_response(self.tx_id, response)

            elif status_code >= 200:
                # Final response - para não-INVITE, sempre vai direto para TERMINATED
                self._transition_to(TxState.TERMINATED)
                await self._cancel_timer(TimerType.TIMER_E)
                await self._cancel_timer(TimerType.TIMER_F)
                await self.callbacks.on_final_response(self.tx_id, response)

        elif self.state == TxState.PROCEEDING:
            if status_code >= 200:
                # Final response - para não-INVITE, sempre vai direto para TERMINATED
                self._transition_to(TxState.TERMINATED)
                await self.callbacks.on_final_response(self.tx_id, response)
            else:
                # Additional provisional response
                await self.callbacks.on_provisional_response(self.tx_id, response)


class InviteServerTransaction(SIPTransaction):
    """Transação INVITE do servidor"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = TxKind.INVITE_SERVER

    async def start(self, request: SIPMessage) -> None:
        """Inicia transação INVITE servidor"""
        self.request = request
        self._transition_to(TxState.PROCEEDING)

        await self.callbacks.on_request_received(self.tx_id, request)

    async def send_provisional_response(self, status_code: int, reason_phrase: str) -> None:
        """Envia resposta provisional"""
        if self.state != TxState.PROCEEDING:
            return

        response = self._create_response(status_code, reason_phrase)
        await self._send_response_internal(response)

    async def send_final_response(
        self, status_code: int, reason_phrase: str, body: str | None = None
    ) -> None:
        """Envia resposta final"""
        if self.state != TxState.PROCEEDING:
            return

        response = self._create_response(status_code, reason_phrase, body)

        if 200 <= status_code <= 299:
            # 2xx response - wait for ACK
            self._transition_to(TxState.ACCEPTED)
            await self._start_timer(TimerType.TIMER_L, self.timers.TIMER_L)
        else:
            # Error response
            self._transition_to(TxState.COMPLETED)
            await self._start_timer(TimerType.TIMER_H, self.timers.TIMER_H)
            await self._start_timer(TimerType.TIMER_G, self.timers.TIMER_G)

        self.response = response
        await self._send_response_internal(response)

    async def process_message(self, message: SIPMessage) -> None:
        """Processa mensagem recebida"""
        if message.is_request:
            method = message.method

            if method == SIPMethod.ACK:
                if self.state == TxState.ACCEPTED:
                    # ACK for 2xx response
                    self._transition_to(TxState.CONFIRMED)
                    await self._cancel_timer(TimerType.TIMER_L)
                    await self._start_timer(TimerType.TIMER_I, self.timers.TIMER_I)

                elif self.state == TxState.COMPLETED:
                    # ACK for error response
                    self._transition_to(TxState.CONFIRMED)
                    await self._cancel_timer(TimerType.TIMER_G)
                    await self._cancel_timer(TimerType.TIMER_H)
                    await self._start_timer(TimerType.TIMER_I, self.timers.TIMER_I)

            elif self.state == TxState.PROCEEDING:
                # Retransmitted INVITE
                if self.response:
                    await self._send_response_internal(self.response)

    def _create_response(
        self, status_code: int, reason_phrase: str, body: str | None = None
    ) -> SIPMessage:
        """Cria resposta baseada na requisição"""
        if not self.request:
            raise ValueError("No request to respond to")

        # Use the new SIPMessage.create_response method with request parameter
        response = SIPMessage.create_response(status_code, reason_phrase, self.request)

        # Add body if provided
        if body:
            response.set_body(body, "application/sdp")

        return response

    async def _send_response_internal(self, response: SIPMessage) -> None:
        """Envia resposta interna"""
        self.response = response
        await self._send_response()


class NonInviteServerTransaction(SIPTransaction):
    """Transação Non-INVITE do servidor"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = TxKind.NON_INVITE_SERVER

    async def start(self, request: SIPMessage) -> None:
        """Inicia transação Non-INVITE servidor"""
        self.request = request
        self._transition_to(TxState.TRYING)

        await self.callbacks.on_request_received(self.tx_id, request)

    async def send_provisional_response(self, status_code: int, reason_phrase: str) -> None:
        """Envia resposta provisional"""
        if self.state != TxState.TRYING:
            return

        self._transition_to(TxState.PROCEEDING)
        response = self._create_response(status_code, reason_phrase)
        await self._send_response_internal(response)

    async def send_final_response(
        self, status_code: int, reason_phrase: str, body: str | None = None
    ) -> None:
        """Envia resposta final"""
        if self.state not in [TxState.TRYING, TxState.PROCEEDING]:
            return

        self._transition_to(TxState.COMPLETED)
        response = self._create_response(status_code, reason_phrase, body)
        self.response = response
        await self._send_response_internal(response)

        # Start Timer J for cleanup
        await self._start_timer(TimerType.TIMER_J, self.timers.TIMER_J)

    async def process_message(self, request: SIPMessage) -> None:
        """Processa requisição retransmitida"""
        if self.state == TxState.COMPLETED and self.response:
            # Retransmit final response
            await self._send_response_internal(self.response)

    def _create_response(
        self, status_code: int, reason_phrase: str, body: str | None = None
    ) -> SIPMessage:
        """Cria resposta baseada na requisição"""
        if not self.request:
            raise ValueError("No request to respond to")

        # Use the new SIPMessage.create_response method with request parameter
        response = SIPMessage.create_response(status_code, reason_phrase, self.request)

        # Add body if provided
        if body:
            response.set_body(body, "application/sdp")

        return response

    async def _send_response_internal(self, response: SIPMessage) -> None:
        """Envia resposta interna"""
        self.response = response
        await self._send_response()


# ======================= DIALOG MANAGEMENT =======================


@dataclass
class SIPDialog:
    """Representa um diálogo SIP"""

    dialog_id: str
    state: DialogState
    local_uri: str
    remote_uri: str
    local_tag: str
    remote_tag: str | None
    call_id: str
    local_cseq: int
    remote_cseq: int | None
    route_set: list[str]
    secure: bool
    created_time: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.remote_tag and self.state == DialogState.INITIAL:
            self.state = DialogState.EARLY


class DialogManager:
    """Gerenciador de diálogos SIP"""

    def __init__(self, callbacks: DialogCallbacks):
        self.callbacks = callbacks
        self._dialogs: dict[str, SIPDialog] = {}
        self._logger = logging.getLogger("DialogManager")

    def create_dialog_from_request(self, request: SIPMessage) -> SIPDialog:
        """Cria diálogo a partir de requisição INVITE"""
        call_id = self._extract_call_id(request)
        from_header = self._extract_from_header(request)
        to_header = self._extract_to_header(request)

        local_tag = self._extract_tag(from_header)
        dialog_id = f"{call_id}-{local_tag}"

        dialog = SIPDialog(
            dialog_id=dialog_id,
            state=DialogState.INITIAL,
            local_uri=from_header.split(";")[0].strip("<>"),
            remote_uri=to_header.split(";")[0].strip("<>"),
            local_tag=local_tag,
            remote_tag=None,
            call_id=call_id,
            local_cseq=self._extract_cseq_number(request),
            remote_cseq=None,
            route_set=[],
            secure=request.uri.scheme == "sips" if request.uri else False,
        )

        self._dialogs[dialog_id] = dialog
        asyncio.create_task(self.callbacks.on_dialog_created(dialog_id))

        return dialog

    def update_dialog_from_response(self, dialog_id: str, response: SIPMessage) -> SIPDialog | None:
        """Atualiza diálogo com resposta"""
        dialog = self._dialogs.get(dialog_id)
        if not dialog:
            return None

        status_code = response.status_code
        if status_code is None:
            return None
        to_header = self._extract_to_header_from_response(response)

        if 100 <= status_code <= 199:
            # Provisional response
            remote_tag = self._extract_tag(to_header)
            if remote_tag and not dialog.remote_tag:
                dialog.remote_tag = remote_tag
                dialog.state = DialogState.EARLY

        elif 200 <= status_code <= 299:
            # Success response
            remote_tag = self._extract_tag(to_header)
            if remote_tag:
                dialog.remote_tag = remote_tag
                dialog.state = DialogState.CONFIRMED
                asyncio.create_task(self.callbacks.on_dialog_confirmed(dialog_id))

        elif status_code >= 300:
            # Error response - terminate dialog
            dialog.state = DialogState.TERMINATED
            asyncio.create_task(
                self.callbacks.on_dialog_terminated(dialog_id, f"Response {status_code}")
            )

        return dialog

    def get_dialog(self, dialog_id: str) -> SIPDialog | None:
        """Obtém diálogo por ID"""
        return self._dialogs.get(dialog_id)

    def terminate_dialog(self, dialog_id: str, reason: str = "Normal termination") -> None:
        """Termina diálogo"""
        dialog = self._dialogs.get(dialog_id)
        if dialog:
            dialog.state = DialogState.TERMINATED
            asyncio.create_task(self.callbacks.on_dialog_terminated(dialog_id, reason))

    def _extract_call_id(self, request: SIPMessage) -> str:
        """Extrai Call-ID"""
        return request.get_header("call-id") or ""

    def _extract_from_header(self, request: SIPMessage) -> str:
        """Extrai header From"""
        return request.get_header("from") or ""

    def _extract_to_header(self, request: SIPMessage) -> str:
        """Extrai header To"""
        return request.get_header("to") or ""

    def _extract_to_header_from_response(self, response: SIPMessage) -> str:
        """Extrai header To da resposta"""
        return response.get_header("to") or ""

    def _extract_tag(self, header_value: str) -> str | None:
        """Extrai tag de header"""
        match = re.search(r"tag=([^;]+)", header_value)
        return match.group(1) if match else None

    def _extract_cseq_number(self, request: SIPMessage) -> int:
        """Extrai número CSeq"""
        cseq_header = request.get_header("cseq")
        if cseq_header:
            return int(cseq_header.split()[0])
        return 0


# ======================= TRANSACTION MANAGER =======================


class TransactionManager:
    """Gerenciador de transações SIP"""

    def __init__(
        self,
        callbacks: TransactionCallbacks,
        transport: TransportCallbacks,
        timers: SIPTimers | None = None,
    ):
        self.callbacks = callbacks
        self.transport = transport
        self.timers = timers or SIPTimers()
        self.timers = timers

        self._transactions: dict[str, SIPTransaction] = {}
        self._logger = logging.getLogger("TransactionManager")

    def generate_transaction_id(self, message: SIPMessage, is_server: bool = False) -> str:
        """Gera ID único para transação"""
        via_header = message.get_header("via")
        via_branch = ""

        if via_header:
            # Extract branch parameter
            match = re.search(r"branch=([^;]+)", via_header)
            if match:
                via_branch = match.group(1)

        # Para garantir consistência, sempre usar apenas o branch parameter
        # O RFC 3261 especifica que o branch parameter identifica a transação
        if via_branch:
            return via_branch

        # Fallback para casos sem branch válido
        return str(uuid.uuid4())[:16]

    async def create_client_transaction(self, request: SIPMessage) -> str:
        """Cria transação cliente"""
        tx_id = self.generate_transaction_id(request, is_server=False)
        method = request.method

        # Check if transaction already exists
        if tx_id in self._transactions:
            self._logger.debug(f"Transaction {tx_id} already exists, returning existing ID")
            return tx_id

        if method == SIPMethod.INVITE:
            tx = InviteClientTransaction(
                tx_id, TxKind.INVITE_CLIENT, self.callbacks, self.transport, self.timers
            )
        else:
            tx = NonInviteClientTransaction(
                tx_id, TxKind.NON_INVITE_CLIENT, self.callbacks, self.transport, self.timers
            )

        self._transactions[tx_id] = tx
        await tx.start(request)

        method_name = method.value if method else "UNKNOWN"
        self._logger.info(f"Created client transaction {tx_id} for {method_name}")
        return tx_id

    async def create_server_transaction(self, request: SIPMessage) -> str:
        """Cria transação servidor"""
        tx_id = self.generate_transaction_id(request, is_server=True)
        method = request.method

        # Check if transaction already exists
        if tx_id in self._transactions:
            # Retransmitted request
            await self._transactions[tx_id].process_message(request)
            return tx_id

        if method == SIPMethod.INVITE:
            tx = InviteServerTransaction(
                tx_id, TxKind.INVITE_SERVER, self.callbacks, self.transport, self.timers
            )
        else:
            tx = NonInviteServerTransaction(
                tx_id, TxKind.NON_INVITE_SERVER, self.callbacks, self.transport, self.timers
            )

        self._transactions[tx_id] = tx
        await tx.start(request)

        method_name = method.value if method else "UNKNOWN"
        self._logger.info(f"Created server transaction {tx_id} for {method_name}")
        return tx_id

    async def process_response(self, response: SIPMessage) -> None:
        """Processa resposta recebida"""
        tx_id = self.generate_transaction_id(response)

        tx = self._transactions.get(tx_id)
        if tx:
            await tx.process_message(response)
        else:
            self._logger.warning(f"No transaction found for response: {tx_id}")

    async def process_request(self, request: SIPMessage) -> str:
        """Processa requisição recebida"""
        method = request.method

        if method == SIPMethod.ACK:
            # ACK para transação INVITE existente
            tx_id = self.generate_transaction_id(request, is_server=True)

            # Para ACK, procurar pela transação INVITE correspondente
            # ACK usa o mesmo branch que o INVITE original
            tx = self._transactions.get(tx_id)
            if tx:
                await tx.process_message(request)
                return tx_id

        # Nova transação servidor
        return await self.create_server_transaction(request)

    def get_transaction(self, tx_id: str) -> SIPTransaction | None:
        """Obtém transação por ID"""
        return self._transactions.get(tx_id)

    async def send_response(
        self, tx_id: str, status_code: int, reason_phrase: str, body: str | None = None
    ) -> None:
        """Envia resposta através da transação"""
        tx = self._transactions.get(tx_id)
        if tx and hasattr(tx, "send_final_response"):
            await tx.send_final_response(status_code, reason_phrase, body)

    async def cleanup_transaction(self, tx_id: str) -> None:
        """Remove transação terminada"""
        if tx_id in self._transactions:
            del self._transactions[tx_id]
            self._logger.debug(f"Cleaned up transaction {tx_id}")


# ======================= SIP USER AGENT =======================


class SIPUserAgent:
    """User Agent SIP completo com suporte a transações e diálogos"""

    def __init__(
        self, transport: TransportCallbacks, local_uri: str, timers: SIPTimers | None = None
    ):
        self.transport = transport
        self.local_uri = local_uri
        self.timers = timers or SIPTimers()

        # Initialize managers
        self.tx_manager = TransactionManager(self, transport, timers)
        self.dialog_manager = DialogManager(self)
        self.authenticator = SIPDigestAuthentication()

        self._logger = logging.getLogger("SIPUserAgent")

    # TransactionCallbacks implementation
    async def on_provisional_response(self, tx_id: str, response: SIPMessage) -> None:
        """Handler para respostas provisórias"""
        self._logger.info(f"Provisional response {response.status_code} in tx {tx_id}")

    async def on_final_response(self, tx_id: str, response: SIPMessage) -> None:
        """Handler para respostas finais"""
        status_code = response.status_code
        self._logger.info(f"Final response {status_code} in tx {tx_id}")

        # Handle authentication challenges
        if status_code in [401, 407]:
            await self._handle_authentication_challenge(tx_id, response)
            return

        # Update any associated dialog
        tx = self.tx_manager.get_transaction(tx_id)
        if tx and tx.kind == TxKind.INVITE_CLIENT:
            # This is a response to our INVITE
            dialog = self.dialog_manager.get_dialog(tx_id)  # Simplified dialog lookup
            if dialog:
                self.dialog_manager.update_dialog_from_response(dialog.dialog_id, response)

    async def on_request_received(self, tx_id: str, request: SIPMessage) -> None:
        """Handler para requisições recebidas"""
        if request.method is None:
            self._logger.error("Invalid request - no method")
            return

        method = request.method.value
        self._logger.info(f"Request {method} received in tx {tx_id}")

        if method == "INVITE":
            # Create dialog
            self.dialog_manager.create_dialog_from_request(request)

            # Send 100 Trying
            await self.tx_manager.send_response(tx_id, 100, "Trying")

            # Application logic would go here
            # For demo, send 200 OK
            await asyncio.sleep(1)  # Simulate processing
            await self.tx_manager.send_response(
                tx_id, 200, "OK", "v=0\no=- 123 456 IN IP4 127.0.0.1\ns=Test\nt=0 0"
            )

        elif method == "BYE":
            # Terminate dialog
            await self.tx_manager.send_response(tx_id, 200, "OK")

        else:
            # Handle other methods
            await self.tx_manager.send_response(tx_id, 200, "OK")

    async def on_timeout(self, tx_id: str, timer_type: TimerType) -> None:
        """Handler para timeouts"""
        # Log já é feito na transação com Rich panel, não duplicar aqui
        pass

    async def on_transport_error(self, tx_id: str, error: Exception) -> None:
        """Handler para erros de transporte"""
        self._logger.error(f"Transport error in tx {tx_id}: {error}")

    async def on_terminated(self, tx_id: str) -> None:
        """Handler para término de transação"""
        await self.tx_manager.cleanup_transaction(tx_id)

    # DialogCallbacks implementation (simplified)
    async def on_dialog_created(self, dialog_id: str) -> None:
        self._logger.info(f"Dialog created: {dialog_id}")

    async def on_dialog_confirmed(self, dialog_id: str) -> None:
        self._logger.info(f"Dialog confirmed: {dialog_id}")

    async def on_dialog_terminated(self, dialog_id: str, reason: str) -> None:
        self._logger.info(f"Dialog terminated: {dialog_id} - {reason}")

    async def on_in_dialog_request(self, dialog_id: str, request: SIPMessage) -> None:
        self._logger.info(f"In-dialog request in {dialog_id}")

    # Public API
    async def send_options(self, target_uri: str) -> str:
        """Envia OPTIONS"""
        request = self._create_options_request(target_uri)
        tx_id = await self.tx_manager.create_client_transaction(request)
        return tx_id

    async def send_invite(self, target_uri: str, body: str | None = None) -> str:
        """Envia INVITE"""
        request = self._create_invite_request(target_uri, body)
        tx_id = await self.tx_manager.create_client_transaction(request)
        return tx_id

    async def send_register(self, registrar_uri: str | None = None, expires: int = 3600) -> str:
        """Envia REGISTER"""
        if not registrar_uri:
            # Use domain from local_uri as registrar
            domain = self.local_uri.split("@")[1] if "@" in self.local_uri else "localhost"
            registrar_uri = f"sip:{domain}"

        request = self._create_register_request(registrar_uri, expires)
        tx_id = await self.tx_manager.create_client_transaction(request)
        return tx_id

    async def send_bye(self, dialog_id: str) -> str:
        """Envia BYE"""
        dialog = self.dialog_manager.get_dialog(dialog_id)
        if not dialog:
            raise ValueError(f"Dialog {dialog_id} not found")

        request = self._create_bye_request(dialog)
        tx_id = await self.tx_manager.create_client_transaction(request)
        return tx_id

    async def process_incoming_message(self, raw_message: str) -> None:
        """Processa mensagem SIP recebida"""
        try:
            message = SIPMessage.parse(raw_message)

            # Validate message
            is_valid, errors = message.validate()
            if not is_valid:
                self._logger.error(f"Invalid SIP message: {errors}")
                return

            if message.is_request:
                await self.tx_manager.process_request(message)
            else:  # response
                await self.tx_manager.process_response(message)
        except Exception as e:
            self._logger.error(f"Failed to parse SIP message: {e}")

    def _create_options_request(self, target_uri: str) -> SIPMessage:
        """Cria requisição OPTIONS"""
        domain = self.local_uri.split("@")[1] if "@" in self.local_uri else "localhost"
        call_id = f"{uuid.uuid4().hex}@{domain}"
        from_tag = uuid.uuid4().hex[:8]
        branch = f"z9hG4bK{uuid.uuid4().hex[:16]}"

        # Parse local URI to extract host
        local_host = self.local_uri.split("@")[1] if "@" in self.local_uri else "localhost"

        # Create OPTIONS request using SIPMessage
        options = SIPMessage.create_request(SIPMethod.OPTIONS, target_uri)

        # Add required headers
        options.add_header("Via", f"SIP/2.0/UDP {local_host};branch={branch}")
        options.add_header("Max-Forwards", "70")
        options.add_header("From", f"<{self.local_uri}>;tag={from_tag}")
        options.add_header("To", f"<{target_uri}>")
        options.add_header("Call-ID", call_id)
        options.add_header("CSeq", "1 OPTIONS")
        options.add_header("Contact", f"<{self.local_uri}>")
        options.add_header("Content-Length", "0")

        return options

    def _create_invite_request(self, target_uri: str, body: str | None = None) -> SIPMessage:
        """Cria requisição INVITE"""
        call_id = f"{uuid.uuid4().hex}@{self.local_uri.split('@')[1]}"
        from_tag = uuid.uuid4().hex[:8]
        branch = f"z9hG4bK{uuid.uuid4().hex[:16]}"

        # Parse local URI to extract host
        local_host = self.local_uri.split("@")[1] if "@" in self.local_uri else "localhost"

        # Create INVITE request using SIPMessage
        invite = SIPMessage.create_request(SIPMethod.INVITE, target_uri)

        # Add required headers
        invite.add_header("Via", f"SIP/2.0/UDP {local_host};branch={branch}")
        invite.add_header("Max-Forwards", "70")
        invite.add_header("From", f"<{self.local_uri}>;tag={from_tag}")
        invite.add_header("To", f"<{target_uri}>")
        invite.add_header("Call-ID", call_id)
        invite.add_header("CSeq", "1 INVITE")
        invite.add_header("Contact", f"<{self.local_uri}>")

        # Add body if provided
        if body:
            invite.set_body(body, "application/sdp")
        else:
            invite.add_header("Content-Length", "0")

        return invite

    def _create_register_request(self, registrar_uri: str, expires: int = 3600) -> SIPMessage:
        """Cria requisição REGISTER"""
        domain = self.local_uri.split("@")[1] if "@" in self.local_uri else "localhost"
        call_id = f"{uuid.uuid4().hex}@{domain}"
        from_tag = uuid.uuid4().hex[:8]
        branch = f"z9hG4bK{uuid.uuid4().hex[:16]}"

        # Parse local URI to extract components
        local_host = self.local_uri.split("@")[1] if "@" in self.local_uri else "localhost"
        local_user = (
            self.local_uri.split("@")[0].replace("sip:", "")
            if "@" in self.local_uri
            else "anonymous"
        )

        # Create REGISTER request
        register = SIPMessage.create_request(SIPMethod.REGISTER, registrar_uri)

        # Add required headers
        register.add_header("Via", f"SIP/2.0/UDP {local_host};branch={branch}")
        register.add_header("Max-Forwards", "70")
        register.add_header("From", f"<{self.local_uri}>;tag={from_tag}")
        register.add_header("To", f"<{self.local_uri}>")  # To = From in REGISTER
        register.add_header("Call-ID", call_id)
        register.add_header("CSeq", "1 REGISTER")
        register.add_header("Contact", f"<sip:{local_user}@{local_host}>;expires={expires}")
        register.add_header("Expires", str(expires))
        register.add_header("Content-Length", "0")

        return register

    def _create_bye_request(self, dialog: SIPDialog) -> SIPMessage:
        """Cria requisição BYE"""
        branch = f"z9hG4bK{uuid.uuid4().hex[:16]}"
        dialog.local_cseq += 1

        # Create BYE request using SIPMessage
        bye = SIPMessage.create_request(SIPMethod.BYE, dialog.remote_uri)

        # Add required headers
        local_host = self.local_uri.split("@")[1] if "@" in self.local_uri else "localhost"
        bye.add_header("Via", f"SIP/2.0/UDP {local_host};branch={branch}")
        bye.add_header("Max-Forwards", "70")
        bye.add_header("From", f"<{dialog.local_uri}>;tag={dialog.local_tag}")
        bye.add_header("To", f"<{dialog.remote_uri}>;tag={dialog.remote_tag}")
        bye.add_header("Call-ID", dialog.call_id)
        bye.add_header("CSeq", f"{dialog.local_cseq} BYE")
        bye.add_header("Content-Length", "0")

        return bye

    async def _handle_authentication_challenge(self, tx_id: str, response: SIPMessage) -> None:
        """Trata challenge de autenticação"""
        tx = self.tx_manager.get_transaction(tx_id)
        if not tx or not tx.request:
            return

        # Rich logging do challenge
        auth_header = response.get_header("WWW-Authenticate") or response.get_header(
            "Proxy-Authenticate"
        )
        if auth_header:
            # Extrair realm e nonce do header
            realm = "Unknown"
            nonce = "Unknown"
            if 'realm="' in auth_header:
                realm = auth_header.split('realm="')[1].split('"')[0]
            if 'nonce="' in auth_header:
                nonce = auth_header.split('nonce="')[1].split('"')[0]

            # Rich logging do challenge
            content = f"🔐 Realm: {realm}\n🎲 Nonce: {nonce[:20]}..."
            panel = Panel(
                content,
                title="[bold yellow]Authentication Challenge",
                border_style="yellow",
            )
            logger.info(panel)

        # Criar requisição autenticada
        authenticated_request = self.authenticator.create_authenticated_request(
            tx.request, response
        )

        if authenticated_request == tx.request:
            # Falha na autenticação
            self._logger.warning(f"Authentication failed for tx {tx_id}")
            # Rich logging de erro
            content = (
                f"❌ Error Type: Authentication Failed\n"
                f"📝 Details: Failed to authenticate transaction {tx_id}"
            )
            panel = Panel(
                content,
                title="[bold red]Error",
                border_style="red",
            )
            logger.info(panel)
            return

        # Rich logging da resposta de autenticação
        auth_header_req = authenticated_request.get_header(
            "Authorization"
        ) or authenticated_request.get_header("Proxy-Authorization")
        if auth_header_req:
            username = "Unknown"
            realm = "Unknown"
            uri = tx.request.uri
            if 'username="' in auth_header_req:
                username = auth_header_req.split('username="')[1].split('"')[0]
            if 'realm="' in auth_header_req:
                realm = auth_header_req.split('realm="')[1].split('"')[0]

            # Rich logging da resposta de autenticação
            content = f"👤 Username: {username}\n🔐 Realm: {realm}\n🌐 URI: {uri}"
            panel = Panel(
                content,
                title="[bold cyan]Authentication Response",
                border_style="cyan",
            )
            logger.info(panel)

        # Enviar nova requisição autenticada
        try:
            new_tx_id = await self.tx_manager.create_client_transaction(authenticated_request)
            self._logger.info(f"Resent request with authentication as tx {new_tx_id}")
        except Exception as e:
            self._logger.error(f"Failed to resend authenticated request: {e}")
            # Rich logging de erro
            content = (
                f"❌ Error Type: Transaction Error\n"
                f"📝 Details: Failed to resend authenticated request: {e}"
            )
            panel = Panel(
                content,
                title="[bold red]Error",
                border_style="red",
            )
            logger.info(panel)

    def add_credentials(self, realm: str, username: str, password: str) -> None:
        """Adiciona credenciais para autenticação"""
        self.authenticator.add_credentials(realm, username, password)
        self._logger.info(f"Added credentials for realm: {realm}")


# ======================= HELPER FUNCTIONS =======================


def create_options_request(
    uri: str,
    from_uri: str,
    to_uri: str | None = None,
    call_id: str | None = None,
    branch: str | None = None,
    local_address: str = "localhost:5060",
) -> SIPMessage:
    """Cria um request OPTIONS usando o sistema genérico"""
    to_uri = to_uri or uri
    call_id = call_id or f"tinysip-{int(time.time())}"
    branch = branch or f"z9hG4bK-{uuid.uuid4().hex[:16]}"

    headers = {
        "Via": f"SIP/2.0/UDP {local_address};branch={branch}",
        "Max-Forwards": "70",
        "To": f"<{to_uri}>",
        "From": f"<{from_uri}>;tag={uuid.uuid4().hex[:8]}",
        "Call-ID": call_id,
        "CSeq": "1 OPTIONS",
        "Content-Length": "0",
    }

    return SIPMessage.create_request(SIPMethod.OPTIONS, uri, extra_headers=headers)


def create_ok_response(
    request: SIPMessage, extra_headers: dict | None = None, body: str | None = None
) -> SIPMessage:
    """Cria uma response 200 OK baseada no request"""
    response_headers = {"Content-Length": "0"}
    if extra_headers:
        response_headers.update(extra_headers)

    return SIPMessage.create_response(200, "OK", request, extra_headers=response_headers, body=body)
