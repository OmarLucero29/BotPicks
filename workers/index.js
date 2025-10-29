// Minimal worker: webhook de Telegram + ping
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/ping") {
      return new Response(JSON.stringify({ ok: true, ts: Date.now() }), {
        headers: { "content-type": "application/json" },
      });
    }

    if (url.pathname === "/webhook") {
      // Valida un secreto simple para evitar spam
      const got = request.headers.get("x-webhook-secret") || url.searchParams.get("secret") || "";
      if (!env.WEBHOOK_SECRET_TOKEN || got !== env.WEBHOOK_SECRET_TOKEN) {
        return new Response("forbidden", { status: 403 });
      }
      // Lee update y responde 200 rápido (Telegram no espera más de 10s)
      const update = await request.json().catch(() => ({}));

      // Ejemplo: eco rápido si hay mensaje
      const text = update?.message?.text;
      if (text && env.TELEGRAM_BOT_TOKEN) {
        const chatId = update.message.chat.id;
        const endpoint = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
        const body = { chat_id: chatId, text: `✅ BotPicks recibió: ${text}` };
        ctx.waitUntil(fetch(endpoint, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body)
        }));
      }

      // Aquí podrías llamar a Supabase si lo requieres:
      // if (env.SUPABASE_URL && env.SUPABASE_SERVICE_ROLE) { ... }

      return new Response("ok", { status: 200 });
    }

    return new Response("not found", { status: 404 });
  }
};