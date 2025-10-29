export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    // Opcional: path secreto para seguridad básica
    const secretPath = env.WEBHOOK_SECRET_PATH || "webhook";
    if (url.pathname !== `/${secretPath}` || req.method !== "POST") {
      return new Response("OK", { status: 200 });
    }

    // Telegram update
    const update = await req.json().catch(() => ({}));
    const msg = update.message || update.edited_message || {};
    const chatId = msg.chat?.id;

    // Helpers
    const tg = async (method, payload) => {
      const r = await fetch(`${env.TELEGRAM_API}/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        const text = await r.text();
        console.log("TG error", r.status, text);
      }
      return r;
    };

    const sbFetch = async (path, init = {}) => {
      const url = `${env.SUPABASE_URL}/rest/v1/${path}`;
      const headers = {
        apikey: env.SUPABASE_SERVICE_ROLE,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE}`,
        "content-type": "application/json",
        ...init.headers,
      };
      return fetch(url, { ...init, headers });
    };

    const ensureSettingsTable = async () => {
      // idempotente usando RPC sql (solo 1 vez; ignorar fallos)
      const ddl = `
        create table if not exists settings(
          key text primary key,
          value text not null,
          updated_at timestamptz default now()
        );
        insert into settings(key,value)
        values('bankroll','500')
        on conflict (key) do nothing;`;
      await fetch(`${env.SUPABASE_URL}/rest/v1/rpc/exec_sql`, {
        method: "POST",
        headers: {
          apikey: env.SUPABASE_SERVICE_ROLE,
          Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ sql: ddl }),
      }).catch(()=>{});
    };

    const getBankroll = async () => {
      const r = await sbFetch("settings?select=value&key=eq.bankroll");
      if (!r.ok) return 500;
      const data = await r.json();
      const v = (data[0]?.value ?? "500");
      const f = parseFloat(v);
      return Number.isFinite(f) ? f : 500;
    };
    const setBankroll = async (val) => {
      await sbFetch("settings", {
        method: "POST",
        body: JSON.stringify([{ key: "bankroll", value: String(val) }]),
        headers: { Prefer: "resolution=merge-duplicates" },
      });
    };

    await ensureSettingsTable();

    // Comandos básicos
    const text = (msg.text || "").trim();
    if (text === "/start") {
      await tg("sendMessage", {
        chat_id: chatId,
        text: "BotPicks en línea ✅\nUsa /config para abrir Configuración.",
      });
      return new Response("OK");
    }

    if (text === "/config") {
      const bank = await getBankroll();
      const keyboard = {
        inline_keyboard: [
          [{ text: `Bank actual: ${bank}`, callback_data: "noop" }],
          [
            { text: "300", callback_data: "bank:300" },
            { text: "500", callback_data: "bank:500" },
            { text: "1000", callback_data: "bank:1000" },
            { text: "2000", callback_data: "bank:2000" },
          ],
          [{ text: "Ingresar valor personalizado", callback_data: "bank:custom" }],
        ],
      };
      await tg("sendMessage", { chat_id: chatId, text: "⚙️ Configuración", reply_markup: keyboard });
      return new Response("OK");
    }

    // Callback buttons
    if (update.callback_query) {
      const cq = update.callback_query;
      const data = cq.data || "";
      const cid = cq.message?.chat?.id;
      if (data.startsWith("bank:")) {
        const v = data.split(":")[1];
        if (v === "custom") {
          await tg("sendMessage", { chat_id: cid, text: "Escribe el valor de Bank inicial (solo números), ej: 750" });
        } else {
          const num = parseFloat(v);
          if (Number.isFinite(num)) {
            await setBankroll(num);
            await tg("sendMessage", { chat_id: cid, text: `✅ Bank inicial actualizado a ${num}` });
          } else {
            await tg("sendMessage", { chat_id: cid, text: "❌ Número inválido" });
          }
        }
      }
      return new Response("OK");
    }

    // Texto luego de 'custom'
    if (text && /^\d+(\.\d+)?$/.test(text)) {
      await setBankroll(parseFloat(text));
      await tg("sendMessage", { chat_id: chatId, text: `✅ Bank inicial actualizado a ${text}` });
      return new Response("OK");
    }

    return new Response("OK");
  },
};
