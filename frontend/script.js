document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('upload-form');
  const imageInput = document.getElementById('image-input');
  const previewImage = document.getElementById('preview-image');
  const resultsList = document.getElementById('results-list');
  const resultsCount = document.getElementById('results-count');
  const nResultsInput = document.getElementById('n-results');
  const dropZone = document.getElementById('drop-zone');
  const fileName = document.getElementById('file-name');
  const themeToggle = document.getElementById('theme-toggle');
  const apiDot = document.getElementById('api-dot');
  const apiStatus = document.getElementById('api-status');

  // ─── Copy ─────────────────────────────────────────────────────────────────
  // Every string a user can see lives here, in Colombian Spanish with the formal
  // "usted" — the audience is ICA. Keeping it in one place keeps the wording
  // consistent and makes a missed translation easy to spot.
  // Console messages stay in English: they are for developers, not users.
  const TEXT = {
    ready: 'Registro listo',
    indexed: (n) => ` · ${n} hierros registrados`,
    asleep: 'Registro en reposo — la primera búsqueda lo activará',
    searching: 'Buscando en el registro… ',
    searchingElapsed: (s) => `${s} s`,
    waking: 'Activando el servidor — puede tardar hasta dos minutos en el plan gratuito ' +
            'y solo ocurre cuando ha estado inactivo.',
    wakingElapsed: (s) => `${s} s transcurridos · después responde rápido`,
    notAnImage: 'Ese archivo no es una imagen. Use un JPG o PNG.',
    noFile: 'Primero elija una imagen: suéltela arriba o haga clic para buscarla.',
    resultCount: (n) => `${n} ${n === 1 ? 'resultado' : 'resultados'}`,
    closest: 'Más similar',
    candidate: 'Candidato',
    imageUnavailable: 'Imagen no disponible',
    noMatches: 'No se encontraron coincidencias.',
    rejected: (status) => `La solicitud fue rechazada (${status}).`,
    unreachable: 'No fue posible conectar con el servidor. Intente de nuevo en unos minutos.',
    unexpected: 'No se pudo completar la búsqueda. Intente de nuevo.',
  };

  // Colombian convention: decimal comma, "75,0%".
  const percent = new Intl.NumberFormat('es-CO', {
    style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1,
  });

  // Only text we wrote, or the API's own detail sentence, is shown as-is.
  // Anything else thrown along the way — a JSON parse error, say — carries the
  // browser's own English wording, so it is replaced with TEXT.unexpected.
  class UserMessage extends Error {}

  // ─── Theme ────────────────────────────────────────────────────────────────
  // No stored choice means "follow the OS", which CSS already handles via
  // prefers-color-scheme. The toggle writes an explicit choice that wins in both
  // directions. The <head> applies it before first paint to avoid a flash.
  function currentTheme() {
    const explicit = document.documentElement.getAttribute('data-theme');
    if (explicit) return explicit;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  themeToggle.addEventListener('click', () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem('brandmatch-theme', next);
    } catch (e) {
      // Private browsing can throw on write. The toggle still works for this
      // visit; it just will not be remembered.
    }
  });

  // ─── Which API to talk to ────────────────────────────────────────────────
  // Decided by where this page is served from.
  //
  // The old version always tried localhost:8000 first, so every search on the
  // deployed site began with a request that could not possibly succeed — a
  // guaranteed failure and a console error before the real call went out.
  //
  // Served from localhost, keep the fallback: it is genuinely useful to develop
  // the page against the deployed API when no local one is running.
  // Served from anywhere else, there is exactly one right answer, so go straight
  // to it and waste nothing.
  const LOCAL_API = 'http://localhost:8000';
  const PROD_API = 'https://brandmatch-api-1815.onrender.com';
  const isLocalPage = ['localhost', '127.0.0.1', '::1', ''].includes(
    window.location.hostname
  );
  const API_URLS = isLocalPage ? [LOCAL_API, PROD_API] : [PROD_API];

  // ─── Warm-up ──────────────────────────────────────────────────────────────
  // The Render Web Service sleeps when idle and takes ~100s to wake — measured,
  // not estimated. Almost all of that is Render starting the container, not our
  // code, so it cannot be optimised away from here.
  //
  // Firing one cheap request the moment the page loads means the server wakes
  // while the user is still choosing a file, instead of only after they press
  // "Buscar coincidencias". This does NOT make anything faster; it overlaps the wait with
  // something the user was going to spend time on anyway.
  let apiAwake = false;
  const warmUpStartedAt = Date.now();

  function setStatus(state, text) {
    apiDot.dataset.state = state;
    apiStatus.textContent = text;
  }

  async function warmUp() {
    for (const base of API_URLS) {
      try {
        const response = await fetch(`${base}/`, { method: 'GET' });
        if (response.ok) {
          apiAwake = true;
          const seconds = ((Date.now() - warmUpStartedAt) / 1000).toFixed(1);
          console.log(`API ready via ${base} after ${seconds}s`);
          let indexed = '';
          try {
            const body = await response.json();
            if (body && typeof body.indexed === 'number') {
              indexed = TEXT.indexed(body.indexed);
            }
          } catch (e) { /* health payload is a bonus, not a requirement */ }
          setStatus('ready', `${TEXT.ready}${indexed}`);
          return;
        }
      } catch (error) {
        // Expected for localhost when only the deployed API is running.
      }
    }
    setStatus('down', TEXT.asleep);
  }
  warmUp();

  // ─── Rendering ────────────────────────────────────────────────────────────
  // Nothing here is ever built as an HTML string. Filenames, image URLs and API
  // messages come from outside the page, and every value goes in through
  // textContent, a DOM property or setAttribute — none of which parse markup.
  //
  // The cards used to be template literals assigned to innerHTML, and a filename
  // of `<img src=x onerror=...>` executed script in the page. Verified, not
  // theoretical; harmless only while every filename came from our own index.
  // tests/test_frontend.py also fails if innerHTML reappears in this file.
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function showMessage(text, { error = false } = {}) {
    const className = error ? 'results__message results__message--error' : 'results__message';
    resultsList.replaceChildren(el('p', className, text));
  }

  // Elapsed-time message shown while a cold server is still starting up.
  function startWakingMessage() {
    const startedAt = Date.now();
    const render = () => {
      const elapsed = Math.round((Date.now() - startedAt) / 1000);
      const message = el('p', 'results__message', apiAwake ? TEXT.searching : TEXT.waking);
      message.appendChild(el('small', null,
        apiAwake ? TEXT.searchingElapsed(elapsed) : TEXT.wakingElapsed(elapsed)));
      resultsList.replaceChildren(message);
    };
    render();
    return setInterval(render, 1000);
  }

  // ─── Choosing a file ──────────────────────────────────────────────────────
  function showPreview(file) {
    previewImage.src = URL.createObjectURL(file);
    dropZone.classList.add('has-image');
    fileName.textContent = file.name;
    fileName.hidden = false;
  }

  function acceptFile(file) {
    if (!file) return false;
    if (!file.type.startsWith('image/')) {
      showMessage(TEXT.notAnImage, { error: true });
      return false;
    }
    // Put the dropped file into the real input so the form submits it normally.
    const transfer = new DataTransfer();
    transfer.items.add(file);
    imageInput.files = transfer.files;
    showPreview(file);
    return true;
  }

  dropZone.addEventListener('click', () => imageInput.click());
  dropZone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      imageInput.click();
    }
  });

  imageInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) showPreview(file);
  });

  // dragover must be cancelled on every event or the browser opens the file.
  ['dragenter', 'dragover'].forEach((type) => {
    dropZone.addEventListener(type, (e) => {
      e.preventDefault();
      dropZone.classList.add('is-dragging');
    });
  });

  ['dragleave', 'dragend'].forEach((type) => {
    dropZone.addEventListener(type, (e) => {
      // relatedTarget is null when the cursor leaves the window entirely.
      if (type === 'dragleave' && dropZone.contains(e.relatedTarget)) return;
      dropZone.classList.remove('is-dragging');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('is-dragging');
    acceptFile(e.dataTransfer.files[0]);
  });

  // Dropping anywhere else should not navigate away to the raw image.
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => e.preventDefault());

  // ─── Search ───────────────────────────────────────────────────────────────
  async function tryAPICall(endpoint, options) {
    for (let i = 0; i < API_URLS.length; i++) {
      try {
        const response = await fetch(`${API_URLS[i]}${endpoint}`, options);
        if (response.ok) {
          return { response, apiUrl: API_URLS[i] };
        }
        // The API answers with a JSON detail for a bad upload — surface that
        // rather than reporting it as an unreachable endpoint.
        if (response.status >= 400 && response.status < 500) {
          const body = await response.json().catch(() => ({}));
          // Our API sends a Spanish sentence. FastAPI's own validation errors send a
          // list instead, which would print as "[object Object]".
          throw new UserMessage(
            typeof body.detail === 'string' ? body.detail : TEXT.rejected(response.status)
          );
        }
      } catch (error) {
        if (error instanceof TypeError) {
          console.log(`Failed to connect to ${API_URLS[i]}: ${error.message}`);
          if (i === API_URLS.length - 1) throw new UserMessage(TEXT.unreachable);
        } else {
          throw error;
        }
      }
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const file = imageInput.files[0];
    if (!file) {
      showMessage(TEXT.noFile, { error: true });
      return;
    }
    if (!file.type.startsWith('image/')) {
      showMessage(TEXT.notAnImage, { error: true });
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    const n_results = parseInt(nResultsInput.value) || 5;

    resultsCount.textContent = '';
    const waitingTimer = startWakingMessage();

    try {
      const { response, apiUrl } = await tryAPICall(`/search?n_results=${n_results}`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      apiAwake = true;          // it answered, so it is up
      clearInterval(waitingTimer);
      setStatus('ready', TEXT.ready);

      resultsList.replaceChildren();

      if (data?.matches && data.matches.length > 0) {
        resultsCount.textContent = TEXT.resultCount(data.matches.length);

        data.matches.forEach((match, index) => {
          // ChromaDB is queried with its default space, which is SQUARED L2 —
          // not cosine. For the unit vectors the API stores, ||a-b||² = 2 - 2·cos,
          // so cos = 1 - distance/2. Dividing by 2 is what keeps this a percentage.
          //
          // Without it, anything past distance 1.0 renders negative: the worst
          // pair in the current index sits at 1.66 and displayed -65.6%.
          // MobileNetV2 ends in ReLU6, so every component is non-negative, which
          // bounds cosine to [0,1] and distance to [0,2] — hence 0-100% here.
          // Swap in a model with signed features (CLIP, say) and that guarantee
          // is gone; clamp at that point.
          const similarity = (1 - match.distance / 2) * 100;
          const similarityPercent = percent.format(similarity / 100);

          const card = el('article', index === 0 ? 'card card--top' : 'card');

          const plate = el('div', 'card__plate');
          const image = document.createElement('img');
          // new URL() resolves the path against the API that answered, rather than
          // gluing strings together.
          image.src = new URL(match.imageUrl, apiUrl).href;
          image.alt = match.filename;
          image.loading = 'lazy';
          image.addEventListener('error', () => {
            image.remove();
            plate.appendChild(el('span', 'card__missing', TEXT.imageUnavailable));
          });
          plate.appendChild(image);

          const name = el('div', 'card__name', match.filename);
          name.title = match.filename;

          const score = el('div', 'card__score');
          score.append(
            el('span', 'card__pct', similarityPercent),
            el('span', 'card__label', index === 0 ? TEXT.closest : TEXT.candidate),
          );

          const meter = el('div', 'card__meter');
          const fill = el('span');
          fill.style.width = `${Math.max(0, Math.min(100, similarity))}%`;
          meter.appendChild(fill);

          const body = el('div', 'card__body');
          body.append(name, score, meter);
          card.append(plate, body);
          resultsList.appendChild(card);
        });
      } else {
        showMessage(TEXT.noMatches);
      }
    } catch (error) {
      clearInterval(waitingTimer);
      console.error('Search failed:', error);
      showMessage(error instanceof UserMessage ? error.message : TEXT.unexpected, { error: true });
    }
  });
});
