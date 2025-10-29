/**
 * BotPicks – Cloudflare Worker (webhook)
 * - /health, /echo, /send para diagnóstico
 * - Webhook con logs y coincidencia flexible de comandos
 * - Persistencia de bankroll en Supabase
 */
const JSON_OK = { status: 200, headers: { "content-type": "application/json" } };
const TXT_OK  = { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } };

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const secretPath = env.WEBHOOK_SECRET_TOKEN || "webhook";

    // --- Endpoints de diagnóstico ---
    if (req.method === "GET" && url.pathname === "/health") {
      return new Response(JSON.stringify({
        ok: !!(env.TELEGRAM_BOT_TOKEN && env.SUPABASE_URL && env.SUPABASE_SERVICE_ROLE),
        has: {
          TELEGRAM_BOT_TOKEN: !!env.TELEGRAM_BOT_TOKEN,
          SUPABASE_URL: !!env.SUPABASE_URL,
          SUPABASE_SERVICE_ROLE: !!env.SUPABASE_SERVICE_ROLE,
          WEBHOOK_SECRET_TOKEN: !!env.WEBHOOK_SECRET_TOKEN
        }
      }), JSON_OK);
    }
    if (req.method === "GET" && url.pathname === "/echo") {
      return new Response(JSON.stringify({
        method: req.method,
        url: req.url,
        headers: Object.fromEntries(req.headers.entries())
      }, null, 2), JSON_OK);
    }
    if (req.method === "GET" && url.pathname === "/send") {
      const chatId = url.searchParams.get("chat_id");
      if (!chatId) return new Response("Falta chat_id", { status: 400 });
      const r = await tgSend(env, "sendMessage", { chat_id: chatId, text: "Ping desde Workers ✅" });
      return new Response(JSON.stringify(await safeJson(r), null, 2), JSON_OK);
    }

    // GET al path del webhook → debe devolver 405 (así comprobamos coincidencia exacta)
    if (req.method === "GET" && url.pathname === `/${secretPath}`) {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Webhook: SOLO aceptamos POST sobre el path secreto
    if (url.pathname !== `/${secretPath}`) {
      return new Response("OK", TXT_OK);
    }
    if (req.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Parse del update
    let update = {};
    try {
      update = await req.json();
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    // Loguea TODO (lo verás en Workers → Logs)
    console.log("Webhook hit:", url.pathname);
    console.log("Update:", JSON.stringify(update));

    const msg = update.message || update.edited_message || {};
    const chatId = msg.chat?.id;
    const textRaw = (msg.text || "").trim();

    // normaliza comando: /cmd, /cmd@Bot, /cmd arg
    const norm = (t) => (t || "").split(/\s+/)[0].split("@")[0].toLowerCase();
    const text = textRaw.toLowerCase();

    const getBankroll = async (def = 500) => {
      const r = await sbFetch(env, "settings?select=value&key=eq.bankroll", { method: "GET" });
      if (!r.ok) { console.log("SB get error", r.status, await r.text().catch(()=>"-")); return def; }
      const data = await r.json().catch(()=>[]);
      const v = parseFloat(data?.[0]?.value || `${def}`);
      return Number.isFinite(v) ? v : def;
    };
    const setBankroll = async (val) => {
      const r = await sbFetch(env, "settings", {
        method: "POST",
        headers: { Prefer: "resolution=merge-duplicates" },
        body: JSON.stringify([{ key: "bankroll", value: String(val) }])
      });
      if (!r.ok) console.log("SB upsert error", r.status, await r.text().catch(()=>"-"));
    };

    // /start
    if (chatId && norm(textRaw) === "/start") {
      await tgSend(env, "sendMessage", { chat_id: chatId, text: "BotPicks en línea ✅\nUsa /config para abrir Configuración." });
      return new Response("OK", TXT_OK);
    }

    // /config
    if (chatId && norm(textRaw) === "/config") {
      const bank = await getBankroll();
      const keyboard = {
        inline_keyboard: [
          [{ text: `Bank actual: ${bank}`, callback_data: "noop" }],
          [
            { text: "300",  callback_data: "bank:300" },
            { text: "500",  callback_data: "bank:500" },
            { text: "1000", callback_data: "bank:1000" },
            { text: "2000", callback_data: "bank:2000" }
          ],
          [{ text: "Ingresar valor personalizado", callback_data: "bank:custom" }]
        ]
      };
      await tgSend(env, "sendMessage", { chat_id: chatId, text: "⚙️ Configuración", reply_markup: keyboard });
      return new Response("OK", TXT_OK);
    }

    // Botones
    if (update.callback_query) {
      const cq = update.callback_query;
      const data = cq.data || "";
      const cid = cq.message?.chat?.id;
      if (data.startsWith("bank:") && cid) {
        const v = data.split(":")[1];
        if (v === "custom") {
          await tgSend(env, "sendMessage", { chat_id: cid, text: "Escribe el valor de Bank inicial (solo números), ej: 750" });
        } else {
          const num = parseFloat(v);
          if (Number.isFinite(num)) {
            await setBankroll(num);
            await tgSend(env, "sendMessage", { chat_id: cid, text: `✅ Bank inicial actualizado a ${num}` });
          } else {
            await tgSend(env, "sendMessage", { chat_id: cid, text: "❌ Número inválido" });
          }
        }
      }
      return new Response("OK", TXT_OK);
    }

    // Si escribe número después de “custom”
    if (chatId && /^\d+(\.\d+)?$/.test(text)) {
      await setBankroll(parseFloat(text));
      await tgSend(env, "sendMessage", { chat_id: chatId, text: `✅ Bank inicial actualizado a ${text}` });
      return new Response("OK", TXT_OK);
    }

    return new Response("OK", TXT_OK);
  }
};

// ---- Helpers ----
async function tgSend(env, method, payload) {
  if (!env.TELEGRAM_BOT_TOKEN) {
    console.log("FALTA TELEGRAM_BOT_TOKEN");
    return new Response(JSON.stringify({ ok:false, error:"TELEGRAM_BOT_TOKEN missing" }), { status: 500 });
  }
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!r.ok) console.log("TG send error", method, r.status, await r.text().catch(()=>"-"));
  return r;
}
function sbFetch(env, path, init = {}) {
  const url = `${env.SUPABASE_URL}/rest/v1/${path}`;
  const headers = {
    apikey: env.SUPABASE_SERVICE_ROLE,
    Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE}`,
    "content-type": "application/json",
    ...init.headers
  };
  return fetch(url, { ...init, headers });
}
async function safeJson(r){ try { return await r.json(); } catch { return { text: await r.text().catch(()=>"-") }; } }