import pytest

from app.modules.contactos.service import InvalidPhoneError, normalize_phone


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("987 654 321", "987654321"),
        ("987   654   321", "987654321"),
        ("+51 987 654 321", "+51987654321"),
        (None, None),
    ],
)
def test_normalize_phone(value: str | None, expected: str | None) -> None:
    assert normalize_phone(value) == expected


@pytest.mark.parametrize("value", ["1234", "987-654-321", "+051987654321"])
def test_normalize_phone_rechaza_formatos_invalidos(value: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalize_phone(value)
