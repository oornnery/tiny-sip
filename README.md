# Tiny SIP

Uma biblioteca SIP (Session Initiation Protocol) leve e moderna para Pytho### Hooks Configurados

O pre-commit está configurado com os seguintes hooks:

- **Formatação**: Remove espaços extras, corrige finais de linha
- **Validação**: Verifica YAML, TOML, JSON
- **Ruff**: Formatação e linting de código Python
- **Ty**: Verificação de tipos no commit
- **Testes**: Executados antes do push

## 🚀 CI/CD

### GitHub Actions

O CI está configurado com múltiplos jobs:

#### **Lint Job** (Code Quality)

- ✅ Formatação com Ruff
- ✅ Linting com Ruff
- ✅ Type checking com Ty

#### **Test Job** (Multi-platform)

- ✅ **Matrix strategy**: Ubuntu, Windows, macOS
- ✅ **Python versions**: 3.12, 3.13
- ✅ **Coverage**: Gerado no Ubuntu + Python 3.13
- ✅ **Codecov**: Upload automático de coverage
- ✅ **Artifacts**: Reports de coverage salvos

#### **Security Job**

- ✅ **Ruff security**: Verificação de vulnerabilidades
- ✅ **Dependency scan**: Checagem de dependências

#### **Build Job**

- ✅ **Package build**: Criação de wheel/sdist
- ✅ **Install test**: Verificação de instalação
- ✅ **Artifacts**: Pacotes salvos

#### **Pre-commit Job**

- ✅ **All hooks**: Execução de todos os hooks

### Triggers

- **Push**: `main`, `master`, `develop`
- **Pull Request**: `main`, `master`, `develop`
- **Schedule**: Testes diários às 2h UTC

### Cache

- ✅ **UV cache**: Dependências cacheadas
- ✅ **Python setup**: Otimizado com cache Início Rápido

### Pré-requisitos

- Python 3.12+
- UV (gerenciador de pacotes)

### Instalação para Desenvolvimento

```bash
# Clone o repositório
git clone <repository-url>
cd tiny-sip

# Configure o ambiente de desenvolvimento
uv sync

# Configure o pre-commit
uv run task pre-commit-install
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

### Pre-commit

```bash
# Executar pre-commit em todos os arquivos
uv run task pre-commit

# Ou executar diretamente
uv run pre-commit run --all-files
```

### Hooks Configurados

O pre-commit está configurado com os seguintes hooks:

- **Formatação**: Remove espaços extras, corrige finais de linha
- **Validação**: Verifica YAML, TOML, JSON
- **Ruff**: Formatação e linting de código Python
- **Ty**: Verificação de tipos
- **Testes**: Executados antes do push

## 📋 Estrutura do Projeto

```text
tinysip/
├── __init__.py      # Módulo principal
├── client.py        # Cliente SIP
├── auth.py          # Autenticação
├── fsm.py           # Máquina de estados
├── message.py       # Mensagens SIP
├── transport.py     # Transporte
├── media/           # Mídia (RTP, codecs)
└── protocol/        # Protocolo (headers, SDP, URIs)
```

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Faça commit das mudanças (`git commit -am 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

O pre-commit será executado automaticamente antes do commit e push.

## 📄 Licença

Este projeto está licenciado sob a Licença MIT.
