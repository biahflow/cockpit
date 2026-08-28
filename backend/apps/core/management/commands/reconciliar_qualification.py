"""Conferência pós-deploy do backfill da migração 0052 (ADR 0049, FDD 044).

A migração traduz cada `Opportunity` de tier `qualification_call` em uma `Qualification`, mas ela
**pula** duas situações de propósito, e as duas pedem decisão de gente:

- **oportunidade sem lead** — `Qualification.lead` é obrigatório, e inventar um lead sintético
  colocaria dado falso na base para satisfazer uma chave estrangeira;
- **oportunidade com projeto** — a avaliação é criada, mas a oportunidade **não** é arquivada,
  porque `Project.opportunity` é `PROTECT` e a tela do projeto lê a oportunidade para montar o
  histórico comercial.

Uma migração que aponta o que não conseguiu traduzir vale mais do que uma que finge cobertura
total. Este comando é read-only: ele não conserta nada, e não deve passar a consertar — o conserto
de cada linha depende de saber o que aquela venda era.
"""

from typing import Any

from django.core.management.base import BaseCommand

from apps.core.models import Opportunity, Qualification, Service


class Command(BaseCommand):
    help = (
        "Relatório read-only do backfill de Qualification (migração 0052): quantas oportunidades "
        "de qualification_call viraram avaliação, quantas ficaram e por quê."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        candidatas = Opportunity.objects.filter(
            service__tier=Service.Tier.QUALIFICATION_CALL
        ).select_related("client")
        total = candidatas.count()
        migradas = Qualification.objects.filter(legacy_opportunity__isnull=False).count()

        sem_lead = [o for o in candidatas if not o.leads.exists()]
        com_projeto = [o for o in candidatas if o.projects.exists()]

        self.stdout.write(f"Oportunidades de qualification_call: {total}")
        self.stdout.write(f"Traduzidas em Qualification: {migradas}")
        self.stdout.write(f"Sem lead (puladas pelo backfill): {len(sem_lead)}")
        for opportunity in sem_lead:
            self.stdout.write(
                f"  · #{opportunity.pk} — {opportunity.title} ({opportunity.client.name})"
            )
        self.stdout.write(f"Com projeto (avaliadas, não arquivadas): {len(com_projeto)}")
        for opportunity in com_projeto:
            self.stdout.write(
                f"  · #{opportunity.pk} — {opportunity.title} → "
                + ", ".join(f"projeto #{p.pk}" for p in opportunity.projects.order_by("id"))
            )
        pendentes = total - migradas
        estilo = self.style.WARNING if pendentes else self.style.SUCCESS
        self.stdout.write(estilo(f"Pendentes de tradução: {pendentes}"))
