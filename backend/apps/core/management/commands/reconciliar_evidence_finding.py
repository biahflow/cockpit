"""Confere o split `Evidencia` → `Evidence` + `Finding` (FDD 045).

**Só lê.** Enquanto o dual-write durar, o modelo fundido e o par novo descrevem o mesmo Discovery
por dois caminhos, e uma divergência entre eles não aparece em lugar nenhum: a tela continua
desenhando o legado, o custo do estado atual continua somando, e o que falta é justamente o dado
que a próxima fatia vai passar a ler. Este comando é o lugar onde a divergência tem nome.

Irmão do `backup_status` e do `check_integrations` no formato — diz em português o que encontrou e
sai com código 1 quando há linha legada sem contraparte, que é a única situação em que alguém
precisa agir. O fato herdado sem revisor **não** derruba o comando: é dívida declarada da migração
`0054`, e falhar por ela transformaria um relatório útil num alarme que ninguém consegue silenciar.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Evidence, Evidencia, Finding


class Command(BaseCommand):
    help = "Confere o split Evidencia → Evidence + Finding (FDD 045). Não escreve nada."

    def handle(self, *args: Any, **options: Any) -> None:
        legadas = Evidencia.objects.count()
        legadas_arquivadas = Evidencia.objects.filter(archived_at__isnull=False).count()
        com_evidence = set(
            Evidence.objects.filter(legacy_evidencia__isnull=False).values_list(
                "legacy_evidencia_id", flat=True
            )
        )
        com_finding = set(
            Finding.objects.filter(legacy_evidencia__isnull=False).values_list(
                "legacy_evidencia_id", flat=True
            )
        )
        pares = com_evidence & com_finding
        # As três formas de ficar pela metade, contadas separadamente: sem nada, só com a metade
        # do dado bruto, só com a metade da conclusão. Somar as três num "faltam N" esconderia
        # justamente a informação que diz onde o backfill parou.
        todas = set(Evidencia.objects.values_list("id", flat=True))
        sem_nada = todas - com_evidence - com_finding
        so_evidence = (com_evidence - com_finding) & todas
        so_finding = (com_finding - com_evidence) & todas

        self.stdout.write(f"Evidencia (legado)        {legadas} — {legadas_arquivadas} arquivada(s)")
        self.stdout.write(f"Par Evidence + Finding    {len(pares)}")
        self.stdout.write(f"Sem contraparte nenhuma   {len(sem_nada)}")
        self.stdout.write(f"Só com Evidence           {len(so_evidence)}")
        self.stdout.write(f"Só com Finding            {len(so_finding)}")

        # O que nasceu depois do backfill: extração e tela. Não é falta, é o modelo novo vivendo a
        # vida dele — mas contar junto com o migrado faria "quantas linhas o split tem?" ter duas
        # respostas certas e diferentes.
        self.stdout.write(
            f"Evidence sem origem legada {Evidence.objects.filter(legacy_evidencia__isnull=True).count()}"
        )
        self.stdout.write(
            f"Finding sem origem legada  {Finding.objects.filter(legacy_evidencia__isnull=True).count()}"
        )

        fatos = Finding.objects.filter(epistemic_status=Finding.EpistemicStatus.FACT)
        sem_revisor = fatos.filter(reviewed_by__isnull=True).count()
        sem_evidencia_viva = sum(
            1 for finding in fatos.filter(archived_at__isnull=True).prefetch_related("evidences")
            if not any(e.archived_at is None for e in finding.evidences.all())
        )
        if sem_revisor:
            # Dívida herdada, e nomeada: o modelo antigo não registrava revisão, então o backfill
            # aproximou pelo `registered_by` — quando nem esse existia, o fato ficou sem ninguém.
            self.stdout.write(self.style.WARNING(
                f"{sem_revisor} achado(s) em 'fato' sem revisor — dívida herdada do modelo "
                "fundido (migração 0054). Promover a fato passou a exigir revisor; estes vieram "
                "de antes da regra."
            ))
        if sem_evidencia_viva:
            self.stdout.write(self.style.WARNING(
                f"{sem_evidencia_viva} achado(s) vivo(s) em 'fato' sem nenhuma evidência viva."
            ))
        if not sem_revisor and not sem_evidencia_viva:
            self.stdout.write(self.style.SUCCESS("Nenhum fato sem revisor nem sem evidência viva."))

        faltam = len(sem_nada) + len(so_evidence) + len(so_finding)
        if faltam:
            raise CommandError(
                f"{faltam} Evidencia sem par completo. Rode `migrate core 0054` ou investigue "
                "antes de descontinuar a gravação legada."
            )
        self.stdout.write(self.style.SUCCESS("Split reconciliado: todo legado tem par."))
