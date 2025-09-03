import re
import time
from dataclasses import dataclass, field
from enum import Enum


class SDPMediaType(Enum):
    """Tipos de media SDP"""

    AUDIO = "audio"
    VIDEO = "video"
    APPLICATION = "application"
    DATA = "data"
    CONTROL = "control"


class SDPCodecName(Enum):
    """Nomes de codecs SDP comuns"""

    # Audio codecs
    PCMU = "PCMU"  # G.711 u-law
    PCMA = "PCMA"  # G.711 A-law
    G722 = "G722"
    G729 = "G729"
    OPUS = "OPUS"
    TELEPHONE_EVENT = "telephone-event"  # DTMF

    # Video codecs
    H264 = "H264"
    VP8 = "VP8"
    VP9 = "VP9"


@dataclass
class SDPCodec:
    """Definicao completa de codec com parametros RFC 3264/8866"""

    name: str  # ex.: "PCMU", "PCMA", "telephone-event", "OPUS"
    clock: int  # ex.: 8000, 48000
    channels: int = 1  # audio: 1 por default
    fmtp: dict[str, str] = field(default_factory=dict)  # ex.: {"events": "0-16"}
    static_pt: int | None = None  # 0 (PCMU), 8 (PCMA), etc.

    @classmethod
    def from_enum(
        cls,
        codec_enum: SDPCodecName,
        clock: int = 8000,
        channels: int = 1,
        fmtp: dict[str, str] | None = None,
        static_pt: int | None = None,
    ) -> "SDPCodec":
        """Cria SDPCodec a partir do enum"""
        return cls(
            name=codec_enum.value,
            clock=clock,
            channels=channels,
            fmtp=fmtp or {},
            static_pt=static_pt,
        )


@dataclass
class SDPAttribute:
    """Atributo SDP (a=)"""

    name: str
    value: str | None = None

    def __str__(self) -> str:
        if self.value is not None:
            return f"a={self.name}:{self.value}"
        return f"a={self.name}"


@dataclass
class SDPMedia:
    """Descricao de media SDP (m=)"""

    media_type: SDPMediaType
    port: int
    protocol: str = "RTP/AVP"
    formats: list[str] = field(default_factory=list)
    attributes: list[SDPAttribute] = field(default_factory=list)

    # Connection info especifica da media
    connection_address: str | None = None
    connection_ttl: int | None = None

    def add_attribute(self, name: str, value: str | None = None):
        """Adiciona atributo a media"""
        self.attributes.append(SDPAttribute(name, value))

    def add_format(self, payload_type: int, codec: SDPCodec, clock_rate: int, channels: int = 1):
        """Adiciona formato de media"""
        self.formats.append(str(payload_type))

        # Adicionar atributo rtpmap
        self.add_attribute("rtpmap", f"{payload_type} {codec.name}/{clock_rate}")
        if channels > 1:
            self.add_attribute("rtpmap", f"{payload_type} {codec.name}/{clock_rate}/{channels}")

    def set_sendrecv(self, direction: str = "sendrecv"):
        """Define direcao da media (sendrecv, sendonly, recvonly, inactive)"""
        self.add_attribute(direction)

    def __str__(self) -> str:
        lines = []

        # Media line
        formats_str = " ".join(self.formats) if self.formats else "0"
        lines.append(f"m={self.media_type.value} {self.port} {self.protocol} {formats_str}")

        # Connection info se especifica para esta media
        if self.connection_address:
            if self.connection_ttl:
                lines.append(f"c=IN IP4 {self.connection_address}/{self.connection_ttl}")
            else:
                lines.append(f"c=IN IP4 {self.connection_address}")

        # Atributos
        for attr in self.attributes:
            lines.append(str(attr))

        return "\r\n".join(lines)


@dataclass
class SDPSession:
    """Sessao SDP completa"""

    # Session info obrigatoria
    version: int = 0
    origin_username: str = "-"
    session_id: str = field(default_factory=lambda: str(int(time.time())))
    session_version: str = field(default_factory=lambda: str(int(time.time())))
    origin_address: str = "127.0.0.1"
    session_name: str = "SIP Session"

    # Connection info global
    connection_address: str = "127.0.0.1"
    connection_ttl: int | None = None

    # Timing (obrigatorio)
    timing_start: int = 0
    timing_stop: int = 0

    # Attributes globais
    attributes: list[SDPAttribute] = field(default_factory=list)

    # Media descriptions
    media: list[SDPMedia] = field(default_factory=list)

    def add_attribute(self, name: str, value: str | None = None):
        """Adiciona atributo global a sessao"""
        self.attributes.append(SDPAttribute(name, value))

    def add_audio_media(
        self, port: int, codecs: list[tuple[int, SDPCodec, int]] | None = None
    ) -> SDPMedia:
        """Adiciona media de audio"""
        audio = SDPMedia(SDPMediaType.AUDIO, port)

        if codecs is None:
            # Codecs padrao
            pcmu_codec = SDPCodec.from_enum(SDPCodecName.PCMU, 8000)
            pcma_codec = SDPCodec.from_enum(SDPCodecName.PCMA, 8000)
            codecs = [
                (0, pcmu_codec, 8000),
                (8, pcma_codec, 8000),
            ]

        for pt, codec, rate in codecs:
            audio.add_format(pt, codec, rate)

        audio.set_sendrecv()
        self.media.append(audio)
        return audio

    def add_video_media(
        self, port: int, codecs: list[tuple[int, SDPCodec, int]] | None = None
    ) -> SDPMedia:
        """Adiciona media de video"""
        video = SDPMedia(SDPMediaType.VIDEO, port)

        if codecs is None:
            # Codecs padrao
            h264_codec = SDPCodec.from_enum(SDPCodecName.H264, 90000)
            codecs = [
                (96, h264_codec, 90000),
            ]

        for pt, codec, rate in codecs:
            video.add_format(pt, codec, rate)

        video.set_sendrecv()
        self.media.append(video)
        return video

    def create_answer(self, offer: "SDPSession") -> "SDPSession":
        """Cria answer SDP baseada em offer"""
        answer = SDPSession(
            session_id=str(int(time.time())),
            session_version=str(int(time.time())),
            origin_address=self.origin_address,
            connection_address=self.connection_address,
            session_name="SIP Answer",
        )

        # Responder a cada media do offer
        for offer_media in offer.media:
            if offer_media.media_type == SDPMediaType.AUDIO:
                # Aceitar audio com codecs compativeis
                pcmu_codec = SDPCodec.from_enum(SDPCodecName.PCMU, 8000)
                answer.add_audio_media(
                    port=offer_media.port,
                    codecs=[(0, pcmu_codec, 8000)],  # Simplificado
                )
            elif offer_media.media_type == SDPMediaType.VIDEO:
                # Aceitar video
                h264_codec = SDPCodec.from_enum(SDPCodecName.H264, 90000)
                answer.add_video_media(
                    port=offer_media.port,
                    codecs=[(96, h264_codec, 90000)],  # Simplificado
                )

        return answer

    def validate(self) -> tuple[bool, list[str]]:
        """Valida a sessao SDP"""
        errors = []

        # Verificar campos obrigatorios
        if not self.session_name:
            errors.append("Session name e obrigatorio")

        if not self.origin_address:
            errors.append("Origin address e obrigatorio")

        if not self.connection_address:
            errors.append("Connection address e obrigatorio")

        # Validar cada media
        for i, media in enumerate(self.media):
            if not media.formats:
                errors.append(f"Media {i} nao tem formatos definidos")

            if media.port < 0 or media.port > 65535:
                errors.append(f"Media {i} tem porta invalida: {media.port}")

        return len(errors) == 0, errors

    def encode(self) -> str:
        """Codifica sessao SDP para string"""
        lines = []

        # Version (obrigatorio)
        lines.append(f"v={self.version}")

        # Origin (obrigatorio)
        origin_line = (
            f"o={self.origin_username} {self.session_id} {self.session_version} "
            f"IN IP4 {self.origin_address}"
        )
        lines.append(origin_line)

        # Session name (obrigatorio)
        lines.append(f"s={self.session_name}")

        # Connection info (se nao especifica por media)
        if self.connection_ttl:
            lines.append(f"c=IN IP4 {self.connection_address}/{self.connection_ttl}")
        else:
            lines.append(f"c=IN IP4 {self.connection_address}")

        # Timing (obrigatorio)
        lines.append(f"t={self.timing_start} {self.timing_stop}")

        # Atributos globais
        for attr in self.attributes:
            lines.append(str(attr))

        # Media descriptions
        for media in self.media:
            lines.append(str(media))

        return "\r\n".join(lines) + "\r\n"

    def __str__(self) -> str:
        return self.encode()

    @classmethod
    def parse(cls, sdp_content: str) -> "SDPSession":
        """Parse de string SDP para objeto SDPSession"""
        session = cls()
        current_media = None

        lines = sdp_content.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line or "=" not in line:
                continue

            line_type, line_value = line.split("=", 1)

            if line_type == "v":
                session.version = int(line_value)
            elif line_type == "o":
                # o=username sess-id sess-version nettype addrtype address
                parts = line_value.split()
                if len(parts) >= 6:
                    session.origin_username = parts[0]
                    session.session_id = parts[1]
                    session.session_version = parts[2]
                    session.origin_address = parts[5]
            elif line_type == "s":
                session.session_name = line_value
            elif line_type == "c":
                # c=nettype addrtype connection-address
                if "IN IP4" in line_value:
                    addr_part = line_value.split("IN IP4")[1].strip()
                    if "/" in addr_part:
                        session.connection_address, ttl = addr_part.split("/")
                        session.connection_ttl = int(ttl)
                    else:
                        session.connection_address = addr_part
            elif line_type == "t":
                parts = line_value.split()
                if len(parts) >= 2:
                    session.timing_start = int(parts[0])
                    session.timing_stop = int(parts[1])
            elif line_type == "m":
                # m=media port proto fmt ...
                parts = line_value.split()
                if len(parts) >= 4:
                    media_type = SDPMediaType(parts[0])
                    port = int(parts[1])
                    protocol = parts[2]
                    formats = parts[3:]

                    current_media = SDPMedia(media_type, port, protocol, formats)
                    session.media.append(current_media)
            elif line_type == "a":
                # Atributo
                if ":" in line_value:
                    name, value = line_value.split(":", 1)
                    attr = SDPAttribute(name, value)
                else:
                    attr = SDPAttribute(line_value)

                if current_media:
                    current_media.attributes.append(attr)
                else:
                    session.attributes.append(attr)

        return session


class SDPNegotiator:
    """Classe para negociacao SDP"""

    def __init__(self):
        self.supported_audio_codecs = [
            (0, SDPCodec.from_enum(SDPCodecName.PCMU, 8000), 8000),
            (8, SDPCodec.from_enum(SDPCodecName.PCMA, 8000), 8000),
        ]
        self.supported_video_codecs = [
            (96, SDPCodec.from_enum(SDPCodecName.H264, 90000), 90000),
        ]

    def create_offer(
        self, local_ip: str = "127.0.0.1", audio_port: int = 5004, video_port: int = 5006
    ) -> SDPSession:
        """Cria offer SDP"""
        offer = SDPSession(
            origin_address=local_ip, connection_address=local_ip, session_name="TinySIP Offer"
        )

        # Adicionar audio
        offer.add_audio_media(audio_port, self.supported_audio_codecs)

        # Adicionar video (opcional)
        # offer.add_video_media(video_port, self.supported_video_codecs)

        return offer

    def create_answer(self, offer: SDPSession, local_ip: str = "127.0.0.1") -> SDPSession:
        """Cria answer SDP baseada em offer"""
        answer = SDPSession(
            origin_address=local_ip, connection_address=local_ip, session_name="TinySIP Answer"
        )

        # Processar cada media do offer
        for offer_media in offer.media:
            if offer_media.media_type == SDPMediaType.AUDIO:
                # Escolher codec compativel
                compatible_codec = self._find_compatible_audio_codec(offer_media.formats)
                if compatible_codec:
                    answer.add_audio_media(offer_media.port, [compatible_codec])
            elif offer_media.media_type == SDPMediaType.VIDEO:
                # Escolher codec compativel
                compatible_codec = self._find_compatible_video_codec(offer_media.formats)
                if compatible_codec:
                    answer.add_video_media(offer_media.port, [compatible_codec])

        return answer

    def _find_compatible_audio_codec(
        self, offered_formats: list[str]
    ) -> tuple[int, SDPCodec, int] | None:
        """Encontra codec de audio compativel"""
        for pt, codec, rate in self.supported_audio_codecs:
            if str(pt) in offered_formats:
                return (pt, codec, rate)
        return None

    def _find_compatible_video_codec(
        self, offered_formats: list[str]
    ) -> tuple[int, SDPCodec, int] | None:
        """Encontra codec de video compativel"""
        for pt, codec, rate in self.supported_video_codecs:
            if str(pt) in offered_formats:
                return (pt, codec, rate)
        return None


# Exemplo de uso
def create_basic_audio_offer(local_ip: str = "127.0.0.1") -> SDPSession:
    """Cria offer SDP basica para audio"""
    negotiator = SDPNegotiator()
    return negotiator.create_offer(local_ip)


def create_basic_audio_answer(offer_sdp: str, local_ip: str = "127.0.0.1") -> SDPSession:
    """Cria answer SDP basica para audio"""
    negotiator = SDPNegotiator()
    offer = SDPSession.parse(offer_sdp)
    return negotiator.create_answer(offer, local_ip)


# ======================= NOVA IMPLEMENTACAO RFC 3264/8866 =======================


@dataclass
class MediaCapability:
    """Capacidade de media com suporte completo RFC 3264"""

    media: str  # "audio" | "video" | "application"
    profile: str = "RTP/AVP"  # "RTP/AVP" | "RTP/SAVP"
    direction: str = "sendrecv"  # "sendrecv" | "sendonly" | "recvonly" | "inactive"
    codecs: list[SDPCodec] = field(default_factory=list)
    rtcp_mux: bool = True
    telephone_event_pt_pref: int = 101  # preferencia de PT dinamico
    port: int = 0  # porta local de media (0 para ofertar depois)


@dataclass
class SessionCapability:
    """Capacidade de sessao completa"""

    origin_user: str
    ip: str
    session_name: str = "TinySIP Session"
    version: int = 0
    timing: str = "0 0"
    audio: MediaCapability | None = None
    video: MediaCapability | None = None


# ---------- Representacoes parseadas ----------


@dataclass
class RtpMap:
    """Mapeamento RTP payload type"""

    pt: int
    encoding: str  # ex.: "PCMU", "telephone-event"
    clock: int
    channels: int = 1


@dataclass
class MediaDesc:
    """Descricao de media parseada"""

    media: str
    port: int
    proto: str
    fmts: list[int]
    conn_addr: str | None = None
    direction: str | None = None
    rtpmap: dict[int, RtpMap] = field(default_factory=dict)
    fmtp: dict[int, dict[str, str]] = field(default_factory=dict)
    rtcp_mux: bool = False


@dataclass
class SDPParsed:
    """SDP parseado para negociacao"""

    origin: str
    session_name: str
    connection: str | None
    timing: str
    media: list[MediaDesc]


# ---------- Parser SDP avancado (RFC 4566/8866) ----------


class SDPParser:
    """Parser SDP compativel RFC 4566/8866"""

    _re_m = re.compile(r"^m=([a-zA-Z]+)\s+(\d+)\s+([A-Z0-9/]+)\s+(.*)$")
    _re_c = re.compile(r"^c=IN\s+(IP4|IP6)\s+([^\s]+)$", re.IGNORECASE)
    _re_rtpmap = re.compile(r"^a=rtpmap:(\d+)\s+([A-Za-z0-9\-\._]+)/(\d+)(?:/(\d+))?$")
    _re_fmtp = re.compile(r"^a=fmtp:(\d+)\s+(.+)$")
    _re_dir = re.compile(r"^a=(sendrecv|sendonly|recvonly|inactive)$")

    @staticmethod
    def parse(sdp_text: str) -> SDPParsed:
        """Parse completo de SDP"""
        lines = [line.strip() for line in sdp_text.strip().splitlines() if line.strip()]
        origin = ""
        session_name = ""
        conn = None
        timing = ""
        media: list[MediaDesc] = []
        current_md: MediaDesc | None = None
        session_dir: str | None = None

        for ln in lines:
            if ln.startswith("o="):
                origin = ln[2:].strip()
            elif ln.startswith("s="):
                session_name = ln[2:].strip()
            elif ln.startswith("t="):
                timing = ln[2:].strip()
            elif ln.startswith("c="):
                m = SDPParser._re_c.match(ln)
                if m:
                    conn = m.group(2)
            elif ln.startswith("m="):
                m = SDPParser._re_m.match(ln)
                if not m:
                    continue
                if current_md:
                    media.append(current_md)
                md = MediaDesc(
                    media=m.group(1),
                    port=int(m.group(2)),
                    proto=m.group(3),
                    fmts=[int(x) for x in m.group(4).split()],
                )
                current_md = md
            elif ln.startswith("a=") and current_md:
                # media-level attributes
                m = SDPParser._re_rtpmap.match(ln)
                if m:
                    pt = int(m.group(1))
                    enc = m.group(2)
                    clock = int(m.group(3))
                    ch = int(m.group(4)) if m.group(4) else 1
                    current_md.rtpmap[pt] = RtpMap(pt, enc, clock, ch)
                    continue
                m = SDPParser._re_fmtp.match(ln)
                if m:
                    pt = int(m.group(1))
                    kvs = {}
                    for kv in m.group(2).split(";"):
                        kv = kv.strip()
                        if not kv:
                            continue
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            kvs[k.strip()] = v.strip()
                        else:
                            kvs[kv] = ""
                    current_md.fmtp[pt] = kvs
                    continue
                m = SDPParser._re_dir.match(ln)
                if m:
                    current_md.direction = m.group(1)
                    continue
                if ln == "a=rtcp-mux":
                    current_md.rtcp_mux = True
                    continue
            elif ln.startswith("a=") and not current_md:
                # session-level attributes
                m = SDPParser._re_dir.match(ln)
                if m:
                    session_dir = m.group(1)

        if current_md:
            media.append(current_md)
        # Propagar direcao default (sendrecv) e session-level override
        for md in media:
            md.direction = md.direction or session_dir or "sendrecv"
            md.conn_addr = md.conn_addr or conn
        return SDPParsed(origin, session_name, conn, timing or "0 0", media)


# ---------- Builder SDP avancado ----------


class SDPBuilder:
    """Builder SDP com suporte completo RFC 3264"""

    @staticmethod
    def _origin(user: str, ip: str, version: int) -> str:
        """Gera linha origin"""
        return f"o={user} {int(time.time())} {version} IN IP4 {ip}"

    @staticmethod
    def _rtpmap_line(pt: int, c: SDPCodec) -> str:
        """Gera linha rtpmap"""
        ch = f"/{c.channels}" if c.channels and c.channels != 1 else ""
        return f"a=rtpmap:{pt} {c.name}/{c.clock}{ch}"

    @staticmethod
    def _fmtp_line(pt: int, fmtp: dict[str, str]) -> str | None:
        """Gera linha fmtp se necessario"""
        if not fmtp:
            return None
        params = ";".join(f"{k}={v}" for k, v in fmtp.items())
        return f"a=fmtp:{pt} {params}"

    @staticmethod
    def build_offer(cap: SessionCapability) -> str:
        """Constroi offer SDP completo"""
        # Cabecalhos de sessao
        lines = []
        lines.append("v=0")
        lines.append(SDPBuilder._origin(cap.origin_user, cap.ip, cap.version))
        lines.append(f"s={cap.session_name}")
        lines.append(f"c=IN IP4 {cap.ip}")
        lines.append(f"t={cap.timing}")

        # Lista de midias
        for mcap in [cap.audio, cap.video]:
            if not mcap:
                continue
            # Alocar PTs: manter estaticos, atribuir dinamicos de 96..127
            dyn_pt_iter = (pt for pt in range(96, 128))
            pt_map: dict[str, int] = {}
            fmts: list[int] = []
            rtpmap_lines: list[str] = []
            fmtp_lines: list[str] = []
            for codec in mcap.codecs:
                if codec.static_pt is not None:
                    pt = codec.static_pt
                else:
                    # reservar PT preferido se telephone-event
                    if codec.name.lower() == "telephone-event":
                        pt = mcap.telephone_event_pt_pref
                    else:
                        pt = next(dyn_pt_iter)
                        if pt == mcap.telephone_event_pt_pref:
                            pt = next(dyn_pt_iter)
                pt_map[codec.name.lower()] = pt
                fmts.append(pt)
                # rtpmap/fmtp
                rtpmap_lines.append(SDPBuilder._rtpmap_line(pt, codec))
                fl = SDPBuilder._fmtp_line(pt, codec.fmtp)
                if fl:
                    fmtp_lines.append(fl)

            # m-line
            port = mcap.port if mcap.port else 0
            lines.append(f"m={mcap.media} {port} {mcap.profile} " + " ".join(str(x) for x in fmts))
            # direcao
            lines.append(f"a={mcap.direction}")
            # rtcp-mux se suportado
            if mcap.rtcp_mux:
                lines.append("a=rtcp-mux")
            # rtpmap/fmtp
            lines.extend(rtpmap_lines)
            lines.extend(fmtp_lines)

        return "\r\n".join(lines) + "\r\n"

    @staticmethod
    def build_answer(offer: SDPParsed, local: SessionCapability) -> str:
        """Constroi answer SDP seguindo RFC 3264"""
        # Cabecalhos de sessao
        lines = []
        lines.append("v=0")
        lines.append(SDPBuilder._origin(local.origin_user, local.ip, local.version))
        lines.append(f"s={local.session_name}")
        lines.append(f"c=IN IP4 {local.ip}")
        lines.append(f"t={offer.timing}")

        # Para cada m-line ofertada, gerar resposta correspondente
        for md in offer.media:
            # Selecionar a capacidade local correspondente
            mcap = (
                local.audio if md.media == "audio" else local.video if md.media == "video" else None
            )
            if not mcap:
                # rejeitar
                lines.append(f"m={md.media} 0 {md.proto} " + " ".join(str(x) for x in md.fmts))
                continue

            # Intersecao de codecs por nome/clock/channels
            local_codecs = {(c.name.lower(), c.clock, c.channels): c for c in mcap.codecs}
            # Cria lista de codecs remotos normalizados (inclui estaticos via mapa implicito)
            remote_codecs: list[tuple[int, tuple[str, int, int], dict[str, str]]] = []
            for pt in md.fmts:
                if pt in md.rtpmap:
                    r = md.rtpmap[pt]
                    key = (r.encoding.lower(), r.clock, r.channels)
                    fmtp = md.fmtp.get(pt, {})
                    remote_codecs.append((pt, key, fmtp))
                else:
                    # estaticos conhecidos
                    static_map = {0: ("pcmu", 8000, 1), 8: ("pcma", 8000, 1)}
                    if pt in static_map:
                        key = static_map[pt]
                        remote_codecs.append((pt, key, {}))

            # Ordenar por preferencia local (ordem dos codecs em mcap.codecs)
            local_order = {
                (c.name.lower(), c.clock, c.channels): idx for idx, c in enumerate(mcap.codecs)
            }
            remote_codecs.sort(key=lambda x: local_order.get(x[1], 9999))

            # Decidir formatos aceitos no sentido remoto->local:
            # anunciar PTs e rtpmap locais para a recepcao
            dyn_pt_iter = (pt for pt in range(96, 128))
            answer_fmts: list[int] = []
            rtpmap_lines: list[str] = []
            fmtp_lines: list[str] = []

            # Direcao: respeitar regras RFC 3264 §6.1
            off_dir = md.direction or "sendrecv"
            if off_dir == "sendonly":
                ans_dir = "recvonly"
            elif off_dir == "recvonly":
                ans_dir = "sendonly"
            elif off_dir == "inactive":
                ans_dir = "inactive"
            else:
                ans_dir = mcap.direction or "sendrecv"

            # Montar m-line answer
            # Se nao houver intersecao de codecs, rejeitar com port 0
            chosen_any = False
            # Primeiro, telephone-event se ambos suportam
            te_key = ("telephone-event", 8000, 1)
            if te_key in local_codecs:
                for _pt, key, rfmtp in remote_codecs:
                    if key == te_key:
                        # publicar nosso PT dinamico para TE
                        te_local = local_codecs[te_key]
                        te_pt = mcap.telephone_event_pt_pref
                        answer_fmts.append(te_pt)
                        rtpmap_lines.append(SDPBuilder._rtpmap_line(te_pt, te_local))
                        # Intersecao de eventos, se presente
                        events_remote = rfmtp.get("events")
                        events_local = te_local.fmtp.get("events")
                        events = events_local or events_remote or "0-16"
                        fl = SDPBuilder._fmtp_line(te_pt, {"events": events})
                        if fl:
                            fmtp_lines.append(fl)
                        chosen_any = True
                        break

            # Agora, codecs de audio regulares
            for _pt, key, _rfmtp in remote_codecs:
                if key in local_codecs and key != te_key:
                    lc = local_codecs[key]
                    # PT: estatico mantem valor fixo na semantica, mas no answer
                    # anunciamos PT que queremos que o remoto use ao nos enviar
                    if lc.static_pt is not None:
                        apt = lc.static_pt
                    else:
                        # evita colisao com te pt
                        apt = (
                            mcap.telephone_event_pt_pref
                            if lc.name.lower() == "telephone-event"
                            else next(dyn_pt_iter)
                        )
                        if (
                            apt == mcap.telephone_event_pt_pref
                            and lc.name.lower() != "telephone-event"
                        ):
                            apt = next(dyn_pt_iter)
                    if apt not in answer_fmts:
                        answer_fmts.append(apt)
                        rtpmap_lines.append(SDPBuilder._rtpmap_line(apt, lc))
                        fl = SDPBuilder._fmtp_line(apt, lc.fmtp)
                        if fl:
                            fmtp_lines.append(fl)
                        chosen_any = True

            if not chosen_any:
                lines.append(f"m={md.media} 0 {md.proto} " + " ".join(str(x) for x in md.fmts))
                continue

            # porta e perfil
            port = mcap.port if mcap.port else 0
            lines.append(
                f"m={md.media} {port} {mcap.profile} " + " ".join(str(x) for x in answer_fmts)
            )
            lines.append(f"a={ans_dir}")
            if mcap.rtcp_mux and md.rtcp_mux:
                lines.append("a=rtcp-mux")
            lines.extend(rtpmap_lines)
            lines.extend(fmtp_lines)

        return "\r\n".join(lines) + "\r\n"


# ---------- Resultados de negociacao ----------


@dataclass
class NegotiatedFormat:
    """Formato negociado com mapeamentos PT por direcao"""

    recv_pt: int  # PT que esperamos receber do par
    send_pt: int  # PT que usaremos para enviar
    codec: SDPCodec


@dataclass
class NegotiatedMedia:
    """Media negociada com todos os parametros"""

    media: str
    remote_addr: str
    remote_port: int
    direction: str
    formats: list[NegotiatedFormat]
    rtcp_mux: bool


# ---------- Negociador SDP completo ----------


class AdvancedSDPNegotiator:
    """Negociador SDP completo RFC 3264/8866"""

    def __init__(self):
        # Codecs padrao com suporte DTMF
        self.supported_audio_codecs = [
            SDPCodec.from_enum(SDPCodecName.PCMU, 8000, 1, static_pt=0),
            SDPCodec.from_enum(SDPCodecName.PCMA, 8000, 1, static_pt=8),
            SDPCodec.from_enum(SDPCodecName.TELEPHONE_EVENT, 8000, 1, {"events": "0-16"}),
        ]
        self.supported_video_codecs = [
            SDPCodec.from_enum(SDPCodecName.H264, 90000, 1),
        ]

    def create_offer(
        self, local_ip: str = "127.0.0.1", audio_port: int = 5004, video_port: int = 5006
    ) -> str:
        """Cria offer SDP completo com DTMF"""
        audio_cap = MediaCapability(
            media="audio",
            profile="RTP/AVP",
            direction="sendrecv",
            codecs=self.supported_audio_codecs.copy(),
            rtcp_mux=True,
            telephone_event_pt_pref=101,
            port=audio_port,
        )

        cap = SessionCapability(
            origin_user="tinysip",
            ip=local_ip,
            session_name="TinySIP Offer",
            version=0,
            audio=audio_cap,
        )

        return SDPBuilder.build_offer(cap)

    def create_answer(
        self, offer_sdp: str, local_ip: str = "127.0.0.1", audio_port: int = 5004
    ) -> str:
        """Cria answer SDP baseado em offer"""
        offer_parsed = SDPParser.parse(offer_sdp)

        audio_cap = MediaCapability(
            media="audio",
            profile="RTP/AVP",
            direction="sendrecv",
            codecs=self.supported_audio_codecs.copy(),
            rtcp_mux=True,
            telephone_event_pt_pref=101,
            port=audio_port,
        )

        local = SessionCapability(
            origin_user="tinysip",
            ip=local_ip,
            session_name="TinySIP Answer",
            version=0,
            audio=audio_cap,
        )

        return SDPBuilder.build_answer(offer_parsed, local)

    @staticmethod
    def negotiate_from_offer_answer(
        local_offer: SDPParsed, remote_answer: SDPParsed, local_caps: SessionCapability
    ) -> list[NegotiatedMedia]:
        """Calcula resultado da negociacao (mapeamentos PT e parametros)"""
        out: list[NegotiatedMedia] = []
        # Mapear m-lines por indice
        for idx, m_offer in enumerate(local_offer.media):
            if idx >= len(remote_answer.media):
                continue
            m_ans = remote_answer.media[idx]
            # Rejeitado?
            if m_ans.port == 0:
                continue
            # Direcao efetiva
            dir_eff = m_ans.direction or "sendrecv"
            # Addr remota
            raddr = m_offer.conn_addr or local_offer.connection or ""
            rport = m_ans.port
            # rtcp-mux efetivo
            mux = m_ans.rtcp_mux and m_offer.rtcp_mux
            # Formatos: construir pares (recv_pt, send_pt, codec)
            formats: list[NegotiatedFormat] = []
            # Local codecs indexados
            mcap = local_caps.audio if m_offer.media == "audio" else local_caps.video
            if not mcap:
                continue
            local_by_key = {(c.name.lower(), c.clock, c.channels): c for c in mcap.codecs}
            # Mapas de rtpmap para offer (nossos PT de envio) e answer (PT remoto para nos enviar)
            # Answer define os PTs que o remoto usara para enviar para nos
            for pt_ans, rtpmap_ans in m_ans.rtpmap.items():
                key = (rtpmap_ans.encoding.lower(), rtpmap_ans.clock, rtpmap_ans.channels)
                if key in local_by_key:
                    codec = local_by_key[key]
                    # Nosso PT de envio e aquele publicado no offer (m_offer.rtpmap)
                    send_pt = None
                    for pt_off, rtp_off in m_offer.rtpmap.items():
                        if (rtp_off.encoding.lower(), rtp_off.clock, rtp_off.channels) == key:
                            send_pt = pt_off
                            break
                    # Se estatico e nao havia rtpmap, inferir
                    if send_pt is None and codec.static_pt is not None:
                        send_pt = codec.static_pt
                    if send_pt is None:
                        continue
                    formats.append(NegotiatedFormat(recv_pt=pt_ans, send_pt=send_pt, codec=codec))
            out.append(
                NegotiatedMedia(
                    media=m_offer.media,
                    remote_addr=raddr,
                    remote_port=rport,
                    direction=dir_eff,
                    formats=formats,
                    rtcp_mux=mux,
                )
            )
        return out

    @staticmethod
    def next_reoffer_version(prev_origin_line: str) -> int:
        """Incrementa a versao do campo o= (RFC 3264 §8)"""
        try:
            parts = prev_origin_line.split()
            return int(parts[2]) + 1
        except Exception:
            return int(time.time())


# ---------- Funcoes auxiliares para compatibilidade ----------


def create_advanced_audio_offer(local_ip: str = "127.0.0.1", audio_port: int = 5004) -> str:
    """Cria offer SDP avancado com DTMF support"""
    negotiator = AdvancedSDPNegotiator()
    return negotiator.create_offer(local_ip, audio_port)


def create_advanced_audio_answer(
    offer_sdp: str, local_ip: str = "127.0.0.1", audio_port: int = 5004
) -> str:
    """Cria answer SDP avancado com DTMF support"""
    negotiator = AdvancedSDPNegotiator()
    return negotiator.create_answer(offer_sdp, local_ip, audio_port)
