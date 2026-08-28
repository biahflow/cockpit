"""`gate_outcome` → `gate_decision` nos dois modelos que carregam a decisão do gate (D7).

"Outcome" já é o resultado de negócio medido (`Measurement(kind=outcome)`, tabela mestra do
`docs/ontology/language-map.md`), e a saída de um decision gate não é isso — é uma decisão. A
decisão D7 renomeia, e a ADR 0052 é o que autoriza fazê-lo agora em vez de na Fase 6.

## Só `RenameField`, e é o que a `aliases.md` §2b permite

Renome de **coluna** preserva linha e pk. A proibição da §2b é contra modelo novo mais migração de
dados, porque **seis pks saíram deste repositório** — o One deriva chave de identidade delas e as
persiste. Um `ALTER TABLE … RENAME COLUMN` não move linha nenhuma e não toca em pk.

Nenhuma tabela troca de nome aqui: os dois modelos continuam se chamando `ProjectPhase` e
`PhaseEvent`, que já são os nomes canônicos. O renome de classe que a ADR 0052 antecipa é das
outras três fatias da issue #67.

Os quatro valores (`go`, `conditional_go`, `redesign`, `no_go`) não mudam, então não há dado a
converter: as linhas gravadas continuam válidas sob o nome novo.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0059_engagement_commercial_model"),
    ]

    operations = [
        migrations.RenameField(
            model_name="projectphase", old_name="gate_outcome", new_name="gate_decision"
        ),
        migrations.RenameField(
            model_name="phaseevent", old_name="gate_outcome", new_name="gate_decision"
        ),
    ]
