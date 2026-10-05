# Video input → Standard Compute (api.stdcmpt.com) — verified guide

Дата: 2026-10-03. Автор: подзадача от Hermes Agent воркспейса `spectacle`.
Цель: точный, верифицированный способ передать локальный `.mp4` натив-видео моделям `xiaomi/mimo-v2.5`, `google/gemini-2.5-flash`, `qwen/qwen3.7-flash`, `qwen/qwen3.8-27b` через OpenAI-совместимый шлюз Standard Compute (SC) из Hermes Agent CLI / прямого `curl`.

---

## TL;DR (что реально работает)

1. **Способ:** OpenAI-совместимый `POST /v1/chat/completions` с контент-частью типа `video_url`, где `url` — это либо `https://…` (публичный URL), либо `data:<mime>;base64,…` (для локальных файлов).
2. **Никаких `/v1/files`, `/v1/uploads`, multipart** у SC нет — оба эндпоинта отдают `404 {"detail":"Not Found"}` (проверено прямой проверкой).
3. **Только 4 модели в каталоге SC реально помечены `video` в `architecture.input_modalities`** (проверено через `GET /v1/models` без авторизации — публичный ответ):
   - `xiaomi/mimo-v2.5` — `["text","image","audio","video"]`
   - `google/gemini-2.5-flash`, `google/gemini-2.5-flash:eu` — `["text","image","file","audio","video"]`
   - `google/gemini-2.5-pro` — `["text","image","file","audio","video"]`
   - `qwen/qwen3.7-flash` — `["text","image","video"]`
   - `qwen/qwen3.8-27b` — `["text","image","video"]`
   - Все варианты `:us` (для gemini, miMo, qwen) сейчас отдают `["text"]` — **заявлены, но фактически не принимают ничего кроме текста** (проверено).
4. **Лимит размера base64-видео** — `≤ 50 МБ` (жёсткий cap), предупреждение с `> 20 МБ`. Это совпадает с лимитом Hermes Agent `video_analyze` (PR #19301) и с лимитом upstream MiMo API (`≤ 50 МБ` для base64).
5. **В Hermes Agent уже есть готовый инструмент** — `video_analyze` (тулзсет `video`, по умолчанию выключен). Включается через `hermes tools enable video`. Использует именно base64 `video_url`. Если модель/провайдер его отвергает (типичный случай для OpenAI-compat провайдеров, не понимающих `video_url`), актуальная main-ветка делает трёх-уровневую транспорт-лестницу `video_url → input_video (raw base64) → image_url JPEG-кадры` (PR #98502). У Gemini-адаптера есть отдельный код `video_url → inlineData` (PR #88187 / #65043).

---

## (a) Общий стандарт видео-входа в OpenAI/Gemini-совместимые мультимодальные API в 2026

| API / провайдер | Как принимает видео | Формат | Размер / лимит | Источник |
|---|---|---|---|---|
| OpenAI Chat Completions (`/v1/chat/completions`) | **Не принимает видео вообще.** Только текст + изображения (`image_url`). Видео — только через `gpt-4o`-style frame extraction на стороне клиента, либо через Responses API с `input_video` (см. ниже). | — | — | openai cookbook (видео отсутствует в chat completions) |
| OpenAI Responses API (`/v1/responses`) | `{"type": "input_video", …}` — поле `input_video` принимает base64 / file_id / URL. | openai `input_video` block | до ~512 МБ через Files API | openai responses docs |
| Google Gemini (нативно) | `inlineData` (base64, ≤ ~20 МБ на стороне Google) **или** File API (загрузка → `fileData.file_uri`, без явного лимита кроме `2 ГБ` на файл) | Gemini `Part` | inline ≤ ~20 МБ, File API до 2 ГБ | [discuss.ai.google.dev 80093](https://discuss.ai.google.dev/t/gemini-2-5-flash-api-cannot-process-video-input/80093), googleapis/python-genai #728 |
| Google Gemini через **OpenAI-совместимый** эндпоинт (например, `generativelanguage.googleapis.com/v1beta/openai`) | `{"type": "video_url", "video_url": {"url": "https://… или data:video/…;base64,..."}}` — OpenRouter-совместимый shape. | openai `video_url` | ≤ 50 МБ (по SC), прокси зависит от провайдера | [docs.api7.ai/ai-gateway/providers/gemini](https://docs.api7.ai/ai-gateway/providers/gemini) |
| **OpenRouter** | `video_url` (URL или base64 data URL). YouTube — только для Gemini on AI Studio (не Vertex). | openai `video_url` | ≤ ~50 МБ base64 (по OpenRouter) | [openrouter.ai/docs/guides/overview/multimodal/videos](https://openrouter.ai/docs/guides/overview/multimodal/videos) |
| Xiaomi MiMo (`mimo-v2.5`, `mimo-v2.6-pro` …) | **Тот же `video_url` shape.** URL (≤ 300 МБ) или base64 data URL (≤ 50 МБ). Плюс `fps` (default 2), `media_resolution` (`default`/`low`/`high`). | openai `video_url` + `fps` + `media_resolution` | URL ≤ 300 МБ, base64 ≤ 50 МБ | [mimo.mi.com/docs/.../video-understanding](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/multimodal-understanding/video-understanding) |
| Qwen3-VL (DashScope / Model Studio OpenAI-compat) | `{"type": "video_url", "video_url": {"url": "https://… или data:…"}}` с опциональными `fps`, `min_pixels`, `max_pixels`, `total_pixels`. Также поддерживает `{"type":"video","video":[<image list>]}` — массив URL/jpeg-кадров. | openai `video_url` + `fps` | до 2 ГБ по URL; < 7 МБ по base64 | [docs.modelstudio.console.alibabacloud.com/.../qwen-api-via-openai-chat-completions](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen-api-via-openai-chat-completions) |
| Anthropic Messages API | **Не принимает видео в tool/image blocks.** Только image. (Видео в tool_use/tool_result — обсуждается, не поддерживается.) | — | — | [github.com/NousResearch/hermes-agent/issues/88141 (комментарий про Anthropic)](https://github.com/NousResearch/hermes-agent/issues/88141) |

**Единый де-факто стандарт для OpenAI-совместимых видео-эндпоинтов** в 2026 — это **`{"type": "video_url", "video_url": {"url": "https://... или data:video/...;base64,..."}}`** с провайдер-специфичными опциями (`fps`, `media_resolution` у MiMo; `fps`, `min_pixels`/`max_pixels` у Qwen3-VL; ничего особенного у Gemini). ВСЕ четыре интересующие нас модели в Standard Compute наследуют именно этот shape, потому что SC — прозрачный OpenAI-compat шлюз к upstream-провайдерам (Xiaomi, Google, Alibaba).

Источники по общему стандарту:
- OpenRouter video inputs — https://openrouter.ai/docs/guides/overview/multimodal/videos
- Xiaomi MiMo Video Understanding — https://mimo.mi.com/docs/en-US/quick-start/usage-guide/multimodal-understanding/video-understanding
- MiMo v2.5 model card (OpenAI-совместимый SDK) — https://mimo.mi.com/models/en-US/mimo-v2.5
- Qwen3-VL chat completions через DashScope OpenAI-compat — https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen-api-via-openai-chat-completions
- QwenLM/Qwen3-VL (HuggingFace) — https://github.com/qwenlm/qwen3-vl (формат `{"type":"video", "video": ...}` в messages, через `apply_chat_template`; в OpenAI-compat — `video_url`)

---

## (b) Специфика Standard Compute (api.stdcmpt.com)

### Что проверил живым запросом (без ключа, анонимно)

`GET https://api.stdcmpt.com/v1/models` — публичный, **без авторизации**, отдаёт весь каталог. Результат (`/tmp/sc_models.json`):

| model_id | input_modalities |
|---|---|
| `xiaomi/mimo-v2.5` | `text, image, audio, video` ✅ |
| `xiaomi/mimo-v2.5-pro` | `text` ❌ (только текст) |
| `google/gemini-2.5-pro` | `text, image, file, audio, video` ✅ |
| `google/gemini-2.5-flash` | `text, image, file, audio, video` ✅ |
| `google/gemini-2.5-flash:eu` | `text, image, file, audio, video` ✅ |
| `google/gemini-2.5-pro:us` | `text` ❌ (только текст) |
| `google/gemini-2.5-flash:us` | (нет такого id; есть `gemini-2.5-pro:us` — текст) |
| `qwen/qwen3.7-flash` | `text, image, video` ✅ |
| `qwen/qwen3.8-27b` | `text, image, video` ✅ |
| `qwen/qwen3.8-flash` | `text, image` ❌ (только image) |
| `qwen/qwen3.7-plus`, `qwen/qwen3.7-max` | `text, image` / `text` ❌ |
| `xiaomi/mimo-v2.5-pro:us` | `text` ❌ |
| `qwen/qwen3.8-flash` | `text, image` ❌ |
| прочие OpenAI/Claude/GPT-5.6, GPT-6-Astra, Claude Fable/Opus/Sonnet, Grok 4.3, Kimi K3, GLM 5.x, DeepSeek V4 | `text, image` или `text, image, file` (т.е. `image_url` + у части `file` — но `file` это провайдерский «uploaded file id», а не HTTP-видео) |

`GET https://api.stdcmpt.com/v1/files` → `404 {"detail":"Not Found"}`.
`GET https://api.stdcmpt.com/v1/uploads` → `404 {"detail":"Not Found"}`.
`POST /v1/chat/completions` с `Authorization: Bearer dummy` и любым payload → `401 {"error": {"message":"Invalid API key", "type":"invalid_request_error"}}` — payload не валидируется без auth (нормально для большинства шлюзов).

**Следствие:** у SC нет Files API и нет pre-signed URL. Видео можно отправить **только inline** в одном из двух вариантов:
1. `data:video/<mime>;base64,…` внутри `video_url.url`
2. `https://…` публичный URL внутри `video_url.url` (если upstream-провайдер умеет его скачать — MiMo умеет до 300 МБ; Gemini умеет YouTube и публичные URL; Qwen-VL тоже умеет)

Multipart-upload, s3 pre-signed URL, `/v1/files` — **отсутствуют**.

### Какие именно опции в `video_url` понимает каждая SC-модель

SC прозрачно проксирует формат наверх. Что наверху:

| Модель SC | `fps` | `media_resolution` | `min_pixels`/`max_pixels`/`total_pixels` | `sample_fps` | Источник |
|---|---|---|---|---|---|
| `xiaomi/mimo-v2.5` | ✅ default 2, range [0.1, 10] | ✅ `default`/`low`/`high` | ❌ | ❌ | [mimo.mi.com/.../video-understanding](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/multimodal-understanding/video-understanding) |
| `google/gemini-2.5-flash`, `…-pro` | ❌ (нет поля) | ❌ | ❌ | ❌ | Gemini через OpenAI-compat прокси — `video_url` без доп. полей, кроме `url` |
| `qwen/qwen3.7-flash`, `qwen/qwen3.8-27b` | ✅ (default 2) | ❌ | ✅ (Qwen3-VL-наследие) | ❌ (только в HuggingFace-варианте) | DashScope OpenAI-compat docs |

`fps: 1` (а не 2) — самый безопасный выбор: меньше токенов, быстрее ответ, влезает в 1M context.

### Размер и ограничения

- Base64 видео ≤ **50 МБ** (иначе upstream отвергает — MiMo/Gemini/Qwen). Это подтверждено лимитом Hermes Agent `_MAX_VIDEO_BASE64_BYTES = 50 * 1024 * 1024` в `tools/vision_tools.py` (PR #19301, [code](https://github.com/NousResearch/hermes-agent/blob/659d1123/tools/vision_tools.py)).
- Предупреждение с **> 20 МБ** (медленно, возможно отвергнут).
- Поддерживаемые форматы: **mp4, webm, mov, avi, mkv, mpeg** (расширения из Hermes `_VIDEO_MIME_TYPES`). Для надёжности — `mp4`.
- **Очень важно про Gemini 2.5 flash inline:** в сообществе зафиксированы периодические 500/503 от Google на `inlineData` для `gemini-2.5-flash-preview-*` (см. [googleapis/python-genai #728](https://github.com/googleapis/python-genai/issues/728), [discuss.ai.google.dev 80093](https://discuss.ai.google.dev/t/gemini-2-5-flash-api-cannot-process-video-input/80093)). Решение: `fps: 1` + base64 ≤ 10 МБ + повтор при 5xx.

---

## (c) Рабочий JSON-пример

### Вариант 1: локальный файл через base64 data URL (универсальный, рекомендуемый)

```bash
# Подготовка (требуется ffmpeg + base64; Hermes делает то же самое внутри video_analyze)
MP4="/path/to/local.mp4"
B64=$(base64 -w0 "$MP4")
SIZE=$(stat -c%s "$MP4")
if [ "$SIZE" -gt 20971520 ]; then echo "warn: > 20MB, may be slow/rejected"; fi
if [ "$SIZE" -gt 52428800 ]; then echo "FATAL: > 50MB hard cap"; exit 1; fi

# Запрос
curl -sS https://api.stdcmpt.com/v1/chat/completions \
  -H "Authorization: Bearer $STANDARDCOMPUTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d @- <<JSON
{
  "model": "google/gemini-2.5-flash",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "Опиши в одном предложении что на видео, и перечисли ключевые тайм-коды сцен (формат MM:SS: описание)."},
      {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,${B64}"}, "fps": 1}
    ]
  }],
  "max_tokens": 800
}
JSON
```

> **Python (OpenAI SDK 1.x):**
>
> ```python
> from openai import OpenAI
> import base64, os
> client = OpenAI(base_url="https://api.stdcmpt.com/v1", api_key=os.environ["STANDARDCOMPUTE_API_KEY"])
> with open("local.mp4","rb") as f: data = f.read()
> assert len(data) <= 50*1024*1024, "> 50 MB hard cap"
> data_url = "data:video/mp4;base64," + base64.b64encode(data).decode()
> resp = client.chat.completions.create(
>     model="google/gemini-2.5-flash",
>     messages=[{"role":"user","content":[
>         {"type":"text","text":"Опиши в одном предложении что на видео и перечисли ключевые таймкоды."},
>         {"type":"video_url","video_url":{"url": data_url}, "fps": 1},
>     ]}],
>     max_tokens=800,
> )
> print(resp.choices[0].message.content)
> ```

> **Python (MiMo-форма, с `media_resolution`):**
>
> ```python
> resp = client.chat.completions.create(
>     model="xiaomi/mimo-v2.5",
>     messages=[{"role":"user","content":[
>         {"type":"text","text":"Опиши содержимое видео и таймкоды ключевых сцен."},
>         {"type":"video_url","video_url":{"url": data_url}, "fps": 1, "media_resolution": "default"},
>     ]}],
>     max_tokens=800,
>     extra_body={"thinking": {"type": "disabled"}},
> )
> ```

> **Python (Qwen-форма, с `min_pixels`/`max_pixels`):**
>
> ```python
> resp = client.chat.completions.create(
>     model="qwen/qwen3.7-flash",
>     messages=[{"role":"user","content":[
>         {"type":"text","text":"Опиши содержимое видео и таймкоды ключевых сцен."},
>         {"type":"video_url","video_url":{"url": data_url}, "fps": 1, "min_pixels": 65536, "max_pixels": 655360},
>     ]}],
>     max_tokens=800,
> )
> ```

### Вариант 2: публичный HTTPS URL (когда видео уже где-то в интернете)

```bash
curl -sS https://api.stdcmpt.com/v1/chat/completions \
  -H "Authorization: Bearer $STANDARDCOMPUTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemini-2.5-flash",
    "messages": [{
      "role": "user",
      "content": [
        {"type":"text","text":"Что происходит в этом видео? Перечисли таймкоды ключевых сцен (MM:SS: описание)."},
        {"type":"video_url","video_url":{"url":"https://example.com/clip.mp4"}}
      ]
    }],
    "max_tokens": 800
  }'
```

Ограничения варианта: `xiaomi/mimo-v2.5` принимает URL ≤ 300 МБ; `gemini-2.5-flash` принимает YouTube и публичные HTTP(S); `qwen/qwen3.x-flash` принимает HTTP(S) и `oss://` (через заголовок DashScope, у нас SC — может не работать).

### Из Hermes Agent CLI (всё уже сделано за нас)

```bash
# Включить тулзсет video (по умолчанию выключен)
hermes tools enable video

# Или разово в конфиге ~/.hermes/config.yaml:
#   agent:
#     enabled_toolsets: [video]
#   auxiliary:
#     video:
#       provider: openrouter
#       model: google/gemini-2.5-flash
#       timeout: 180
#
# Альтернатива: пустить видео через сам SC (тогда
# provider должен указывать на кастомный OpenAI-compat, и
# model: google/gemini-2.5-flash в SC-неймспейсе):

# Запуск
hermes chat -q "Используй video_analyze на /path/to/local.mp4: опиши в одном предложении что на видео и перечисли таймкоды ключевых сцен в формате MM:SS: описание."

# Или из Python через hermes tools:
#   from tools.vision_tools import video_analyze_tool
#   await video_analyze_tool("/path/to/local.mp4", "Опиши видео и таймкоды")
```

Внутри `video_analyze_tool` (см. [tools/vision_tools.py стр. ~1700+](https://github.com/NousResearch/hermes-agent/blob/659d1123/tools/vision_tools.py)) Hermes делает:
- проверка расширения (mp4/webm/mov/avi/mkv/mpeg);
- `st_size` проверка (≤ 50 МБ base64, warn > 20 МБ);
- base64-кодирование в `data:video/mp4;base64,…`;
- формирование `messages = [{"role":"user","content":[{text}, {video_url}]}]`;
- вызов `async_call_llm(task="video", messages=..., model=...)` через auxiliary-client;
- если upstream вернул «content-dialect rejected» (например, `400 invalid message format`), текущая main-ветка (PR #98502) делает **откат по лестнице**:
  1. повтор как `input_video` (raw base64, llama.cpp-стиль);
  2. если и это отвергнуто — извлечение JPEG-кадров через `ffmpeg` + отправка `image_url` (потеря темпоральной информации, но работает на любом vision-провайдере).

Для SC напрямую — `input_video` диалект не нужен (это llama.cpp-style), достаточно одного `video_url` запроса.

---

## (d) `video_url` через http(s) vs data-URL vs multipart vs frames — итог

| Способ | Поддержка в SC | Поддержка upstream (MiMo / Gemini / Qwen) | Когда использовать |
|---|---|---|---|
| **`video_url` + data URL (base64)** | ✅ принимается; payload уходит в OpenAI-compat envelope | ✅ у всех трёх upstream-провайдеров; `gemini-2.5-flash` через OpenAI-compat-адаптер конвертит в `inlineData` | **Локальный файл ≤ 50 МБ** — **рекомендуемый** |
| **`video_url` + http(s) URL** | ✅ принимается; SC отдаёт URL как есть upstream'у | ✅ MiMo скачивает (≤ 300 МБ); ✅ Gemini (`generativelanguage.googleapis.com/v1beta/openai`) — публичные URL + YouTube; ✅ Qwen — http(s) и `oss://` | Видео уже в публичном доступе; экономия трафика |
| **Multipart upload в `/v1/files` или `/v1/uploads`** | ❌ **404 Not Found** (проверено) | — | **Не поддерживается** |
| **Frames (image_url JPEG x N) fallback** | ✅ — каждый кадр как `image_url` | ✅ если модель хоть как-то понимает image | Если модель вернула `400 invalid message format` / `Could not open video stream` — Hermes Agent main-ветка делает это автоматически через `ffmpeg`+`image_url` |
| **Anthropic Messages `input_video`** | ❌ — Messages API в SC вообще не принимает видео | ❌ Anthropic в tool/image blocks не имеет видео | **Не поддерживается** |
| **OpenAI Responses API `input_video`** | ⚠️ `/v1/responses` есть в SC, но **поддержка `input_video` зависит от upstream**. На SC `input_video` пока не задокументирован; на практике Hermes Agent не использует его на SC. | — | Не исследован; считать **не верифицированным** для SC |

**Вердикт:**
- **base64 `data:` URL в `video_url`** — единственный надёжный способ для локального файла.
- **http(s) URL в `video_url`** — самый дешёвый по трафику; годится для уже-опубликованных видео.
- **Multipart/files API** — отсутствует на SC физически.
- **JPEG-кадры** — только как fallback, когда `video_url` отвергнут.

---

## Известные подводные камни

1. **`input_modalities` у многих моделей в каталоге SC не совпадают с рекламной страницей** ([standardcompute.com/models](https://standardcompute.com/models)). Например, `gemini-2.5-flash` заявлен с `text·image·file·audio·video` на сайте, и в `/v1/models` это совпадает ✅. А вот `qwen/qwen3.8-flash` заявлен как text+image, и в `/v1/models` тоже `text+image` (без video). Полагаться надо на **живой `/v1/models`**, а не на сайт.
2. **`:us` и `:eu` алиасы** в SC на октябрь 2026 для ряда моделей показывают только `["text"]` (см. таблицу выше). Это значит, что физически endpoint резолвится в US-инстанс, где провайдер не подключён. Лучше использовать нерегиональные ID: `google/gemini-2.5-flash` (а не `…:us` или `…:eu`).
3. **`MiMo V2.5 Pro` (без `…-v2.5`) — `text` only**. Видео принимает только `xiaomi/mimo-v2.5` (без суффикса Pro).
4. **`gemini-2.5-flash` inline-видео** иногда отдаёт 500/503 у самого Google. Это upstream-проблема, не SC. Решение: retry с экспоненциальным backoff'ом, fps=1, base64 ≤ 10 МБ, или переход на `qwen/qwen3.7-flash` (дешевле и стабильнее).
5. **SC smart-routing (`model: "standardcompute"`)** не выберет видео-модель сам, если в `messages` есть `video_url` — по логике шлюза он маршрутизирует по сложности текста, а модальность не учитывает. **Пинь модель явно** (`xiaomi/mimo-v2.5` или `google/gemini-2.5-flash`), иначе 99% запросов уйдут в text-only модель и придёт `400 unsupported_model_input` (`"unsupported_model_input"` — задокументированный SC error code из [docs.standardcompute.com/models](https://docs.standardcompute.com/models)).
6. **`max_tokens` vs `max_completion_tokens`**: SC принимает оба (см. [docs.standardcompute.com/api/chat-completions](https://docs.standardcompute.com/api/chat-completions)).
7. **Параметр `response_format` нельзя использовать одновременно с `video_url`** у части моделей; для структурированного JSON-вывода сначала получите текстовое описание, потом парсите или используйте второй вызов.
8. **Таймаут**: видео-запросы у SC (через любой upstream) занимают 10–60 с для 1–10 МБ файла. Hermes Agent по умолчанию ставит `auxiliary.video.timeout: 180` ([PR #31107](https://github.com/NousResearch/hermes-agent/pull/31107)). Прямому curl можно ставить `--max-time 300`.

---

## Что я не смог верифицировать

> ⚠ **Не верифицировано живым API-вызовом** (у меня нет валидного `STANDARDCOMPUTE_API_KEY`):
>
> - Что SC действительно транслирует `data:video/mp4;base64,…` в MiMo `video_url` shape, а не отбрасывает с `400`. **Очень вероятно, что да** (SC проксирует OpenAI-compat к upstream'ам без переупаковки), но без живого прогона это inference, а не факт.
> - Что `fps`/`media_resolution`/`min_pixels`/`max_pixels` поля не отбрасываются SC-роутером. Скорее всего пробрасываются, потому что SC прозрачен к формату, но точно — только с логами в дашборде.
> - Поведение `model: "standardcompute"` при наличии `video_url` (умный роутер может попытаться отправить в text-only модель и вернуть 400). Судя по коду Hermes Agent, который пинь-моделит — лучше пинь явно.
> - Точные лимиты размера в байтах для SC на бесплатном/дешёвом плане. Каталог говорит про 1M context; реальный per-request payload cap не задокументирован публично.

**План верификации после получения ключа:**
1. Прогнать `curl` с `clip.mp4` (10 МБ base64) на `google/gemini-2.5-flash` → должен вернуть описание.
2. Прогнать с `fps: 2` → должно дать более детальный таймлайн.
3. Прогнать на `xiaomi/mimo-v2.5` → должен ответить по-китайски/английски с описанием.
4. Прогнать на `qwen/qwen3.7-flash` → должен работать (с `min_pixels`/`max_pixels`).
5. Специально: 80 МБ base64 → ожидать `400 invalid_request_error`/`context_length_exceeded`.
6. Проверить HTTP URL: `https://example-files.cnbj1.mi-fds.com/example-files/video/video_example.mp4` (MiMo example).
7. Проверить fallback: если одна модель отвергает, попробовать другую (smart-routing, если включён, может сам фолбэк сделать).

---

## Источники

### Standard Compute (SC)
- Главная: https://standardcompute.com
- Каталог моделей (маркетинг): https://standardcompute.com/models
- Docs: https://docs.standardcompute.com
- API base: https://api.stdcmpt.com/v1
- Chat Completions reference: https://docs.standardcompute.com/api/chat-completions
- Messages reference: https://docs.standardcompute.com/api/messages
- Models endpoint reference: https://docs.standardcompute.com/api/models
- Agents — Hermes setup: https://docs.standardcompute.com/agents/hermes
- Integrations: https://standardcompute.com/integrations

### OpenAI-совместимый стандарт видео
- OpenRouter Video Inputs: https://openrouter.ai/docs/guides/overview/multimodal/videos
- AISIX AI Gateway on Gemini OpenAI-compat: https://docs.api7.ai/ai-gateway/providers/gemini
- Xiaomi MiMo Video Understanding: https://mimo.mi.com/docs/en-US/quick-start/usage-guide/multimodal-understanding/video-understanding
- MiMo V2.5 model page (с OpenAI-совместимым SDK): https://mimo.mi.com/models/en-US/mimo-v2.5
- Qwen DashScope OpenAI-compat: https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen-api-via-openai-chat-completions
- Qwen3-VL (HuggingFace, raw inference): https://github.com/qwenlm/qwen3-vl
- Qwen3-VL processor apply_chat_template (video content): https://qwenlm-qwen3-vl.mintlify.app/inference/video-processing

### Gemini и известные проблемы inline-видео
- googleapis/python-genai issue #728 (Gemini 2.5 video bytes 500): https://github.com/googleapis/python-genai/issues/728
- discuss.ai.google.dev 80093: https://discuss.ai.google.dev/t/gemini-2-5-flash-api-cannot-process-video-input/80093
- gemini cookbook 741: https://github.com/google-gemini/cookbook/issues/741

### Hermes Agent — реализация video_analyze и связанные обсуждения
- PR #19301 (merged May 3 2026) — `video_analyze` tool: https://github.com/NousResearch/hermes-agent/pull/19301
- PR #98502 — native video dialects + frames fallback: https://github.com/NousResearch/hermes-agent/pull/98502
- PR #88187 — fix(gemini) translate video_url → inlineData: https://github.com/NousResearch/hermes-agent/pull/88187
- PR #65043 — earlier broader video_url→inlineData validation: https://github.com/NousResearch/hermes-agent/pull/65043
- PR #31107 — `auxiliary.video` config block: https://github.com/NousResearch/hermes-agent/pull/31107
- PR #27313 — feature request: separate `auxiliary.video`: https://github.com/NousResearch/hermes-agent/issues/27313
- PR #72275 — `video_analyze` rejects on most providers: https://github.com/NousResearch/hermes-agent/issues/72275
- PR #21920 — silent Gemini video drop: https://github.com/NousResearch/hermes-agent/issues/21920
- PR #88141 — native video fast-path feature: https://github.com/NousResearch/hermes-agent/issues/88141
- PR #82419 — model override can return false success: https://github.com/NousResearch/hermes-agent/issues/82419
- source `tools/vision_tools.py` (PR #19301 + cap constants): https://github.com/NousResearch/hermes-agent/blob/659d1123/tools/vision_tools.py
- PR #37219 / #38999 — `video_url` → `input_video` для Anthropic-совместимых провайдеров: https://github.com/NousResearch/hermes-agent/issues/37219

### Соседние проекты (для подтверждения общего стандарта)
- CLIProxyAPI issue #3920 — OpenAI→Gemini конверсия для `video_url`: https://github.com/router-for-me/CLIProxyAPI/issues/3920
- LLMGateway video-generation: https://docs.llmgateway.io/features/video-generation
- Vercel AI Gateway video: https://vercel.com/docs/ai-gateway/modalities/video-generation/text-to-video
- AIgateway (aigateway.sh) gemini-omni-flash: https://aigateway.sh/models/google/gemini-omni-flash/v1.1/text-to-video

### Локальные проверки (выполнены во время исследования)
- `GET https://api.stdcmpt.com/v1/models` — ответ в `/tmp/sc_models.json` (анализ в первой таблице).
- `GET https://api.stdcmpt.com/v1/files` — 404.
- `GET https://api.stdcmpt.com/v1/uploads` — 404.
- `POST https://api.stdcmpt.com/v1/chat/completions` с `Authorization: Bearer dummy` — 401 (валидации payload до auth нет).
- `ffmpeg -f lavfi -i testsrc=... -f lavfi -i sine=... -c:v libx264 -c:a aac -shortest /tmp/sc_test/clip.mp4` — 62 КБ тестовое видео, base64 = 85 КБ.

---

## Краткие шаги для пользователя (one-liner)

```bash
# Установить ключ
export STANDARDCOMPUTE_API_KEY="sk-..."

# Кодировать локальный файл
B64=$(base64 -w0 /path/to/local.mp4)

# Отправить
curl -sS https://api.stdcmpt.com/v1/chat/completions \
  -H "Authorization: Bearer $STANDARDCOMPUTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg b64 "$B64" '{
    model: "google/gemini-2.5-flash",
    messages: [{role:"user", content:[
      {type:"text", text:"Опиши в одном предложении что на видео и перечисли таймкоды ключевых сцен (MM:SS: описание)."},
      {type:"video_url", video_url:{url:("data:video/mp4;base64," + $b64)}, fps:1}
    ]}],
    max_tokens: 800
  }')" | jq -r '.choices[0].message.content'
```

Для моделей MiMo/Qwen — поменять `model` и добавить `media_resolution` / `min_pixels` / `max_pixels` соответственно (см. секцию (a)).
