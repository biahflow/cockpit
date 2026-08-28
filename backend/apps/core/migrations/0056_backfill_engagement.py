"""Dá um mandato a cada projeto que já existe — **passo 2 de 3** (ADR 0050, FDD 046).

A 0055 abriu `Project.engagement` nullable; a 0057 a fecha em NOT NULL. Entre as duas está esta,
e o que ela precisa garantir é simples de dizer e fácil de errar: **nenhum projeto pode sobrar
sem engajamento**, ou o passo 3 falha no `ALTER TABLE` — em produção, no meio do deploy.

O agrupamento é **por conta**, e não por venda: um engajamento por `Client` que tenha ao menos um
`Project`, e todos os projetos daquela conta apontam para ele.

- `name = "Engajamento — <conta>"`. Nome derivado e reconhecível como automático: quem abrir a
  tela precisa saber que ninguém escreveu aquilo, e é isso que faz o nome ser trocado em vez de
  aceito por inércia.
- `owner = client.owner`. É a única atribuição de responsabilidade que a base já afirma sobre a
  conta. Inventar outra pessoa aqui seria dado falso numa coluna `PROTECT`.
- `started_at` = o menor `start_date` entre os projetos da conta — a data em que o trabalho de
  fato começou, que é o que o mandato deveria dizer.
- `status = active` para todos. Derivar "encerrado" do estado dos projetos exigiria decidir que
  uma conta sem projeto vivo encerrou o mandato, e isso é afirmação de relação comercial, não de
  banco. Errar para `active` é o lado barato: quem encerrou, encerra na tela.

**Contas sem projeto não ganham engajamento.** O mandato nasce quando a primeira venda vira
projeto (`convert-to-project` cria o dele), e criar engajamentos vazios encheria a listagem de
linhas que nunca tiveram trabalho — exatamente o ruído que faria a tela nova nascer inútil.

## O carimbo `needs_review`, e por que ele não separa nada

Agrupar por conta é a única regra que a base sustenta, e ela está **errada** para a conta que
comprou duas jornadas distintas com anos de intervalo: aquilo eram dois mandatos, e vira um só.
Separá-los exigiria saber o que foi contratado, e isso não está em nenhuma coluna — a migração
que tentasse adivinhar produziria uma divisão plausível e falsa, que é pior que uma junção
visivelmente grosseira, porque ninguém a revisa.

Então ela **sinaliza** em vez de decidir. Duas heurísticas, explícitas e deliberadamente
grosseiras, marcam `needs_review=True`:

1. **Mais de um `service_id` distinto** entre os projetos da conta. Degraus diferentes da escada
   FDE podem ser o mesmo mandato (Discovery → Feasibility → PROVE é a jornada inteira), mas
   também podem ser duas contratações sem relação. Nulo não conta como valor distinto: projeto
   sem serviço é lacuna de cadastro, não sinal de outra jornada.
2. **Mais de 180 dias entre o `start_date` de dois projetos consecutivos.** Meio ano de silêncio
   entre um projeto e o seguinte descreve uma conta que voltou a comprar, não um mandato contínuo.

Falso positivo aqui é barato (alguém olha e desmarca); falso negativo é caro (dois mandatos
somados para sempre num só, e ninguém procura). É por isso que o `ou` é inclusivo.

## Reversa

Aponta `Project.engagement` de volta para nulo e apaga **os engajamentos que esta migração
criou** — os que ainda têm o nome derivado e nenhuma oportunidade ligada. Não é uma assinatura
tão forte quanto a `legacy_opportunity` da 0052, e o motivo é que aqui não há onde guardá-la:
a coluna de vínculo é o próprio `Project.engagement`, que a reversa precisa limpar. Em
compensação, a janela em que a reversa é útil é a do deploy, antes de qualquer engajamento novo
existir, e ela só desce até a 0055 — onde a coluna volta a ser nullable e nada quebra.

## Idempotência

O `get_or_create` por conta e o `filter(engagement__isnull=True)` fazem a segunda execução não
ter nada a fazer, o que importa quando um deploy é reexecutado depois de falhar no passo 3.
"""

from django.db import migrations

JANELA_DE_JORNADA_DIAS = 180


def _precisa_de_revisao(projetos) -> bool:
    """As duas heurísticas do cabeçalho, sobre os projetos de **uma** conta, já ordenados."""
    servicos = {p.service_id for p in projetos if p.service_id is not None}
    if len(servicos) > 1:
        return True
    datas = sorted(p.start_date for p in projetos if p.start_date is not None)
    return any(
        (posterior - anterior).days > JANELA_DE_JORNADA_DIAS
        for anterior, posterior in zip(datas, datas[1:], strict=False)
    )


def backfill_engagement(apps, schema_editor):
    Client = apps.get_model("core", "Client")
    Project = apps.get_model("core", "Project")
    Engagement = apps.get_model("core", "Engagement")

    contas = Client.objects.filter(projects__isnull=False).distinct().order_by("id")
    for conta in contas.iterator():
        projetos = list(conta.projects.all().order_by("start_date", "id"))
        if not projetos:  # pragma: no cover - `filter` acima já garante, mas o custo é uma linha
            continue
        inicio = min((p.start_date for p in projetos if p.start_date is not None), default=None)
        engagement, _ = Engagement.objects.get_or_create(
            account=conta,
            name=f"Engajamento — {conta.name}",
            defaults={
                "owner_id": conta.owner_id,
                "status": "active",
                "started_at": inicio,
                "needs_review": _precisa_de_revisao(projetos),
            },
        )
        Project.objects.filter(client=conta, engagement__isnull=True).update(
            engagement=engagement
        )


def desfazer_backfill(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    Engagement = apps.get_model("core", "Engagement")

    criados = Engagement.objects.filter(
        name__startswith="Engajamento — ", commercial_opportunities__isnull=True
    ).distinct()
    ids = list(criados.values_list("id", flat=True))
    # Primeiro solta os projetos: `Project.engagement` é `PROTECT`, e o `delete()` abaixo
    # levantaria em vez de apagar se algum projeto ainda apontasse para cá.
    Project.objects.filter(engagement_id__in=ids).update(engagement=None)
    Engagement.objects.filter(id__in=ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0055_engagement"),
    ]

    operations = [
        migrations.RunPython(backfill_engagement, desfazer_backfill),
    ]
