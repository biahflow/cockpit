"""Regressão: `signer_email` continua criando a solicitação de assinatura na `/api/v1/`.

A issue #115 trocou o corpo do `request-signature` de um e-mail solto para uma **lista** de
signatários com papel — a casa, a parte contratante e as testemunhas assinam o mesmo documento, e
só a lista permite pedir isso numa chamada. A chave antiga continua aceita, e isso não é gentileza:
a SPA ainda manda a forma antiga (`frontend/src/pages/DocumentsPage.tsx`), a tela de escolher
contatos e papéis é `INTERFACE_CHANGE` e depende de um DAP que ainda não existe, e quebrar agora
deixaria o produto sem caminho nenhum para pedir assinatura.

**Este teste existe porque nada aqui dentro exercita o alias.** Quem escreve `signer_email` é o
navegador, não o backend; sem esta regressão a linha que o normaliza não tem chamador dentro do
repositório, e a próxima varredura atrás do nome antigo a remove achando que paga dívida —
quebrando a `/api/v1/` no único lugar onde nada fica vermelho. É a regra de `docs/ontology/aliases.md`
§2c, e o prazo do alias é a `/api/v2/`.

A outra metade da regra é a precedência: **a forma canônica vence** quando as duas chaves vêm no
mesmo corpo. Um corpo com as duas é confusão do chamador, e resolver pela nova é o que não trava
quem já migrou.
"""

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Document, SignatureRequest, User
from apps.core.tests.factories import AccountFactory, UserFactory

# Sem `ESIGN_PROVIDER`: o registro local do `NullProvider`, que é o modo previsto quando não há
# fornecedor homologado — e o que mantém este teste longe da rede (ADR 0059).
REGISTRO_LOCAL = override_settings(
    ESIGN_ENABLED=True, ESIGN_PROVIDER="", ESIGN_HOUSE_SIGNER_EMAIL=""
)


def _documento(user: User) -> Document:
    return Document.objects.create(
        account=AccountFactory(owner=user),
        original_name="contrato.pdf",
        uploaded_by=user,
        kind=Document.Kind.COMMERCIAL_CONTRACT,
    )


def _pedir(document: Document, corpo: dict) -> tuple[int, dict]:
    client = APIClient()
    client.force_authenticate(document.uploaded_by)
    response = client.post(
        reverse("document-request-signature", args=[document.pk]), corpo, format="json"
    )
    return response.status_code, response.data


@pytest.mark.django_db
@REGISTRO_LOCAL
def test_o_corpo_antigo_continua_criando_uma_solicitacao_de_contraparte():
    document = _documento(UserFactory(role=User.Role.ADMIN))

    code, data = _pedir(document, {"signer_email": "quem.assina@cliente.test"})

    assert code == 201
    assert len(data["signatures"]) == 1
    solicitacao = document.signature_requests.get()
    assert solicitacao.signer_email == "quem.assina@cliente.test"
    # O papel não é adivinhado: até esta issue o único signatário que existia era a outra parte, e
    # é esse o default do campo — a mesma decisão que dispensou backfill na migração `0080`.
    assert solicitacao.signer_role == SignatureRequest.SignerRole.COUNTERPARTY


@pytest.mark.django_db
@REGISTRO_LOCAL
def test_a_forma_canonica_vence_quando_as_duas_chaves_vem_juntas():
    document = _documento(UserFactory(role=User.Role.ADMIN))

    code, _ = _pedir(
        document,
        {
            "signer_email": "antigo@cliente.test",
            "signers": [
                {"email": "novo@cliente.test", "role": "counterparty"},
                {"email": "testemunha@cliente.test", "role": "witness"},
            ],
        },
    )

    assert code == 201
    criadas = list(document.signature_requests.order_by("id"))
    assert [s.signer_email for s in criadas] == ["novo@cliente.test", "testemunha@cliente.test"]
    assert "antigo@cliente.test" not in [s.signer_email for s in criadas]
