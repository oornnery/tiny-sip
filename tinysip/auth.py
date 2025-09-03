import hashlib
import logging
import random
import re
import time

from tinysip.message import SIPMessage


class SIPDigestAuthentication:
    """Implementação de autenticação Digest para SIP (RFC 3261)"""

    def __init__(self):
        self.credentials: dict[str, tuple[str, str]] = {}  # realm -> (username, password)
        self.nonce_count: dict[str, int] = {}  # nonce -> count
        self._logger = logging.getLogger("SIPDigestAuth")

    def add_credentials(self, realm: str, username: str, password: str) -> None:
        """Adiciona credenciais para um realm"""
        self.credentials[realm] = (username, password)
        self._logger.debug(f"Credenciais adicionadas para realm: {realm}")

    def parse_www_authenticate(self, header_value: str) -> dict[str, str]:
        """
        Parse do header WWW-Authenticate ou Proxy-Authenticate
        Formato: Digest realm="...", nonce="...", ...
        """
        params = {}

        # Remove "Digest " do início
        if header_value.startswith("Digest "):
            header_value = header_value[7:]

        # Parse dos parâmetros
        for match in re.finditer(r'(\w+)=(?:"([^"]+)"|([^,\s]+))', header_value):
            key = match.group(1).lower()
            value = match.group(2) if match.group(2) is not None else match.group(3)
            params[key] = value

        self._logger.debug(f"Parâmetros de autenticação parseados: {list(params.keys())}")
        return params

    def generate_authorization_header(
        self, method: str, uri: str, auth_params: dict[str, str], body: str | None = None
    ) -> str:
        """
        Gera header Authorization baseado no challenge
        """
        realm = auth_params.get("realm", "")
        nonce = auth_params.get("nonce", "")
        opaque = auth_params.get("opaque")
        algorithm = auth_params.get("algorithm", "MD5").upper()
        qop = auth_params.get("qop")

        # Verificar se temos credenciais para este realm
        if realm not in self.credentials:
            raise ValueError(f"Sem credenciais para realm: {realm}")

        username, password = self.credentials[realm]

        # Gerar cnonce e nc
        cnonce = self._generate_cnonce()
        nc = self._get_nonce_count(nonce)

        # Calcular response
        response = self._calculate_response(
            username, realm, password, method, uri, nonce, nc, cnonce, qop, algorithm, body
        )

        # Construir header Authorization
        auth_header = (
            f'Digest username="{username}", realm="{realm}", '
            f'nonce="{nonce}", uri="{uri}", response="{response}"'
        )

        if algorithm:
            auth_header += f", algorithm={algorithm}"
        if opaque:
            auth_header += f', opaque="{opaque}"'
        if qop:
            auth_header += f', qop={qop}, nc={nc:08x}, cnonce="{cnonce}"'

        self._logger.debug("Header Authorization gerado")
        return auth_header

    def _calculate_response(
        self,
        username: str,
        realm: str,
        password: str,
        method: str,
        uri: str,
        nonce: str,
        nc: int,
        cnonce: str,
        qop: str | None,
        algorithm: str,
        body: str | None = None,
    ) -> str:
        """Calcula o response digest"""

        # Calcular HA1
        ha1 = self._calculate_ha1(username, realm, password, nonce, cnonce, algorithm)

        # Calcular HA2
        ha2 = self._calculate_ha2(method, uri, qop, body, algorithm)

        # Calcular response
        if qop in ["auth", "auth-int"]:
            response_data = f"{ha1}:{nonce}:{nc:08x}:{cnonce}:{qop}:{ha2}"
        else:
            response_data = f"{ha1}:{nonce}:{ha2}"

        response = self._hash_function(response_data, algorithm)

        self._logger.debug("Response digest calculado")
        return response

    def _calculate_ha1(
        self, username: str, realm: str, password: str, nonce: str, cnonce: str, algorithm: str
    ) -> str:
        """Calcula HA1"""
        base_ha1 = f"{username}:{realm}:{password}"
        ha1 = self._hash_function(base_ha1, algorithm)

        if algorithm.endswith("-sess"):
            ha1 = self._hash_function(f"{ha1}:{nonce}:{cnonce}", algorithm)

        return ha1

    def _calculate_ha2(
        self, method: str, uri: str, qop: str | None, body: str | None, algorithm: str
    ) -> str:
        """Calcula HA2"""
        if qop == "auth-int" and body is not None:
            body_hash = self._hash_function(body, algorithm)
            ha2_data = f"{method}:{uri}:{body_hash}"
        else:
            ha2_data = f"{method}:{uri}"

        return self._hash_function(ha2_data, algorithm)

    def _hash_function(self, data: str, algorithm: str) -> str:
        """Função de hash baseada no algoritmo"""
        if algorithm.startswith("MD5"):
            return hashlib.md5(data.encode("utf-8")).hexdigest()
        elif algorithm.startswith("SHA-256"):
            return hashlib.sha256(data.encode("utf-8")).hexdigest()
        else:
            raise ValueError(f"Algoritmo não suportado: {algorithm}")

    def _generate_cnonce(self) -> str:
        """Gera client nonce"""
        return hashlib.md5(f"{random.random()}{time.time()}".encode()).hexdigest()[:16]

    def _get_nonce_count(self, nonce: str) -> int:
        """Obtém e incrementa nonce count"""
        if nonce not in self.nonce_count:
            self.nonce_count[nonce] = 0

        self.nonce_count[nonce] += 1
        return self.nonce_count[nonce]

    def handle_authentication_challenge(
        self, response: SIPMessage, original_request: SIPMessage
    ) -> str | None:
        """
        Processa challenge de autenticação SIP e retorna header Authorization
        """
        if response.status_code not in [401, 407]:
            return None

        # Obter header de autenticação
        auth_header_name = (
            "WWW-Authenticate" if response.status_code == 401 else "Proxy-Authenticate"
        )
        auth_header = response.get_header(auth_header_name.lower())

        if not auth_header:
            return None

        # Parse do challenge
        auth_params = self.parse_www_authenticate(auth_header)

        # Gerar resposta
        try:
            if original_request.method is None:
                raise ValueError("Request method is None")
            method = original_request.method.value
            uri = str(original_request.uri)
            body = str(original_request.body) if original_request.body else None

            return self.generate_authorization_header(method, uri, auth_params, body)

        except Exception as e:
            self._logger.error(f"Erro ao gerar authorization: {e}")
            return None

    def create_authenticated_request(
        self, original_request: SIPMessage, auth_response: SIPMessage
    ) -> SIPMessage:
        """
        Cria nova requisição com header de autenticação baseada no challenge
        """
        auth_header = self.handle_authentication_challenge(auth_response, original_request)
        if not auth_header:
            return original_request

        # Criar nova mensagem com mesmo conteúdo
        if original_request.method is None:
            return original_request
        new_request = SIPMessage.create_request(
            original_request.method, str(original_request.uri), body=original_request.body
        )

        # Copiar todos os headers do original EXCETO Via (que precisa de novo branch)
        for header in original_request.headers:
            if header.name.lower() != "via":
                new_request.add_header(header.name, header.value)

        # Gerar novo branch ID para nova transação
        import uuid

        new_branch = f"z9hG4bK{uuid.uuid4().hex[:16]}"

        # Adicionar novo Via header com novo branch
        via_header = original_request.get_header("via")
        if via_header:
            # Substituir o branch no Via header original
            import re

            new_via = re.sub(r"branch=[^;]+", f"branch={new_branch}", via_header)
            new_request.set_header("Via", new_via)
        else:
            # Criar novo Via header se não existir
            new_request.set_header("Via", f"SIP/2.0/UDP 0.0.0.0;branch={new_branch}")

        # Adicionar/substituir header de autorização
        header_name = "Authorization" if auth_response.status_code == 401 else "Proxy-Authorization"
        new_request.set_header(header_name, auth_header)

        # Incrementar CSeq
        cseq_header = new_request.get_header("cseq")
        if cseq_header:
            parts = cseq_header.split()
            if len(parts) >= 2:
                new_cseq = int(parts[0]) + 1
                new_request.set_header("CSeq", f"{new_cseq} {parts[1]}")

        return new_request
