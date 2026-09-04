"""A versão da API sai do **prefixo do caminho**, e é um lugar só que a responde.

A `/api/v2/` (issue #122) não é um produto novo: são os mesmos viewsets e os mesmos serializers,
servidos sob outro prefixo, sem as chaves e as rotas legadas que a `docs/ontology/aliases.md`
sempre marcou para morrer ali. Para isso o servidor precisa saber, em cada requisição, **qual das
duas está falando** — e é só isso que este módulo faz.

**Por que uma classe própria, e não uma das do DRF.** As duas candidatas cobram um preço que esta
travessia não pode pagar:

- `URLPathVersioning` exige a versão como **kwarg de toda rota** (`/api/<version>/...`) e faz o
  `reverse()` do DRF injetar esse kwarg de volta; adotá-la reescreveria as 57 rotas do router e
  quebraria a raiz da API, que reverte cada lista por nome.
- `NamespaceVersioning` resolve pelo **namespace** do resolver, o que renomeia o alvo de todo
  `reverse("client-detail")` do repositório — exatamente os nomes que a issue #67 fixou explícitos
  para não quebrarem (`urls.py`).

O prefixo já **é** a versão. Lê-lo do caminho é o mecanismo inteiro, custa uma comparação de
string por requisição e não toca em nome de rota nenhum. O preço declarado, e ele é pequeno: o
drf-spectacular não reconhece a classe (`plumbing.is_versioning_supported` aceita só as três dele)
e emite **um** aviso na geração do esquema, dizendo que a view será tratada como não versionada —
que é precisamente o que se quer nesta fatia, já que a v2 fica fora do `openapi.yaml` até a forma
dela ser verdadeira (ver `openapi_aliases.excluir_a_v2_do_contrato`).

As duas frases de recusa moram aqui pelo motivo de `exceptions.py`: quem recusa a chave legada é o
serializer e quem recusa o parâmetro legado é o viewset, e os dois precisam dizer a mesma coisa.
Duas redações do mesmo "não existe mais, use este nome" divergiriam na primeira edição.
"""

from __future__ import annotations

from typing import Any

from rest_framework.versioning import BaseVersioning

V1 = "v1"
V2 = "v2"

PREFIXO_DA_V2 = "/api/v2/"


class VersaoPeloCaminho(BaseVersioning):
    """`request.version` a partir do prefixo do caminho — sem tocar em `reverse()`.

    Tudo que não começa com `/api/v2/` é `v1`, inclusive o que está fora da API: um default
    explícito é o que faz um serializer instanciado fora de requisição (portal, agentes, teste)
    manter a forma de sempre, em vez de perder as chaves legadas por omissão.
    """

    def determine_version(self, request: Any, *args: Any, **kwargs: Any) -> str:
        return V2 if request.path.startswith(PREFIXO_DA_V2) else V1


def versao_de(request: Any) -> str:
    """A versão de uma requisição, com `v1` para quem não passou pelo versionamento do DRF.

    `request.version` só existe depois de `APIView.initial()`; o corpo de uma requisição simulada
    (a geração do esquema) e o `None` de um `request` ausente caem no default de sempre.
    """
    return getattr(request, "version", None) or V1


def frase_da_chave_removida(antiga: str, canonica: str) -> str:
    """A recusa de uma chave de payload legada na v2 — dizendo o nome canônico, nunca calada.

    Recusar é decisão de contrato da issue #122, e o que ela evita é o modo de falha mudo: o DRF
    ignora chave desconhecida, então um `POST` legado na v2 responderia 201 sem ter gravado o
    vínculo que o chamador pensou ter mandado.
    """
    return f"A chave '{antiga}' não existe na /api/v2/; use '{canonica}'."


def frase_do_parametro_removido(antigo: str, canonico: str) -> str:
    """A mesma recusa, para o filtro de query string: `?client=` responde dizendo `?account=`."""
    return f"O parâmetro '?{antigo}=' não existe na /api/v2/; use '?{canonico}='."


def frase_da_chave_sem_sucessora(antiga: str) -> str:
    """A recusa de uma chave que não tem canônica de **escrita** — o par do §2d.

    `kpi_baseline`/`kpi_current` pararam de aceitar escrita ainda na `/api/v1/` (ADR 0055, decisão
    C1 do DAP `dap-prove-e-valor-r1`): a leitura é derivada e a gravação vive em `/kpis/` e
    `/measurements/`. `frase_da_chave_removida` não serve aqui porque não há nome de campo para
    apontar — dizer "use 'None'" mentiria sobre existir um sucessor direto.
    """
    return (
        f"A chave '{antiga}' não existe na /api/v2/; a medição vive em /kpis/ e /measurements/."
    )
