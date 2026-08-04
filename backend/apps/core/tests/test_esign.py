import pytest

from apps.core import esign
from apps.core.models import Document, SignatureRequest

from .factories import ClientFactory, UserFactory


def _document() -> Document:
    user = UserFactory()
    client = ClientFactory(owner=user)
    return Document.objects.create(client=client, original_name="contrato.pdf", uploaded_by=user)


@pytest.mark.django_db
def test_remind_pending_emails_only_pending_and_stamps(mailoutbox):
    document = _document()
    SignatureRequest.objects.create(document=document, signer_email="pendente@x.test")
    SignatureRequest.objects.create(
        document=document, signer_email="assinado@x.test", status=SignatureRequest.Status.SIGNED
    )

    reminded = esign.remind_pending(document)

    assert reminded == 1
    assert [mail.to for mail in mailoutbox] == [["pendente@x.test"]]
    pending = document.signature_requests.get(signer_email="pendente@x.test")
    assert pending.reminded_at is not None


@pytest.mark.django_db
def test_remind_pending_returns_zero_without_pending(mailoutbox):
    document = _document()
    SignatureRequest.objects.create(
        document=document, signer_email="ok@x.test", status=SignatureRequest.Status.SIGNED
    )

    assert esign.remind_pending(document) == 0
    assert mailoutbox == []
