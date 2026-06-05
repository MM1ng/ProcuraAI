# Frontend

Next.js App Router interface for Enterprise Procurement Agent.

## Setup

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Pages

- `/chat`
- `/products`
- `/procurement`
- `/orders`
- `/payment/success`
- `/payment/cancel`
- `/observability`
- `/evaluation`

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` in `.env.local` if the
backend runs on a different port.
