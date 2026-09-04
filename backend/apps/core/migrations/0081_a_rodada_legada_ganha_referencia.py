# A rodada de assinatura passou a ser o recorte de "este documento está assinado?" (issue #115,
# ADR 0065), e o recorte é o `document_ref`. Toda solicitação criada dali em diante tem um: o do
# fornecedor, ou o `local:` que `esign.send_for_signature` cunha quando não há fornecedor.
#
# As linhas **anteriores** a essa entrega, criadas sem fornecedor homologado, ficaram com
# `document_ref` vazio — e vazio agrupa todas na *mesma* rodada. Um documento recusado, reenviado e
# assinado à mão apareceria com uma concluída e uma recusada no mesmo grupo, e deixaria de contar
# como assinado; até esta entrega ele contava, porque a pergunta era um `.exists()`.
#
# Historicamente **uma solicitação era uma rodada** — o endpoint criava uma por chamada, com um
# signatário. Então dar a cada linha órfã a sua própria referência não inventa história nenhuma:
# reproduz exatamente o que o `.exists()` respondia antes, agora sob o recorte novo.
#
# Aditiva e idempotente: só toca linha com `document_ref` vazio, e rodá-la duas vezes não acha
# nenhuma na segunda. Não há reversão útil — voltar seria reintroduzir o agrupamento defeituoso —,
# então a reversa é no-op, no molde das demais migrações de dado da casa.

from django.db import migrations


def carimbar_rodada_das_linhas_legadas(apps, schema_editor):
    import uuid

    SignatureRequest = apps.get_model("core", "SignatureRequest")
    orfas = SignatureRequest.objects.filter(document_ref="")
    for solicitacao in orfas.iterator():
        solicitacao.document_ref = f"local:{uuid.uuid4().hex}"
        solicitacao.save(update_fields=["document_ref"])


def nao_desfaz(apps, schema_editor):
    """Sem reversão: apagar a referência devolveria o agrupamento que a issue #115 corrigiu."""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0080_o_papel_do_signatario"),
    ]

    operations = [
        migrations.RunPython(carimbar_rodada_das_linhas_legadas, nao_desfaz),
    ]
