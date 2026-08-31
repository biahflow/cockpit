# ADR 0059 — A suíte não atravessa a rede para provar um adapter

**Status:** aceita
**Data:** 31/08/2026
**Contexto:** issue #92, FDD 024 (sondas de integração), FDD 036 (régua de cobrança e IA de tom)

## Contexto

Um teste da carência da régua construía a fatura em relação a uma data fixa, mas deixava a rota ler
o relógio real. Quando os dois dias caíam em janelas diferentes, a rota alcançava `ai.complete` sem
mock e tentava autenticar na OpenAI com a chave fictícia da suíte. O 401 tornava o vazamento
visível; com credencial válida no ambiente, o mesmo teste teria consumido rede e cota.

Mockar só esse caso fecha o sintoma e deixa todos os outros testes sujeitos ao mesmo modo de falha.
Credencial falsa também não é cerca: depende do fornecedor recusar a chamada depois de DNS,
conexão e envio do pedido.

## Decisão

**A suíte backend é hermética por padrão.** Durante toda a sessão pytest, a resolução por
`socket.getaddrinfo`, as conexões síncronas e assíncronas e os envios UDP por `sendto`/`sendmsg`
recusam destinos externos antes de resolver DNS ou fazer I/O. A mensagem manda substituir o cliente
do provider, em vez de expor a falha incidental do fornecedor. Sockets UDP conectados passam pela
mesma guarda de `connect`; `socket.create_connection`, `socket.socket.connect` e
`socket.socket.connect_ex` seguem cobertos diretamente.

Loopback (`localhost`, `127.0.0.0/8` e `::1`) e Unix sockets permanecem permitidos. Eles são
infraestrutura local de teste: o job PostgreSQL/pgvector usa `localhost`, e um teste pode subir um
servidor efêmero deliberadamente sem ganhar uma exceção global.

Chamadas de integração na suíte terminam no limite do adapter e usam mock/fake explícito. Exercício
contra fornecedor real continua pertencendo às sondas e aos roteiros de homologação da FDD 024,
executados deliberadamente fora da suíte.

O caso que revelou o defeito congela `django.utils.timezone.localdate` no módulo da régua e instala
um `Mock` em `ai.complete`, afirmando também que ele não foi chamado. Assim a data determina a
carência e a cerca global protege contra qualquer regressão vizinha.

## Alternativas consideradas

**Consertar apenas `test_rascunhar_sem_degrau_aplicavel_recusa`.** Necessário, mas insuficiente:
outro teste sem mock voltaria a sair para a internet sem nenhuma falha local que explicasse o
contrato violado.

**Confiar em chaves falsas.** Rejeitada. A chamada ainda atravessa a rede, fica sujeita a latência e
indisponibilidade e muda de risco conforme o ambiente que executa pytest.

**Bloquear todos os sockets.** Rejeitada porque quebraria o teste do caminho PostgreSQL/pgvector e
servidores locais controlados. O limite é saída da máquina, não comunicação local deliberada.

**Adicionar uma dependência de plugin para pytest.** Não foi necessário: a superfície usada pelos
clientes HTTP cabe no `conftest.py`, e regressões próprias fixam bloqueio, mensagem e exceção de
loopback sem ampliar a cadeia de dependências.

## Consequências

- um teste que esquecer o mock falha antes de DNS ou I/O — inclusive em cliente async e UDP —, com
  destino e correção explícitos;
- DNS, latência, cota e credenciais externas deixam de participar do resultado da suíte;
- integrações locais necessárias continuam exercitáveis;
- uma homologação real não pode ser disfarçada de teste unitário: precisa de comando/roteiro
  deliberado, credencial autorizada e evidência própria;
- novos transportes que não usem resolução, conexão ou envio pela superfície de sockets protegida
  precisam ampliar a guarda e sua regressão antes de entrar na suíte.
