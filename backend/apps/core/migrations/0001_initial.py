# Generated manually from the initial domain model.
import uuid

import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def seed_pipeline(apps, schema_editor):
    stage = apps.get_model("core", "PipelineStage")
    stage.objects.bulk_create([
        stage(name="Prospecção", kind="open", position=10),
        stage(name="Qualificação", kind="open", position=20),
        stage(name="Proposta", kind="open", position=30),
        stage(name="Negociação", kind="open", position=40),
        stage(name="Ganho", kind="won", position=50),
        stage(name="Perdido", kind="lost", position=60),
    ])


class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]
    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
                ("username", models.CharField(error_messages={"unique": "A user with that username already exists."}, help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.", max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name="username")),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="email address")),
                ("is_staff", models.BooleanField(default=False, help_text="Designates whether the user can log into this admin site.", verbose_name="staff status")),
                ("is_active", models.BooleanField(default=True, help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.", verbose_name="active")),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                ("role", models.CharField(choices=[("admin", "Administrador"), ("sales", "Vendas"), ("delivery", "Entrega")], default="delivery", max_length=16)),
                ("groups", models.ManyToManyField(blank=True, help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.", related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
                ("user_permissions", models.ManyToManyField(blank=True, help_text="Specific permissions for this user.", related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
            ],
            options={"verbose_name": "user", "verbose_name_plural": "users"},
            managers=[("objects", django.contrib.auth.models.UserManager())],
        ),
        migrations.CreateModel(
            name="Client",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(max_length=255)), ("legal_name", models.CharField(blank=True, max_length=255)), ("tax_id", models.CharField(blank=True, max_length=32)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_clients", to=settings.AUTH_USER_MODEL)),
            ], options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="PipelineStage",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=80)), ("kind", models.CharField(choices=[("open", "Aberta"), ("won", "Ganho"), ("lost", "Perdido")], default="open", max_length=8)), ("position", models.PositiveIntegerField(default=0))],
            options={"ordering": ["position", "id"]},
        ),
        migrations.CreateModel(
            name="Contact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(max_length=255)), ("email", models.EmailField(blank=True, max_length=254)), ("phone", models.CharField(blank=True, max_length=32)), ("job_title", models.CharField(blank=True, max_length=128)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contacts", to="core.client")),
            ], options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Opportunity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("title", models.CharField(max_length=255)), ("scope", models.TextField(blank=True)), ("estimated_value", models.DecimalField(decimal_places=2, max_digits=12)), ("expected_close_date", models.DateField()),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="opportunities", to="core.client")), ("contact", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.contact")), ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_opportunities", to=settings.AUTH_USER_MODEL)), ("stage", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="opportunities", to="core.pipelinestage")),
            ], options={"ordering": ["expected_close_date", "id"]},
        ),
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(max_length=255)), ("description", models.TextField(blank=True)), ("start_date", models.DateField()), ("due_date", models.DateField()), ("status", models.CharField(choices=[("planning", "Planejamento"), ("active", "Ativo"), ("on_hold", "Em espera"), ("completed", "Concluído")], default="planning", max_length=16)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="projects", to="core.client")), ("opportunity", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="project", to="core.opportunity")), ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_projects", to=settings.AUTH_USER_MODEL)),
            ], options={"ordering": ["due_date", "id"]},
        ),
        migrations.CreateModel(
            name="Milestone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("title", models.CharField(max_length=255)), ("description", models.TextField(blank=True)), ("due_date", models.DateField()), ("completed_at", models.DateTimeField(blank=True, null=True)), ("status", models.CharField(choices=[("todo", "A fazer"), ("in_progress", "Em andamento"), ("done", "Concluído")], default="todo", max_length=16)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_items", to=settings.AUTH_USER_MODEL)), ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_items", to="core.project")),
            ], options={"ordering": ["due_date", "id"]},
        ),
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("title", models.CharField(max_length=255)), ("description", models.TextField(blank=True)), ("due_date", models.DateField()), ("completed_at", models.DateTimeField(blank=True, null=True)), ("status", models.CharField(choices=[("todo", "A fazer"), ("in_progress", "Em andamento"), ("done", "Concluído")], default="todo", max_length=16)),
                ("milestone", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tasks", to="core.milestone")), ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_items", to=settings.AUTH_USER_MODEL)), ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(class)s_items", to="core.project")),
            ], options={"ordering": ["due_date", "id"]},
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("file", models.FileField(upload_to="documents/%Y/%m/")), ("original_name", models.CharField(max_length=255)),
                ("client", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="core.client")), ("opportunity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="core.opportunity")), ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="core.project")), ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="uploaded_documents", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Invitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("email", models.EmailField(max_length=254, unique=True)), ("role", models.CharField(choices=[("admin", "Administrador"), ("sales", "Vendas"), ("delivery", "Entrega")], max_length=16)), ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)), ("expires_at", models.DateTimeField()), ("accepted_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("invited_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sent_invitations", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name="pipelinestage", constraint=models.UniqueConstraint(condition=models.Q(("kind", "won")), fields=("kind",), name="one_won_pipeline_stage")),
        migrations.AddConstraint(model_name="pipelinestage", constraint=models.UniqueConstraint(condition=models.Q(("kind", "lost")), fields=("kind",), name="one_lost_pipeline_stage")),
        migrations.RunPython(seed_pipeline, migrations.RunPython.noop),
    ]
