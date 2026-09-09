"""Check available Python packages."""
for pkg in ['yaml', 'requests', 'bs4', 'pytest']:
    try:
        mod = __import__(pkg)
        ver = getattr(mod, '__version__', 'unknown')
        print(f"OK: {pkg} {ver}")
    except ImportError:
        print(f"MISSING: {pkg}")
