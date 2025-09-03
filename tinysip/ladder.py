"""
Exemplo sngrep

           172.19.112.223:57471          148.251.28.187:37075
          ──────────┬─────────          ──────────┬─────────
  16:46:04.603249   │  INV (172.19.112.223:5004)  │
                    │    audio 5004 (g711u)       │
        +0.266899   │ ──────────────────────────> │
  16:46:04.870148   │         100 Trying          │
        +0.046929   │ <────────────────────────── │
  16:46:04.917077   │      401 Unauthorized       │
        +0.001137   │ <────────────────────────── │
  16:46:04.918214   │  INV (172.19.112.223:5004)  │
                    │    audio 5004 (g711u)       │
        +0.280005   │ ──────────────────────────> │
  16:46:05.198219   │         100 Trying          │
        +0.062966   │ <────────────────────────── │
  16:46:05.261185   │        404 Not Found        │
       +29.939578   │ <────────────────────────── │
  16:46:35.200763   │        404 Not Found        │
                    │ <<<──────────────────────── │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │                             │
                    │

(tiny-sip) ➜  tiny-sip git:(master) ✗ uv run tinysip/ladder.py
Found existing alias for "uv run". You should use: "uvr"
╭──────────────────────────────────────── SIP Call Flow Ladder ─────────────────────────────────────────╮
│                     10.10.1.142:5061               10.10.9.40:5060                10.10.1.245:5063    │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────╯
15:01:30.395894            │ ──────────INVITE───────────▶ │                              │
15:01:30.396222            │◀─────401 Unauthorized──────  │                              │
15:01:30.401112            │ ────────────ACK────────────▶ │                              │
15:01:30.405455            │ ───────INVITE (SDP)────────▶ │                              │
15:01:30.405906            │◀────────100 Trying─────────  │                              │
15:01:30.735636            │                              │ ───────INVITE (SDP)────────▶ │
15:01:30.741073            │                              │◀────────100 Trying─────────  │
15:01:30.755964            │                              │◀────────180 Ringing────────  │
15:01:30.756674            │◀────────180 Ringing────────  │                              │
15:01:32.435633            │                              │◀────────────BYE────────────  │
15:01:32.435880            │                              │ ──────────200 OK───────────▶ │

"""  # noqa: E501

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def color_for(method: str) -> str:
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


def render_sip_ladder(messages: list[dict], col_width: int = 23, gap: int = 6):
    # 1) Participantes na ordem de aparição
    participants = []
    for m in messages:
        for p in (m["source"], m["dest"]):
            if p not in participants:
                participants.append(p)

    # 2) Geometria do layout
    ts_width = 16  # área do timestamp
    n = len(participants)
    total_width = ts_width + n * col_width + (n - 1) * gap
    centers = [ts_width + i * (col_width + gap) + col_width // 2 for i in range(n)]

    # 3) Cabeçalho com IPs centralizados sobre as colunas
    header = Text()
    header.append(" " * ts_width)
    for i, p in enumerate(participants):
        header.append(p.center(col_width), style="bold white on grey23")
        if i < n - 1:
            header.append(" " * gap)
    console.print(Panel(header, title="SIP Call Flow Ladder", border_style="cyan", expand=False))

    # 4) Molde de linha com as linhas de vida preenchendo toda a largura
    lifeline_template = [" "] * total_width
    for c in centers:
        lifeline_template[c] = "│"  # mantém a coluna em TODOS os frames

    # 5) Renderização das mensagens
    for m in messages:
        row = lifeline_template.copy()

        # timestamp à esquerda
        ts = (m.get("timestamp") or "")[:ts_width].ljust(ts_width)
        row[:ts_width] = list(ts)

        # origem/destino e limites do traçado
        si, di = participants.index(m["source"]), participants.index(m["dest"])
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

        # rótulo centralizado entre draw_start e draw_end, evitando colunas
        label = m["method"] + (f" | {m['status']}" if m.get("status") else "")
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
        line.stylize(color_for(m["method"]), style_start, style_end)

        console.print(line)

    # legenda
    legend = Text.assemble(
        ("│", "dim"),
        (" lifeline  ", "dim"),
        ("─▶/◀", "bold white"),
        (" fluxo  ", "bold white"),
        ("1xx", "yellow"),
        (" provisional  ", "yellow"),
        ("2xx", "bold green"),
        (" sucesso  ", "bold green"),
        ("4xx-6xx", "bold red"),
        (" erro", "bold red"),
    )
    console.print(legend)


# Exemplo mínimo
if __name__ == "__main__":
    msgs = [
        {
            "timestamp": "15:01:30.395894",
            "source": "10.10.1.142:5061",
            "dest": "10.10.9.40:5060",
            "method": "INVITE",
        },
        {
            "timestamp": "15:01:30.396222",
            "source": "10.10.9.40:5060",
            "dest": "10.10.1.142:5061",
            "method": "401 Unauthorized",
        },
        {
            "timestamp": "15:01:30.401112",
            "source": "10.10.1.142:5061",
            "dest": "10.10.9.40:5060",
            "method": "ACK",
        },
        {
            "timestamp": "15:01:30.405455",
            "source": "10.10.1.142:5061",
            "dest": "10.10.9.40:5060",
            "method": "INVITE (SDP)",
        },
        {
            "timestamp": "15:01:30.405906",
            "source": "10.10.9.40:5060",
            "dest": "10.10.1.142:5061",
            "method": "100 Trying",
        },
        {
            "timestamp": "15:01:30.735636",
            "source": "10.10.9.40:5060",
            "dest": "10.10.1.245:5063",
            "method": "INVITE (SDP)",
        },
        {
            "timestamp": "15:01:30.741073",
            "source": "10.10.1.245:5063",
            "dest": "10.10.9.40:5060",
            "method": "100 Trying",
        },
        {
            "timestamp": "15:01:30.755964",
            "source": "10.10.1.245:5063",
            "dest": "10.10.9.40:5060",
            "method": "180 Ringing",
        },
        {
            "timestamp": "15:01:30.756674",
            "source": "10.10.9.40:5060",
            "dest": "10.10.1.142:5061",
            "method": "180 Ringing",
        },
        {
            "timestamp": "15:01:32.435633",
            "source": "10.10.1.245:5063",
            "dest": "10.10.9.40:5060",
            "method": "BYE",
        },
        {
            "timestamp": "15:01:32.435880",
            "source": "10.10.9.40:5060",
            "dest": "10.10.1.245:5063",
            "method": "200 OK",
        },
    ]
    render_sip_ladder(msgs, col_width=23, gap=8)
