# Adding a New Provider to PostMule

This guide covers everything needed to add a new provider backend. A provider is an external service adapter — email, storage, LLM, spreadsheet, mailbox, finance, or notifications.

---

## 1. Understand the provider categories

| Category | Protocol | Where used |
|---|---|---|
| `email` | `EmailProvider` | Fetch VPM notifications + bill PDFs from inbox |
| `storage` | `StorageProvider` | Upload, move, rename PDFs in cloud storage |
| `llm` | `LLMProvider` | Classify and extract data from OCR text |
| `spreadsheet` | `SpreadsheetProvider` | Write the generated spreadsheet view |
| `mailbox` | *(no Protocol yet)* | Poll a physical mail service for new scans |
| `finance` | *(no Protocol yet)* | Pull bank transactions for bill matching |
| `notifications` | *(no Protocol yet)* | Send summary and alert emails |

Protocols live in `postmule/providers/<category>/base.py`. Every method in the Protocol **must** be implemented by your new class.

---

## 2. Create the provider file

Place your file at `postmule/providers/<category>/<service_key>.py`.

### Required module-level constants

```python
SERVICE_KEY = "my_service"   # matches config.yaml service: value
DISPLAY_NAME = "My Service"  # shown in the dashboard Providers tab
```

### Required class structure

```python
from postmule.providers.<category>.base import <CategoryProtocol>

class MyServiceProvider:
    """One-line summary. Longer description if needed."""

    def __init__(self, ...):
        # Accept only what config + credentials provide.
        # Defer all I/O to method call time — __init__ must not make network calls.
        ...

    # --- implement every method from the Protocol ---

    def health_check(self):
        """Return a HealthResult indicating whether credentials/connectivity are good."""
        from postmule.providers import HealthResult
        try:
            # minimal connectivity check, e.g. list root folder or fetch profile
            ...
            return HealthResult(ok=True, status="ok", message="Connected")
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))
```

`health_check()` is required on every provider class, including stubs. For unimplemented stubs, raise `NotImplementedError`.

### Stub providers (not yet implemented)

If you are registering a provider that isn't implemented yet, follow the existing stub pattern:

```python
class MyStubProvider:
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "My provider is not yet implemented. "
            "Use service: <default> in config.yaml for now."
        )

    def some_method(self, ...):
        raise NotImplementedError("My provider is not yet implemented.")

    def health_check(self):
        raise NotImplementedError("My provider is not yet implemented.")
```

---

## 3. Register the provider

Open `postmule/providers/registry.py` and add your provider to the relevant category dict:

```python
from postmule.providers.email.my_service import MyServiceProvider

_EMAIL_PROVIDERS: dict[str, type] = {
    "gmail": GmailProvider,
    "my_service": MyServiceProvider,   # ← add here
    ...
}
```

---

## 4. Add config.example.yaml entry

Open `config.example.yaml` and add a commented-out example block for your provider under the appropriate category:

```yaml
email:
  providers:
    # - service: my_service
    #   enabled: false
    #   address: you@example.com
    #   some_setting: value
```

---

## 5. Update the Providers dashboard

If your provider should appear in the web dashboard (recommended for all non-stub providers):

- Add a display entry to the relevant section of `postmule/web/routes/connections.py`
- Update `postmule/web/templates/page.html` if a new UI card field is needed
- Keep `mockup_dashboard.html` in sync with any visible UI changes

---

## 6. Write tests

### Unit test — at minimum, test `health_check()`

Add a test file at `tests/unit/test_<service_key>.py`:

```python
from unittest.mock import MagicMock, patch
from postmule.providers.<category>.my_service import MyServiceProvider

class TestMyServiceProvider:
    def test_health_check_ok(self):
        provider = MyServiceProvider(...)
        with patch.object(provider, "_some_internal_call", return_value=...):
            result = provider.health_check()
        assert result.ok
        assert result.status == "ok"

    def test_health_check_error(self):
        provider = MyServiceProvider(...)
        with patch.object(provider, "_some_internal_call", side_effect=RuntimeError("fail")):
            result = provider.health_check()
        assert not result.ok
        assert result.status == "error"
```

### Completeness test — automatic

`tests/unit/test_provider_completeness.py` automatically verifies that your class has all Protocol methods. Add your class to the relevant list in that file:

```python
EMAIL_PROVIDERS = [
    GmailProvider,
    MyServiceProvider,   # ← add here
    ...
]
```

---

## 7. Checklist before opening a PR

- [ ] `SERVICE_KEY` and `DISPLAY_NAME` defined
- [ ] All Protocol methods implemented (including `health_check()`)
- [ ] Class added to `registry.py`
- [ ] Example config block added to `config.example.yaml`
- [ ] Class added to the completeness test list in `test_provider_completeness.py`
- [ ] Unit tests written for the concrete implementation
- [ ] Dashboard / `page.html` / `mockup_dashboard.html` updated if UI changes were made
- [ ] `CLAUDE.md` updated if any architecture decisions changed
