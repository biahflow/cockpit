# Captação de leads pelo site

O formulário "Fale com um consultor" do site envia os dados para a API pública de intake
do Biahflow, que cria um **Lead** no CRM. A equipe tria e converte em oportunidade pela
tela **Leads**.

## Configuração (uma vez)

No ambiente do backend (`.env`):

```
LEAD_INTAKE_TOKEN=<gere-um-token-forte-aleatorio>
CORS_ALLOWED_ORIGINS=https://seusite.com.br
```

Depois reinicie a API (`docker compose up -d api`). Use o **mesmo** token no snippet do
site (header `X-Intake-Token`).

- Endpoint: `POST https://SEU-BACKEND/api/v1/leads/intake/`
- Proteções: token compartilhado, honeypot (`website`), rate limiting (20/hora por IP) e
  CORS restrito à(s) origem(ns) do site.

## Snippet para o site

```html
<form id="lead-form">
  <input name="name" placeholder="Seu nome*" required />
  <input name="email" type="email" placeholder="E-mail*" required />
  <input name="company" placeholder="Empresa" />
  <input name="phone" placeholder="Telefone" />
  <textarea name="message" placeholder="Como podemos ajudar?*" required></textarea>
  <!-- honeypot: mantenha escondido; bots preenchem, humanos não -->
  <input name="website" tabindex="-1" autocomplete="off"
         style="position:absolute;left:-9999px" aria-hidden="true" />
  <button type="submit">Fale com um consultor</button>
</form>

<script>
  const API = "https://SEU-BACKEND/api/v1/leads/intake/";
  const INTAKE_TOKEN = "COLE_AQUI_O_MESMO_TOKEN"; // igual ao LEAD_INTAKE_TOKEN
  document.getElementById("lead-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target).entries());
    const response = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Intake-Token": INTAKE_TOKEN },
      body: JSON.stringify(data),
    });
    if (response.ok) {
      event.target.reset();
      alert("Recebemos seu contato! Em breve retornaremos.");
    } else {
      alert("Não foi possível enviar agora. Tente novamente em instantes.");
    }
  });
</script>
```

## Teste rápido via curl

```bash
curl -X POST https://SEU-BACKEND/api/v1/leads/intake/ \
  -H "Content-Type: application/json" \
  -H "X-Intake-Token: SEU_TOKEN" \
  -d '{"name":"Fulano","email":"fulano@x.com","company":"ACME","message":"quero saber mais"}'
# 201 {"detail":"Recebido."}  -> o lead aparece no menu Leads do portal
```

## Observações

- O token fica visível no JavaScript do site (é client-side). Isso é aceitável para um
  formulário de contato: honeypot + rate limiting + CORS restrito contêm abuso casual.
  Para endurecer, futuramente dá para adicionar um captcha (hCaptcha/reCAPTCHA) ou fazer o
  envio pelo backend do próprio site.
- Nenhum dado comercial é exposto: o intake só **cria** leads; listar/converter exige
  login no portal (perfis Administrador e Vendas).
