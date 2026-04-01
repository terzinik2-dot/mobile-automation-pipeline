# Mobile Automation Pipeline — Android E2E Автоматизация

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Appium](https://img.shields.io/badge/Appium-2.0-663399?style=flat-square&logo=appium&logoColor=white)](https://appium.io)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.9-5C3EE8?style=flat-square&logo=opencv&logoColor=white)](https://opencv.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Clerk](https://img.shields.io/badge/Clerk-Auth-6C47FF?style=flat-square&logo=clerk&logoColor=white)](https://clerk.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Run on Replit](https://replit.com/badge/github/terzinik2-dot/mobile-automation-pipeline)](https://replit.com/github.com/terzinik2-dot/mobile-automation-pipeline)

---

## Запуск на Replit

> **Replit используется как основная среда разработки и control plane** для управления сценариями автоматизации.

### Быстрый старт (1 минута)

1. Нажмите кнопку **"Run on Replit"** выше или откройте: `replit.com/github.com/terzinik2-dot/mobile-automation-pipeline`
2. Replit автоматически импортирует репозиторий и настроит окружение (Python 3.11 + Node.js 20 + Tesseract + ADB)
3. Заполните **Secrets** в Replit (вкладка Tools > Secrets):
   - `GOOGLE_TEST_EMAIL` — тестовый Google-аккаунт
   - `GOOGLE_TEST_PASSWORD` — пароль
   - `CLERK_SECRET_KEY` — ключ от Clerk.com
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` — публичный ключ Clerk
   - `BROWSERSTACK_USERNAME` / `BROWSERSTACK_ACCESS_KEY` — (опционально) для облачной фермы
4. Нажмите **Run** — запустятся FastAPI (порт 8000) + Next.js Dashboard (порт 3000)
5. Dashboard доступен по внешнему URL Replit

### Что работает на Replit

| Компонент | Статус | Описание |
|-----------|--------|----------|
| FastAPI Orchestrator | Полностью | API-сервер, управление прогонами, WebSocket |
| Next.js Dashboard + Clerk | Полностью | Web-панель с авторизацией, запуск сценариев |
| BrowserStack / AWS Adapter | Полностью | Управление облачными устройствами через API |
| Appium Remote Sessions | Полностью | Подключение к удалённым Appium-серверам ферм |
| CV/OCR Engine | Полностью | OpenCV + Tesseract установлены через Nix |
| Local ADB | Ограниченно | USB-устройства недоступны, используйте ADB over WiFi |

### Архитектура на Replit

```
┌─────────────────────────────────────────────────┐
│                  REPLIT                          │
│                                                 │
│  ┌──────────────┐    ┌───────────────────────┐  │
│  │  Next.js +   │◄──►│  FastAPI Orchestrator  │  │
│  │  Clerk Auth  │    │  + SQLite + WebSocket  │  │
│  │  (port 3000) │    │  (port 8000)           │  │
│  └──────────────┘    └───────────┬────────────┘  │
│                                  │               │
└──────────────────────────────────┼───────────────┘
                                   │ HTTPS API
                    ┌──────────────┼──────────────┐
                    │              │              │
              ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐
              │BrowserStack│ │ AWS Device│ │  ADB WiFi │
              │  Appium    │ │   Farm    │ │  (local)  │
              └───────────┘ └───────────┘ └───────────┘
```

Replit выступает как **control plane**: всё управление, аутентификация, оркестрация и визуализация результатов происходят здесь. Реальное взаимодействие с Android-устройствами идёт через API провайдеров ферм.

---

## Обзор проекта

**Mobile Automation Pipeline** — это production-ready система E2E автоматизации на Android, которая воспроизводит полный пользовательский путь монетизации в мобильной игре за **не более 3 минут** на облачных фермах устройств.

### Что делает система

Единый запуск pipeline выполняет следующую последовательность полностью автономно:

1. **Вход в Google-аккаунт** — авторизация на устройстве с обходом экранов 2FA и восстановления
2. **Установка MLBB из Play Store** — поиск, загрузка и установка Mobile Legends: Bang Bang
3. **Регистрация в игре** — прохождение onboarding, создание персонажа, привязка аккаунта
4. **Покупка через Google Pay** — выбор товара и проведение тестовой транзакции через Google Play Billing

### Для чего это нужно

- **QA-автоматизация** — верификация purchase funnel после каждого релиза
- **Device farm тестирование** — прогон одного сценария на десятках устройств параллельно
- **Мониторинг** — регулярная проверка, что критический путь монетизации не сломан
- **Демонстрация зрелости инженерного процесса** — пример устойчивой автоматизации реальных user flow

Система спроектирована так, чтобы пережить изменения UI/DOM без переписывания сценариев — через каскадный движок локаторов с CV/OCR-фолбэком.

---

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│           Web Dashboard (Next.js 14 + Clerk)            │
│         Запуск / мониторинг / история прогонов          │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP REST + WebSocket
                          ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Orchestrator (Python)               │
│    Управление очередью, time budget, артефактами         │
└──────────┬──────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│                  Provider Adapter Layer                   │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │BrowserStack │  │  AWS Device  │  │  Local / ADB   │  │
│  │App Automate │  │    Farm      │  │   Emulator     │  │
│  └─────────────┘  └──────────────┘  └────────────────┘  │
└──────────┬───────────────────────────────────────────────┘
           │  Unified Appium Session
           ▼
┌──────────────────────────────────────────────────────────┐
│          Appium 2.0 Driver (UiAutomator2)                │
│                                                          │
│   ┌──────────────────────────────────────────────────┐   │
│   │         Multi-Layer Locator Engine               │   │
│   │  resource-id → text → a11y → XPath → CV → OCR   │   │
│   └──────────────────────────────────────────────────┘   │
└──────────┬───────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│                   Scenario Executor                       │
│                                                          │
│  [Google Login] → [Play Store] → [MLBB Reg] → [Purchase] │
│                                                          │
│   Time Budget Monitor ████████████░░░ 2m 34s / 3m 00s   │
└──────────┬───────────────────────────────────────────────┘
           │ fallback
           ▼
┌──────────────────────────────────────────────────────────┐
│           CV/OCR Fallback Engine                         │
│         OpenCV template matching + Tesseract OCR         │
└──────────┬───────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│                    Artifacts Store                        │
│      Video • Screenshots • Logs • HTML Report            │
└──────────────────────────────────────────────────────────┘
```

---

## Ключевые решения и trade-offs

| Решение | Выбранный подход | Альтернатива | Почему именно так |
|---|---|---|---|
| **Фреймворк автоматизации** | Appium 2.0 | Playwright, Detox, Espresso | Appium — единственный вариант для black-box автоматизации нативных Android-приложений без доступа к исходному коду. Playwright поддерживает только мобильный web. Detox/Espresso требуют исходный код приложения |
| **Стратегия авторизации Google** | Pre-authenticated device profile | Cold login каждый раз | Холодный вход в Google занимает 45–90 секунд, а при автоматизации часто триггерит антибот-защиту (CAPTCHA, верификация устройства). Предзагруженный профиль сокращает это до 5 секунд и устраняет класс нестабильных отказов |
| **Locator strategy** | Каскад из 6 методов | Один метод (XPath) | Ни один метод локации не работает надёжно во всех состояниях приложения. XPath ломается при рефакторинге. Каскад обеспечивает устойчивость: если верхние уровни не срабатывают, система деградирует gracefully до CV |
| **Тестирование оплаты** | Google Play Billing test mode | Реальная транзакция | Реальные транзакции требуют реальных денег, имеют постоянные лимиты и юридические ограничения. Test mode Google Play полностью симулирует платёжный флоу с настоящим UI без фактического списания |
| **Control plane** | Replit (hosted) | Self-hosted VPS, Railway | Для демонстрации и тестового задания Replit даёт нулевой DevOps-overhead: zero-config деплой, публичный URL, встроенные env vars и secrets |
| **Аутентификация дашборда** | Clerk | Auth.js, Firebase Auth, Supabase Auth | Clerk — это production-grade auth с готовыми компонентами для Next.js. Экономит 2–3 дня работы по сравнению с кастомной реализацией, при этом покрывает MFA, сессии, webhooks |

---

## Self-Healing Locator Strategy

Ключевая инженерная особенность системы — каскадный движок локаторов, который обеспечивает устойчивость сценариев к изменениям в приложении.

### Порядок каскада

```
Шаг 1: resource-id
  └─ com.mobile.legends:id/btn_login
  └─ Самый быстрый (~50ms). Стабилен пока не изменится код разработчика.
  └─ Фолбэк: переходим к шагу 2

Шаг 2: text / content-description
  └─ "Войти", "Install", "Купить"
  └─ Работает даже после рефакторинга UI, пока не изменился текст.
  └─ Учитываем локализацию: для en/ru/id используем маппинг.
  └─ Фолбэк: переходим к шагу 3

Шаг 3: accessibility-id
  └─ Устанавливается разработчиками для a11y поддержки.
  └─ Обычно стабильнее text — реже меняется при редизайне.
  └─ Фолбэк: переходим к шагу 4

Шаг 4: XPath с семантическими якорями
  └─ //android.widget.Button[@text="Install" or @content-desc="Install"]
  └─ Избегаем абсолютных XPath (/hierarchy/...) — они ломаются при любом изменении.
  └─ Используем относительные выражения с семантическими атрибутами.
  └─ Фолбэк: переходим к шагу 5

Шаг 5: CV template matching (OpenCV)
  └─ Ищем скриншот элемента (эталон из ./templates/) на текущем экране.
  └─ Threshold: 0.80 по умолчанию. Устойчив к небольшим изменениям layout.
  └─ Конвертируем найденные координаты в touch action.
  └─ Фолбэк: переходим к шагу 6

Шаг 6: OCR text detection (Tesseract)
  └─ Полный скриншот → Tesseract → поиск целевого текста → координаты bounding box.
  └─ Последний рубеж. Работает даже если весь UI был переписан.
  └─ При confidence < 0.7: step failure + screenshot + уведомление.
```

### Почему именно такой порядок

Порядок определён по двум осям: **скорость** (resource-id ~50ms vs OCR ~800ms) и **специфичность** (resource-id уникален, OCR может дать ложные срабатывания). Быстрые и точные методы идут первыми; медленные и «широкие» — последними. Это минимизирует среднее время поиска элемента при сохранении максимальной устойчивости.

### Что происходит при исчерпании всех уровней

1. Step помечается как `FAILED` с кодом `ELEMENT_NOT_FOUND`
2. Делается скриншот текущего экрана
3. Если `STEP_RETRY_COUNT > 0` — повтор с той же стратегией
4. После всех ретраев — выброс `StepTimeoutError` с полным контекстом
5. Оркестратор записывает failure в БД, сохраняет артефакты, обновляет дашборд

---

## Time Budget Management

Весь pipeline должен выполниться за **3 минуты (180 секунд)**. Бюджет распределён по шагам:

| Шаг | Бюджет | Буфер | Описание |
|---|---|---|---|
| Инициализация сессии | 15 сек | 5 сек | Подключение к Appium / device farm, получение сессии |
| Вход в Google | 20 сек | 10 сек | Предзагруженный профиль, ввод пароля, подтверждение |
| Открытие Play Store | 10 сек | 5 сек | Запуск приложения, ожидание главного экрана |
| Поиск и установка MLBB | 45 сек | 15 сек | Поиск → Install → Download → Launch (самый долгий шаг) |
| Onboarding и регистрация | 35 сек | 10 сек | Обучение, выбор сервера, создание персонажа |
| Покупка через Google Pay | 25 сек | 10 сек | Выбор товара → Pay → подтверждение биометрией |
| Сбор артефактов | 10 сек | 5 сек | Финальный скриншот, завершение записи, закрытие сессии |
| **Итого** | **160 сек** | **60 сек** | Суммарный буфер: 20 сек |

### Как работает time budget enforcement

```python
# Упрощённая схема работы TimeBudgetMonitor
class TimeBudgetMonitor:
    def __init__(self, total_budget=180):
        self.deadline = time.monotonic() + total_budget
        self.step_deadlines = {}

    def check_budget(self, step_name, step_budget):
        remaining = self.deadline - time.monotonic()
        if remaining < step_budget:
            raise TimeBudgetExceededError(
                f"Step '{step_name}' requires {step_budget}s, only {remaining:.1f}s left"
            )
        self.step_deadlines[step_name] = time.monotonic() + step_budget

    def assert_step_in_time(self, step_name):
        if time.monotonic() > self.step_deadlines[step_name]:
            raise StepTimeoutError(step_name)
```

Перед каждым шагом оркестратор проверяет, хватит ли оставшегося времени. Если нет — прогон завершается `TIMEOUT_ABORT` вместо того, чтобы начать шаг и заведомо не успеть. Это позволяет корректно сохранять артефакты даже при таймауте.

---

## Device Farm Provider Support

| Провайдер | Устройства | Параллельность | Плюсы | Минусы |
|---|---|---|---|---|
| **BrowserStack App Automate** | 3000+ реальных устройств | До 25 параллельных сессий | Реальные устройства, готовые APK-адреса, встроенная видеозапись, детальные логи | Цена: от $399/мес, задержки сети до устройства |
| **AWS Device Farm** | ~200 реальных устройств | Зависит от плана | Интеграция с AWS CI/CD, data residency в конкретном регионе | Дороже BrowserStack при high volume, меньший каталог |
| **Local / ADB** | 1-N устройств/эмуляторов | Ограничено железом | Нет сетевой задержки, бесплатно, удобно для разработки | Нет облачной инфраструктуры, не масштабируется |

### Переключение провайдера

```bash
# BrowserStack
DEVICE_PROVIDER=browserstack python -m pipeline.run

# AWS Device Farm
DEVICE_PROVIDER=aws_device_farm python -m pipeline.run

# Локальный эмулятор
DEVICE_PROVIDER=local LOCAL_DEVICE_UDID=emulator-5554 python -m pipeline.run
```

---

## Устойчивость к изменениям UI/DOM

Ниже описано, как система реагирует на каждый тип изменений в приложении:

### Изменение resource-id элементов
**Сценарий:** Разработчики MLBB переименовали `btn_login` → `button_sign_in`  
**Реакция:** Шаг 1 каскада не находит элемент → автоматический переход к шагу 2 (text matching). Сценарий продолжается без изменений в коде. Система логирует `locator_fallback` событие — инженер видит деградацию в дашборде и обновляет resource-id в фоне.

### Изменение текста кнопок
**Сценарий:** "Войти" → "Авторизоваться" или локализация  
**Реакция:** Шаги 1-2 падают. Шаг 3 (accessibility-id) или шаг 4 (XPath с семантикой) подхватывают элемент. Если изменился весь язык — OCR на шаге 6 читает новый текст с экрана напрямую.

### Добавление новых промежуточных экранов
**Сценарий:** Google добавил новый экран "Добро пожаловать" или CAPTCHA  
**Реакция:** Система обнаруживает неожиданный экран через CV-матчинг известных шаблонов. Если шаблон не найден — включается `UnknownScreenHandler`, который логирует скриншот, пробует найти кнопки "Продолжить", "OK", "Принять" через OCR. Это покрывает большинство interstitial экранов.

### Изменение layout в WebView
**Сценарий:** Play Store обновил внутреннюю страницу приложения  
**Реакция:** WebView-элементы имеют нестабильные локаторы по природе. Система переключается в `WEBVIEW` контекст Appium и использует CSS-селекторы / JS execution. CV-шаблоны для кнопок Play Store обновляются с каждым новым скриншотом успешного прогона (self-updating templates feature).

### Полное изменение UI (redesign)
**Сценарий:** MLBB выпустил major visual update  
**Реакция:** Все методы уровней 1-4 падают. CV шаг 5 пробует старые шаблоны — не совпадают. OCR шаг 6 ищет текст по смыслу. При полном редизайне человек получает алерт `CRITICAL_UI_CHANGE`, видит скриншоты в дашборде и обновляет шаблоны. Порог обнаружения редизайна: если >3 шагов подряд деградировали до OCR.

---

## Быстрый старт

### Предварительные требования

```bash
# Python 3.11+
python --version

# Node.js 18+
node --version

# Tesseract OCR
tesseract --version   # apt install tesseract-ocr / brew install tesseract

# ADB (для локального запуска)
adb --version
```

### Локальный запуск

```bash
# 1. Клонировать репозиторий
git clone https://github.com/yourname/mobile-automation-pipeline.git
cd mobile-automation-pipeline

# 2. Создать виртуальное окружение и установить зависимости
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Настроить переменные окружения
cp .env.example .env
# Отредактировать .env: указать Google-аккаунт, путь к ADB, UDID устройства

# 4. Запустить Appium сервер (отдельный терминал)
npm install -g appium@2.0
appium driver install uiautomator2
appium

# 5. Запустить оркестратор
uvicorn orchestrator.main:app --reload --host 0.0.0.0 --port 8000

# 6. Запустить дашборд (отдельный терминал)
cd dashboard
npm install
cp .env.local.example .env.local
# Вставить NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY и CLERK_SECRET_KEY
npm run dev

# 7. Открыть дашборд
open http://localhost:3000

# 8. Запустить pipeline через CLI
python -m pipeline.run --provider local --device emulator-5554
```

### Запуск через BrowserStack

```bash
# 1. Установить переменные окружения
export DEVICE_PROVIDER=browserstack
export BROWSERSTACK_USERNAME=your_username
export BROWSERSTACK_ACCESS_KEY=your_access_key

# 2. Загрузить APK на BrowserStack (если нужно)
# python scripts/upload_apk.py --apk path/to/mlbb.apk

# 3. Запустить pipeline
python -m pipeline.run \
  --provider browserstack \
  --device "Google Pixel 7" \
  --os-version "13.0"

# 4. Параллельный запуск на нескольких устройствах
python -m pipeline.run \
  --provider browserstack \
  --parallel 5 \
  --device-matrix devices.json
```

---

## Структура проекта

```
mobile-automation-pipeline/
│
├── orchestrator/               # FastAPI бэкенд
│   ├── main.py                 # Точка входа, роуты, WebSocket
│   ├── models.py               # SQLAlchemy модели (Run, Step, Artifact)
│   ├── schemas.py              # Pydantic схемы для API
│   ├── runner.py               # Логика запуска прогонов
│   ├── time_budget.py          # TimeBudgetMonitor
│   └── artifacts.py            # Сохранение скриншотов, видео, логов
│
├── providers/                  # Адаптеры провайдеров устройств
│   ├── base.py                 # Абстрактный DeviceProvider
│   ├── browserstack.py         # BrowserStack App Automate
│   ├── aws_device_farm.py      # AWS Device Farm
│   └── local.py                # Локальный ADB / эмулятор
│
├── executors/                  # Движок выполнения
│   ├── locator_engine.py       # Каскадный локатор (6 уровней)
│   ├── cv_engine.py            # OpenCV template matching
│   ├── ocr_engine.py           # Tesseract OCR wrapper
│   └── base_executor.py        # Базовый класс с wait/retry логикой
│
├── scenarios/                  # Сценарии автоматизации
│   ├── google_login.py         # Шаг 1: вход в Google-аккаунт
│   ├── play_store_install.py   # Шаг 2: поиск и установка MLBB
│   ├── mlbb_registration.py    # Шаг 3: onboarding и регистрация
│   └── google_pay_purchase.py  # Шаг 4: покупка через Google Pay
│
├── dashboard/                  # Next.js 14 фронтенд
│   ├── app/                    # App Router
│   │   ├── page.tsx            # Главная / редирект
│   │   ├── dashboard/          # Защищённые страницы
│   │   │   ├── page.tsx        # Список прогонов
│   │   │   └── run/[id]/       # Детальная страница прогона
│   │   ├── sign-in/[[...sign-in]]/page.tsx
│   │   └── sign-up/[[...sign-up]]/page.tsx
│   └── components/             # UI компоненты
│       ├── RunCard.tsx          # Карточка прогона
│       ├── StepTimeline.tsx     # Таймлайн шагов
│       ├── LiveLog.tsx          # Реалтайм лог через WebSocket
│       └── ArtifactViewer.tsx  # Просмотр скриншотов и видео
│
├── templates/                  # Эталонные изображения для CV
│   ├── play_store_install_btn.png
│   ├── google_pay_button.png
│   └── ...
│
├── artifacts/                  # Артефакты прогонов (gitignored)
│   └── {run_id}/
│       ├── video.mp4
│       ├── screenshots/
│       └── report.html
│
├── tests/                      # Тесты системы
│   ├── test_locator_engine.py
│   ├── test_time_budget.py
│   └── test_scenarios_mock.py
│
├── scripts/                    # Утилиты
│   ├── upload_apk.py           # Загрузка APK на BrowserStack
│   └── cleanup_artifacts.py    # Очистка старых артефактов
│
├── docs/                       # Документация
│   ├── ARCHITECTURE.md
│   ├── DECISION_LOG.md
│   └── VIDEO_SCRIPT.md
│
├── .env.example                # Шаблон переменных окружения
├── requirements.txt            # Python зависимости
└── README.md                   # Этот файл
```

---

## API Endpoints

Все endpoints доступны по базовому URL `http://localhost:8000/api/v1`.

| Метод | Endpoint | Описание |
|---|---|---|
| `POST` | `/runs` | Запустить новый прогон pipeline |
| `GET` | `/runs` | Список всех прогонов (с пагинацией) |
| `GET` | `/runs/{run_id}` | Детали конкретного прогона |
| `DELETE` | `/runs/{run_id}` | Отменить активный прогон |
| `GET` | `/runs/{run_id}/steps` | Шаги прогона с метриками |
| `GET` | `/runs/{run_id}/artifacts` | Список артефактов прогона |
| `GET` | `/artifacts/{artifact_id}` | Скачать конкретный артефакт |
| `GET` | `/providers` | Доступные провайдеры и их статус |
| `GET` | `/health` | Health check оркестратора |
| `WS` | `/ws/runs/{run_id}` | WebSocket для реалтайм обновлений |

### Пример запроса

```bash
# Запустить прогон через BrowserStack
curl -X POST http://localhost:8000/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "browserstack",
    "device": "Google Pixel 7",
    "os_version": "13.0",
    "scenario": "full_pipeline",
    "notify_webhook": "https://hooks.slack.com/..."
  }'
```

---

## Запуск тестов

```bash
# Все тесты
pytest tests/ -v

# Unit-тесты (без устройства)
pytest tests/ -v -m "not integration"

# Только тесты локатора
pytest tests/test_locator_engine.py -v

# С покрытием
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html

# Интеграционный тест на локальном устройстве
DEVICE_PROVIDER=local pytest tests/ -m integration -v
```

---

## Ограничения и Assumptions

Честный список того, что система **не** делает или делает с оговорками:

1. **Google 2FA** — система рассчитана на предзагруженный профиль или аккаунт без 2FA. Полная автоматизация SMS/TOTP 2FA выходит за рамки данной реализации и нарушает ToS Google.

2. **Реальные транзакции** — используется исключительно Google Play Billing test mode. Реальные покупки не проводятся. Тестовый аккаунт должен быть добавлен как licensed tester в консоли Google Play.

3. **APK доступность** — MLBB должен быть доступен в Play Store для тестируемого региона. Гео-ограничения могут потребовать VPN-настройки на уровне устройства.

4. **Версия MLBB** — сценарии написаны под MLBB 1.8.x. Значительный редизайн onboarding потребует обновления шаблонов CV и, возможно, корректировки сценариев.

5. **Время установки** — 45 секунд на установку MLBB предполагают скорость загрузки ≥ 10 Мбит/с. На медленных соединениях прогон может выйти за 3 минуты.

6. **Масштабирование** — текущая реализация оркестратора использует SQLite. Для production > 10 параллельных прогонов рекомендуется PostgreSQL.

7. **Секреты** — Google-аккаунт хранится в .env. Для production необходим vault (HashiCorp Vault, AWS Secrets Manager).

---

## Roadmap

| Приоритет | Фича | Описание |
|---|---|---|
| P0 | **PostgreSQL** | Замена SQLite для concurrent запусков |
| P0 | **Retry при timeout** | Автоматический перезапуск при TIMEOUT_ABORT |
| P1 | **Параллельный запуск** | N устройств одновременно из одного API call |
| P1 | **Self-updating CV templates** | Автоматическое обновление эталонов при успешных прогонах |
| P1 | **Slack / PagerDuty notifications** | Алерты при failure critical path |
| P2 | **Scheduled runs** | CRON-подобное расписание для мониторинга |
| P2 | **Multi-scenario support** | Поддержка дополнительных игр и сценариев |
| P2 | **AI-powered screen analysis** | GPT-4V вместо Tesseract для сложных экранов |
| P3 | **iOS support** | XCUITest driver + Appium для iOS сценариев |
| P3 | **Distributed tracing** | OpenTelemetry для профилирования шагов |

---

## Технологии

| Технология | Версия | Назначение |
|---|---|---|
| Python | 3.11 | Основной язык бэкенда и автоматизации |
| FastAPI | 0.111 | REST API + WebSocket оркестратора |
| Appium | 2.0 | Mobile automation framework |
| UiAutomator2 | 3.0 | Appium driver для Android |
| OpenCV | 4.9 | Computer vision, template matching |
| Tesseract | 5.3 | OCR для текстовой детекции |
| pytesseract | 0.3.10 | Python обёртка для Tesseract |
| Pillow | 10.2 | Обработка изображений |
| SQLAlchemy | 2.0 | ORM для работы с БД |
| SQLite | 3.x | База данных (dev/demo) |
| Next.js | 14 | Веб-дашборд (App Router) |
| TypeScript | 5.x | Типизация фронтенда |
| Clerk | 5.x | Аутентификация дашборда |
| Tailwind CSS | 3.4 | Стилизация дашборда |
| BrowserStack | API v1 | Облачная ферма устройств (основной) |
| AWS Device Farm | — | Облачная ферма устройств (альтернатива) |
| ADB | 1.0.41 | Управление локальными устройствами |

---

> Система разработана как демонстрация production-ready подхода к мобильной автоматизации. Вопросы и предложения — в Issues.
