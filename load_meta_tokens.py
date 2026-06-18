import subprocess, re
from pathlib import Path

log = subprocess.check_output(["git","log","-p","--all","--","fetch_data.py"], text=True, errors="ignore")
def grab(var):
    m = re.search(var + r'[^\n]*"(EAA[A-Za-z0-9]{30,})"', log)
    return m.group(1) if m else None
t1, t2 = grab("META_TOKEN_BM1"), grab("META_TOKEN_BM2")
assert t1 and t2, "Токени не знайдено в історії"

env = Path(".env")
text = env.read_text() if env.exists() else ""
keep = [l for l in text.splitlines() if l.split("=",1)[0] not in ("META_TOKEN_BM1","META_TOKEN_BM2")]
keep += [f"META_TOKEN_BM1={t1}", f"META_TOKEN_BM2={t2}"]
env.write_text("\n".join(keep).strip()+"\n"); env.chmod(0o600)
print(f"✅ META_TOKEN_BM1/BM2 у .env (chmod 600). Довжини: {len(t1)}/{len(t2)} симв.")
