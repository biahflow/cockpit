"""Bootstrap do primeiro administrador em ambiente remoto (FDD 019)."""

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.tests.factories import UserFactory

User = get_user_model()

_VARS = {
    "DJANGO_SUPERUSER_USERNAME": "admin",
    "DJANGO_SUPERUSER_EMAIL": "admin@example.test",
    "DJANGO_SUPERUSER_PASSWORD": "Senha-Forte-987!",
}


def _set_vars(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    valores = {**_VARS, **overrides}
    for nome, valor in valores.items():
        monkeypatch.setenv(nome, valor)


@pytest.mark.django_db
def test_cria_administrador_quando_nao_ha_nenhum(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vars(monkeypatch)

    call_command("bootstrap_admin")

    usuario = User.objects.get(username="admin")
    assert usuario.is_superuser
    assert usuario.is_active
    # Provar que a senha gravada autentica de verdade, não só que uma linha foi escrita.
    assert authenticate(username="admin", password=_VARS["DJANGO_SUPERUSER_PASSWORD"]) == usuario


@pytest.mark.django_db
def test_nao_faz_nada_quando_ja_existe_superusuario_ativo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existente = UserFactory(
        username="ja-existe", is_superuser=True, is_active=True, password="SenhaAntiga987!"
    )
    senha_hash_antes = existente.password
    _set_vars(monkeypatch, DJANGO_SUPERUSER_USERNAME="outro")

    call_command("bootstrap_admin")

    assert User.objects.count() == 1
    existente.refresh_from_db()
    assert existente.password == senha_hash_antes


@pytest.mark.django_db
def test_superusuario_inativo_nao_conta_e_bootstrap_prossegue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    UserFactory(username="inativo", is_superuser=True, is_active=False)
    _set_vars(monkeypatch)

    call_command("bootstrap_admin")

    assert User.objects.filter(username="admin", is_superuser=True).exists()


@pytest.mark.django_db
def test_senha_fraca_recusa_e_nao_cria_ninguem(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vars(monkeypatch, DJANGO_SUPERUSER_PASSWORD="12345678")

    with pytest.raises(CommandError):
        call_command("bootstrap_admin")

    assert User.objects.count() == 0


@pytest.mark.django_db
def test_senha_parecida_com_o_usuario_e_recusada(monkeypatch: pytest.MonkeyPatch) -> None:
    """O quarto validador, que é o único que precisa da instância para existir.

    `validate_password(senha)` sem usuário devolve cedo dentro do
    `UserAttributeSimilarityValidator` — o **primeiro** dos quatro em `AUTH_PASSWORD_VALIDATORS`.
    Sem este teste, validar três dos quatro passaria por validar, e a senha que o runbook promete
    recusar entraria: `danielcampos` tem doze caracteres, não está na lista de comuns e não é
    numérica, então os outros três a aprovam em coro.
    """
    _set_vars(
        monkeypatch,
        DJANGO_SUPERUSER_USERNAME="danielcampos",
        DJANGO_SUPERUSER_PASSWORD="danielcampos",
    )

    with pytest.raises(CommandError):
        call_command("bootstrap_admin")

    assert User.objects.count() == 0


@pytest.mark.django_db
def test_sem_variaveis_sai_limpo_sem_exigir(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in _VARS:
        monkeypatch.delenv(nome, raising=False)

    call_command("bootstrap_admin")

    assert User.objects.count() == 0


@pytest.mark.django_db
def test_sem_variaveis_com_exigir_levanta_command_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in _VARS:
        monkeypatch.delenv(nome, raising=False)

    with pytest.raises(CommandError):
        call_command("bootstrap_admin", "--exigir")

    assert User.objects.count() == 0


@pytest.mark.django_db
def test_senha_nunca_aparece_na_saida(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_vars(monkeypatch)

    call_command("bootstrap_admin")

    saida = capsys.readouterr()
    assert _VARS["DJANGO_SUPERUSER_PASSWORD"] not in saida.out
    assert _VARS["DJANGO_SUPERUSER_PASSWORD"] not in saida.err


@pytest.mark.django_db
def test_senha_nunca_aparece_na_saida_quando_fraca(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_vars(monkeypatch, DJANGO_SUPERUSER_PASSWORD="12345678")

    with pytest.raises(CommandError) as excinfo:
        call_command("bootstrap_admin")

    saida = capsys.readouterr()
    assert "12345678" not in saida.out
    assert "12345678" not in saida.err
    assert "12345678" not in str(excinfo.value)
