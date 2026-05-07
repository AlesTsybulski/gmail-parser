import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from textxtract import SyncTextExtractor

sys.stdout.reconfigure(encoding="utf-8")

_pdf_extractor = SyncTextExtractor()

# ── line classifiers for PDF text parsing ───────────────────────────────────
_DECIMAL_RE  = re.compile(r'^\s*\d+[,.]\d+\s*$')
_VAT_RATE_RE = re.compile(r'^\s*\d+%\s*$')
_QUANTITY_RE = re.compile(r'^\s*(\d+:\d+:\d+|\d+[a-zA-Z]+|\d+)\s*$')

def _line_type(line: str) -> str:
    if not line.strip():
        return 'empty'
    if _VAT_RATE_RE.match(line):
        return 'vat_rate'
    if _DECIMAL_RE.match(line):
        return 'amount'
    if _QUANTITY_RE.match(line):
        return 'quantity'
    return 'text'


def extract_text(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() == ".html":
        soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
        return soup.get_text(separator="\n", strip=True)
    return _pdf_extractor.extract(path)


# ── HTML parser ──────────────────────────────────────────────────────────────

def parse_subscriber_sections(html_path: str) -> list[dict]:
    soup = BeautifulSoup(Path(html_path).read_text(encoding="utf-8"), "html.parser")

    sections = []
    for caption in soup.find_all("p", class_="table2-preamble-caption"):
        if "Абонентский номер" not in caption.get_text():
            continue

        table = caption.find_parent("table")
        info = {}
        charges = []
        totals = []

        for tr in table.find_all("tr"):
            cls = tr.get("class", [])
            tds = tr.find_all("td")

            if "table2-preamble-text" in cls and tds:
                label = tds[0].get_text(strip=True).rstrip(":")
                value = " ".join(td.get_text(separator=" ", strip=True) for td in tds[1:])
                info[label] = value.strip()

            elif "table-text" in cls and tds:
                charges.append([td.get_text(separator=" ", strip=True) for td in tds])

            elif "group1-summary" in cls and tds:
                totals.append([td.get_text(separator=" ", strip=True) for td in tds])

        sections.append({"info": info, "charges": charges, "totals": totals})

    return sections


# ── PDF parser ───────────────────────────────────────────────────────────────

_BLOCK_RE = re.compile(
    r'Абонентский номер:\s+(.+?)\n'
    r'Тарифные планы:\s+(.+?)\n'
    r'№ SIM-карты:\s+(\S+)\n'
    r'(.*?)'
    r'Итого начислений по абонентскому номеру\n'
    r'((?:[ \t]*[\d,\.]+\n)+)'
    r'Итого начислений по абонентскому номеру с учетом округлений\n'
    r'[ \t]*([\d,\.]+)',
    re.DOTALL,
)


def _parse_charge_lines(lines: list[str]) -> list[list[str]]:
    charges = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _line_type(line) != 'text':
            i += 1
            continue

        # Collect multi-line service name
        name_parts = [line.strip()]
        i += 1
        while i < len(lines) and _line_type(lines[i]) == 'text':
            name_parts.append(lines[i].strip())
            i += 1
        service = ' '.join(name_parts)

        # Optional quantity (time / bytes / integer)
        qty = ''
        if i < len(lines) and _line_type(lines[i]) == 'quantity':
            qty = lines[i].strip()
            i += 1

        # Amounts and VAT rate — PDF order: amount_excl, total, vat_rate%, vat
        amounts = []
        vat_rate = ''
        while i < len(lines) and _line_type(lines[i]) in ('amount', 'vat_rate'):
            if _line_type(lines[i]) == 'vat_rate':
                vat_rate = lines[i].strip()
            else:
                amounts.append(lines[i].strip())
            i += 1

        amount_excl = amounts[0] if len(amounts) > 0 else ''
        total       = amounts[1] if len(amounts) > 1 else ''
        vat         = amounts[2] if len(amounts) > 2 else ''

        # Output columns match HTML: [service, qty, amount_excl, vat_rate, vat, total]
        charges.append([service, qty, amount_excl, vat_rate, vat, total])

    return charges


def parse_pdf_subscriber_sections(pdf_path: str) -> list[dict]:
    import fitz
    text = "\n".join(page.get_text() for page in fitz.open(pdf_path))

    sections = []
    for m in _BLOCK_RE.finditer(text):
        info = {
            'Абонентский номер': m.group(1).strip(),
            'Тарифные планы':    m.group(2).strip(),
            '№ SIM-карты':       m.group(3).strip(),
        }
        charges = _parse_charge_lines(m.group(4).splitlines())
        summary_nums = [x.strip() for x in m.group(5).splitlines() if x.strip()]
        totals = [
            ['Итого начислений по абонентскому номеру'] + summary_nums,
            ['Итого начислений по абонентскому номеру с учетом округлений', m.group(6).strip()],
        ]
        sections.append({'info': info, 'charges': charges, 'totals': totals})

    return sections


# ── unified entry point ──────────────────────────────────────────────────────

def parse_bill(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".html":
        return parse_subscriber_sections(path)
    return parse_pdf_subscriber_sections(path)


def _print_sections(sections: list[dict]) -> None:
    for section in sections:
        info = section["info"]
        print(f"\nАбонентский номер: {info.get('Абонентский номер', '—')}")
        print(f"Тарифные планы:    {info.get('Тарифные планы', '—')}")
        print(f"№ SIM-карты:       {info.get('№ SIM-карты', '—')}")
        print()
        for row in section["charges"]:
            print("  ", " | ".join(row))
        print()
        for row in section["totals"]:
            print("  ", " | ".join(row))


if __name__ == "__main__":
    bills_dir = Path(r"C:\Scripts\gmail-parser\bills")
    for file in sorted(bills_dir.iterdir()):
        if file.suffix.lower() in (".pdf", ".html"):
            print(f"\n{'='*60}\n{file.name}\n{'='*60}")
            _print_sections(parse_bill(str(file)))
