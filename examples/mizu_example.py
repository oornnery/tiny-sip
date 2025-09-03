#!/usr/bin/env python3
"""
Exemplo de cliente SIP usando o servidor demo da Mizu-VoIP
https://www.mizu-voip.com/DemoServer.aspx

Este exemplo demonstra:
- Conectar ao servidor demo da Mizu-VoIP
- Keep-alive com OPTIONS periódicos
- Registro (REGISTER)
- Chamada (INVITE) com SDP
- Sistema FSM completo
- Call Flow Ladder Diagram
"""

import asyncio
import logging
import signal
from dataclasses import dataclass, field

from rich.panel import Panel
from rich.traceback import install

from tinysip.call_flow import SIPCallFlowTracker
from tinysip.fsm import SIPTimers, SIPUserAgent
from tinysip.logging_utils import RichSIPLogger, console, setup_logging
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
    """Adaptador para fazer Transport compatível com TransportCallbacks e capturar mensagens"""

    def __init__(self, transport: Transport, call_flow_tracker: SIPCallFlowTracker):
        self.transport = transport
        self.call_flow_tracker = call_flow_tracker

    async def send_message(self, message: str, destination: tuple[str, int]) -> None:
        """Envia mensagem através do transporte e captura no call flow"""
        try:
            # Parse da mensagem para capturar Call-ID
            sip_msg = SIPMessage.parse(message)
            call_id = sip_msg.get_header("call-id")

            if call_id:
                dest_addr = f"{destination[0]}:{destination[1]}"
                self.call_flow_tracker.add_outbound_message(call_id, dest_addr, sip_msg)

        except Exception:
            # Se falhar o parse, continua enviando mesmo assim
            pass

        # Enviar mensagem
        await self.transport.send(message.encode("utf-8"), destination)


class SIPClient:
    """Cliente SIP usando sistema FSM completo"""

    def __init__(self, user_agent: UserAgent):
        self.ua = user_agent
        self._transport = Transport(config=self.ua.transport_cfg)
        self._logger = RichSIPLogger("SIPClient")
        self._std_logger = logging.getLogger("SIPClient")

        # Call flow tracker
        self._call_flow_tracker = SIPCallFlowTracker()
        self._current_call_id: str | None = None

        # Transport adapter com call flow tracking
        self._transport_adapter = TransportAdapter(self._transport, self._call_flow_tracker)

        # Criar local URI para o user agent
        local_host = self.ua.transport_cfg.local_host or "localhost"
        from_user = self.ua.username or "Anonymous"
        local_uri = f"sip:{from_user}@{local_host}"

        # Inicializar SIP User Agent com sistema FSM
        self._sip_ua = SIPUserAgent(
            transport=self._transport_adapter, local_uri=local_uri, timers=SIPTimers()
        )

        # Controle de keep-alive
        self._keep_alive_task = None
        self._running = False

    async def start(self):
        """Inicia cliente"""
        await self._transport.start(self._on_message_received)
        self._running = True

        # Configurar endereços no call flow tracker
        local_addr = f"{self._transport.local_address[0]}:{self._transport.local_address[1]}"
        remote_addr = f"{self.ua.domain}:{self.ua.port}"
        self._call_flow_tracker.set_addresses(local_addr, remote_addr)

        self._logger.log_success("SIP Client with FSM started")

    async def stop(self):
        """Para cliente"""
        self._running = False
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except asyncio.CancelledError:
                pass
        await self._transport.stop()

        # Mostrar TODOS os call flows por diálogo
        if self._call_flow_tracker.call_flows:
            console.print("\n📊 [bold cyan]SIP Call Flow Summary por Diálogo[/bold cyan]")
            self._call_flow_tracker.render_all_flows()

        self._logger.log_success("SIP Client stopped")

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

            # Capturar TODAS as mensagens por Call-ID (criando diálogos automáticamente)
            call_id = sip_msg.get_header("call-id")
            if call_id:
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
                # Usar um usuário válido ou nome genérico para OPTIONS
                target_uri = f"sip:{self.ua.domain}:{self.ua.port}"

            tx_id = await self._sip_ua.send_options(target_uri)
            self._logger.log_transaction(tx_id, "OPTIONS", target_uri)
            return tx_id
        except Exception as e:
            self._logger.log_error(e, "sending OPTIONS")
            return None

    async def send_register(self, registrar_uri: str | None = None, expires: int = 3600):
        """Envia REGISTER usando sistema FSM"""
        try:
            if not registrar_uri:
                registrar_uri = f"sip:{self.ua.domain}:{self.ua.port}"

            tx_id = await self._sip_ua.send_register(registrar_uri, expires)
            self._logger.log_transaction(tx_id, "REGISTER", registrar_uri)
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

            return tx_id
        except Exception as e:
            self._logger.log_error(e, "sending INVITE")
            return None

    def add_credentials(self, realm: str, username: str, password: str):
        """Adiciona credenciais para autenticação SIP"""
        self._sip_ua.add_credentials(realm, username, password)
        self._logger.log_info(f"🔐 Added credentials for realm: {realm}", style="dim green")

    async def start_keep_alive(self, interval: int = 30):
        """Inicia keep-alive enviando OPTIONS periodicamente"""
        self._keep_alive_task = asyncio.create_task(self._keep_alive_loop(interval))

    async def _keep_alive_loop(self, interval: int):
        """Loop de keep-alive"""
        await asyncio.sleep(5)  # Aguardar inicialização

        while self._running:
            try:
                console.print("💓 [dim cyan]Keep-alive: enviando OPTIONS...[/dim cyan]")
                await self.send_options()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.log_error(e, "keep-alive OPTIONS")
                await asyncio.sleep(interval)


class MizuSIPDemo:
    """Demo cliente SIP para servidor Mizu-VoIP"""

    def __init__(self):
        self.client = None
        self._shutdown_event = asyncio.Event()

        # Configurar signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handler para sinais de interrupção"""
        console.print(f"\n🛑 [yellow]Recebido sinal {signum}, parando...[/yellow]")
        if self._shutdown_event:
            self._shutdown_event.set()

    async def run_demo(self):
        """Executa demo completo com servidor Mizu-VoIP"""
        console.print("\n🚀 [bold cyan]Demo TinySIP com Servidor Mizu-VoIP[/bold cyan]")
        console.print("📖 [dim]https://www.mizu-voip.com/DemoServer.aspx[/dim]")

        # Configurar logging
        setup_logging(level="INFO")

        # Configuração do servidor demo Mizu-VoIP
        # Credenciais válidas conforme documentação oficial
        ua = UserAgent(
            domain="demo.mizu-voip.com",
            port=37075,
            username="1111",
            password="1111xxx",
            realm="demo.mizu-voip.com",
            user_agent="TinySIP-Demo/1.0",
        )

        self.client = SIPClient(ua)

        try:
            # Iniciar cliente
            await self.client.start()
            console.print(
                f"🌐 [bold green]Conectado ao servidor demo:[/bold green] {ua.domain}:{ua.port}"
            )
            console.print(
                f"📍 [dim]Cliente rodando em:[/dim] {self.client._transport.local_address}"
            )

            # Adicionar credenciais
            self.client.add_credentials(ua.realm, ua.username, ua.password)

            # Iniciar keep-alive
            console.print("💓 [yellow]Iniciando keep-alive com OPTIONS (30s)...[/yellow]")
            await self.client.start_keep_alive(interval=30)

            # Aguardar um pouco antes de iniciar operações
            await asyncio.sleep(2)

            # 1. Enviar REGISTER
            console.print("\n📝 [bold yellow]1. Enviando REGISTER...[/bold yellow]")
            register_tx_id = await self.client.send_register(expires=300)
            if register_tx_id:
                console.print(f"✨ [green]REGISTER enviado, transaction:[/green] {register_tx_id}")

            await asyncio.sleep(3)

            # 2. Enviar INVITE
            console.print("\n📞 [bold yellow]2. Enviando INVITE com SDP...[/bold yellow]")
            target_number = "100"  # Número de teste do servidor Mizu
            target_uri = f"sip:{target_number}@{ua.domain}:{ua.port}"

            local_addr = self.client._transport.local_address
            sdp_offer = create_basic_audio_offer(local_addr[0])

            invite_tx_id = await self.client.send_invite(target_uri, sdp_body=sdp_offer)
            if invite_tx_id:
                console.print(
                    f"✨ [green]INVITE enviado para {target_number}, "
                    f"transaction:[/green] {invite_tx_id}"
                )

            # 3. Aguardar algumas mensagens e finalizar
            console.print("\n⏳ [bold blue]Aguardando respostas (30 segundos)...[/bold blue]")
            console.print("[dim]O keep-alive continuará por mais 30 segundos[/dim]")

            # Aguardar 30 segundos ou sinal de shutdown
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=30.0)
            except TimeoutError:
                console.print("⏰ [yellow]Tempo limite atingido, finalizando...[/yellow]")

        except Exception as e:
            console.print(
                Panel(f"{type(e).__name__}: {str(e)}", title="💥 Demo Error", border_style="red")
            )
        finally:
            if self.client:
                await self.client.stop()
            console.print("👋 [green]Demo finalizado[/green]")


async def run_simple_test():
    """Teste simples sem keep-alive contínuo"""
    console.print("\n🧪 [bold cyan]Teste Simples Mizu-VoIP[/bold cyan]")

    setup_logging(level="WARNING")

    # Credenciais válidas conforme documentação oficial da Mizu-VoIP
    ua = UserAgent(
        domain="demo.mizu-voip.com",
        port=37075,
        username="1111",
        password="1111xxx",
        realm="demo.mizu-voip.com",
    )

    client = SIPClient(ua)

    try:
        await client.start()
        client.add_credentials(ua.realm, ua.username, ua.password)

        # Sequência simples
        console.print("📤 Enviando OPTIONS...")
        await client.send_options()
        await asyncio.sleep(2)

        console.print("📝 Enviando REGISTER...")
        await client.send_register()
        await asyncio.sleep(3)

        console.print("📞 Enviando INVITE...")
        await client.send_invite(f"sip:100@{ua.domain}:{ua.port}")
        await asyncio.sleep(5)

        console.print("✅ Teste concluído")

    except Exception as e:
        console.print(f"❌ Erro: {e}")
    finally:
        await client.stop()


async def main():
    """Função principal"""
    console.print("\n🔥 [bold red]TinySIP[/bold red] - [bold]Demo Mizu-VoIP[/bold]")
    console.print("1. [cyan]Demo completo com keep-alive[/cyan]")
    console.print("2. [cyan]Teste simples[/cyan]")

    try:
        choice = input("\nEscolha (1 ou 2): ").strip()

        if choice == "1":
            demo = MizuSIPDemo()
            await demo.run_demo()
        elif choice == "2":
            await run_simple_test()
        else:
            console.print("❌ [red]Escolha inválida[/red]")
    except KeyboardInterrupt:
        console.print("\n🛑 [yellow]Interrompido pelo usuário[/yellow]")
    except EOFError:
        console.print("\n🛑 [yellow]Entrada fechada[/yellow]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n🛑 [yellow]Interrompido pelo usuário[/yellow]")
    except Exception as e:
        console.print(
            Panel(f"{type(e).__name__}: {str(e)}", title="💥 Fatal Error", border_style="red")
        )
