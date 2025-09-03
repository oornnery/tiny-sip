# ======================= EXEMPLOS DE USO =======================
import asyncio
import logging
import time
from dataclasses import dataclass, field

from rich.panel import Panel
from rich.traceback import install

from tinysip.call_flow import SIPCallFlowTracker, SIPFlowEntry
from tinysip.fsm import SIPTimers, SIPUserAgent
from tinysip.logging_utils import RichSIPLogger, console
from tinysip.message import SIPMessage
from tinysip.sdp import SDPSession, create_basic_audio_offer
from tinysip.transport import Transport, TransportConfig, TransportType

# Instalar Rich traceback para exceções mais bonitas
install(show_locals=True)


@dataclass
class UserAgent:
    domain: str
    port: int
    realm: str = field(default_factory=str)
    username: str = field(default_factory=str)
    password: str = field(default_factory=str)
    display_user: str = field(default_factory=str)
    user_agent: str = field(default="TinySIP-UA/1.0")
    transport_cfg: TransportConfig | None = field(default=None)

    def __post_init__(self):
        if not self.transport_cfg:
            self.transport_cfg = TransportConfig(
                remote_host=self.domain,
                remote_port=self.port,
                transport_type=TransportType.UDP,
                local_port=0,
            )


class TransportAdapter:
    """Adaptador para fazer Transport compatível com TransportCallbacks"""

    def __init__(self, transport: Transport):
        self.transport = transport

    async def send_message(self, message: str, destination: tuple[str, int]) -> None:
        """Envia mensagem através do transporte"""
        await self.transport.send(message.encode("utf-8"), destination)


class SIPClient:
    """Cliente SIP usando sistema FSM completo"""

    def __init__(self, user_agent: UserAgent):
        self.ua = user_agent
        self._transport = Transport(config=self.ua.transport_cfg)
        self._transport_adapter = TransportAdapter(self._transport)
        self._logger = RichSIPLogger("SIPClient")
        self._std_logger = logging.getLogger("SIPClient")

        # Call flow tracker
        self._call_flow_tracker = SIPCallFlowTracker()
        self._current_call_id: str | None = None

        # Criar local URI para o user agent
        local_host = self.ua.transport_cfg.local_host or "localhost"
        from_user = self.ua.username or "Anonymous"
        local_uri = f"sip:{from_user}@{local_host}"

        # Inicializar SIP User Agent com sistema FSM
        self._sip_ua = SIPUserAgent(
            transport=self._transport_adapter, local_uri=local_uri, timers=SIPTimers()
        )

    async def start(self):
        """Inicia cliente"""
        await self._transport.start(self._on_message_received)
        self._logger.log_success("SIP Client with FSM started")

    async def stop(self):
        """Para cliente"""
        await self._transport.stop()

        # Mostrar call flow se houver
        if self._current_call_id and self._call_flow_tracker.call_flows:
            console.print("\n📊 [bold cyan]Call Flow Summary[/bold cyan]")
            self._call_flow_tracker.render_current_flow()

        self._logger.log_success("SIP Client stopped")

    def start_call_flow_tracking(self, call_id: str | None = None):
        """Inicia tracking de call flow"""
        import uuid

        if not call_id:
            call_id = f"{uuid.uuid4().hex[:8]}@{self.ua.domain}"

        local_addr = f"{self._transport.local_address[0]}:{self._transport.local_address[1]}"
        remote_addr = f"{self.ua.domain}:{self.ua.port}"

        self._call_flow_tracker.start_call_flow(call_id, local_addr, remote_addr)
        self._current_call_id = call_id
        return call_id

    async def _on_message_received(self, data: bytes, addr: tuple[str, int]):
        """Processa mensagens SIP recebidas usando FSM"""
        try:
            message_str = data.decode("utf-8", errors="ignore")

            # Log da mensagem recebida com Rich
            sip_msg = SIPMessage.parse(message_str)
            if sip_msg.is_response:
                self._logger.log_sip_message_received(
                    message_str, addr, status_code=sip_msg.status_code
                )
            else:
                method = sip_msg.method.value if sip_msg.method else "UNKNOWN"
                self._logger.log_sip_message_received(message_str, addr, method=method)

            # Capturar no call flow se tiver call_id ativo
            call_id = sip_msg.get_header("call-id")
            if call_id and self._current_call_id:
                if call_id == self._current_call_id:
                    source_addr = f"{addr[0]}:{addr[1]}"
                    self._call_flow_tracker.add_inbound_message(call_id, source_addr, sip_msg)

            # Processar através do FSM
            await self._sip_ua.process_incoming_message(message_str)

        except Exception as e:
            self._logger.log_error(e, "processing SIP message")
            raw_msg = data.decode("utf-8", errors="ignore")
            self._logger.log_sip_message_received(raw_msg, addr, method="RAW")

    async def send_options(self, target_uri: str | None = None):
        """Envia OPTIONS usando sistema FSM"""
        try:
            if not target_uri:
                # Usar o domínio sem @ para evitar URI malformada
                target_uri = f"sip:{self.ua.domain}:{self.ua.port}"

            # Iniciar call flow tracking
            if not self._current_call_id:
                self.start_call_flow_tracking()

            tx_id = await self._sip_ua.send_options(target_uri)
            self._logger.log_transaction(tx_id, "OPTIONS", target_uri)

            # Capturar mensagem enviada no call flow
            if self._current_call_id:
                # Criar entrada direta no call flow
                entry = SIPFlowEntry(
                    timestamp=time.strftime("%H:%M:%S.%f")[:-3],
                    source=f"{self._transport.local_address[0]}:{self._transport.local_address[1]}",
                    dest=f"{self.ua.domain}:{self.ua.port}",
                    method="OPTIONS",
                    transaction_id=tx_id,
                    direction="outbound",
                )

                flow = self._call_flow_tracker.get_call_flow(self._current_call_id)
                if flow:
                    flow.entries.append(entry)

            return tx_id
        except Exception as e:
            self._logger.log_error(e, "sending OPTIONS")
            return None

    async def send_register(self, registrar_uri: str | None = None, expires: int = 3600):
        """Envia REGISTER usando sistema FSM"""
        try:
            if not registrar_uri:
                # Use domain from local_uri as registrar
                registrar_uri = f"sip:{self.ua.domain}:{self.ua.port}"

            # Garantir call flow tracking
            if not self._current_call_id:
                self.start_call_flow_tracking()

            tx_id = await self._sip_ua.send_register(registrar_uri, expires)
            self._logger.log_transaction(tx_id, "REGISTER", registrar_uri)

            # Capturar mensagem enviada no call flow
            if self._current_call_id:
                entry = SIPFlowEntry(
                    timestamp=time.strftime("%H:%M:%S.%f")[:-3],
                    source=f"{self._transport.local_address[0]}:{self._transport.local_address[1]}",
                    dest=f"{self.ua.domain}:{self.ua.port}",
                    method="REGISTER",
                    transaction_id=tx_id,
                    direction="outbound",
                )

                flow = self._call_flow_tracker.get_call_flow(self._current_call_id)
                if flow:
                    flow.entries.append(entry)

            return tx_id
        except Exception as e:
            self._logger.log_error(e, "sending REGISTER")
            return None

    async def send_invite(
        self, target_uri: str, sdp_body: SDPSession | None = None, body: str | None = None
    ):
        """Envia INVITE usando sistema FSM com suporte a SDP"""
        try:
            # Se não fornecido SDP nem body, criar offer SDP básico
            if not sdp_body and not body:
                local_addr = self._transport.local_address
                sdp_body = create_basic_audio_offer(local_addr[0])

            # Usar SDP se fornecido, senão usar body string
            invite_body = str(sdp_body) if sdp_body else body

            # Garantir call flow tracking
            if not self._current_call_id:
                self.start_call_flow_tracking()

            tx_id = await self._sip_ua.send_invite(target_uri, invite_body)
            self._logger.log_transaction(tx_id, "INVITE", target_uri)

            # Log do SDP offer se disponível
            if sdp_body:
                self._logger.logger.info(
                    Panel(
                        str(sdp_body),
                        title="📋 SDP Offer Generated",
                        border_style="magenta",
                        expand=False,
                    )
                )

            # Capturar mensagem enviada no call flow
            if self._current_call_id:
                # Extrair informações do SDP para o call flow
                body_summary = None
                if sdp_body and sdp_body.media:
                    media = sdp_body.media[0]
                    codecs = []
                    for attr in media.attributes:
                        if attr.name == "rtpmap" and attr.value:
                            codec_info = attr.value.split(" ", 1)[1].split("/")[0]
                            codecs.append(codec_info)
                    codec_list = ", ".join(codecs[:2]) if codecs else "audio"
                    body_summary = f"audio {media.port} ({codec_list})"

                entry = SIPFlowEntry(
                    timestamp=time.strftime("%H:%M:%S.%f")[:-3],
                    source=f"{self._transport.local_address[0]}:{self._transport.local_address[1]}",
                    dest=target_uri.replace("sip:", ""),
                    method="INVITE",
                    transaction_id=tx_id,
                    body_type="SDP" if sdp_body else "TEXT",
                    body_summary=body_summary,
                    direction="outbound",
                )

                flow = self._call_flow_tracker.get_call_flow(self._current_call_id)
                if flow:
                    flow.entries.append(entry)

            return tx_id
        except Exception as e:
            self._logger.log_error(e, "sending INVITE")
            return None

    async def send_bye(self, dialog_id: str):
        """Envia BYE usando sistema FSM"""
        try:
            tx_id = await self._sip_ua.send_bye(dialog_id)
            self._logger.log_transaction(tx_id, "BYE", f"dialog:{dialog_id}")
            return tx_id
        except Exception as e:
            self._logger.log_error(e, "sending BYE")
            return None

    def add_credentials(self, realm: str, username: str, password: str):
        """Adiciona credenciais para autenticação SIP"""
        self._sip_ua.add_credentials(realm, username, password)
        self._logger.log_info(f"🔐 Added credentials for realm: {realm}", style="dim green")

    def get_sdp_from_response(self, response: SIPMessage) -> SDPSession | None:
        """Extrai SDP de uma response SIP"""
        if response.body and response.body.is_sdp:
            return response.body.get_sdp()
        return None


async def example_udp_client():
    """Exemplo de cliente UDP com FSM"""
    console.print("\n🚀 [bold cyan]Exemplo UDP Client com sistema FSM[/bold cyan]")

    # Configurar logging centralizado
    from tinysip.logging_utils import setup_logging

    setup_logging(level="WARNING")

    ua = UserAgent(
        domain="demo.mizu-voip.com",
        port=37075,
        username="testuser",
        password="testpass",  # Adicionar password para teste de auth
        realm="demo.mizu-voip.com",
        user_agent="TinySIP-UA/1.0",
    )
    client = SIPClient(ua)

    try:
        await client.start()
        console.print(
            f"🌐 [bold green]UDP Client rodando em:[/bold green] {client._transport.local_address}"
        )

        # Demonstrar diferentes tipos de mensagens
        console.print("\n📤 [bold yellow]Enviando OPTIONS com FSM...[/bold yellow]")
        await client.send_options()

        # Aguardar resposta
        await asyncio.sleep(2)

        # Adicionar credenciais se necessário
        if ua.username and ua.password:
            client.add_credentials(ua.realm or ua.domain, ua.username, ua.password)

        # Exemplo de REGISTER
        console.print("\n📝 [bold yellow]Enviando REGISTER...[/bold yellow]")
        register_tx_id = await client.send_register()
        if register_tx_id:
            console.print(f"✨ [green]REGISTER transaction iniciada:[/green] {register_tx_id}")
            await asyncio.sleep(3)  # Aguardar resposta

        # Exemplo de INVITE com SDP
        console.print("\n📞 [bold yellow]Enviando INVITE com SDP...[/bold yellow]")
        from tinysip.sdp import create_basic_audio_offer

        sdp_offer = create_basic_audio_offer(client._transport.local_address[0])
        invite_tx_id = await client.send_invite(
            f"sip:test@{ua.domain}:{ua.port}", sdp_body=sdp_offer
        )
        if invite_tx_id:
            console.print(f"✨ [green]INVITE transaction iniciada:[/green] {invite_tx_id}")

        console.print("\n⏳ [dim]Aguardando mais mensagens...[/dim]")
        await asyncio.sleep(8)

    except Exception as e:
        console.print(
            Panel(f"{type(e).__name__}: {str(e)}", title="💥 Client Error", border_style="red")
        )
    finally:
        await client.stop()


async def example_tcp_server():
    """Exemplo de servidor TCP"""
    console.print("\n🚀 [bold cyan]Exemplo TCP Server[/bold cyan]")
    logging.basicConfig(level=logging.WARNING)

    # Criar transporte TCP
    transport_cfg = TransportConfig(
        remote_host="demo.mizu-voip.com",
        remote_port=37075,
        transport_type=TransportType.TCP,
        local_port=0,
    )
    transport = Transport(config=transport_cfg)

    async def on_message(data: bytes, addr: tuple[str, int]):
        message = data.decode("utf-8", errors="ignore")
        console.print(
            Panel(message, title=f"📨 TCP Message from {addr[0]}:{addr[1]}", border_style="blue")
        )

    try:
        await transport.start(on_message)
        console.print(
            f"🌐 [bold green]TCP Server rodando em:[/bold green] {transport.local_address}"
        )
        console.print("[dim]Teste com: telnet localhost 5061[/dim]")

        # Manter servidor ativo
        await asyncio.sleep(30)

    except Exception as e:
        console.print(
            Panel(f"{type(e).__name__}: {str(e)}", title="💥 Server Error", border_style="red")
        )
    finally:
        await transport.stop()


async def example_fsm_server():
    """Exemplo de servidor SIP com FSM completo"""
    console.print("\n🚀 [bold cyan]Exemplo SIP Server com sistema FSM[/bold cyan]")
    logging.basicConfig(level=logging.WARNING)

    # Criar configuração para servidor
    ua = UserAgent(
        domain="localhost",
        port=5060,
        username="server",
        user_agent="TinySIP-Server/1.0",
        transport_cfg=TransportConfig(
            remote_host="0.0.0.0",
            remote_port=5060,
            transport_type=TransportType.UDP,
            local_port=5060,
            local_host="0.0.0.0",
        ),
    )

    server = SIPClient(ua)

    try:
        await server.start()
        console.print(
            f"🎯 [bold green]SIP Server rodando em:[/bold green] {server._transport.local_address}"
        )
        console.print("[dim]Servidor aguardando conexões SIP...[/dim]")
        console.print("[dim]Teste enviando mensagens SIP para localhost:5060[/dim]")

        # Manter servidor ativo
        await asyncio.sleep(60)

    except Exception as e:
        console.print(
            Panel(f"{type(e).__name__}: {str(e)}", title="💥 Server Error", border_style="red")
        )
    finally:
        await server.stop()


async def main():
    """Função principal"""
    console.print("\n🔥 [bold red]TinySIP[/bold red] - [bold]Sistema SIP Completo com FSM[/bold]")
    console.print("1. [cyan]UDP Client com FSM[/cyan]")
    console.print("2. [cyan]TCP Server (básico)[/cyan]")
    console.print("3. [cyan]SIP Server com FSM[/cyan]")

    choice = input("\nEscolha (1, 2 ou 3): ").strip()

    if choice == "1":
        await example_udp_client()
    elif choice == "2":
        await example_tcp_server()
    elif choice == "3":
        await example_fsm_server()
    else:
        console.print("❌ [red]Escolha inválida[/red]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n🛑 [yellow]Interrompido pelo usuário[/yellow]")
    except Exception as e:
        console.print(
            Panel(f"{type(e).__name__}: {str(e)}", title="💥 Fatal Error", border_style="red")
        )
