import asyncio
import logging
import re
import socket


class SIPDNSResolver:
    """Resolvedor DNS para SIP com suporte a registros SRV"""

    def __init__(self):
        self._logger = logging.getLogger("SIPDNSResolver")

    async def resolve_sip_target(self, uri: str) -> list[tuple[str, int, str]]:
        """
        Resolve URI SIP para lista de targets (host, port, transport)
        Retorna lista ordenada por prioridade
        """
        # Extrair domínio do URI
        domain = self._extract_domain(uri)
        if not domain:
            raise ValueError(f"Não foi possível extrair domínio de: {uri}")

        # Determinar se é SIP ou SIPS
        is_secure = uri.lower().startswith("sips:")

        # Tentar registros SRV
        srv_targets = await self._resolve_srv_records(domain, is_secure)

        if srv_targets:
            return srv_targets

        # Fallback: resolver A/AAAA record
        return await self._resolve_fallback(domain, is_secure)

    def _extract_domain(self, uri: str) -> str | None:
        """Extrai domínio do URI SIP"""
        # sip:user@domain ou sip:domain
        match = re.match(r"sips?:(?:[^@]+@)?([^;:/?]+)", uri, re.IGNORECASE)
        return match.group(1) if match else None

    async def _resolve_srv_records(
        self, domain: str, is_secure: bool
    ) -> list[tuple[str, int, str]]:
        """Resolve registros SRV para SIP"""
        targets = []

        # Definir queries SRV baseado em segurança
        if is_secure:
            queries = [f"_sips._tcp.{domain}", f"_sip._tls.{domain}"]
        else:
            queries = [f"_sips._tcp.{domain}", f"_sip._tcp.{domain}", f"_sip._udp.{domain}"]

        for query in queries:
            try:
                records = await self._query_srv(query)
                for priority, weight, port, target in records:
                    # Extrair protocolo do query
                    protocol = self._extract_protocol_from_query(query)
                    targets.append((target, port, protocol, priority, weight))
            except Exception as e:
                self._logger.debug(f"SRV query falhou para {query}: {e}")

        # Ordenar por prioridade e peso
        targets.sort(key=lambda x: (x[3], -x[4]))  # prioridade asc, peso desc

        # Retornar apenas (host, port, transport)
        return [(t[0], t[1], t[2]) for t in targets]

    def _extract_protocol_from_query(self, query: str) -> str:
        """Extrai protocolo do query SRV"""
        if "_sips._tcp" in query:
            return "TLS"
        elif "_sip._tcp" in query:
            return "TCP"
        elif "_sip._tls" in query:
            return "TLS"
        elif "_sip._udp" in query:
            return "UDP"
        return "UDP"

    async def _query_srv(self, query: str) -> list[tuple[int, int, int, str]]:
        """Query SRV usando socket (implementação básica)"""
        # Esta é uma implementação simplificada
        # Em produção, use dnspython ou similar

        try:
            # Para simplificar, vamos simular alguns resultados
            # Em implementação real, usar socket.getaddrinfo ou dnspython

            if "_sips._tcp" in query:
                return [(10, 60, 5061, "sip1.example.com"), (20, 40, 5061, "sip2.example.com")]
            elif "_sip._tcp" in query:
                return [(10, 60, 5060, "sip1.example.com"), (20, 40, 5060, "sip2.example.com")]
            elif "_sip._udp" in query:
                return [(30, 60, 5060, "sip1.example.com")]

            return []

        except Exception as e:
            self._logger.error(f"Erro na query SRV {query}: {e}")
            return []

    async def _resolve_fallback(self, domain: str, is_secure: bool) -> list[tuple[str, int, str]]:
        """Fallback para A/AAAA records"""
        try:
            # Resolver endereço IP
            loop = asyncio.get_running_loop()
            addrs = await loop.getaddrinfo(
                domain, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
            )

            if addrs:
                ip = addrs[0][4][0]
                port = 5061 if is_secure else 5060
                protocol = "TLS" if is_secure else "UDP"

                return [(ip, port, protocol)]

        except Exception as e:
            self._logger.error(f"Fallback resolution falhou para {domain}: {e}")

        return []
