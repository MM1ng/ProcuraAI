# Frontend / 前端

Next.js App Router interface for Enterprise Procurement Agent.

Enterprise Procurement Agent 的 Next.js App Router 前端界面。

## Setup / 启动方式

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

打开 `http://localhost:3000`。

## Pages / 页面

- `/chat` - Chat procurement interface / 采购聊天界面
- `/products` - Product catalog / 商品目录
- `/procurement` - Procurement plans / 采购方案
- `/orders` - Orders / 订单
- `/payment/success` - Payment success page / 支付成功页
- `/payment/cancel` - Payment cancel page / 支付取消页
- `/observability` - Observability dashboard / 可观测性看板
- `/evaluation` - Evaluation dashboard / 评估看板

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` in `.env.local` if the
backend runs on a different port.

如果后端运行在其他端口，请在 `.env.local` 中设置
`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`。
