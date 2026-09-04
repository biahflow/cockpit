"""Issue #122, fatia 5.4 — a família 1 (`CobrancaContato`) vira `DunningContact`, e fala inglês.

Última das quatro famílias que a decisão D10 (`docs/ontology/language-map.md` §4) marcou, e a que
junta tudo o que as três anteriores fizeram em separado: **classe** (como a `0085` e a `0086`),
**tabela** (como a `0086`), **campo** (como a `0085`) e **valor** (como as três). Com ela não sobra
enum persistido em português no repositório.

## A coinagem, e por que ela veio pelo espelho

`dunning_step` e os cinco valores já estavam cunhados no `language-map` §4 — o que faltava era o
**substantivo da classe** que os carrega. `DunningContact` foi cunhado em
`docs/ontology/aliases.md` (§8), invertendo o caminho normal "Notion → espelho → Pulse", pelo mesmo
precedente e pelo mesmo motivo de `DunningSignal` na fatia 5.2: o conceito já estava decidido, e
esperar a página do Notion para escrever um nome que o campo já ditava adiaria a fatia por um ato
de secretaria. A página recebe depois.

## Por que o `RenameModel` pode renomear a tabela aqui

`docs/ontology/aliases.md` §2b lista as seis pks que o One deriva e **persiste**: `Client`
(→`Account`), `Project`, `Engagement`, `ProjectDeliverable`, `Document` e `Pendencia`. A pk do
contato de cobrança **não é uma delas**, e o argumento é mais forte que a lista: `portal.py` não
emite id de cobrança nenhum — o registro sequer atravessa a fronteira do snapshot, então não há
consumidor externo de que se despregar. Por isso não há `AlterModelTable` a escrever antes: o
`RenameModel` emite o `ALTER TABLE core_cobrancacontato RENAME TO core_dunningcontact`, que preserva
linha e pk pelo mesmo mecanismo da `0069`, e a reversa o desfaz. É a mesma leitura da `0086`.

## A ordem das operações, e por que ela é esta

1. `RenameModel` — a tabela primeiro, porque todas as operações seguintes se dizem sobre um
   `model_name`, e escrevê-las sobre o nome velho deixaria o arquivo falando as duas línguas no
   meio de si mesmo.
2. `RenameIndex` e `RemoveConstraint` — o que o renome de tabela e de coluna arrasta, aberto aqui e
   fechado no fim (ver a seção seguinte).
3. `RenameField` (`degrau` → `dunning_step`) — a coluna renomeia, linha e pk sobrevivem (§2b).
4. `AlterField` — os `choices` novos, sobre o nome de coluna já novo.
5. `RunPython` — a tradução do dado, **depois** da 3, porque ela opera sobre a coluna nova:
   invertidas, o `.update()` teria de nomear `degrau` e a migração passaria por um estado em que
   fala metade de cada nome. É a mesma ordem que a `0085` explicou.
6. `AddConstraint` — a constraint de volta, já citando `dunning_step`.

A reversa é a lista ao contrário, e o Django a percorre sozinho: o dado volta ao português, depois
os `choices`, depois o nome da coluna, e só então a tabela volta a se chamar `core_cobrancacontato`.

## As três operações que o renome arrasta, e que as fatias anteriores não tiveram

Esta é a primeira família em que renome de **tabela** e de **campo** chegam juntos, e é isso que
produz as três últimas operações — nenhuma delas é decisão nova, todas são o que
`makemigrations` exige para o estado voltar a bater com o modelo:

* `RenameIndex` — o índice de `Meta.indexes` não tem nome declarado, então o Django o deriva do
  **nome da tabela** (`core_cobran_…` → `core_dunnin_…`). Sem isto, `makemigrations --check`
  reprova para sempre.
* `RemoveConstraint` + `AddConstraint` — a `UniqueConstraint` cita o campo pelo nome, e
  `RenameField` **não** reescreve `Meta.constraints`; não existe operação de renome dentro de
  constraint, então o caminho é derrubar e recriar o mesmo índice único. Elas **abraçam** o
  `RenameField`, uma de cada lado, e a razão está no comentário junto do `RemoveConstraint`: a
  reversa recria a constraint como o estado vizinho a descreve, e com as duas depois do renome ela
  tentava recriá-la sobre um campo `degrau` que já não existe. O **nome** dela
  (`unique_cobranca_degrau_por_fatura`) fica como está de propósito: nome de constraint é
  identificador de banco, não contrato, e trocá-lo custaria outro `DROP`/`CREATE` por nada. O que a
  §2b exige é que a linha e a pk sobrevivam — e nenhuma destas operações as toca.

## O par que autoriza, e a metade que não está aqui

`docs/ontology/aliases.md`, a linha "degraus `pre_aviso` / `lembrete` / `firme` / `escalada` /
`renegociacao`" da tabela de aliases vivos, e a nota D10 logo abaixo dela.

**As `key` da dataclass `cobranca.DunningStep` são estes mesmos valores**, e por isso atravessaram
na mesma fatia, fora desta migração: traduzir a coluna sem traduzir as chaves da régua faria
`_degrau_gasto` parar de casar com o banco **em silêncio** — a idempotência nunca mais encontraria
o degrau gasto, e o mesmo e-mail sairia de novo.

## A checagem que a fatia pediu

Nenhuma migração ou seed anterior cria `CobrancaContato` com degrau em português: a `0041_regua_de_
cobranca` só cria o modelo (`CreateModel`), sem `RunPython` de dados, e não há `management command`
que semeie contato — os dois caminhos até a linha (o job e a action de envio) são de runtime. A
forward abaixo não precisa cobrir linhas criadas por outra migração.
"""

from django.db import migrations, models

# Um `.update()` por par, e não `RunPython` linha a linha, pelo motivo da `0084`: a tradução é sobre
# o **valor** fechado do enum, não sobre uma coluna livre.
_PARES_PT_PARA_EN: tuple[tuple[str, str], ...] = (
    ("pre_aviso", "pre_notice"),
    ("lembrete", "reminder"),
    ("firme", "firm"),
    ("escalada", "escalation"),
    ("renegociacao", "renegotiation"),
)


def traduzir_para_ingles(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Forward: cinco `.filter(dunning_step=antigo).update(dunning_step=novo)`, um por par."""
    DunningContact = apps.get_model("core", "DunningContact")
    for antigo, novo in _PARES_PT_PARA_EN:
        DunningContact.objects.filter(dunning_step=antigo).update(dunning_step=novo)


def traduzir_para_portugues(apps, schema_editor):  # type: ignore[no-untyped-def]
    """Reversa simétrica: valor persistido sem caminho de volta é migração destrutiva disfarçada."""
    DunningContact = apps.get_model("core", "DunningContact")
    for antigo, novo in _PARES_PT_PARA_EN:
        DunningContact.objects.filter(dunning_step=novo).update(dunning_step=antigo)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0086_a_satisfacao_fala_ingles'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='CobrancaContato',
            new_name='DunningContact',
        ),
        migrations.RenameIndex(
            model_name='dunningcontact',
            new_name='core_dunnin_account_fa8574_idx',
            old_name='core_cobran_account_b3dc5c_idx',
        ),
        # **Antes** do `RenameField`, e a ordem foi medida: `RemoveConstraint.database_backwards`
        # recria a constraint como ela está no estado imediatamente anterior a si mesma. Escrita
        # depois do renome, esse estado ainda diz `fields=('invoice', 'degrau')` — porque
        # `RenameField` não reescreve `Meta.constraints`, que é justamente o motivo destas duas
        # operações existirem — e a reversa morria com `FieldDoesNotExist: has no field named
        # 'degrau'` num modelo que já se chama `dunning_step`. Aqui o par abre e fecha em volta do
        # renome, e os dois sentidos casam.
        migrations.RemoveConstraint(
            model_name='dunningcontact',
            name='unique_cobranca_degrau_por_fatura',
        ),
        migrations.RenameField(
            model_name='dunningcontact',
            old_name='degrau',
            new_name='dunning_step',
        ),
        migrations.AlterField(
            model_name='dunningcontact',
            name='dunning_step',
            field=models.CharField(
                choices=[
                    ('pre_notice', 'Pré-aviso'),
                    ('reminder', 'Lembrete'),
                    ('firm', 'Cobrança firme'),
                    ('escalation', 'Escalada interna'),
                    ('renegotiation', 'Renegociação'),
                ],
                max_length=16,
            ),
        ),
        migrations.RunPython(traduzir_para_ingles, traduzir_para_portugues),
        migrations.AddConstraint(
            model_name='dunningcontact',
            constraint=models.UniqueConstraint(
                fields=('invoice', 'dunning_step'), name='unique_cobranca_degrau_por_fatura'
            ),
        ),
    ]
