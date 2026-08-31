from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Account,
    AppSetting,
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
    [Account, Contact, PipelineStage, CommercialOpportunity, Project, Milestone, Task, Document,
     Invitation, AppSetting, Meeting, Pendencia, Decisao, EngineeringHandoff]
)


# A tela operacional cobre **criação nova** com instrumento assinado (DAP engagement r2). O admin
# continua sendo a superfície deliberada de remediação do legado: a migração 0074 não inventa
# venda nem acordo, apenas carimba `needs_review=True` para uma pessoa registrar o que observou.
@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    list_display = [
        "name", "account", "status", "commercial_model", "needs_review", "owner"
    ]
    list_filter = ["status", "commercial_model", "needs_review"]
    search_fields = [
        "name",
        "account__name",
        "originating_commercial_opportunity__title",
        "originating_design_partner_agreement__original_name",
    ]


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
