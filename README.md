# Parallax Invest IA — RCS Technology

Site institucional + backend funcional para plataforma de investimento em ações com IA.

## Frontend

- `index.html` — landing page com proposta de produto.
- `styles.css` — visual premium e responsivo.
- `script.js` — animações e simulador demonstrativo no client.

## Backend (completo)

- `backend.py` — API HTTP com persistência SQLite para:
  - cadastro de usuários,
  - watchlist,
  - predições de IA (simuladas),
  - ordens de compra/venda,
  - posições/carteira,
  - extrato de transações.

### Endpoints

- `POST /api/users`
- `POST /api/watchlist`
- `POST /api/predictions`
- `POST /api/orders`
- `GET /api/portfolio/{user_id}`
- `GET /api/transactions/{user_id}`
- `GET /health`

## Rodando local

### 1) Frontend

```bash
python3 -m http.server 8080
```

Acesse `http://localhost:8080`.

### 2) Backend

```bash
python3 backend.py
```

API em `http://localhost:8090`.

Variáveis úteis:

- `PARALLAX_DB_PATH` (padrão: `parallax.db`)
- `PARALLAX_HOST` (padrão: `0.0.0.0`)
- `PARALLAX_PORT` (padrão: `8090`)

## Testes

```bash
python3 -m unittest -v
```

> Nota: o módulo de predição é determinístico e demonstrativo para a experiência do produto.
