"""Retenção de dado pessoal arquivado (LGPD, ADR 0017).

Esta é a única operação do portal que **destrói dado de propósito**, num repositório cuja regra é
soft delete em todo lugar. Os testes existem menos para provar que ela apaga e mais para provar
que ela **não apaga o que não deve**.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.core import retention
from apps.core.models import Document, Lead

from .factories import ClientFactory, UserFactory

pytestmark = pytest.mark.django_db


def _lead(*, arquivado_ha: int | None) -> Lead:
    lead = Lead.objects.create(name="Fulano", email="fulano@exemplo.test")
    if arquivado_ha is not None:
        Lead.objects.filter(pk=lead.pk).update(
            archived_at=timezone.now() - timedelta(days=arquivado_ha)
        )
    return lead


def test_nasce_inerte_todas_as_familias_desligadas() -> None:
    """O default é **nunca expurgar**. Ninguém pode perder dado por ter atualizado o portal."""
    _lead(arquivado_ha=3650)

    planos = retention.planejar()

    assert all(not plano.ativa for plano in planos)
    assert all(plano.quantidade == 0 for plano in planos)


def test_retencao_zero_nao_apaga_nem_no_executar() -> None:
    """A trava mais importante do módulo, e a que faltava.

    O teste do "nasce inerte" acima exercita só o **ensaio** — e ensaio não apaga nada por
    construção, então ele não prova a propriedade que interessa. Quem apaga é o `executar()`, e é
    nele que retenção `0` precisa significar *nunca*: com prazo zero, o corte por data casaria com
    tudo que está arquivado, e o expurgo levaria a base inteira.

    Descoberto por sabotagem: remover a guarda do `executar()` não reprovava teste nenhum.
    """
    lead = _lead(arquivado_ha=3650)

    retention.executar()

    assert Lead.objects.filter(pk=lead.pk).exists()


@override_settings(RETENTION_DAYS={"lead": 30, "document": 0})
def test_familia_desligada_nao_e_afetada_pela_ligada() -> None:
    """Uma família com prazo não pode arrastar a outra: `document` está em `0` aqui."""
    from django.core.files.base import ContentFile

    admin = UserFactory()
    doc = Document.objects.create(
        client=ClientFactory(owner=admin), original_name="fica.pdf", uploaded_by=admin,
    )
    doc.file.save("fica.pdf", ContentFile(b"x"), save=True)
    Document.objects.filter(pk=doc.pk).update(archived_at=timezone.now() - timedelta(days=3650))
    _lead(arquivado_ha=60)

    retention.executar()

    assert Lead.objects.count() == 0  # a ligada expurgou
    assert Document.objects.filter(pk=doc.pk).exists()  # a desligada, não


@override_settings(RETENTION_DAYS={"lead": 30, "document": 0})
def test_ensaio_nao_apaga_nada() -> None:
    """`planejar()` conta e não toca — é o que o comando faz sem `--apply`."""
    _lead(arquivado_ha=60)

    planos = retention.planejar()

    assert next(p for p in planos if p.familia == "lead").quantidade == 1
    assert Lead.objects.count() == 1  # ainda lá


@override_settings(RETENTION_DAYS={"lead": 30, "document": 0})
def test_apaga_so_o_que_passou_do_prazo() -> None:
    velho = _lead(arquivado_ha=60)
    recente = _lead(arquivado_ha=10)

    retention.executar()

    assert not Lead.objects.filter(pk=velho.pk).exists()
    assert Lead.objects.filter(pk=recente.pk).exists()


@override_settings(RETENTION_DAYS={"lead": 30, "document": 0})
def test_nunca_toca_em_linha_viva() -> None:
    """O comando não decide o que sai de uso — ele esquece o que **já** saiu. Lead nunca arquivado
    fica, por mais antigo que seja."""
    vivo = _lead(arquivado_ha=None)
    Lead.objects.filter(pk=vivo.pk).update(created_at=timezone.now() - timedelta(days=3650))

    retention.executar()

    assert Lead.objects.filter(pk=vivo.pk).exists()


@override_settings(RETENTION_DAYS={"lead": 0, "document": 30})
def test_o_arquivo_sai_junto_com_a_linha() -> None:
    """Apagar o registro e deixar o PDF é meio expurgo — e o pior tipo: some o índice e fica o
    conteúdo, sem ninguém saber que existe."""
    from django.core.files.base import ContentFile

    admin = UserFactory()
    doc = Document.objects.create(
        client=ClientFactory(owner=admin), original_name="contrato.pdf", uploaded_by=admin,
    )
    doc.file.save("contrato.pdf", ContentFile(b"conteudo"), save=True)
    caminho = doc.file.path
    Document.objects.filter(pk=doc.pk).update(archived_at=timezone.now() - timedelta(days=60))

    retention.executar()

    import os

    assert not Document.objects.filter(pk=doc.pk).exists()
    assert not os.path.exists(caminho)


@override_settings(RETENTION_DAYS={"lead": 30, "document": 0})
def test_comando_sem_apply_e_ensaio(capsys: pytest.CaptureFixture[str]) -> None:
    """A trava que mais importa: rodar o comando errado não pode destruir nada."""
    _lead(arquivado_ha=60)

    call_command("purge_archived")

    assert Lead.objects.count() == 1
    saida = capsys.readouterr().out
    assert "seriam apagados" in saida
    assert "--apply" in saida


@override_settings(RETENTION_DAYS={"lead": 30, "document": 0})
def test_comando_com_apply_apaga(capsys: pytest.CaptureFixture[str]) -> None:
    _lead(arquivado_ha=60)

    call_command("purge_archived", "--apply")

    assert Lead.objects.count() == 0
    assert "Expurgo concluído" in capsys.readouterr().out


def test_comando_avisa_alto_quando_nada_esta_configurado(capsys: pytest.CaptureFixture[str]) -> None:
    """Silêncio aqui levaria à conclusão errada de que o expurgo rodou e não achou nada."""
    call_command("purge_archived")

    assert "Nenhuma família tem prazo configurado" in capsys.readouterr().out
