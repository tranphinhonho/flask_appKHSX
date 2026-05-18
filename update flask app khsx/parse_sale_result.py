import json, sys, os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

res_file = sys.argv[1]
day      = sys.argv[2]
log_file = sys.argv[3] if len(sys.argv) > 3 else None

try:
    with open(res_file, encoding='utf-8') as f:
        d = json.load(f)

    ok        = d.get('success', False)
    msg       = d.get('message', '')
    count     = d.get('count', 0)
    not_found = d.get('not_found', [])

    if ok:
        print(f"  [OK] Ngay {day}/5 - Import thanh cong {count} san pham")
    else:
        print(f"  [FAIL] Ngay {day}/5 - {msg}")

    if not_found:
        print(f"  [!] Code cam CHUA CO trong DB ({len(not_found)} code):")
        for c in not_found:
            print(f"       - {c}")
        # Ghi vao log tong hop
        if log_file:
            with open(log_file, 'a', encoding='utf-8') as lf:
                for c in not_found:
                    lf.write(f"Ngay {day}/5: {c}\n")

    # Tra ve exit code de bat script kiem tra
    sys.exit(0 if ok else 1)

except Exception as e:
    print(f"  [ERR] Khong doc duoc ket qua: {e}")
    sys.exit(2)
