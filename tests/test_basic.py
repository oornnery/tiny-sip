"""Test para o módulo principal do tinysip."""

import pytest


def test_import_tinysip():
    """Testa se o módulo tinysip pode ser importado."""
    import tinysip

    assert tinysip is not None
    assert hasattr(tinysip, "__version__")
    assert tinysip.__version__ == "0.1.0"


def test_tinysip_attributes():
    """Testa os atributos principais do módulo."""
    import tinysip

    assert hasattr(tinysip, "__author__")
    assert hasattr(tinysip, "__description__")
    assert tinysip.__description__ == "A tiny SIP client library"


def test_sample_function():
    """Teste de exemplo que sempre passa."""
    assert True


def test_sample_math():
    """Teste de matemática básica."""
    assert 2 + 2 == 4
    assert 3 * 3 == 9


@pytest.mark.asyncio
async def test_async_example():
    """Teste assíncrono de exemplo."""

    async def async_function():
        return "hello"

    result = await async_function()
    assert result == "hello"


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (1, 1, 2),
        (2, 3, 5),
        (10, 20, 30),
    ],
)
def test_parametrized_addition(a, b, expected):
    """Teste parametrizado de adição."""
    assert a + b == expected


@pytest.mark.unit
def test_unit_example():
    """Teste marcado como unit test."""
    assert True


@pytest.mark.integration
def test_integration_example():
    """Teste marcado como integration test."""
    assert True


@pytest.mark.slow
def test_slow_example():
    """Teste marcado como slow."""
    import time

    time.sleep(0.01)  # Simula operação lenta
    assert True
