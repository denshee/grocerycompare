import sys

with open("debug_real.txt", "w", encoding="utf-8") as f:
    sys.stdout = f
    sys.stderr = f
    try:
        import match
        match.main()
    except Exception as e:
        f.write(f"\nCRASH: {e}")
