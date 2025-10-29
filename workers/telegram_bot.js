/**
 * BotPicks – Cloudflare Worker (webhook)
 * - Responde /start y /config
 * - Guarda/lee bankroll en Supabase
 * - Endpoints de diagnóstico: /health, /echo, /send
 * - Logs detallados de errores TG/Supabase
 */
const JSON_OK = { status: 200, headers: { "content-type": "application/json" } };
const TXT_OK  = { status: 200, headers: { "content-type": "text/plain; charset=utf-8" } };

export default {
  async fetch(req, env) {
    const url = new URL(req.url);

    // --- Endpoints de diagnóstico (GET) ---
    if (req.method === "GET" && url.pathname === "/health") {
      // Verifica variables mínimas
      const ok =
        !!env.TELEGRAM_BOT_TOKEN &&
        !!env.SUPABASE_URL &&
        !!env.SUPABASE_SERVICE_ROLE;
      return new Response(JSON.stringify({
        ok,
        has: {
          TELEGRAM_BOT_TOKEN: !!env.TELEGRAM_BOT_TOKEN,
          SUPABASE_URL: !!env.SUPABASE_URL,
          SUPABASE_SERVICE_ROLE: !!env.SUPABASE_SERVICE_ROLE,
          WEBHOOK_SECRET_TOKEN: !!env.WEBHOOK_SECRET_TOKEN
        }
      }), JSON_OK);
    }

    // Devuelve lo que recibe (debug)
    if (req.method === "GET" && url.pathname === "/echo") {
      return new Response(JSON.stringify({
        method: req.method,
        url: req.url,
        headers: Object.fromEntries(req.headers.entries())
      }, null, 2), JSON_OK);
    }

    // Auto-prueba de envío a un chat (requiere ?chat_id=123)
    if (req.method === "GET" && url.pathname === "/send") {
      const chatId = url.searchParams.get("chat_id");
      if (!chatId) return new Response("Falta chat_id", { status: 400 });
      const r = await tgSend(env, "sendMessage", {
        chat_id: chatId,
        text: "Ping desde Workers ✅"
      });
      return new Response(JSON.stringify(await safeJson(r), null, 2), JSON_OK);
    }

    // --- Webhook (POST) ---
    const secretPath = env.WEBHOOK_SECRET_TOKEN || "webhook";
    if (url.pathname !== `/${secretPath}`) {
      // Cualquier otra ruta: 200 para evitar reintentos innecesarios.
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

    // Determinar mensaje / chat
    const msg = update.message || update.edited_message || {};
    const chatId = msg.chat?.id;
    const text = (msg.text || "").trim();

    // Supabase helpers
    const getBankroll = (defaultValue = 500) =>
      sbGet(env, "settings?select=value&key=eq.bankroll")
        .then(async r => {
          if (!r.ok) {
            console.log("SB get error", r.status, await r.text().catch(()=>"-"));
            return defaultValue;
          }
          const data = await r.json().catch(()=>[]);
          const v = parseFloat(data?.[0]?.value || `${defaultValue}`);
          return Number.isFinite(v) ? v : defaultValue;
        });

    const setBankroll = async (val) => {
      const r = await sbPost(env, "settings", [{
        key: "bankroll",
        value: String(val)
      }], { Prefer: "resolution=merge-duplicates" });
      if (!r.ok) console.log("SB upsert error", r.status, await r.text().catch(()=>"-"));
    };

    // Comandos
    if (text === "/start" && chatId) {
      await tgSend(env, "sendMessage", {
        chat_id: chatId,
        text: "BotPicks en línea ✅\nUsa /config para abrir Configuración."
      });
      return new Response("OK", TXT_OK);
    }

    if (text === "/config" && chatId) {
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
      await tgSend(env, "sendMessage", {
        chat_id: chatId,
        text: "⚙️ Configuración",
        reply_markup: keyboard
      });
      return new Response("OK", TXT_OK);
    }

    // Callback buttons
    if (update.callback_query) {
      const cq = update.callback_query;
      const data = cq.data || "";
      const cid = cq.message?.chat?.id;
      if (data.startsWith("bank:") && cid) {
        const v = data.split(":")[1];
        if (v === "custom") {
          await tgSend(env, "sendMessage", {
            chat_id: cid, text: "Escribe el valor de Bank inicial (solo números), ej: 750"
          });
        } else {
          const num = parseFloat(v);
          if (Number.isFinite(num)) {
            await setBankroll(num);
            await tgSend(env, "sendMessage", {
              chat_id: cid, text: `✅ Bank inicial actualizado a ${num}`
            });
          } else {
            await tgSend(env, "sendMessage", {
              chat_id: cid, text: "❌ Número inválido"
            });
          }
        }
      }
      return new Response("OK", TXT_OK);
    }

    // Si escribe un número suelto tras "custom"
    if (chatId && /^\d+(\.\d+)?$/.test(text)) {
      try {
        await setBankroll(parseFloat(text));
        await tgSend(env, "sendMessage", {
          chat_id: chatId, text: `✅ Bank inicial actualizado a ${text}`
        });
      } catch (e) {
        await tgSend(env, "sendMessage", {
          chat_id: chatId, text: `❌ No pude guardar el bank.`
        });
        console.log("Error set bank:", e);
      }
      return new Response("OK", TXT_OK);
    }

    // Silencioso para otros mensajes
    return new Response("OK", TXT_OK);
  }
};

// --- Helpers Telegram / Supabase ---
async function tgSend(env, method, payload) {
  if (!env.TELEGRAM_BOT_TOKEN) {
    return new Response(JSON.stringify({ ok: false, error: "TELEGRAM_BOT_TOKEN missing" }), { status: 500 });
  }
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!r.ok) {
    console.log("TG send error", method, r.status, await r.text().catch(()=>"-"));
  }
  return r;
}

async function sbFetch(env, path, init = {}) {
  const url = `${env.SUPABASE_URL}/rest/v1/${path}`;
  const headers = {
    apikey: env.SUPABASE_SERVICE_ROLE,
    Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE}`,
    "content-type": "application/json",
    ...init.headers
  };
  return fetch(url, { ...init, headers });
}
const sbGet  = (env, path) => sbFetch(env, path, { method: "GET" });
const sbPost = (env, path, body, extraHeaders = {}) =>
  sbFetch(env, path, { method: "POST", body: JSON.stringify(body), headers: extraHeaders });

async function safeJson(r) { try { return await r.json(); } catch { return { text: await r.text().catch(()=>"-") }; } }
