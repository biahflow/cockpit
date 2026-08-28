"""Parte cada `Evidencia` no par `Evidence` + `Finding` que a ADR 0049 pede (FDD 045).

A `Evidencia` da FDD 039 guarda três coisas numa linha só: a **forma** de onde o achado veio, a
**afirmação** já interpretada e o **rótulo** epistemológico. O split separa o dado bruto (que
sustenta) da conclusão (que é sustentada). Sem backfill, tudo o que foi levantado até aqui ficaria
só do lado antigo, e o modelo novo nasceria vazio — o que na prática significaria descartar o
Discovery de todo mundo e recomeçar.

**Nada é apagado nem alterado.** A gravação legada continua (é dual-write nesta fase: a tela de
processo e `processos.custo_do_estado_atual` ainda leem `Evidencia`), e cada linha nova aponta de
volta para a de origem por `legacy_evidencia`. É esse ponteiro que permite descontinuar o legado
depois sem perder o vínculo — e é ele que a reversa usa para desfazer exatamente o que esta
migração fez, sem tocar no que foi criado à mão.

Três aproximações declaradas, porque nenhuma delas está no dado de origem:

1. **`raw_excerpt` recebe `content`.** É conhecidamente impreciso: o `content` legado pode ser
   conclusão interpretada ("o fechamento é lento"), e não o trecho bruto que a `Evidence` pede.
   É a única fonte que existe, e inventar uma separação que o dado não tem seria pior — a marca
   de que o texto veio do modelo fundido é o próprio `legacy_evidencia` preenchido.
2. **`rotulo=fato` vira `reviewed_by=registered_by` e `reviewed_at=updated_at`.** O modelo antigo
   não registrava revisão; alguém marcou aquilo como fato, e quem registrou o achado na última
   edição é a melhor aproximação auditável de quem e quando. Um `fact` sem revisor nenhum seria
   dívida invisível — assim ela fica nomeada, e o comando `reconciliar_evidence_finding` conta as
   que sobraram sem ninguém.
3. **Arquivadas vêm junto, com o carimbo preservado.** Deixá-las fora faria o par novo divergir do
   legado justamente no que já tinha sido decidido guardar, e desarquivar do lado antigo passaria
   a produzir um registro sem contraparte.

Idempotente pelo `legacy_evidencia`: rodar duas vezes não duplica.
"""

from django.db import migrations

from apps.core.models import hash_do_trecho

#: As cinco formas, uma a uma. `Evidencia.Forma` → `Evidence.Kind`.
FORMA_PARA_KIND = {
    "entrevista": "interview",
    "observacao": "observation",
    "artefato": "artifact",
    "sistema": "system",
    "dado": "data",
}

#: Os três rótulos. `Evidencia.Rotulo` → `Finding.EpistemicStatus` (ADR 0049, `language-map` §4).
ROTULO_PARA_STATUS = {
    "fato": "fact",
    "hipotese": "hypothesis",
    "desconhecido": "unknown",
}


def split_evidencias(apps, schema_editor):
    Evidencia = apps.get_model("core", "Evidencia")
    Evidence = apps.get_model("core", "Evidence")
    Finding = apps.get_model("core", "Finding")

    for evidencia in Evidencia.objects.select_related("processo").iterator():
        if Evidence.objects.filter(legacy_evidencia_id=evidencia.pk).exists():
            continue
        processo = evidencia.processo
        conta_id = processo.client_id
        evidence = Evidence.objects.create(
            account_id=conta_id,
            process_id=processo.pk,
            step_id=evidencia.etapa_id,
            # Forma fora do vocabulário não existe (o campo é `choices` desde a FDD 039), mas o
            # `.get` com padrão evita que uma linha estranha derrube a migração inteira: entrevista
            # é a forma menos afirmativa das cinco, e é a que a extração já usa.
            kind=FORMA_PARA_KIND.get(evidencia.forma, "interview"),
            raw_excerpt=evidencia.content,
            source_meeting_id=evidencia.source_meeting_id,
            captured_at=evidencia.created_at,
            captured_by_id=evidencia.registered_by_id,
            content_hash=hash_do_trecho(evidencia.content),
            legacy_evidencia_id=evidencia.pk,
            archived_at=evidencia.archived_at,
        )
        e_fato = evidencia.rotulo == "fato"
        finding = Finding.objects.create(
            account_id=conta_id,
            process_id=processo.pk,
            step_id=evidencia.etapa_id,
            statement=evidencia.content,
            epistemic_status=ROTULO_PARA_STATUS.get(evidencia.rotulo, "hypothesis"),
            reviewed_by_id=evidencia.registered_by_id if e_fato else None,
            reviewed_at=evidencia.updated_at if e_fato else None,
            legacy_evidencia_id=evidencia.pk,
            archived_at=evidencia.archived_at,
        )
        finding.evidences.add(evidence)


def desfaz_split(apps, schema_editor):
    """Apaga **só** o que veio do backfill — o que o `legacy_evidencia` marca.

    Sem esse recorte a reversa levaria junto a `Evidence` e o `Finding` criados depois pela
    extração e pela tela, que nunca tiveram origem legada.
    """
    apps.get_model("core", "Finding").objects.filter(
        legacy_evidencia__isnull=False
    ).delete()
    apps.get_model("core", "Evidence").objects.filter(
        legacy_evidencia__isnull=False
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0053_evidence_finding_discovery"),
    ]

    operations = [
        migrations.RunPython(split_evidencias, desfaz_split),
    ]
