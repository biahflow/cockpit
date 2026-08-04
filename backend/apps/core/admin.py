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
    Task,
    User,
)

admin.site.register(User, UserAdmin)
admin.site.register(
    [Client, Contact, PipelineStage, Opportunity, Project, Milestone, Task, Document, Invitation,
     AppSetting, Meeting, Pendencia]
)
