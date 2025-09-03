"""
Transport layer
Sistema completo de transporte SIP com suporte a UDP, TCP e TLS assíncrono.
"""

import asyncio
import logging
import socket
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class TransportError(Exception):
    """Exceção para erros de transporte"""

    pass


class TransportType(Enum):
    UDP = "udp"
    TCP = "tcp"
    # TODO: TLS = "tls"
    # TODO: WS = "ws"
    # TODO: WSS = "wss"


@dataclass
class TransportConfig:
    """Configuração do transporte SIP"""

    remote_host: str
    remote_port: int
    transport_type: TransportType = field(default=TransportType.UDP)
    local_host: str = field(default="0.0.0.0")
    local_port: int = field(default=0)  # 0 = porta automática
    reuse_addr: bool = field(default=True)
    reuse_port: bool = field(default=False)


class TransportBase(ABC):
    """Classe base abstrata para transportes"""

    def __init__(self, config: TransportConfig):
        self.cfg = config
        self._sock = None
        self._recv_callback = None
        self._running = False
        self._logger = logging.getLogger("tinysip.transport")

    @abstractmethod
    async def start(self, recv_callback: Callable[[bytes, tuple[str, int]], None]):
        """Inicia o transporte"""
        self._recv_callback = recv_callback
        self._running = True
        self._logger.info(
            f"Starting {self.cfg.transport_type.value.upper()} transport on {self.cfg.local_host}:{
                self.cfg.local_port
            }"
        )

    @abstractmethod
    async def send(self, data: bytes, addr: tuple[str, int]):
        """Envia dados para endereço específico"""
        if not self._running:
            raise TransportError("Transport not running")
        self._logger.debug(f"Sending {len(data)} bytes to {addr}")

    @abstractmethod
    async def stop(self):
        """Para o transporte"""
        self._running = False
        self._logger.info("Stopping transport")

    @property
    def is_running(self) -> bool:
        """Verifica se o transporte está rodando"""
        return self._running

    @property
    def local_address(self) -> tuple[str, int]:
        """Retorna endereço local do socket"""
        if self._sock:
            return self._sock.getsockname()
        return (self.cfg.local_host, self.cfg.local_port)


class UDPProtocol(asyncio.DatagramProtocol):
    """Protocol handler para UDP"""

    def __init__(self, on_datagram_received: Callable[[bytes, tuple[str, int]], None]):
        self.transport = None
        self.on_datagram_received = on_datagram_received
        self._logger = logging.getLogger("tinysip.transport.udp")

    def connection_made(self, transport):
        """Callback quando conexão UDP é estabelecida"""
        self.transport = transport
        sock = transport.get_extra_info("socket")
        if sock:
            addr = sock.getsockname()
            self._logger.info(f"UDP endpoint created on {addr}")

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        """Callback quando datagram UDP é recebido"""
        self._logger.debug(f"UDP datagram received from {addr}: {len(data)} bytes")
        if self.on_datagram_received:
            # Execute callback em task assíncrona
            asyncio.create_task(self.on_datagram_received(data, addr))

    def error_received(self, exc):
        """Callback para erros UDP"""
        self._logger.error(f"UDP error received: {exc}")

    def connection_lost(self, exc):
        """Callback quando conexão UDP é perdida"""
        if exc:
            self._logger.error(f"UDP connection lost: {exc}")
        else:
            self._logger.info("UDP connection closed")


class TCPProtocol(asyncio.Protocol):
    """Protocol handler para TCP"""

    def __init__(self, on_data_received: Callable[[bytes, tuple[str, int]], None]):
        self.transport = None
        self.on_data_received = on_data_received
        self.buffer = bytearray()
        self._logger = logging.getLogger("tinysip.transport.tcp")
        self.peer_addr = None

    def connection_made(self, transport):
        """Callback quando conexão TCP é estabelecida"""
        self.transport = transport
        self.peer_addr = transport.get_extra_info("peername")
        self._logger.info(f"TCP connection established with {self.peer_addr}")

    def data_received(self, data: bytes):
        """Callback quando dados TCP são recebidos"""
        self.buffer.extend(data)
        self._logger.debug(f"TCP data received from {self.peer_addr}: {len(data)} bytes")

        # Processar mensagens SIP completas no buffer
        while b"\r\n\r\n" in self.buffer:
            # Encontrar fim dos headers
            header_end = self.buffer.find(b"\r\n\r\n") + 4
            headers = self.buffer[:header_end].decode("utf-8", errors="ignore")

            # Extrair Content-Length se existir
            content_length = 0
            for line in headers.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    try:
                        content_length = int(line.split(":", 1)[1].strip())
                        break
                    except (ValueError, IndexError):
                        pass

            # Verificar se temos mensagem completa
            total_length = header_end + content_length
            if len(self.buffer) >= total_length:
                # Extrair mensagem completa
                complete_message = bytes(self.buffer[:total_length])
                self.buffer = self.buffer[total_length:]

                # Processar mensagem
                if self.on_data_received:
                    asyncio.create_task(self.on_data_received(complete_message, self.peer_addr))
            else:
                break  # Aguardar mais dados

    def connection_lost(self, exc):
        """Callback quando conexão TCP é perdida"""
        if exc:
            self._logger.error(f"TCP connection lost with {self.peer_addr}: {exc}")
        else:
            self._logger.info(f"TCP connection closed with {self.peer_addr}")

    def eof_received(self):
        """Callback quando EOF é recebido"""
        self._logger.debug(f"TCP EOF received from {self.peer_addr}")
        return False  # Fechar conexão


class Transport(TransportBase):
    """Implementação principal do transporte SIP"""

    def __init__(self, config: TransportConfig):
        super().__init__(config)
        self._protocol = None
        self._transport = None
        self._server = None
        self._tcp_connections: dict[tuple[str, int], asyncio.Transport] = {}

    async def start(self, recv_callback: Callable[[bytes, tuple[str, int]], None]):
        """Inicia o transporte baseado na configuração"""
        await super().start(recv_callback)

        if self.cfg.transport_type == TransportType.UDP:
            await self._start_udp()
        elif self.cfg.transport_type == TransportType.TCP:
            await self._start_tcp()
        else:
            raise TransportError(f"Unsupported transport type: {self.cfg.transport_type}")

    async def _start_udp(self):
        """Inicia transporte UDP"""
        loop = asyncio.get_running_loop()

        # Criar socket UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Configurar opções do socket
        if self.cfg.reuse_addr:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.cfg.reuse_port and hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        # Bind socket
        sock.bind((self.cfg.local_host, self.cfg.local_port))

        # Opcional: Connect para UDP (define remote endpoint padrão)
        if self.cfg.remote_host and self.cfg.remote_port:
            try:
                sock.connect((self.cfg.remote_host, self.cfg.remote_port))
                self._logger.info(
                    f"UDP socket connected to {self.cfg.remote_host}:{self.cfg.remote_port}"
                )
            except Exception as e:
                self._logger.warning(f"UDP connect failed: {e}")

        # Criar datagram endpoint
        self._protocol = UDPProtocol(self._recv_callback)
        self._transport, _ = await loop.create_datagram_endpoint(lambda: self._protocol, sock=sock)

        self._sock = sock
        actual_addr = sock.getsockname()
        self._logger.info(f"UDP transport started on {actual_addr}")

    async def _start_tcp(self):
        """Inicia transporte TCP (servidor)"""
        loop = asyncio.get_running_loop()

        # Criar servidor TCP
        def protocol_factory():
            return TCPProtocol(self._on_tcp_data_received)

        self._server = await loop.create_server(
            protocol_factory,
            host=self.cfg.local_host,
            port=self.cfg.local_port,
            reuse_address=self.cfg.reuse_addr,
            reuse_port=self.cfg.reuse_port,
        )

        # Obter socket do servidor para configurações
        server_sockets = self._server.sockets
        if server_sockets:
            self._sock = server_sockets[0]
            actual_addr = self._sock.getsockname()
            self._logger.info(f"TCP server listening on {actual_addr}")

    async def _on_tcp_data_received(self, data: bytes, addr: tuple[str, int]):
        """Handler interno para dados TCP recebidos"""
        # Repassar para callback do usuário
        if self._recv_callback:
            await self._recv_callback(data, addr)

    async def send(self, data: bytes, addr: tuple[str, int]):
        """Envia dados via transporte"""
        await super().send(data, addr)

        if self.cfg.transport_type == TransportType.UDP:
            if self._transport:
                self._transport.sendto(data, addr)
            else:
                raise TransportError("UDP transport not initialized")

        elif self.cfg.transport_type == TransportType.TCP:
            # Para TCP, verificar se já temos conexão ativa
            if addr in self._tcp_connections:
                transport = self._tcp_connections[addr]
                transport.write(data)
            else:
                # Criar nova conexão TCP cliente
                await self._tcp_connect_and_send(data, addr)
        else:
            raise TransportError(f"Send not supported for {self.cfg.transport_type}")

    async def _tcp_connect_and_send(self, data: bytes, addr: tuple[str, int]):
        """Conecta via TCP e envia dados"""
        try:
            loop = asyncio.get_running_loop()

            # Criar protocolo para conexão cliente
            def client_protocol_factory():
                return TCPProtocol(self._recv_callback)

            transport, protocol = await loop.create_connection(
                client_protocol_factory, host=addr[0], port=addr[1]
            )

            # Armazenar conexão
            self._tcp_connections[addr] = transport

            # Enviar dados
            transport.write(data)

            self._logger.info(f"TCP connection established and data sent to {addr}")

        except Exception as err:
            raise TransportError(f"Failed to connect and send TCP data to {addr}: {err}") from err

    async def stop(self):
        """Para o transporte"""
        await super().stop()

        # Fechar transporte UDP
        if self._transport:
            self._transport.close()
            self._transport = None

        # Fechar servidor TCP
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Fechar conexões TCP clientes
        for transport in self._tcp_connections.values():
            transport.close()
        self._tcp_connections.clear()

        self._sock = None
        self._logger.info(f"{self.cfg.transport_type.value.upper()} transport stopped")
