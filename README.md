# Tiny SIP

Uma biblioteca SIP (Session Initiation Protocol) leve e moderna para Python 3.12+

## 🌟 Características

- ✅ **Implementação completa do RFC 3261** - Máquinas de estado para transações e diálogos SIP
- ✅ **Autenticação Digest SIP** - Suporte completo com challenge-response automático
- ✅ **Visualização de Call Flow** - Diagramas ladder em tempo real com Rich
- ✅ **Suporte a mídia** - RTP, codecs de áudio (PCMU, PCMA), DTMF
- ✅ **Transporte assíncrono** - UDP e TCP com suporte completo async/await
- ✅ **Logging rico** - Interface visual com Rich para debugging
- ✅ **Compatível com SIP servers** - Testado com Mizu-VoIP demo server

## 🚀 Início Rápido

### Pré-requisitos

- Python 3.12+
- UV (gerenciador de pacotes)

### Instalação

```bash
# Clone o repositório
git clone <repository-url>
cd tiny-sip

# Configure o ambiente de desenvolvimento
uv sync

# Configure o pre-commit (opcional)
uv run task pre-commit-install
```

## 💡 Exemplos de Uso

### Exemplo Básico com Servidor Demo

```bash
# Teste simples com o servidor demo Mizu-VoIP
echo "2" | uv run python mizu_example.py

# Demo completo com keep-alive
echo "1" | uv run python mizu_example.py
```

### Exemplo de Código

```python
import asyncio
from tinysip.fsm import SIPUserAgent, SIPTimers
from tinysip.transport import Transport, TransportConfig, TransportType

async def exemplo_sip():
    # Configurar transporte
    config = TransportConfig(
        remote_host="demo.mizu-voip.com",
        remote_port=37075,
        transport_type=TransportType.UDP
    )

    transport = Transport(config=config)

    # Criar User Agent
    ua = SIPUserAgent(
        transport=transport,
        local_uri="sip:1111@0.0.0.0",
        timers=SIPTimers()
    )

    # Adicionar credenciais
    ua.add_credentials("demo.mizu-voip.com", "1111", "1111")

    # Iniciar transporte
    await transport.start()

    # Enviar OPTIONS
    tx_id = await ua.send_options("sip:demo.mizu-voip.com:37075")
    print(f"OPTIONS enviado: {tx_id}")

    # Aguardar resposta
    await asyncio.sleep(2)

    await transport.stop()

# Executar
asyncio.run(exemplo_sip())
```

## 🎭 Saída do Demo

Aqui está um exemplo da saída visual do `mizu_example.py` em modo teste simples:

```
🔥 TinySIP - Demo Mizu-VoIP
1. Demo completo com keep-alive
2. Teste simples

Escolha (1 ou 2): 2
🧪 Teste Simples Mizu-VoIP
✅ SIP Client with FSM started
🔐 Added credentials for realm: demo.mizu-voip.com

📤 Enviando OPTIONS...
╭──────────────────────────── Transaction Started ─────────────────────────────╮
│ 🚀 Transaction ID: z9hG4bK434bdd4983f44573                                   │
│ 📋 Method: OPTIONS                                                           │
│ 🔄 Initial State: INITIAL                                                    │
╰──────────────────────────────────────────────────────────────────────────────╯

╭─ 📨 SIP 200 RESPONSE ← 148.251.28.187:37075 ─────────────────────────────────╮
│ SIP/2.0 200 OK                                                               │
│ Via: SIP/2.0/UDP 0.0.0.0;received=177.189.76.17;rport=64334                  │
│ From: <sip:1111@0.0.0.0>;tag=c48dcf6b                                        │
│ To: <sip:demo.mizu-voip.com:37075>;tag=a495899820399560                      │
│ Server: MizuVoIPServer 10.2                                                  │
│ Allow: ACK,BYE,CANCEL,INVITE,REGISTER,MESSAGE,INFO,OPTIONS                   │
╰──────────────────────────────────────────────────────────────────────────────╯

📝 Enviando REGISTER...
╭────────────────────────── Authentication Challenge ──────────────────────────╮
│ 🔐 Realm: demo.mizu-voip.com                                                 │
│ 🎲 Nonce: 10706362963400899768...                                            │
╰──────────────────────────────────────────────────────────────────────────────╯

╭────────────────────────── Authentication Response ───────────────────────────╮
│ 👤 Username: 1111                                                            │
│ 🔐 Realm: demo.mizu-voip.com                                                 │
│ 🌐 URI: sip:demo.mizu-voip.com:37075                                         │
╰──────────────────────────────────────────────────────────────────────────────╯

📞 Enviando INVITE...
✅ Teste concluído

📊 SIP Call Flow Summary por Diálogo

🎯 Call Flow Dialog: ea4914b8462042cbb44eb07cdb0ab061@0.0.0.0
╭──── 📞 SIP Call Flow Ladder - ea4914b8462042cbb44eb07cdb0ab061@0.0.0.0 ────╮
│                    172.19.112.223:33125           demo.mizu-voip.com:37075 │
│ 23:51:33                    │ ───────────OPTIONS───────────▶ │             │
│ 23:51:33                    │◀───────────200 OK────────────  │             │
╰────────────────────────────────────────────────────────────────────────────╯
📊 Duração: 10.0s  📨 Enviadas: 1  📥 Recebidas: 1  🔄 Total: 2

🎯 Call Flow Dialog: 46baf019a0b5432b875c684540fed273@0.0.0.0
╭──── 📞 SIP Call Flow Ladder - 46baf019a0b5432b875c684540fed273@0.0.0.0 ────╮
│                    172.19.112.223:33125           demo.mizu-voip.com:37075 │
│ 23:51:35                    │ ──────────REGISTER───────────▶ │             │
│ 23:51:35                    │◀─────────100 Trying──────────  │             │
│ 23:51:35                    │◀──────401 Unauthorized───────  │             │
│ 23:51:35                    │ ──────────REGISTER───────────▶ │             │
│ 23:51:36                    │◀─────────100 Trying──────────  │             │
│ 23:51:36                    │◀───────────200 OK────────────  │             │
╰────────────────────────────────────────────────────────────────────────────╯
📊 Duração: 8.0s  📨 Enviadas: 2  📥 Recebidas: 4  🔄 Total: 6

✅ SIP Client stopped
```

## 🔧 Comandos de Desenvolvimento

### Qualidade de Código

```bash
# Formatação de código
uv run task format

# Linting
uv run task lint

# Verificação de tipos
uv run task type

# Todos os checks de qualidade
uv run task quality
```

### Testes

```bash
# Executar todos os testes
uv run task test

# Testes com output verboso
uv run task test-v

# Testes com coverage
uv run task test-cov

# Testes rápidos (sem coverage)
uv run task test-fast

# Testes específicos por categoria
uv run task test-unit         # Apenas testes unitários
uv run task test-integration  # Apenas testes de integração
uv run task test-slow         # Apenas testes lentos
```

### Pipeline Completo

```bash
# Executar todo o pipeline de qualidade
uv run task all

# Ou por partes:
uv run task quality    # Formatação + Linting + Types + Testes rápidos
uv run task security   # Verificação de segurança
uv run task test-cov   # Testes com coverage
```

## 🏗️ Arquitetura

### Componentes Principais

- **`tinysip/fsm.py`** - Máquinas de estado SIP (RFC 3261)
- **`tinysip/auth.py`** - Autenticação Digest com re-auth automático
- **`tinysip/call_flow.py`** - Rastreamento e visualização de chamadas
- **`tinysip/transport.py`** - Camada de transporte UDP/TCP
- **`tinysip/message.py`** - Parsing e geração de mensagens SIP
- **`tinysip/media/`** - Suporte RTP, codecs e DTMF

### Estrutura do Projeto

```text
tinysip/
├── __init__.py          # Módulo principal
├── client.py            # Cliente SIP de alto nível
├── auth.py              # Autenticação Digest
├── fsm.py               # Máquinas de estado FSM
├── message.py           # Mensagens SIP
├── transport.py         # Transporte de rede
├── call_flow.py         # Rastreamento de call flows
├── ladder.py            # Diagramas ladder ASCII
├── sdp.py               # Session Description Protocol
├── dns.py               # Resolução DNS
├── logging_utils.py     # Logging com Rich
└── media/               # Suporte de mídia
    ├── rtp.py           # Real-time Transport Protocol
    ├── codecs.py        # Codecs de áudio
    ├── dtmf.py          # Tons DTMF
    └── audio.py         # Utilitários de áudio
```

## 🚀 CI/CD

### GitHub Actions

O CI está configurado com múltiplos jobs:

- **Lint Job**: Formatação, linting e type checking
- **Test Job**: Testes em Ubuntu, Windows, macOS com Python 3.12/3.13
- **Security Job**: Verificação de vulnerabilidades
- **Build Job**: Build de pacotes wheel/sdist

### Hooks Configurados

O pre-commit está configurado com os seguintes hooks:

- **Formatação**: Remove espaços extras, corrige finais de linha
- **Validação**: Verifica YAML, TOML, JSON
- **Ruff**: Formatação e linting de código Python
- **Ty**: Verificação de tipos
- **Testes**: Executados antes do push

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Faça commit das mudanças (`git commit -am 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

O pre-commit será executado automaticamente antes do commit e push.

## 📄 Licença

Este projeto está licenciado sob a Licença MIT.
