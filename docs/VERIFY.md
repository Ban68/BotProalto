# Verificacion local

Comandos minimos para validar que la app sigue arrancando y que los tests
existentes cubren el flujo de errores y media sin depender de `pytest`.

```powershell
python -m compileall app.py config.py src cloud_run tests test_error_tracker.py
$env:PYTHONIOENCODING='utf-8'
.\venv\Scripts\python.exe test_error_tracker.py
.\venv\Scripts\python.exe -m unittest tests.verify_media
```
