from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AppSetting,
    Client,
    CommercialOpportunity,
    Contact,
    Decisao,
    Document,
    Engagement,
    EngineeringHandoff,
    Invitation,
    Meeting,
    Milestone,
    Pendencia,
    PipelineStage,
    Project,
    ScheduledJobRun,
    Task,
    User,
)

admin.site.register(User, UserAdmin)
admin.site.register(
    [Client, Contact, PipelineStage, CommercialOpportunity, Project, Milestone, Task, Document,
     Invitation, AppSetting, Meeting, Pendencia, Decisao, EngineeringHandoff]
)


# `commercial_model` não tem tela própria (a tela de Engagement exige Design Approval Package, e
# não há um aprovado — FDD 046), e a lista de contas de design partner cresce por venda, não por
# deploy. Sem um lugar para carimbar a conta nova, o campo dependeria de shell/curl toda vez. O
# admin não substitui a tela: é o único jeito de gente-não-engenharia ler e mudar o campo hoje.
@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    list_display = ["name", "account", "status", "commercial_model", "owner"]
    list_filter = ["status", "commercial_model"]
    search_fields = ["name", "account__name"]


# Só-leitura: quem escreve aqui é o `run_scheduler`. Editar o carimbo à mão é reagendar um job por
# baixo do agendador — e um `last_attempt_at` apagado por engano reenviaria o digest do dia.
@admin.register(ScheduledJobRun)
class ScheduledJobRunAdmin(admin.ModelAdmin):
    list_display = ["name", "last_attempt_at", "last_success_at", "ok"]
    readonly_fields = ["name", "last_attempt_at", "last_success_at", "ok", "detail"]

    def has_add_permission(self, request, obj=None) -> bool:  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # type: ignore[no-untyped-def]
        return False
