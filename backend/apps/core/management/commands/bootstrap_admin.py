import os
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()

# Mesmas variáveis que o `createsuperuser` do próprio Django já lê no modo `--noinput` — reusar o
# nome em vez de inventar um novo é deliberado: quem já sabe subir Django não precisa aprender um
# segundo contrato para este.
_VAR_USERNAME = "DJANGO_SUPERUSER_USERNAME"
_VAR_EMAIL = "DJANGO_SUPERUSER_EMAIL"
_VAR_PASSWORD = "DJANGO_SUPERUSER_PASSWORD"


class Command(BaseCommand):
    help = (
        "Cria o primeiro administrador em ambiente remoto, se nenhum existir (FDD 019). "
        "Idempotente: seguro de rodar em todo deploy, nunca altera senha de quem já existe."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--exigir",
            action="store_true",
            help=(
                "Reprova o deploy (CommandError) em vez de só avisar quando faltar variável "
                "e não houver administrador."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if User.objects.filter(is_superuser=True, is_active=True).exists():
            # Superusuário inativo não conta: ninguém entra com ele, então o bootstrap precisa
            # seguir em frente — daí o filtro por `is_active=True` além de `is_superuser=True`.
            self.stdout.write(self.style.SUCCESS("Já existe administrador ativo; nada a fazer."))
            return

        username = os.environ.get(_VAR_USERNAME)
        email = os.environ.get(_VAR_EMAIL)
        password = os.environ.get(_VAR_PASSWORD)
        faltando = [
            nome
            for nome, valor in (
                (_VAR_USERNAME, username),
                (_VAR_EMAIL, email),
                (_VAR_PASSWORD, password),
            )
            if not valor
        ]
        if faltando:
            mensagem = (
                f"Faltando: {', '.join(faltando)}. Sem elas nenhum administrador é criado e o "
                "ambiente fica inacessível."
            )
            if options["exigir"]:
                raise CommandError(mensagem)
            self.stderr.write(self.style.WARNING(mensagem))
            return

        # `faltando` vazio já garante as três preenchidas; só falta o mypy enxergar isso.
        assert username is not None and email is not None and password is not None

        # `createsuperuser --noinput` não roda os validadores de senha — eles só valem no modo
        # interativo do Django. É exatamente o caminho automatizado, sem ninguém olhando, que
        # precisa da validação: por isso ela roda aqui, antes de criar qualquer coisa.
        #
        # O usuário **não salvo** é a parte que parece detalhe e não é: `validate_password` sem
        # instância devolve cedo dentro do `UserAttributeSimilarityValidator`, que é o primeiro
        # dos quatro em `AUTH_PASSWORD_VALIDATORS`. Validar sem ele restauraria três dos quatro e
        # deixaria passar exatamente a senha que o runbook promete recusar — a parecida com o nome
        # de usuário. É o que o próprio `createsuperuser` interativo faz ao montar um usuário de
        # mentira só para validar.
        try:
            validate_password(password, User(username=username, email=email))
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        # `User.role` fica no default (delivery): quem autoriza é `is_superuser`, lido pelos dois
        # lados como `is_admin` (FDD 017) — o próprio `createsuperuser` também não decide papel.
        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Administrador criado: {username}"))
