"""Semeia a Jornada de Transformação padrão e materializa nos projetos existentes.

As fases/entregáveis são configuráveis (o admin pode renomear/reordenar depois); este é
apenas o ponto de partida com o vocabulário Biahflow. O backfill dá aos projetos já
existentes o mesmo estado inicial que um projeto novo recebe via signals.
"""

from django.db import migrations
from django.utils import timezone

# (nome da fase, descrição, [entregáveis]) — ordem = ordem da jornada.
DEFAULT_PHASES = [
    ("Welcome", "Recepção e onboarding do cliente.",
     ["Acesso ao portal", "Apresentação da equipe", "Canais de comunicação definidos"]),
    ("Launch Session", "Alinhamento e planejamento do piloto.",
     ["Escopo do piloto", "Cronograma", "Equipe definida"]),
    ("Prove", "Construção e validação do piloto.",
     ["Funcionário Digital", "Dashboard", "KPIs", "Manual", "Vídeo de treinamento"]),
    ("Activation", "Entrada em produção (go-live).",
     ["Go-live", "Treinamento da operação"]),
    ("Assisted Evolution", "Acompanhamento assistido pós go-live.",
     ["Acompanhamento assistido", "Ajustes pós go-live"]),
    ("Scale", "Expansão para novos processos.",
     ["Roadmap de expansão", "Processos priorizados"]),
    ("Optimize", "Melhoria contínua da operação.",
     ["Revisão de KPIs", "Plano de melhoria contínua"]),
]


def seed(apps, schema_editor):
    JourneyPhase = apps.get_model("core", "JourneyPhase")
    PhaseDeliverable = apps.get_model("core", "PhaseDeliverable")
    if JourneyPhase.objects.exists():  # respeita configuração já existente
        return
    for position, (name, description, deliverables) in enumerate(DEFAULT_PHASES):
        phase = JourneyPhase.objects.create(name=name, description=description, position=position)
        for d_position, d_name in enumerate(deliverables):
            PhaseDeliverable.objects.create(phase=phase, name=d_name, position=d_position)


def backfill(apps, schema_editor):
    JourneyPhase = apps.get_model("core", "JourneyPhase")
    ProjectPhase = apps.get_model("core", "ProjectPhase")
    ProjectDeliverable = apps.get_model("core", "ProjectDeliverable")
    Project = apps.get_model("core", "Project")

    phases = list(JourneyPhase.objects.prefetch_related("deliverables").order_by("position", "id"))
    if not phases:
        return
    now = timezone.now()
    for project in Project.objects.all():
        if ProjectPhase.objects.filter(project=project).exists():
            continue
        for index, phase in enumerate(phases):
            project_phase = ProjectPhase.objects.create(
                project=project,
                phase=phase,
                status="active" if index == 0 else "locked",
                started_at=now if index == 0 else None,
            )
            for deliverable in phase.deliverables.all():
                ProjectDeliverable.objects.create(
                    project_phase=project_phase,
                    name=deliverable.name,
                    position=deliverable.position,
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_journeyphase_phasedeliverable_projectphase_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, noop),
        migrations.RunPython(backfill, noop),
    ]
