"""PyInstaller entrypoint; source collector CLI remains independently usable."""
from src.distribution import main

if __name__ == '__main__':
    raise SystemExit(main())
