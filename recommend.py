import re
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

from extractor import parse_bill

BILLS_DIR    = Path(r"C:\Scripts\gmail-parser\bills")
TARIFFS_FILE = Path(r"C:\Scripts\gmail-parser\tariff_plans.json")


def _minutes(s: str) -> float:
    h, m, sec = (int(x) for x in s.strip().split(":"))
    return h * 60 + m + sec / 60

def _gb(s: str) -> float:
    m = re.match(r"(\d+)", s.strip())
    return int(m.group(1)) / 1_073_741_824 if m else 0.0

def _amount(s: str) -> float:
    return float(s.strip().replace(",", ".")) if s.strip() else 0.0


def extract_usage(sections: list[dict]) -> dict:
    phone = ""
    outgoing_min = 0.0
    internet_gb  = 0.0
    total_paid   = 0.0

    for section in sections:
        raw = section["info"].get("Абонентский номер", "")
        phone = re.split(r"[,\s]", raw.strip())[0]

        for row in section["charges"]:
            service = row[0].lower()
            qty     = row[1].strip() if len(row) > 1 else ""

            if "исходящая" in service and re.match(r"\d+:\d+:\d+", qty):
                outgoing_min += _minutes(qty)
            elif re.search(r"интернет|gprs|передача|данн", service) and re.match(r"\d+[a-z]", qty):
                internet_gb += _gb(qty)

        for row in section["totals"]:
            if "округлен" in row[0].lower() and len(row) > 1:
                total_paid += _amount(row[-1])

    return {
        "phone":        phone,
        "outgoing_min": round(outgoing_min),
        "internet_gb":  round(internet_gb, 2),
        "total_paid":   total_paid,
    }


def find_best_plan(usage: dict, tariffs: list[dict]) -> dict | None:
    mins = usage["outgoing_min"]
    gb   = usage["internet_gb"]

    def covers(plan: dict) -> bool:
        m = plan.get("minutes_all_networks", 0)
        mins_ok = m == "Безлимит" or (isinstance(m, (int, float)) and m >= mins)

        internet = plan.get("internet", "")
        plan_gb  = plan.get("internet_gb", 0)
        gb_ok = "Безлимит" in str(internet) or (isinstance(plan_gb, (int, float)) and plan_gb >= gb)

        return mins_ok and gb_ok

    candidates = [p for p in tariffs if covers(p)]
    return min(candidates, key=lambda p: p["price_byn"]) if candidates else None


def main():
    tariffs = json.loads(TARIFFS_FILE.read_text(encoding="utf-8"))

    for f in sorted(BILLS_DIR.iterdir()):
        if f.suffix.lower() not in (".pdf", ".html"):
            continue

        usage = extract_usage(parse_bill(str(f)))
        best  = find_best_plan(usage, tariffs)

        print(f"\n{'='*55}")
        print(f"Номер:          {usage['phone']}")
        print(f"Исходящие:      {usage['outgoing_min']} мин")
        print(f"Интернет:       {usage['internet_gb']} ГБ")
        print(f"Оплачено:       {usage['total_paid']:.2f} BYN")

        if best:
            saving = usage["total_paid"] - best["price_byn"]
            print(f"Лучший тариф:   {best['name']} — {best['price_byn']} BYN/мес")
            if saving > 0.01:
                print(f"Экономия:       ~{saving:.2f} BYN/мес")
            else:
                print("Текущий план уже оптимален")
        else:
            print("Нет подходящего тарифа — использование превышает все доступные планы")


if __name__ == "__main__":
    main()
