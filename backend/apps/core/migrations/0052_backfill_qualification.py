"""Traduz em `Qualification` a conversa que estava gravada como venda (ADR 0049).

Até a 0051, `POST /leads/{id}/convert/` criava uma `Opportunity` no degrau `qualification_call`.
Cada uma dessas linhas é uma **avaliação de lead**, não uma venda: ela nunca teve valor, nunca
passou por proposta e, ainda assim, somava no funil e podia virar `Project`. Deixá-las como estão
manteria a leitura errada do pipeline exatamente onde a fatia nova promete corrigi-la.

O que a migração faz, por oportunidade de `qualification_call`:

1. **Cria a `Qualification`** com o lead que aponta para a oportunidade, a conta, a data de criação
   e o dono da oportunidade como avaliador. O `outcome` é **derivado do estado comercial**, que é a
   única evidência que existe do que se decidiu na época: estágio `won` (ou já com projeto) foi
   `qualified`; estágio `lost` foi `disqualified`; qualquer estágio aberto vira `nurture`, o
   resultado que **não** afirma nada — a conversa aconteceu e a decisão ficou em aberto, que é
   literalmente o estado daquela linha. Para o `nurture`, `nurture_until` é a criação + 180 dias,
   porque o `clean()` do modelo exige data de retorno e inventar "hoje" faria a lista de nutrição
   nascer inteira vencida.
2. **Registra uma `Activity`** de nota no cliente, apontando para a oportunidade. É a auditoria de
   que a linha existiu e do que aconteceu com ela — sem isso, quem abrir a conta daqui a um ano vê
   uma oportunidade arquivada sem explicação.
3. **Arquiva a oportunidade**, e só quando ela **não** tem `Project`. Com projeto, fica como está:
   `Project.opportunity` é `PROTECT` e a tela do projeto lê a oportunidade para montar o histórico
   comercial — escondê-la deixaria o projeto apontando para um registro que a interface não mostra
   (o mesmo argumento de `OpportunityViewSet.perform_destroy`, FDD 025).

**Nada é apagado.** Arquivamento é soft (`archived_at`), `legacy_opportunity` guarda o vínculo, e a
reversa desfaz os dois lados: apaga as avaliações que esta migração criou (as que têm
`legacy_opportunity`), remove as notas de auditoria e desarquiva o que ela arquivou — **só** isso.
O que ela arquivou se reconhece por uma assinatura, não por uma janela de tempo: a ida grava
`archived_at` com o **mesmo instante** da avaliação que acabou de criar, e a volta compara por
igualdade. Arquivamento feito por gente, antes ou depois do deploy, tem outro instante e a reversa
não o toca.

## Sobre o reverso do projeto

"Tem projeto?" se responde por `_tem_projeto` e não por um nome de atributo cravado. Quando esta
migração foi escrita o reverso se chamava `opportunity.project`, porque `Project.opportunity` era
`OneToOneField`; a ADR 0050 renomeou o campo para `originating_commercial_opportunity` e o tornou
1-N, e o reverso virou `opportunity.projects`.

Sob `migrate` isso seria indiferente — um `RunPython` recebe o estado histórico, onde o nome
antigo continua valendo para sempre. O que não é indiferente é o **teste** de
`tests/regression/test_qualification_backfill.py`, que executa esta função contra o registro vivo
e um banco no HEAD, e é a única coisa que prova que ela faz o que diz. Com o nome cravado, ele
passou a ler `False` para toda oportunidade e a afirmar um comportamento que a migração não tem —
verde, e medindo o esquema errado. As duas linhas abaixo mantêm a resposta certa nos dois estados;
o comportamento em produção é exatamente o de antes.

**Oportunidade de `qualification_call` sem lead é pulada.** `Qualification.lead` é obrigatório
porque uma avaliação sem lead não é avaliação de ninguém; inventar um lead sintético colocaria dado
falso na base para satisfazer uma FK. O caso aparece quando alguém criou a oportunidade à mão pela
tela do pipeline, escolhendo o degrau gratuito. O comando
`manage.py reconciliar_qualification` lista essas linhas depois do deploy — a decisão sobre cada
uma é de gente, e é por isso que ela não está aqui.
"""

from datetime import timedelta

from django.db import migrations

NURTURE_DIAS = 180


def _tem_projeto(opportunity):
    """O reverso do projeto, sob qualquer um dos dois estados. Ver o cabeçalho."""
    projetos = getattr(opportunity, "projects", None)  # depois da ADR 0050: FK 1-N
    if projetos is not None:
        return projetos.exists()
    return hasattr(opportunity, "project")  # no estado histórico daqui: OneToOneField


def backfill_qualification(apps, schema_editor):
    Opportunity = apps.get_model("core", "Opportunity")
    Qualification = apps.get_model("core", "Qualification")
    Activity = apps.get_model("core", "Activity")

    candidatas = (
        Opportunity.objects.filter(service__tier="qualification_call")
        .select_related("stage")
        .order_by("id")
    )
    for opportunity in candidatas.iterator():
        if hasattr(opportunity, "backfilled_qualification"):
            continue  # já traduzida (a migração é idempotente por linha)
        lead = opportunity.leads.order_by("id").first()
        if lead is None:
            continue  # sem lead não há avaliação; o comando de reconciliação reporta
        tem_projeto = _tem_projeto(opportunity)
        kind = opportunity.stage.kind if opportunity.stage_id else "open"
        if kind == "won" or tem_projeto:
            outcome, nurture_until = "qualified", None
        elif kind == "lost":
            outcome, nurture_until = "disqualified", None
        else:
            outcome = "nurture"
            nurture_until = (opportunity.created_at + timedelta(days=NURTURE_DIAS)).date()
        qualification = Qualification.objects.create(
            lead=lead,
            account_id=opportunity.client_id,
            happened_at=opportunity.created_at,
            assessor_id=opportunity.owner_id,
            outcome=outcome,
            nurture_until=nurture_until,
            rationale=opportunity.scope or "",
            legacy_opportunity=opportunity,
        )
        Activity.objects.create(
            client_id=opportunity.client_id,
            opportunity=opportunity,
            kind="note",
            happened_on=opportunity.created_at.date(),
            summary=f"Qualificação migrada da oportunidade #{opportunity.pk}",
            owner_id=opportunity.owner_id,
        )
        if not tem_projeto and opportunity.archived_at is None:
            # **O carimbo é o instante da avaliação, e não `now()`.** É o que torna "arquivado por
            # esta migração" uma *assinatura* em vez de uma janela de tempo: a reversa compara por
            # igualdade e não toca em nada com outro instante. Com um carimbo próprio, a volta
            # precisaria de um critério aproximado ("posterior à avaliação"), e ele ressuscitaria
            # a oportunidade que uma pessoa arquivou **depois** do deploy — a mesma perda que ele
            # existiria para evitar, do outro lado da linha do tempo.
            opportunity.archived_at = qualification.created_at
            opportunity.save(update_fields=["archived_at"])


def desfazer_backfill(apps, schema_editor):
    Opportunity = apps.get_model("core", "Opportunity")
    Qualification = apps.get_model("core", "Qualification")
    Activity = apps.get_model("core", "Activity")

    migradas = Qualification.objects.filter(legacy_opportunity__isnull=False)
    ids, desarquivar = [], []
    # Tudo antes do `delete()`: depois, o vínculo que diz quais oportunidades foram tocadas já não
    # existe. E desarquiva **só o que esta migração arquivou**, por **igualdade** de carimbo: a ida
    # grava `archived_at` com o mesmo instante da avaliação que criou, então o par idêntico é a
    # assinatura dela. Desarquivar em bloco restauraria uma oportunidade que alguém tirou da lista
    # de propósito, e um critério de janela ("carimbo posterior ao da avaliação") erraria nos dois
    # sentidos: pega o arquivamento humano **depois** do deploy e depende de a ida ter acontecido
    # antes dele. Instante diferente é decisão de gente, e a volta não a desfaz.
    for qualification in migradas.select_related("legacy_opportunity"):
        opportunity = qualification.legacy_opportunity
        ids.append(opportunity.pk)
        if opportunity.archived_at == qualification.created_at:
            desarquivar.append(opportunity.pk)
    Opportunity.objects.filter(id__in=desarquivar).update(archived_at=None)
    Activity.objects.filter(
        opportunity_id__in=ids, kind="note", summary__startswith="Qualificação migrada da "
    ).delete()
    migradas.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0051_qualification_e_service_category"),
    ]

    operations = [
        migrations.RunPython(backfill_qualification, desfazer_backfill),
    ]
