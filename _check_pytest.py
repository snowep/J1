import importlib
try:
    import pytest
    print(f"pytest {pytest.__version__} OK")
except Exception as e:
    print(f"pytest missing: {e}")