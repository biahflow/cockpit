from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from apps.core.models import Client, Meeting, Opportunity, PipelineStage, Project, User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.test")
    role = User.Role.ADMIN

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "Segura123!senha")
        if create:
            obj.save()


class ClientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Client

    name = factory.Sequence(lambda n: f"Cliente {n}")
    owner = factory.SubFactory(UserFactory)


class PipelineStageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PipelineStage

    name = factory.Sequence(lambda n: f"Etapa {n}")
    kind = PipelineStage.Kind.OPEN
    position = factory.Sequence(lambda n: n + 100)


class OpportunityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Opportunity

    client = factory.SubFactory(ClientFactory)
    title = "Diagnóstico comercial"
    scope = "Escopo inicial"
    estimated_value = Decimal("10000.00")
    stage = factory.SubFactory(PipelineStageFactory)
    owner = factory.SubFactory(UserFactory)
    expected_close_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=7))


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    client = factory.SubFactory(ClientFactory)
    name = "Projeto de aceleração"
    owner = factory.SubFactory(UserFactory)
    start_date = factory.LazyFunction(timezone.localdate)
    due_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=30))


class MeetingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Meeting

    project = factory.SubFactory(ProjectFactory)
    title = "Reunião de discovery"
    date = factory.LazyFunction(timezone.localdate)
    transcript = "Cliente relatou processo manual de faturamento e atraso nas entregas."
    status = Meeting.Status.HELD
