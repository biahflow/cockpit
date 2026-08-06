"""Integração com o Google Drive (conta de serviço + Shared Drive).

Organiza os documentos por cliente usando o método PARA:
``[raiz]/{Cliente}/{1-Projetos|2-Áreas|3-Recursos|4-Arquivo}/arquivo``.
Quando ``GOOGLE_DRIVE_ENABLED`` está desligado, o app usa o storage local e nada
aqui é chamado. As funções que falam com a API do Google são finas e ficam fora da
cobertura de teste; a lógica de negócio (bucket PARA e cliente-dono) é testada.
"""

from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING

from django.conf import settings

from . import flags

if TYPE_CHECKING:
    from .models import Client, Document, Project

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveProviderError(Exception):
    """O Drive recusou: credencial, escopo, pasta inexistente, cota ou rede.

    Tipo **estreito** de propósito, como o `ai.AiProviderError` da rodada 2: quem chama envolve só
    a chamada de rede, e um erro de banco logo depois continua sendo 500 em vez de virar "o Google
    caiu" — que é exatamente o tipo de mentira que a FDD 024 existe para evitar.
    """

PROJECT_BUCKET = "1-Projetos"
CLIENT_BUCKET = "2-Áreas"
OPPORTUNITY_BUCKET = "3-Recursos"
ARCHIVE_BUCKET = "4-Arquivo"


# O id de uma pasta/Shared Drive só aparece **dentro** da URL, que é de onde a pessoa o copia —
# então colar a URL inteira é o erro natural, não descuido. Observado na rodada 3 da homologação
# (FDD 024): sem isto, o valor colado vira um 404 do Drive que se parece com falta de permissão, e
# manda quem opera depurar a coisa errada.
_URL_DE_PASTA = re.compile(r"/folders/([A-Za-z0-9_-]+)")


def is_enabled() -> bool:
    return flags.is_enabled("drive")


def parse_root_folder_id(valor: str) -> str:
    """Aceita o id da pasta **ou** a URL de onde ele foi copiado.

    O que não casa com o padrão volta como veio: não inventamos id — quem reclama de um valor
    inválido é a sonda do `check_integrations`, que pergunta ao Drive.
    """
    valor = (valor or "").strip()
    achado = _URL_DE_PASTA.search(valor)
    return achado.group(1) if achado else valor


def root_folder_id() -> str:
    return parse_root_folder_id(settings.GOOGLE_DRIVE_ROOT_FOLDER_ID)


def para_bucket_for(document: Document) -> str:
    """Subpasta PARA de acordo com o vínculo do documento."""
    if document.project_id:
        return PROJECT_BUCKET
    if document.opportunity_id:
        return OPPORTUNITY_BUCKET
    return CLIENT_BUCKET


def client_of(document: Document) -> Client | None:
    """Cliente-dono do documento, seguindo o vínculo (cliente, oportunidade ou projeto)."""
    if document.client_id:
        return document.client
    opportunity = document.opportunity if document.opportunity_id else None
    if opportunity:
        return opportunity.client
    project = document.project if document.project_id else None
    if project:
        return project.client
    return None


def _service():  # pragma: no cover - I/O com a API do Google
    from googleapiclient.discovery import build

    from . import google_auth

    return build(
        "drive", "v3", credentials=google_auth.credentials([DRIVE_SCOPE]), cache_discovery=False
    )


def _find_folder(service, name: str, parent: str) -> str | None:  # pragma: no cover - I/O
    safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"name = '{safe_name}' and '{parent}' in parents "
        f"and mimeType = '{FOLDER_MIME}' and trashed = false"
    )
    response = (
        service.files()
        .list(
            q=query,
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives",
        )
        .execute()
    )
    folders = response.get("files", [])
    return folders[0]["id"] if folders else None


def _create_folder(service, name: str, parent: str) -> str:  # pragma: no cover - I/O
    metadata = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent]}
    folder = service.files().create(body=metadata, fields="id", supportsAllDrives=True).execute()
    return folder["id"]


def _ensure_subfolder(service, name: str, parent: str) -> str:  # pragma: no cover - I/O
    return _find_folder(service, name, parent) or _create_folder(service, name, parent)


def _ensure_client_folder(service, client: Client) -> str:  # pragma: no cover - I/O
    if client.drive_folder_id:
        return client.drive_folder_id
    folder_id = _ensure_subfolder(service, client.name, root_folder_id())
    client.drive_folder_id = folder_id
    client.save(update_fields=["drive_folder_id", "updated_at"])
    return folder_id


def ensure_project_folder(project: Project) -> str:  # pragma: no cover - I/O
    """Garante ``{Cliente}/1-Projetos/{Projeto}`` e persiste o id no projeto.

    No-op (retorna "") quando o Drive está desligado, para o kickoff seguir sem I/O.
    """
    if not is_enabled():
        return ""
    if project.drive_folder_id:
        return project.drive_folder_id
    service = _service()
    client_folder = _ensure_client_folder(service, project.client)
    bucket_folder = _ensure_subfolder(service, PROJECT_BUCKET, client_folder)
    folder_id = _ensure_subfolder(service, project.name, bucket_folder)
    project.drive_folder_id = folder_id
    project.save(update_fields=["drive_folder_id", "updated_at"])
    return folder_id


def upload_document(document: Document, uploaded_file) -> tuple[str, str]:  # pragma: no cover - I/O
    """Sobe o arquivo para ``{Cliente}/{subpasta PARA}`` e retorna ``(file_id, link)``."""
    from googleapiclient.http import MediaIoBaseUpload

    client = client_of(document)
    if client is None:
        raise ValueError("Documento sem cliente-dono para o Drive.")
    service = _service()
    client_folder = _ensure_client_folder(service, client)
    bucket_folder = _ensure_subfolder(service, para_bucket_for(document), client_folder)
    media = MediaIoBaseUpload(
        io.BytesIO(uploaded_file.read()),
        mimetype=getattr(uploaded_file, "content_type", None) or "application/octet-stream",
        resumable=False,
    )
    created = (
        service.files()
        .create(
            body={"name": document.original_name, "parents": [bucket_folder]},
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return created["id"], created.get("webViewLink", "")


def download_document(document: Document) -> io.BytesIO:  # pragma: no cover - I/O
    """Baixa o conteúdo do arquivo pela conta de serviço, preservando o RBAC do app.

    Traduz qualquer falha para `DriveProviderError`. A FDD 024 blindou o **upload** e deixou esta
    crua: era 500 mudo no caminho em que a pessoa tenta pegar de volta o próprio arquivo.
    """
    from googleapiclient.http import MediaIoBaseDownload

    try:
        service = _service()
        request = service.files().get_media(fileId=document.drive_file_id, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    except Exception as exc:  # noqa: BLE001 - a família do SDK vira um tipo só
        raise DriveProviderError(str(exc) or exc.__class__.__name__) from exc
    buffer.seek(0)
    return buffer
