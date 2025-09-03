import re
from enum import Enum
from typing import TYPE_CHECKING, Optional, Union
from urllib.parse import unquote

if TYPE_CHECKING:
    from tinysip.sdp import SDPSession


class SIPMethod(Enum):
    INVITE = "INVITE"
    ACK = "ACK"
    OPTIONS = "OPTIONS"
    BYE = "BYE"
    CANCEL = "CANCEL"
    REGISTER = "REGISTER"
    INFO = "INFO"
    MESSAGE = "MESSAGE"


class SIPStatusCode(Enum):
    # 1xx Provisional
    TRYING = 100
    RINGING = 180
    SESSION_PROGRESS = 183

    # 2xx Success
    OK = 200
    ACCEPTED = 202

    # 3xx Redirection
    MULTIPLE_CHOICES = 300
    MOVED_PERMANENTLY = 301

    # 4xx Client Error
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405

    # 5xx Server Error
    INTERNAL_SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503

    # 6xx Global Failure
    BUSY_EVERYWHERE = 600
    DECLINE = 603


class SIPURI:
    """Classe para URIs SIP (sip: ou sips:)"""

    def __init__(self, uri: str):
        self.raw_uri = uri.strip()
        self.scheme = "sip"
        self.user = None
        self.password = None
        self.host = ""
        self.port = None
        self.parameters = {}
        self.headers = {}
        self._parse()

    def _parse(self):
        """Parse básico do URI"""
        if not self.raw_uri:
            return

        # Remove scheme
        if ":" in self.raw_uri:
            scheme_part, rest = self.raw_uri.split(":", 1)
            self.scheme = scheme_part.lower()
        else:
            return

        # Separar headers (após ?)
        if "?" in rest:
            rest, headers_part = rest.split("?", 1)
            for header in headers_part.split("&"):
                if "=" in header:
                    key, value = header.split("=", 1)
                    self.headers[key] = unquote(value)

        # Separar parâmetros (após ;)
        if ";" in rest:
            rest, params_part = rest.split(";", 1)
            for param in params_part.split(";"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    self.parameters[key] = value
                else:
                    self.parameters[param] = True

        # Parse user@host:port
        if "@" in rest:
            user_part, host_part = rest.rsplit("@", 1)
            if ":" in user_part:
                self.user, self.password = user_part.split(":", 1)
            else:
                self.user = user_part
        else:
            host_part = rest

        # Parse host:port
        if ":" in host_part and not host_part.startswith("["):
            self.host, port_str = host_part.rsplit(":", 1)
            try:
                self.port = int(port_str)
            except ValueError:
                self.host = host_part
        else:
            self.host = host_part

    def __str__(self):
        return self.raw_uri

    @property
    def is_secure(self) -> bool:
        return self.scheme == "sips"


class SIPHeader:
    """Classe para headers SIP"""

    def __init__(self, name: str, value: str):
        self.name = name.strip()
        self.value = value.strip()

    def validate(self) -> bool:
        """Validação básica do header"""
        if not self.name or not self.value:
            return False

        # Nome deve ser um token válido
        if not re.match(r"^[A-Za-z0-9!#$%&'*+\-.^_`|~]+$", self.name):
            return False

        # Valor não deve ter caracteres de controle
        if re.search(r"[\x00-\x08\x0A-\x1F\x7F]", self.value):
            return False

        return True

    def encode(self) -> str:
        """Codifica header para formato SIP"""
        return f"{self.name}: {self.value}"

    def __str__(self):
        return self.encode()


class SIPBody:
    """Classe para corpo SIP"""

    def __init__(self, content: Union[str, "SDPSession"], content_type: str = "text/plain"):
        # Importação lazy para evitar circular imports
        try:
            from tinysip.sdp import SDPSession

            if isinstance(content, SDPSession):
                self.content = str(content)
                self.content_type = "application/sdp"
                self.sdp = content
            else:
                self.content = content
                self.content_type = content_type
                self.sdp = None
        except ImportError:
            # Fallback se SDP não estiver disponível
            self.content = str(content)
            self.content_type = content_type
            self.sdp = None

    @property
    def content_length(self) -> int:
        """Retorna o tamanho do conteúdo em bytes"""
        return len(self.content.encode("utf-8"))

    @property
    def is_sdp(self) -> bool:
        """Verifica se o corpo contém SDP"""
        return self.content_type == "application/sdp" or self.sdp is not None

    def get_sdp(self) -> Optional["SDPSession"]:
        """Retorna objeto SDP se disponível"""
        if self.sdp:
            return self.sdp

        if self.is_sdp:
            try:
                from tinysip.sdp import SDPSession

                return SDPSession.parse(self.content)
            except Exception:
                return None

        return None

    def validate(self) -> bool:
        """Validação básica do corpo"""
        # Validar Content-Type básico
        if not re.match(r"^[a-zA-Z]+/[a-zA-Z0-9\-\+\.]+", self.content_type):
            return False

        # Se for SDP, validar estrutura SDP
        if self.is_sdp:
            sdp = self.get_sdp()
            if sdp:
                is_valid, _ = sdp.validate()
                return is_valid

        return True

    def encode(self) -> str:
        """Codifica corpo para formato SIP"""
        return self.content

    def __str__(self):
        return self.content


class SIPMessage:
    """Classe principal para mensagens SIP"""

    # Headers obrigatórios
    REQUIRED_HEADERS = ["via", "from", "to", "call-id", "cseq", "max-forwards"]

    # Reason phrases padrão
    REASON_PHRASES = {
        100: "Trying",
        180: "Ringing",
        183: "Session Progress",
        200: "OK",
        202: "Accepted",
        300: "Multiple Choices",
        301: "Moved Permanently",
        302: "Moved Temporarily",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
        501: "Not Implemented",
        502: "Bad Gateway",
        503: "Service Unavailable",
        600: "Busy Everywhere",
        603: "Decline",
    }

    def __init__(self):
        self.headers: list[SIPHeader] = []
        self.body: SIPBody | None = None

        # Request attributes
        self.method: SIPMethod | None = None
        self.uri: SIPURI | None = None

        # Response attributes
        self.status_code: int | None = None
        self.reason_phrase: str | None = None

        self.sip_version = "SIP/2.0"

    @classmethod
    def create_request(
        cls,
        method: SIPMethod,
        uri: str,
        extra_headers: dict[str, str] | None = None,
        body: Union[str, "SDPSession", SIPBody] | None = None,
    ) -> "SIPMessage":
        """Cria uma mensagem de request genérica"""
        msg = cls()
        msg.method = method
        msg.uri = SIPURI(uri)

        # Adicionar headers extras se fornecidos
        if extra_headers:
            for name, value in extra_headers.items():
                msg.add_header(name, value)

        # Adicionar body se fornecido
        if body:
            if isinstance(body, SIPBody):
                msg.body = body
            else:
                msg.body = SIPBody(body)

        return msg

    @classmethod
    def create_response(
        cls,
        status_code: int,
        reason_phrase: str | None = None,
        request: "SIPMessage | None" = None,
        extra_headers: dict[str, str] | None = None,
        body: Union[str, "SDPSession", SIPBody] | None = None,
    ) -> "SIPMessage":
        """Cria uma mensagem de response, opcionalmente baseada em um request"""
        msg = cls()
        msg.status_code = status_code
        msg.reason_phrase = reason_phrase or cls.REASON_PHRASES.get(status_code, "Unknown")

        # Se um request foi fornecido, copiar headers relevantes
        if request and request.is_request:
            # Copiar headers essenciais do request
            for header_name in ["call-id", "cseq", "from"]:
                header_value = request.get_header(header_name)
                if header_value:
                    msg.add_header(header_name.title(), header_value)

            # Para Via, copiar mas sem modificar branch
            via_value = request.get_header("via")
            if via_value:
                msg.add_header("Via", via_value)

            # Para To, adicionar tag se não existir (apenas em responses)
            to_value = request.get_header("to")
            if to_value:
                if ";tag=" not in to_value.lower():
                    to_value += f";tag={id(msg)}"
                msg.add_header("To", to_value)

        # Adicionar headers extras se fornecidos
        if extra_headers:
            for name, value in extra_headers.items():
                msg.set_header(name, value)  # usar set_header para sobrescrever se necessário

        # Adicionar body se fornecido
        if body:
            if isinstance(body, SIPBody):
                msg.body = body
            else:
                msg.body = SIPBody(body)

        return msg

    @classmethod
    def parse(cls, message: str) -> "SIPMessage":
        """Parse de uma mensagem SIP raw"""
        msg = cls()
        lines = message.strip().split("\r\n")

        if not lines:
            raise ValueError("Mensagem SIP vazia")

        # Parse primeira linha
        first_line = lines[0].strip()
        if first_line.startswith("SIP/"):
            # Response: SIP/2.0 200 OK
            parts = first_line.split(" ", 2)
            if len(parts) >= 2:
                msg.status_code = int(parts[1])
                msg.reason_phrase = parts[2] if len(parts) > 2 else ""
        else:
            # Request: OPTIONS sip:user@host SIP/2.0
            parts = first_line.split(" ", 2)
            if len(parts) >= 2:
                msg.method = SIPMethod(parts[0])
                msg.uri = SIPURI(parts[1])

        # Parse headers
        empty_line_idx = -1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "":
                empty_line_idx = i
                break

            if ":" in line:
                name, value = line.split(":", 1)
                msg.add_header(name.strip(), value.strip())

        # Parse body se existir
        if empty_line_idx > 0 and empty_line_idx + 1 < len(lines):
            body_lines = lines[empty_line_idx + 1 :]
            body_content = "\r\n".join(body_lines)
            if body_content.strip():
                content_type = "text/plain"
                for header in msg.headers:
                    if header.name.lower() == "content-type":
                        content_type = header.value
                        break
                msg.body = SIPBody(body_content, content_type)

        return msg

    def add_header(self, name: str, value: str):
        """Adiciona um header"""
        header = SIPHeader(name, value)
        self.headers.append(header)

    def get_header(self, name: str) -> str | None:
        """Obtém valor de um header"""
        name_lower = name.lower()
        for header in self.headers:
            if header.name.lower() == name_lower:
                return header.value
        return None

    def set_header(self, name: str, value: str):
        """Define ou atualiza um header"""
        name_lower = name.lower()
        for header in self.headers:
            if header.name.lower() == name_lower:
                header.value = value
                return
        self.add_header(name, value)

    def remove_header(self, name: str):
        """Remove um header"""
        name_lower = name.lower()
        self.headers = [h for h in self.headers if h.name.lower() != name_lower]

    def set_body(
        self, content: Union[str, "SDPSession", SIPBody], content_type: str = "text/plain"
    ):
        """Define o corpo da mensagem"""
        if isinstance(content, SIPBody):
            self.body = content
        else:
            self.body = SIPBody(content, content_type)

        # Atualiza headers relacionados
        self.set_header("Content-Type", self.body.content_type)
        self.set_header("Content-Length", str(self.body.content_length))

    def validate(self) -> tuple[bool, list[str]]:
        """Valida a mensagem SIP"""
        errors = []

        # Validar tipo de mensagem
        if not self.method and not self.status_code:
            errors.append("Mensagem deve ser request ou response")

        # Validar headers obrigatórios (apenas para requests)
        if self.method:
            header_names = [h.name.lower() for h in self.headers]
            for required in self.REQUIRED_HEADERS:
                if required not in header_names:
                    errors.append(f"Header obrigatório ausente: {required}")

        # Validar headers individuais
        for header in self.headers:
            if not header.validate():
                errors.append(f"Header inválido: {header.name}")

        # Validar corpo se existir
        if self.body and not self.body.validate():
            errors.append("Corpo da mensagem inválido")

        # Validar URI em requests
        if self.method and self.uri and not self.uri.host:
            errors.append("URI deve conter host válido")

        return len(errors) == 0, errors

    def encode(self) -> bytes:
        """Codifica mensagem para bytes"""
        lines = []

        # Primeira linha
        if self.method:
            # Request line
            lines.append(f"{self.method.value} {self.uri} {self.sip_version}")
        else:
            # Status line
            lines.append(f"{self.sip_version} {self.status_code} {self.reason_phrase}")

        # Headers
        for header in self.headers:
            lines.append(header.encode())

        # Adicionar Content-Length se não existir e houver body
        if self.body and not self.get_header("content-length"):
            lines.append(f"Content-Length: {self.body.content_length}")

        # Linha vazia separando headers do body
        lines.append("")

        # Body
        if self.body:
            lines.append(self.body.encode())

        message_str = "\r\n".join(lines)
        return message_str.encode("utf-8")

    def __str__(self):
        return self.encode().decode("utf-8")

    @property
    def is_request(self) -> bool:
        """Verifica se é uma mensagem de request"""
        return self.method is not None

    @property
    def is_response(self) -> bool:
        """Verifica se é uma mensagem de response"""
        return self.status_code is not None


# Aliases para compatibilidade
SIPRequestURI = SIPURI
SIPResponseURI = SIPURI
