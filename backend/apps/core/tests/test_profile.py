"""Meu perfil: o usuário edita o **próprio** nome, a própria senha e a própria foto.

Este arquivo é o oráculo de segurança da superfície, e não só o de comportamento. O caminho
que ela abre é o primeiro de escrita sobre `User` em toda a API, e `UserSerializer` tem `role`
gravável — o comentário dele já dizia que o dia em que alguém o pendurasse num endpoint de
escrita não podia ser o dia em que virou caminho de promoção. É esse dia, e é por isso que
metade dos testes aqui pergunta o que **não** mudou.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import User

from .factories import UserFactory

SENHA = "Segura123!senha"
NOVA_SENHA = "OutraSenha987!forte"

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"0" * 64

MEDIA = override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")


def _logado(role: str = User.Role.DELIVERY) -> tuple[User, APIClient]:
    """Sessão de verdade, não `force_authenticate`.

    A troca de senha depende de `update_session_auth_hash`, e sem uma sessão real não há hash
    para rotacionar — o teste passaria sem exercitar exatamente o que ele existe para provar.
    """
    user = UserFactory(role=role, password=SENHA)
    client = APIClient()
    assert client.post(reverse("login"), {"username": user.username, "password": SENHA}).status_code == 200
    return user, client


# --------------------------------------------------------------------------- nome


@pytest.mark.django_db
@pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.SALES, User.Role.DELIVERY])
def test_todo_papel_edita_o_proprio_nome(role: str) -> None:
    user, client = _logado(role)

    response = client.patch(reverse("me"), {"first_name": "Daniel", "last_name": "Campos"}, format="json")

    assert response.status_code == 200
    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Daniel", "Campos")
    assert response.data["first_name"] == "Daniel"


@pytest.mark.django_db
def test_entrega_mandando_role_admin_nao_vira_admin() -> None:
    """O teste de escalonamento de privilégio desta entrega.

    `UserSerializer` aceita `role`; o serializer de perfil é outro, com allowlist de dois campos.
    Se alguém trocar um pelo outro para "reaproveitar", é aqui que fica vermelho.
    """
    user, client = _logado(User.Role.DELIVERY)

    response = client.patch(
        reverse("me"),
        {"first_name": "Daniel", "role": User.Role.ADMIN, "is_admin": True},
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.role == User.Role.DELIVERY
    assert user.is_admin_role is False
    assert response.data["role"] == User.Role.DELIVERY
    assert response.data["is_admin"] is False


@pytest.mark.django_db
def test_campos_de_identidade_e_privilegio_nao_sao_gravaveis_pelo_perfil() -> None:
    user, client = _logado(User.Role.SALES)
    antes = (user.username, user.email, user.is_superuser, user.is_staff, user.is_active)

    response = client.patch(reverse("me"), {
        "first_name": "Daniel",
        "username": "sequestrado",
        "email": "outro@example.test",
        "is_superuser": True,
        "is_staff": True,
        "is_active": False,
        "id": 9999,
    }, format="json")

    assert response.status_code == 200
    user.refresh_from_db()
    assert (user.username, user.email, user.is_superuser, user.is_staff, user.is_active) == antes


@pytest.mark.django_db
def test_ninguem_altera_outro_usuario_pelas_rotas_novas() -> None:
    """As rotas de escrita operam sobre `request.user` e não aceitam alvo vindo do cliente."""
    user, client = _logado(User.Role.ADMIN)
    outro = UserFactory(role=User.Role.DELIVERY, first_name="Intacto", last_name="Fica")

    # `id` no corpo é o único alvo que o cliente consegue sugerir — e ele é ignorado.
    pelo_corpo = client.patch(reverse("me"), {"id": outro.id, "first_name": "Sequestrado"}, format="json")
    # A rota de coleção de usuários continua sendo só leitura, inclusive para admin.
    pela_colecao = client.patch(f"/api/v1/users/{outro.id}/", {"first_name": "Sequestrado"}, format="json")

    assert pelo_corpo.status_code == 200
    assert pela_colecao.status_code == 405
    outro.refresh_from_db()
    assert (outro.first_name, outro.last_name) == ("Intacto", "Fica")
    user.refresh_from_db()
    assert user.first_name == "Sequestrado"  # o próprio, sim


@pytest.mark.django_db
def test_usuarios_continua_fechado_para_vendas_e_entrega() -> None:
    """Regressão do estado atual: o perfil não pode ter afrouxado `RolePermission`."""
    for role in (User.Role.SALES, User.Role.DELIVERY):
        _, client = _logado(role)
        assert client.get(reverse("user-list")).status_code == 403, role


# --------------------------------------------------------------------------- senha


@pytest.mark.django_db
def test_troca_de_senha_preserva_a_sessao_corrente() -> None:
    user, client = _logado(User.Role.DELIVERY)

    response = client.post(reverse("me-password"), {
        "current_password": SENHA,
        "new_password": NOVA_SENHA,
        "new_password_confirm": NOVA_SENHA,
    }, format="json")
    depois = client.get(reverse("me"))

    assert response.status_code == 204
    # Sem `update_session_auth_hash`, o Django rotaciona o hash de sessão e derruba **todas** as
    # sessões, inclusive esta: a pessoa trocaria a senha e cairia na tela de login.
    assert depois.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NOVA_SENHA)


@pytest.mark.django_db
def test_senha_atual_errada_recusa_e_nao_troca_nada() -> None:
    user, client = _logado(User.Role.SALES)

    response = client.post(reverse("me-password"), {
        "current_password": "nao-e-a-minha",
        "new_password": NOVA_SENHA,
        "new_password_confirm": NOVA_SENHA,
    }, format="json")

    assert response.status_code == 400
    assert "current_password" in response.data
    user.refresh_from_db()
    assert user.check_password(SENHA)


@pytest.mark.django_db
@pytest.mark.parametrize("fraca", ["1234", "senha", "abcdefgh"])
def test_senha_nova_fraca_e_recusada_com_a_regra_do_convite(fraca: str) -> None:
    user, client = _logado(User.Role.DELIVERY)

    response = client.post(reverse("me-password"), {
        "current_password": SENHA,
        "new_password": fraca,
        "new_password_confirm": fraca,
    }, format="json")

    assert response.status_code == 400
    assert "new_password" in response.data
    user.refresh_from_db()
    assert user.check_password(SENHA)


@pytest.mark.django_db
def test_confirmacao_divergente_e_recusada() -> None:
    user, client = _logado(User.Role.DELIVERY)

    response = client.post(reverse("me-password"), {
        "current_password": SENHA,
        "new_password": NOVA_SENHA,
        "new_password_confirm": f"{NOVA_SENHA}x",
    }, format="json")

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password(SENHA)


@pytest.mark.django_db
def test_troca_de_senha_exige_sessao() -> None:
    assert APIClient().post(reverse("me-password"), {}, format="json").status_code == 403


# --------------------------------------------------------------------------- foto


@pytest.mark.django_db
@MEDIA
@pytest.mark.parametrize(("nome", "conteudo"), [
    ("retrato.png", PNG), ("retrato.jpg", JPEG), ("retrato.JPEG", JPEG), ("retrato.webp", WEBP),
])
def test_envia_a_propria_foto_nos_tres_tipos_aceitos(nome: str, conteudo: bytes) -> None:
    user, client = _logado(User.Role.DELIVERY)

    response = client.put(
        reverse("me-avatar"),
        {"avatar": SimpleUploadedFile(nome, conteudo)},
        format="multipart",
    )

    assert response.status_code == 200
    assert response.data["has_avatar"] is True
    user.refresh_from_db()
    assert user.avatar.name.startswith("avatars/")
    # O nome enviado não entra no caminho do storage.
    assert "retrato" not in user.avatar.name
    assert user.avatar_updated_at is not None


@pytest.mark.django_db
@MEDIA
def test_foto_acima_de_dois_megabytes_e_recusada() -> None:
    user, client = _logado(User.Role.DELIVERY)

    response = client.put(
        reverse("me-avatar"),
        {"avatar": SimpleUploadedFile("grande.png", PNG + b"0" * (2 * 1024 * 1024))},
        format="multipart",
    )

    assert response.status_code == 400
    assert "avatar" in response.data
    user.refresh_from_db()
    assert not user.avatar


@pytest.mark.django_db
@MEDIA
@pytest.mark.parametrize(("nome", "conteudo"), [
    ("payload.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
    ("payload.html", b"<script>alert(1)</script>"),
    ("animado.gif", b"GIF89a" + b"0" * 32),
    ("sem-extensao", PNG),
    # Extensão aceita, conteúdo não: o header é conferido, e não só o nome.
    ("disfarcado.png", b"<script>alert(1)</script>"),
])
def test_tipo_nao_aceito_e_recusado(nome: str, conteudo: bytes) -> None:
    user, client = _logado(User.Role.DELIVERY)

    response = client.put(reverse("me-avatar"), {"avatar": SimpleUploadedFile(nome, conteudo)}, format="multipart")

    assert response.status_code == 400, nome
    assert "avatar" in response.data
    user.refresh_from_db()
    assert not user.avatar


@pytest.mark.django_db
@MEDIA
def test_trocar_a_foto_apaga_o_arquivo_anterior() -> None:
    from django.core.files.storage import default_storage

    user, client = _logado(User.Role.DELIVERY)
    client.put(reverse("me-avatar"), {"avatar": SimpleUploadedFile("a.png", PNG)}, format="multipart")
    user.refresh_from_db()
    primeiro = user.avatar.name

    client.put(reverse("me-avatar"), {"avatar": SimpleUploadedFile("b.png", PNG)}, format="multipart")
    user.refresh_from_db()

    assert user.avatar.name != primeiro
    assert not default_storage.exists(primeiro)


@pytest.mark.django_db
@MEDIA
def test_remover_a_foto_apaga_o_arquivo_e_zera_o_campo() -> None:
    from django.core.files.storage import default_storage

    user, client = _logado(User.Role.DELIVERY)
    client.put(reverse("me-avatar"), {"avatar": SimpleUploadedFile("a.png", PNG)}, format="multipart")
    user.refresh_from_db()
    gravado = user.avatar.name

    response = client.delete(reverse("me-avatar"))

    assert response.status_code == 200
    assert response.data["has_avatar"] is False
    user.refresh_from_db()
    assert not user.avatar
    assert user.avatar_updated_at is None
    assert not default_storage.exists(gravado)


@pytest.mark.django_db
@MEDIA
def test_remover_sem_foto_nao_estoura() -> None:
    _, client = _logado(User.Role.DELIVERY)

    assert client.delete(reverse("me-avatar")).status_code == 200


@pytest.mark.django_db
@MEDIA
def test_a_rota_da_foto_nega_sem_sessao() -> None:
    user, client = _logado(User.Role.DELIVERY)
    client.put(reverse("me-avatar"), {"avatar": SimpleUploadedFile("a.png", PNG)}, format="multipart")

    anonimo = APIClient().get(reverse("user-avatar", args=[user.id]))

    assert anonimo.status_code == 403


@pytest.mark.django_db
@MEDIA
def test_a_rota_da_foto_serve_a_propria_e_esconde_a_dos_outros() -> None:
    user, client = _logado(User.Role.DELIVERY)
    client.put(reverse("me-avatar"), {"avatar": SimpleUploadedFile("a.png", PNG)}, format="multipart")
    outro = UserFactory(role=User.Role.SALES)

    propria = client.get(reverse("user-avatar", args=[user.id]))
    alheia = client.get(reverse("user-avatar", args=[outro.id]))

    assert propria.status_code == 200
    assert propria["Content-Type"] == "image/png"
    assert propria["X-Content-Type-Options"] == "nosniff"
    assert b"".join(propria.streaming_content) == PNG
    # 404 e não 403: quem não alcança a foto também não precisa saber que o usuário existe.
    assert alheia.status_code == 404


@pytest.mark.django_db
@MEDIA
def test_admin_alcanca_a_foto_de_quem_ele_ja_lista() -> None:
    """`/users/` é admin-only e devolve a lista inteira; esconder a foto dela seria incoerente."""
    _, admin_client = _logado(User.Role.ADMIN)
    outro, outro_client = _logado(User.Role.DELIVERY)
    outro_client.put(reverse("me-avatar"), {"avatar": SimpleUploadedFile("a.png", PNG)}, format="multipart")

    assert admin_client.get(reverse("user-avatar", args=[outro.id])).status_code == 200


@pytest.mark.django_db
@MEDIA
def test_a_rota_da_foto_devolve_304_quando_o_etag_bate() -> None:
    """Sem isto o topbar baixa a foto inteira uma vez por tela."""
    user, client = _logado(User.Role.DELIVERY)
    client.put(reverse("me-avatar"), {"avatar": SimpleUploadedFile("a.png", PNG)}, format="multipart")

    primeira = client.get(reverse("user-avatar", args=[user.id]))
    etag = primeira["ETag"]
    revalidada = client.get(reverse("user-avatar", args=[user.id]), HTTP_IF_NONE_MATCH=etag)

    assert etag and primeira["Last-Modified"]
    assert revalidada.status_code == 304
    assert revalidada["ETag"] == etag


@pytest.mark.django_db
@MEDIA
def test_a_rota_da_foto_devolve_404_para_quem_nao_tem_foto() -> None:
    user, client = _logado(User.Role.DELIVERY)

    assert client.get(reverse("user-avatar", args=[user.id])).status_code == 404
    assert client.get(reverse("user-avatar", args=[user.id + 9999])).status_code == 404


@pytest.mark.django_db
@MEDIA
def test_o_envio_de_foto_exige_sessao() -> None:
    anonimo = APIClient()

    assert anonimo.put(reverse("me-avatar"), {}, format="multipart").status_code == 403
    assert anonimo.delete(reverse("me-avatar")).status_code == 403
    assert anonimo.patch(reverse("me"), {}, format="json").status_code == 403


@pytest.mark.django_db
@MEDIA
def test_me_expoe_o_estado_da_foto_para_o_topbar() -> None:
    user, client = _logado(User.Role.DELIVERY)

    sem_foto = client.get(reverse("me"))
    client.put(reverse("me-avatar"), {"avatar": SimpleUploadedFile("a.png", PNG)}, format="multipart")
    com_foto = client.get(reverse("me"))

    assert sem_foto.data["has_avatar"] is False
    assert sem_foto.data["avatar_updated_at"] is None
    assert com_foto.data["has_avatar"] is True
    assert com_foto.data["avatar_updated_at"]
    assert user.id == com_foto.data["id"]


@pytest.mark.django_db
@MEDIA
def test_envio_sem_arquivo_e_erro_de_campo() -> None:
    _, client = _logado(User.Role.DELIVERY)

    response = client.put(reverse("me-avatar"), {}, format="multipart")

    assert response.status_code == 400
    assert "avatar" in response.data
