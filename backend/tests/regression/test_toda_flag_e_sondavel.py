"""Regressão: ligar uma integração não pode derrubar `check_integrations` (FDD 024).

`flags.FLAGS` e `integrations.PROBES` são dois registros do mesmo mundo, e nada os obrigava a
concordar. Três flags — `discovery_booking`, `cobranca` e `github_delivery` — existiam no primeiro
e não no segundo, então `PROBES[name]` levantava `KeyError`. O `except Exception` de `_executar`
capturava, e o comando reprovava com o nome da chave como diagnóstico: `'discovery_booking'`.

O efeito é pior do que uma mensagem ruim. `check_integrations` sai com código de erro, e ele é o
comando que se roda **antes de subir**: ligar o agendamento pela tela de Configurações passava a
reprovar o gate de um deploy que não tinha nada a ver com aquilo. E a falha só aparecia depois de
alguém ligar a integração — a flag desligada nem chega em `_executar`.

Nem toda integração tem o que sondar, e isso já era estado legítimo do comando muito antes deste
conserto: `esign`, `payments` e `portal` respondem `NAO_SONDAVEL` porque só o primeiro uso real
valida. O conserto é dizer a mesma coisa para quem não tem sonda **nenhuma**, em vez de estourar.

O teste é sobre o **par**, e não sobre as três chaves: listar os nomes de hoje deixaria a flag de
amanhã nascer com o mesmo defeito, que é exatamente como estas três nasceram.
"""

import pytest

from apps.core import flags, integrations

pytestmark = pytest.mark.django_db


def test_toda_flag_declarada_pode_ser_sondada_sem_estourar() -> None:
    """O par `FLAGS`/`PROBES` não precisa ser completo — precisa não quebrar quando não é."""
    for nome in flags.FLAGS:
        resultado = integrations._forcado(nome)

        assert resultado.name == nome
        assert resultado.detail, f"{nome} sondou sem dizer nada"


def test_flag_sem_sonda_responde_a_frase_que_o_comando_ja_usa() -> None:
    """E responde **passando**: ausência de sonda não é reprovação.

    `_executar` é o ponto do conserto, e não `probe`, porque `_forcado` também o chama — é ele que
    confere credencial antes de ligar a integração, e era por ele que o defeito também passava.
    """
    sem_sonda = [nome for nome in flags.FLAGS if nome not in integrations.PROBES]
    assert sem_sonda, "sem nenhuma flag sem sonda este teste não afirma nada"

    for nome in sem_sonda:
        ok, detalhe = integrations._executar(nome)

        assert ok is True, f"{nome} reprovou por não ter sonda"
        assert detalhe == integrations.NAO_SONDAVEL


def test_a_sonda_que_existe_continua_sendo_chamada() -> None:
    """A metade simétrica: a guarda não pode engolir a sonda de quem tem uma.

    Sem esta asserção, um `_executar` que devolvesse `NAO_SONDAVEL` para todo mundo passaria nos
    dois testes acima — e o comando inteiro viraria um "ok" que não olha nada.
    """
    ok, detalhe = integrations._executar("email")

    assert detalhe != integrations.NAO_SONDAVEL
    assert "SMTP" in detalhe or ok is False
