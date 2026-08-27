"""Linha do tempo operacional da entrega (FDD 042, ADR 0047).

Aditiva sobre a Jornada de Transformação que já existe (FDD 011/033): classifica a fase
configurável sobre a jornada canônica FDE (`canonical_stage`), dá à fase ativa de quem/de quê
espera (`waiting_party`/`blocker_note`) e abre o histórico append-only (`PhaseEvent`).

O backfill mapeia **apenas os nomes da semente padrão** (migração 0015) sobre a escada canônica —
`Welcome→discover`, `Launch Session→prioritize`, `Prove→prove`, `Scale→scale`, `Optimize→optimize`.
`Activation` e `Assisted Evolution` ficam em branco de propósito: são fases operacionais Biahflow
sem equivalente FDE limpo, e forçar um mapa mentiria. Qualquer fase renomeada pelo admin também
fica em branco — o mapa canônico é edição de admin daqui pra frente, como o `requires_gate`.

Nota de merge: o número 0047 é deliberado — 0046 foi reservado ao branch da projeção GitHub
(issue #41). Se ambos aterrissarem, a linearização das migrações é reconciliada no merge.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Nome exato da fase semeada → estágio canônico. Só a semente padrão; o resto fica em branco.
SEED_CANONICAL = {
    "Welcome": "discover",
    "Launch Session": "prioritize",
    "Prove": "prove",
    "Scale": "scale",
    "Optimize": "optimize",
}


def backfill_canonical_stage(apps, schema_editor):
    JourneyPhase = apps.get_model("core", "JourneyPhase")
    for name, stage in SEED_CANONICAL.items():
        JourneyPhase.objects.filter(name=name, canonical_stage="").update(canonical_stage=stage)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0045_engineering_handoff"),
    ]

    operations = [
        migrations.AddField(
            model_name="journeyphase",
            name="canonical_stage",
            field=models.CharField(
                blank=True,
                choices=[
                    ("discover", "Discover"),
                    ("prioritize", "Prioritize"),
                    ("feasibility", "Feasibility"),
                    ("prove", "Prove"),
                    ("scale", "Scale"),
                    ("optimize", "Optimize"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="projectphase",
            name="blocker_note",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="projectphase",
            name="waiting_party",
            field=models.CharField(
                blank=True,
                choices=[
                    ("biahflow", "Biahflow"),
                    ("client", "Cliente"),
                    ("engineering", "Engenharia"),
                    ("external", "Dependência externa"),
                    ("human_gate", "Human Gate"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="PhaseEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phase_name", models.CharField(blank=True, default="", max_length=80)),
                ("kind", models.CharField(choices=[("started", "Fase iniciada"), ("completed", "Fase concluída"), ("reopened", "Fase reaberta"), ("locked_by_redesign", "Fase trancada por REDESIGN"), ("gate_recorded", "Decision gate registrado"), ("waiting_set", "Aguardando definido"), ("waiting_cleared", "Aguardando resolvido")], max_length=24)),
                ("from_status", models.CharField(blank=True, default="", max_length=16)),
                ("to_status", models.CharField(blank=True, default="", max_length=16)),
                ("gate_outcome", models.CharField(blank=True, default="", max_length=16)),
                ("waiting_party", models.CharField(blank=True, default="", max_length=16)),
                ("note", models.TextField(blank=True, default="")),
                ("source", models.CharField(choices=[("user", "Ação de pessoa"), ("system", "Automático")], default="system", max_length=8)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="phase_events", to="core.project")),
                ("project_phase", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="events", to="core.projectphase")),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.RunPython(backfill_canonical_stage, noop),
    ]
