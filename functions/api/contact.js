const RECIPIENT = 'mail@agora.in.net';
const SENDER = 'Agora Contact Form <contact@agora.in.net>';

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store'
    }
  });
}

function clean(value, maxLength) {
  return String(value == null ? '' : value).trim().slice(0, maxLength);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
    .replace(/\r?\n/g, '<br>');
}

async function readPayload(request) {
  const contentType = request.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    return request.json();
  }

  const formData = await request.formData();
  return Object.fromEntries(formData.entries());
}

export async function onRequestPost(context) {
  let input;
  try {
    input = await readPayload(context.request);
  } catch (error) {
    return json({ ok: false, error: 'The request body could not be read.' }, 400);
  }

  // Keep the trap server-side as well as in the browser. Bots receive a
  // neutral success response without creating a Resend message.
  if (clean(input.company, 120)) {
    return json({ ok: true });
  }

  const name = clean(input.name, 80);
  const email = clean(input.email, 120);
  const topic = clean(input.topicLabel || input.topic, 120);
  const message = clean(input.message, 10000);

  if (name.length < 2 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) || !topic || message.length < 10) {
    return json({ ok: false, error: 'Please provide a valid name, email, topic, and message.' }, 400);
  }

  if (message.length > 2000) {
    return json({ ok: false, error: 'The message is too long.' }, 400);
  }

  const apiKey = context.env && context.env.RESEND_API_KEY;
  if (!apiKey) {
    console.error('RESEND_API_KEY is not configured for the contact function.');
    return json({ ok: false, error: 'The contact service is not configured yet.' }, 500);
  }

  const subject = `New Agora Feedback: ${topic}`;
  const html = [
    '<div style="font-family:Arial,sans-serif;line-height:1.6;color:#17131f">',
    `<h2>${escapeHtml(subject)}</h2>`,
    '<table cellpadding="6" cellspacing="0" style="border-collapse:collapse">',
    `<tr><td><strong>Name</strong></td><td>${escapeHtml(name)}</td></tr>`,
    `<tr><td><strong>Email</strong></td><td><a href="mailto:${escapeHtml(email)}">${escapeHtml(email)}</a></td></tr>`,
    `<tr><td><strong>Topic</strong></td><td>${escapeHtml(topic)}</td></tr>`,
    '</table>',
    '<hr style="border:0;border-top:1px solid #ddd;margin:20px 0">',
    `<p>${escapeHtml(message)}</p>`,
    '<p style="color:#6b6475;font-size:12px">Sent from the Agora website feedback form.</p>',
    '</div>'
  ].join('');

  try {
    const resendResponse = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify({
        from: SENDER,
        to: [RECIPIENT],
        subject,
        html,
        reply_to: email
      })
    });

    const resendBody = await resendResponse.json().catch(() => ({}));
    if (!resendResponse.ok) {
      console.error('Resend rejected the Agora contact message.', resendBody);
      return json({ ok: false, error: 'The email service could not accept the message.' }, 500);
    }

    return json({ ok: true, id: resendBody.id || null });
  } catch (error) {
    console.error('Agora contact function failed.', error);
    return json({ ok: false, error: 'The contact service is temporarily unavailable.' }, 500);
  }
}
