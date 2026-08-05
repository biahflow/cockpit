from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# O `MEDIA_ROOT` não é servido pelo Django em nenhum ambiente. Documento é recurso privado
# (ADR 0002): a única porta é `/api/v1/documents/<id>/download/`, que passa por sessão e
# RBAC. Servir `/media/` sob `if DEBUG` deixava contrato e proposta acessíveis por URL
# adivinhável em dev e homologação, onde `DJANGO_DEBUG=true` é o default. Ver FDD 017.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/", include("apps.core.urls")),
]
