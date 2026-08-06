from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AppSetting,
    Client,
    Contact,
    Document,
    Invitation,
    Meeting,
    Milestone,
    Opportunity,
    Pendencia,
    PipelineStage,
    Project,
    ScheduledJobRun,
    Task,
    User,
)

admin.site.register(User, UserAdmin)
admin.site.register(
    [Client, Contact, PipelineStage, Opportunity, Project, Milestone, Task, Document, Invitation,
     AppSetting, Meeting, Pendencia]
)


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
