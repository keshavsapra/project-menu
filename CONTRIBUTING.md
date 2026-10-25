# Contributing to project-menu

Thank you for your interest in contributing to **project-menu**!

## How to Contribute

### 1. Setting Up Development Environment

Clone the repository and run the test suite:

```bash
git clone https://github.com/keshavsapra/project-menu.git
cd project-menu
python3 -m unittest discover -s tests -p "test_*.py" -v
```

### 2. Adding a New Display Backend

Adding support for a new compositor or desktop environment is straightforward:

1. **Create `backends/<name>.py`**:
   Subclass `SubprocessBackend` (from `backends.base`) or `DisplayBackend` (from `interfaces`).
   Implement:
   * `can_handle(env)`: returns True if suitable for the detected environment.
   * `list_outputs()`: returns `list[Output]`.
   * `get_current_mode()`: returns active `DisplayMode` (or `infer_mode(self.list_outputs())`).
   * `plan(mode_or_selection, target_output, position)`: returns human-readable commands.
   * `apply(mode_or_selection, target_output, position)`: applies changes and records snapshot for restore.
   * `restore(snapshot)`: restores previous display state.

2. **Register the Backend**:
   Add the backend class to `BACKENDS` in `backends/registry.py` and add aliases to `ALIASES`.

3. **Add Unit Tests**:
   Create `tests/test_<name>_backend.py` using `make_runner` from `tests/helpers.py` to mock command output.

### 3. Adding a New Hotkey Registrar

If your desktop has a specific keybinding mechanism:
1. Create `hotkeys/<desktop>.py` subclassing `HotkeyRegistrar`.
2. Implement `register(command)`, `unregister()`, and `instructions(command)`.
3. Register it in `hotkeys/registry.py`.

### 4. Running Tests

Before submitting a Pull Request, ensure all tests pass:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
python3 -m compileall .
```

### 5. Pull Request Guidelines

* Keep commits clean and focused.
* Follow existing code conventions and type hints.
* Include unit tests covering new features or bug fixes.
