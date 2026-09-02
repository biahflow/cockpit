"""O mandato de Design Partner nasce do acordo assinado, sem passar por venda nenhuma.

Hoje o `Engagement` de parceria é criado à mão na tela (detalhe da conta → seção Engagements).
Isso é o passo que faltava para automatizar: quando um `Document` marcado
`kind=DESIGN_PARTNER_AGREEMENT` é assinado, o mandato deve existir sozinho — sem ele não há onde
pendurar projeto nenhum (`Project.engagement` é `NOT NULL`).

Quatro condições, e todas as quatro precisam valer: `kind` certo, conta vinculada, assinatura
concluída e nenhum mandato anterior originado do mesmo documento. Elas servem a invariante 13 da
§6 de `docs/ontology/language-map.md` — *todo `Engagement` tem `commercial_model` preenchido e
referência ao instrumento assinado que o originou* —, que `Engagement.clean()` cobra e que o
`full_clean()` daqui faz valer também neste caminho.

Fora dessas quatro, silêncio: um NDA assinado, um contrato comercial assinado ou um acordo
pendurado numa oportunidade **não** podem produzir mandato. É a metade que mais importa, porque
um mandato que nasce da assinatura errada não faz barulho nenhum ao nascer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import IntegrityError
from django.utils import timezone

if TYPE_CHECKING:
    from .models import Document, Engagement


def abrir_engagement_do_acordo(document: Document) -> Engagement | None:
    """O mandato de parceria nasce do acordo assinado — sem passar por venda nenhuma."""
    from .models import Document, Engagement

    if document.kind != Document.Kind.DESIGN_PARTNER_AGREEMENT:
        return None
    # Uma pergunta só, e não `account_id is None` seguido de estreitar o tipo depois: o acordo
    # pendurado numa oportunidade ou num projeto cai exatamente aqui, e é a conta que a linha
    # abaixo precisa de qualquer jeito.
    account = document.account
    if account is None:
        return None
    if not document.is_signed:
        return None
    if Engagement.objects.filter(originating_design_partner_agreement=document).exists():
        return None

    engagement = Engagement(
        account=account,
        name=f"Design Partner — {account.name}",
        owner=document.uploaded_by,
        started_at=timezone.localdate(),
        commercial_model=Engagement.CommercialModel.DESIGN_PARTNER,
        originating_design_partner_agreement=document,
    )
    engagement.full_clean()
    try:
        engagement.save()
    except IntegrityError:
        # Corrida: outra chamada concluiu primeiro — o `OneToOneField` é a trava natural contra
        # duplicata. Um 500 aqui faria o fornecedor do webhook reentregar em laço.
        return Engagement.objects.filter(
            originating_design_partner_agreement=document
        ).first()
    return engagement
