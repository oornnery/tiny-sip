"""
SIP Call Flow Tracking and Ladder Diagram Generator
"""

import time
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from tinysip.message import SIPMessage

console = Console()


@dataclass
class SIPFlowEntry:
    """Entrada no fluxo de chamada SIP"""

    timestamp: str
    source: str
    dest: str
    method: str
    status: str | None = None
    transaction_id: str | None = None
    body_type: str | None = None  # SDP, RTP, etc.
    body_summary: str | None = None
    direction: str = "outbound"  # outbound/inbound


@dataclass
class SIPCallFlow:
    """Rastreamento completo de um fluxo de chamada SIP"""

    call_id: str
    local_address: str
    remote_address: str
    entries: list[SIPFlowEntry] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def add_outbound_message(
        self,
        dest: str,
        message: SIPMessage,
        transaction_id: str | None = None,
        body_summary: str | None = None,
    ):
        """Adiciona mensagem enviada"""
        timestamp = time.strftime("%H:%M:%S.%f")[:-3]

        if message.is_request:
            method = message.method.value if message.method else "UNKNOWN"
            status = None
        else:
            method = f"{message.status_code} {message.reason_phrase}"
            status = str(message.status_code)

        # Detectar tipo de body
        body_type = None
        if message.body:
            if message.body.is_sdp:
                body_type = "SDP"
                if not body_summary:
                    sdp = message.body.get_sdp()
                    if sdp and sdp.media:
                        # Extrair informações do SDP
                        codecs = []
                        for media in sdp.media:
                            for attr in media.attributes:
                                if attr.name == "rtpmap" and attr.value:
                                    # rtpmap format: "0 PCMU/8000"
                                    parts = attr.value.split(" ", 1)
                                    if len(parts) > 1:
                                        codec_info = parts[1].split("/")[0]
                                        codecs.append(codec_info)
                        if codecs and sdp.media:
                            media_port = sdp.media[0].port
                            codec_list = ", ".join(codecs[:2])  # Limit to first 2 codecs
                            body_summary = f"audio {media_port} ({codec_list})"
                        else:
                            body_summary = "audio"
            else:
                body_type = "TEXT"

        entry = SIPFlowEntry(
            timestamp=timestamp,
            source=self.local_address,
            dest=dest,
            method=method,
            status=status,
            transaction_id=transaction_id,
            body_type=body_type,
            body_summary=body_summary,
            direction="outbound",
        )
        self.entries.append(entry)

    def add_inbound_message(
        self,
        source: str,
        message: SIPMessage,
        transaction_id: str | None = None,
        body_summary: str | None = None,
    ):
        """Adiciona mensagem recebida"""
        timestamp = time.strftime("%H:%M:%S.%f")[:-3]

        if message.is_request:
            method = message.method.value if message.method else "UNKNOWN"
            status = None
        else:
            method = f"{message.status_code} {message.reason_phrase}"
            status = str(message.status_code)

        # Detectar tipo de body
        body_type = None
        if message.body:
            if message.body.is_sdp:
                body_type = "SDP"
                if not body_summary:
                    sdp = message.body.get_sdp()
                    if sdp and sdp.media:
                        # Extrair informações do SDP
                        codecs = []
                        for media in sdp.media:
                            for attr in media.attributes:
                                if attr.name == "rtpmap" and attr.value:
                                    # rtpmap format: "0 PCMU/8000"
                                    parts = attr.value.split(" ", 1)
                                    if len(parts) > 1:
                                        codec_info = parts[1].split("/")[0]
                                        codecs.append(codec_info)
                        if codecs and sdp.media:
                            media_port = sdp.media[0].port
                            codec_list = ", ".join(codecs[:2])  # Limit to first 2 codecs
                            body_summary = f"audio {media_port} ({codec_list})"
                        else:
                            body_summary = "audio"
            else:
                body_type = "TEXT"

        entry = SIPFlowEntry(
            timestamp=timestamp,
            source=source,
            dest=self.local_address,
            method=method,
            status=status,
            transaction_id=transaction_id,
            body_type=body_type,
            body_summary=body_summary,
            direction="inbound",
        )
        self.entries.append(entry)

    def render_ladder(self, col_width: int = 25, gap: int = 8) -> None:
        """Renderiza o ladder diagram do call flow"""
        if not self.entries:
            console.print("📭 [yellow]Nenhuma mensagem no call flow[/yellow]")
            return

        # 1) Participantes fixos: apenas local e remote
        participants = [self.local_address, self.remote_address]

        # 2) Geometria do layout
        ts_width = 16  # área do timestamp
        n = len(participants)
        total_width = ts_width + n * col_width + (n - 1) * gap
        centers = [ts_width + i * (col_width + gap) + col_width // 2 for i in range(n)]

        # 3) Cabeçalho com IPs centralizados sobre as colunas dentro do painel
        header = Text()
        header.append(" " * ts_width)
        for i, p in enumerate(participants):
            header.append(p.center(col_width), style="bold white on grey23")
            if i < n - 1:
                header.append(" " * gap)

        title = f"📞 SIP Call Flow Ladder - {self.call_id}"

        # Renderizar o painel com header e conteúdo
        ladder_content = []
        ladder_content.append(header)

        # 4) Molde de linha com as linhas de vida preenchendo toda a largura
        lifeline_template = [" "] * total_width
        for c in centers:
            lifeline_template[c] = "│"  # mantém a coluna em TODOS os frames

        # 5) Renderização das mensagens
        for entry in self.entries:
            row = lifeline_template.copy()

            # timestamp à esquerda
            ts = entry.timestamp[:ts_width].ljust(ts_width)
            row[:ts_width] = list(ts)

            # origem/destino e limites do traçado (normalizar endereços)
            # Mapear endereços reais para os participantes esperados
            source_addr = entry.source
            dest_addr = entry.dest

            # Se o destino é 0.0.0.0:5060 ou similar, mapear para o remote address
            if "0.0.0.0" in dest_addr:
                dest_addr = self.remote_address
            # Se a origem é diferente mas da mesma porta, usar local address
            if source_addr != self.local_address and dest_addr == self.local_address:
                # Mensagem recebida - origin deve ser mapeado para remote
                source_addr = self.remote_address
            elif source_addr != self.local_address and source_addr.startswith("148.251.28.187"):
                # IP real do servidor
                source_addr = self.remote_address

            # Para destino, se não for local nem remote, provavelmente é o remote real
            if dest_addr not in participants and source_addr == self.local_address:
                dest_addr = self.remote_address

            try:
                si = participants.index(source_addr)
                di = participants.index(dest_addr)
            except ValueError:
                # Se ainda não conseguir mapear, usar força bruta: local->remote sempre
                if entry.direction == "outbound":
                    si, di = 0, 1
                else:
                    si, di = 1, 0

            s, d = centers[si], centers[di]
            left, right = (s, d) if s < d else (d, s)
            # deixa a coluna intacta: inicia 2 casas após a coluna e termina 2 casas antes
            draw_start = left + 2
            draw_end = right - 2

            # trilho horizontal sem tocar nas colunas
            for x in range(draw_start, draw_end):
                if x not in centers:
                    row[x] = "─"

            # ponteiras antes das colunas de destino/origem
            if s < d:
                row[draw_end] = "▶"  # um passo antes da coluna de destino
            else:
                row[draw_start - 1] = "◀"  # um passo depois da coluna de destino (seta voltando)

            # rótulo com SDP info se disponível
            label = entry.method
            if entry.body_summary:
                label += f" ({entry.body_summary})"

            text_start = max(draw_start, (draw_start + draw_end - len(label)) // 2)
            text_end = min(draw_end, text_start + len(label))
            i_label = 0
            for x in range(text_start, text_end):
                if x not in centers and i_label < len(label):
                    row[x] = label[i_label]
                    i_label += 1

            # aplica estilo só na faixa do fluxo
            line = Text("".join(row))
            style_start = draw_start
            style_end = draw_end + 1
            line.stylize(self._color_for_method(entry.method), style_start, style_end)

            ladder_content.append(line)

        # Renderizar o painel completo
        panel_text = Text()
        for i, content in enumerate(ladder_content):
            if i > 0:  # Não adicionar quebra de linha antes do header
                panel_text.append("\n")
            panel_text.append_text(content)

        console.print(Panel(panel_text, title=title, border_style="cyan", expand=False))

        # 6) Estatísticas do call flow
        self._print_call_stats()

    def _color_for_method(self, method: str) -> str:
        """Determina cor baseada no método SIP"""
        m = method.upper()
        if m.startswith(("100", "180", "183")):
            return "yellow"
        if m.startswith("2"):
            return "bold green"
        if m[0:1] in {"3", "4", "5", "6"}:
            return "bold red"
        if "INVITE" in m:
            return "bold cyan"
        if "BYE" in m or "CANCEL" in m:
            return "red"
        if "ACK" in m:
            return "green"
        return "white"

    def _print_call_stats(self):
        """Imprime estatísticas do call flow"""
        duration = time.time() - self.start_time
        total_messages = len(self.entries)
        outbound_count = sum(1 for e in self.entries if e.direction == "outbound")
        inbound_count = sum(1 for e in self.entries if e.direction == "inbound")

        # Contar tipos de mensagem
        methods = {}
        for entry in self.entries:
            method = entry.method.split()[0]  # Pegar só o método (sem status)
            methods[method] = methods.get(method, 0) + 1

        stats = Text.assemble(
            ("📊 ", "bold blue"),
            (f"Duração: {duration:.1f}s  ", "dim"),
            ("📨 ", "green"),
            (f"Enviadas: {outbound_count}  ", "green"),
            ("📥 ", "cyan"),
            (f"Recebidas: {inbound_count}  ", "cyan"),
            ("🔄 ", "yellow"),
            (f"Total: {total_messages}  ", "yellow"),
            ("📋 ", "magenta"),
            (f"Métodos: {', '.join(f'{k}({v})' for k, v in methods.items())}", "magenta"),
        )
        console.print(stats)


class SIPCallFlowTracker:
    """Gerenciador de múltiplos call flows SIP"""

    def __init__(self):
        self.call_flows: dict[str, SIPCallFlow] = {}
        self.local_address: str = ""
        self.remote_address: str = ""

    def set_addresses(self, local_address: str, remote_address: str):
        """Define endereços local e remoto padrão"""
        self.local_address = local_address
        self.remote_address = remote_address

    def get_or_create_call_flow(self, call_id: str) -> SIPCallFlow:
        """Obtém ou cria um call flow para o Call-ID"""
        if call_id not in self.call_flows:
            flow = SIPCallFlow(
                call_id=call_id,
                local_address=self.local_address,
                remote_address=self.remote_address,
            )
            self.call_flows[call_id] = flow
        return self.call_flows[call_id]

    def start_call_flow(self, call_id: str, local_address: str, remote_address: str) -> SIPCallFlow:
        """Inicia um novo call flow"""
        flow = SIPCallFlow(
            call_id=call_id,
            local_address=local_address,
            remote_address=remote_address,
        )
        self.call_flows[call_id] = flow
        return flow

    def get_call_flow(self, call_id: str) -> SIPCallFlow | None:
        """Obtém call flow por call_id"""
        return self.call_flows.get(call_id)

    def add_outbound_message(
        self,
        call_id: str,
        dest: str,
        message: SIPMessage,
        transaction_id: str | None = None,
        body_summary: str | None = None,
    ):
        """Adiciona mensagem enviada ao call flow"""
        flow = self.get_or_create_call_flow(call_id)
        flow.add_outbound_message(dest, message, transaction_id, body_summary)

    def add_inbound_message(
        self,
        call_id: str,
        source: str,
        message: SIPMessage,
        transaction_id: str | None = None,
        body_summary: str | None = None,
    ):
        """Adiciona mensagem recebida ao call flow"""
        flow = self.get_or_create_call_flow(call_id)
        flow.add_inbound_message(source, message, transaction_id, body_summary)

    def render_all_flows(self):
        """Renderiza todos os call flows"""
        if not self.call_flows:
            console.print("📭 [yellow]Nenhum call flow encontrado[/yellow]")
            return

        for call_id, flow in self.call_flows.items():
            console.print(f"\n🎯 [bold]Call Flow Dialog: {call_id}[/bold]")
            flow.render_ladder()

    def render_current_flow(self):
        """Renderiza o último call flow criado"""
        if not self.call_flows:
            console.print("📭 [yellow]Nenhum call flow ativo[/yellow]")
            return

        # Pegar o call flow mais recente
        latest_flow = list(self.call_flows.values())[-1]
        latest_flow.render_ladder()

    def clear_flows(self):
        """Limpa todos os call flows"""
        self.call_flows.clear()
