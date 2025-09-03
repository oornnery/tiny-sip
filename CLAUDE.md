# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TinySIP is a lightweight, modern SIP (Session Initiation Protocol) library for Python 3.12+. The project implements a complete SIP user agent with support for authentication, finite state machines, media handling, transport layers, and rich call flow visualization.

## Commands

### Development Workflow
```bash
# Environment setup
uv sync                          # Install dependencies

# Code quality
uv run task format              # Format code with Ruff
uv run task lint                # Lint with Ruff (with --fix)
uv run task type                # Type check with Ty
uv run task quality             # Run format + lint + type + test-fast

# Testing
uv run task test                # Run tests with coverage
uv run task test-v              # Verbose test output
uv run task test-fast           # Quick tests without coverage
uv run task test-unit           # Unit tests only
uv run task test-integration    # Integration tests only
uv run task test-cov            # Tests with HTML coverage report

# Security and maintenance
uv run task security            # Security checks with Ruff
uv run task all                 # Complete pipeline: clean + quality + test-cov + security
uv run task clean               # Clean build artifacts and caches

# Pre-commit hooks
uv run task pre-commit-install  # Install pre-commit hooks
uv run task pre-commit          # Run pre-commit on all files
```

### Running Examples
```bash
# Test with Mizu-VoIP demo server
echo "2" | uv run python mizu_example.py    # Simple test mode
echo "1" | uv run python mizu_example.py    # Full demo with keep-alive

# Rich SIP example
uv run python example_rich_sip.py
```

### Package Management
Use `uv` for all dependency management:
```bash
uv add package-name             # Add runtime dependency
uv add --dev package-name       # Add development dependency
uv remove package-name          # Remove dependency
```

## Architecture

### Core Components

**SIP Protocol Stack:**
- `tinysip/message.py` - SIP message parsing and generation (SIPMessage, SIPMethod, SIPStatusCode)
- `tinysip/fsm.py` - State machines for SIP transactions and dialogs (TxState, DialogState, SIPUserAgent)
- `tinysip/auth.py` - SIP Digest authentication with automatic re-authentication on 401/407
- `tinysip/transport.py` - Transport layer abstraction (UDP/TCP support, TransportConfig)

**Call Flow Visualization:**
- `tinysip/call_flow.py` - Real-time call flow tracking and ladder diagram generation
- `tinysip/ladder.py` - ASCII ladder diagrams for debugging SIP message flows
- Rich-powered visual debugging with automatic participant mapping

**Media Handling:**
- `tinysip/media/rtp.py` - RTP packet handling and streaming
- `tinysip/media/codecs.py` - Audio codec support (PCMU, PCMA)
- `tinysip/media/dtmf.py` - DTMF tone generation
- `tinysip/media/audio.py` - Audio processing utilities

**Protocol Support:**
- `tinysip/sdp.py` - Session Description Protocol implementation
- `tinysip/dns.py` - DNS resolution for SIP URIs
- `tinysip/client.py` - High-level SIP client implementation

**Rich Logging & Utilities:**
- `tinysip/logging_utils.py` - Rich-powered SIP-aware logging with panels and styling
- Beautiful console output for SIP messages, transactions, and authentication

### Key Design Patterns

1. **RFC 3261 Compliance** - Strict adherence to SIP specification for transactions and dialogs
2. **Finite State Machines** - Separate FSMs for INVITE and non-INVITE client/server transactions
3. **Async/Await** - Full async support throughout the stack with proper transaction management
4. **Rich Integration** - Comprehensive visual debugging and call flow visualization
5. **Authentication Handling** - Automatic challenge-response with proper branch ID generation

### Authentication Flow
- Implements SIP Digest authentication per RFC 3261
- Automatic handling of 401/407 challenges with new transaction creation
- Proper branch ID generation for authenticated requests to avoid transaction conflicts
- Credential management with realm support and nonce count tracking

### Call Flow Tracking
- Real-time SIP message flow visualization with Rich-powered ladder diagrams
- Per-dialog tracking with automatic participant address mapping
- Visual representation of transactions, authentication flows, and media negotiation
- Export capabilities for debugging and analysis

## Development Guidelines

### Code Quality Standards
- **Line length**: 100 characters (configured in Ruff)
- **Target Python**: 3.13+ (though 3.12+ required)
- **Type hints**: Mandatory for all public APIs
- **Coverage**: Minimum 20% (configured in pytest)

### Testing Strategy
- Unit tests in `tests/` directory
- Markers: `unit`, `integration`, `slow`, `asyncio`
- Pytest with coverage reporting
- Pre-commit hooks run tests before push

### Dependency Management
- Runtime: httpx, pydantic, pydantic-settings, rich
- Development: pytest, pytest-asyncio, ruff, ty, pre-commit
- Use `uv` for all dependency operations (never edit pyproject.toml manually)

## Important Implementation Details

### SIP Message Flow Architecture
- `SIPUserAgent` is the central coordinator managing transactions and dialogs
- `TransactionManager` handles client/server transaction state machines per RFC 3261
- `SIPCallFlowTracker` provides real-time visualization of all SIP message exchanges
- Authentication is handled transparently with automatic challenge-response cycles

### Working Examples
- `mizu_example.py` - Complete SIP client demo with Mizu-VoIP demo server
- `example_rich_sip.py` - Rich console integration examples
- Both examples demonstrate authentication, registration, and call establishment

### Key Implementation Notes
- Project uses PT-BR comments and documentation in many files
- The protocol/ directory was removed (files moved to root tinysip/)
- Authentication automatically generates new branch IDs to avoid transaction conflicts
- Call flow diagrams render in real-time during SIP operations
- Rich console integration provides comprehensive debugging visualization
- All async operations use proper asyncio patterns with transaction lifecycle management

### Recent Enhancements
- Fixed authentication challenge handling for REGISTER and INVITE methods
- Implemented proper call flow ladder diagram formatting within Rich panels
- Added automatic participant address mapping for visual debugging
- Enhanced transaction state machine with proper RFC 3261 compliance
