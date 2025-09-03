"""
Módulo centralizado de logging com Rich para TinySIP
"""

import logging

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Console global compartilhado
console = Console()


class RichConsoleHandler(logging.Handler):
    """Handler personalizado que usa Rich console diretamente"""

    def __init__(self, console: Console | None = None):
        super().__init__()
        self.console = console or Console()

    def emit(self, record):
        """Emitir log usando Rich console"""
        try:
            msg = record.getMessage()

            # Se a mensagem é um objeto Rich, renderizar diretamente
            if hasattr(record, "msg") and hasattr(record.msg, "__rich__"):
                self.console.print(record.msg)
            elif isinstance(record.msg, Panel | Text):
                self.console.print(record.msg)
            else:
                # Mensagem normal
                self.console.print(msg)
        except Exception:
            self.handleError(record)


class RichSIPLogger:
    """Logger personalizado com Rich para mensagens SIP"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)
        # Configurar handler personalizado para este logger apenas se não tiver
        if not self.logger.handlers:
            self.logger.addHandler(RichConsoleHandler(console))
            self.logger.setLevel(logging.DEBUG)
            self.logger.propagate = False  # Evitar propagação para root logger

    def log_sip_message_sent(
        self, message: str, destination: tuple[str, int], method: str | None = None
    ):
        """Log de mensagem SIP enviada com panel"""
        title = f"📤 SIP {method or 'MESSAGE'} SENT → {destination[0]}:{destination[1]}"
        panel = Panel(
            message.strip(), title=title, title_align="left", border_style="green", expand=False
        )
        self.logger.info(panel)

    def log_sip_message_received(
        self,
        message: str,
        source: tuple[str, int],
        method: str | None = None,
        status_code: int | None = None,
    ):
        """Log de mensagem SIP recebida com panel"""
        if status_code:
            title = f"📨 SIP {status_code} RESPONSE ← {source[0]}:{source[1]}"
            border_style = (
                "blue" if 200 <= status_code < 300 else "yellow" if status_code < 400 else "red"
            )
        else:
            title = f"📨 SIP {method or 'MESSAGE'} REQUEST ← {source[0]}:{source[1]}"
            border_style = "cyan"

        panel = Panel(
            message.strip(),
            title=title,
            title_align="left",
            border_style=border_style,
            expand=False,
        )
        self.logger.info(panel)

    def log_transaction(self, tx_id: str, method: str, target: str, status: str = "STARTED"):
        """Log de transação"""
        text = Text()
        text.append("🔄 ", style="bold cyan")
        text.append(f"Transaction {status}: ", style="bold")
        text.append(f"{tx_id}", style="bold blue")
        text.append(f" [{method}] → {target}", style="dim")
        self.logger.info(text)

    def log_error(self, error: Exception, context: str | None = None):
        """Log de erro com panel"""
        title = "❌ ERROR"
        if context:
            title += f" in {context}"

        error_text = f"{type(error).__name__}: {str(error)}"
        panel = Panel(error_text, title=title, title_align="left", border_style="red", expand=False)
        self.logger.info(panel)

    def log_info(self, message: str, style: str = ""):
        """Log de informação simples"""
        text = Text(message, style=style)
        self.logger.info(text)

    def log_success(self, message: str):
        """Log de sucesso"""
        text = Text()
        text.append("✅ ", style="bold green")
        text.append(message, style="green")
        self.logger.info(text)


# Função para configurar logging global
def setup_logging(level: str = "DEBUG") -> None:
    """Configura o sistema de logging global para TinySIP"""
    # Limpar handlers existentes para evitar duplicação
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configurar root logger com nosso handler
    FORMAT = "%(message)s"
    logging.basicConfig(
        level=level,
        format=FORMAT,
        datefmt="[%X]",
        handlers=[RichConsoleHandler(console)],
        force=True,  # Força reconfiguração
    )


# Função para obter logger configurado
def get_logger(name: str) -> logging.Logger:
    """Retorna um logger configurado para o módulo"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(RichConsoleHandler(console))
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger
